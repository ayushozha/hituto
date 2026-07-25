"""Media providers (image / audio).

Images: TokenRouter's Gemini-style generateContent API (preferred) or GMI Cloud's
request-queue API, selected by `resolve_image_provider()`. Audio: always GMI Cloud
TTS — no TokenRouter recipe for that yet. Disk-caches generated files under
backend/.cache to avoid re-billing on duplicate renders.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from pathlib import Path

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
_IMG_CACHE_DIR = _CACHE_DIR / "images"
_AUD_CACHE_DIR = _CACHE_DIR / "audio"

_inflight_img: dict[str, asyncio.Lock] = {}
_inflight_aud: dict[str, asyncio.Lock] = {}


def _img_cache_path(prompt: str, aspect: str, provider: str) -> Path:
    # Provider is part of the key so swapping IMAGE_PROVIDER never serves a stale
    # image rendered by the other backend for the same prompt.
    key = hashlib.sha256(f"{provider}|{prompt}|{aspect}".encode()).hexdigest()[:32]
    return _IMG_CACHE_DIR / f"{key}.jpg"


def _aud_cache_path(text: str) -> Path:
    key = hashlib.sha256(text.encode()).hexdigest()[:32]
    return _AUD_CACHE_DIR / f"{key}.mp3"


def resolve_image_provider(s=None) -> str:
    """"tokenrouter" or "gmi" — `auto` prefers TokenRouter once its key is set.

    Uses `getattr`/`isinstance` guards (not raw truthiness) so settings doubles that
    predate these fields — e.g. a `MagicMock(gmi_api_key=...)` that never mentions
    `tokenrouter_api_key` — fall back to "gmi" instead of tripping on MagicMock's
    auto-truthy attributes.
    """
    s = s or get_settings()
    raw_choice = getattr(s, "image_provider", "auto")
    choice = raw_choice.strip().lower() if isinstance(raw_choice, str) else "auto"
    if choice in ("tokenrouter", "gmi"):
        return choice
    tr_key = getattr(s, "tokenrouter_api_key", "")
    return "tokenrouter" if isinstance(tr_key, str) and tr_key.strip() else "gmi"


def get_image_media(s=None) -> "TokenRouterMedia | GMIMedia":
    """The MediaProvider instance whose `generate_image()` is currently selected."""
    return TokenRouterMedia() if resolve_image_provider(s) == "tokenrouter" else GMIMedia()


async def _image_bytes(prompt: str, aspect: str = "16:9", *, provider: str = "gmi") -> bytes | None:
    """Generate image bytes via the given provider ("gmi" | "tokenrouter")."""
    s = get_settings()
    key = s.tokenrouter_api_key if provider == "tokenrouter" else s.gmi_api_key
    if not (key or "").strip():
        return None

    path = _img_cache_path(prompt, aspect, provider)
    if path.exists():
        return path.read_bytes()

    lock = _inflight_img.setdefault(path.name, asyncio.Lock())
    async with lock:
        if path.exists():
            return path.read_bytes()
        try:
            data = await _fetch_image(s, prompt, aspect, provider=provider)
        except Exception as exc:
            logger.warning("Image generation failed for prompt %.60r: %s", prompt, exc)
            return None
        if data:
            _IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _inflight_img.pop(path.name, None)
        return data


_ASPECT_SIZES = {
    # GMI's gpt-image queue accepts the gpt-image family's fixed size set. Map the
    # requested aspect to the nearest supported dimension; unknown/square → 1:1.
    # NOTE: if GMI rejects a non-square size, revert this map to always "1024x1024".
    "16:9": "1536x1024",
    "3:2": "1536x1024",
    "4:3": "1536x1024",
    "1:1": "1024x1024",
    "3:4": "1024x1536",
    "2:3": "1024x1536",
    "9:16": "1024x1536",
}


def _aspect_to_size(aspect: str) -> str:
    """Translate a lesson aspect hint (e.g. '16:9') into a GMI image size string."""
    return _ASPECT_SIZES.get(aspect, "1024x1024")


def _extract_asset_url(outcome: dict, primary_key: str) -> str | None:
    """Pull a signed asset URL out of a GMI request-queue `outcome` envelope.

    Tolerates the flat primary key (image_url/audio_url) plus the list-shaped
    fallbacks, whose entries may be either {"url": ...} dicts or bare URL strings.
    """
    direct = outcome.get(primary_key)
    if isinstance(direct, str) and direct:
        return direct
    for key in ("media_urls", "media", "medias"):
        for item in outcome.get(key) or []:
            if isinstance(item, str) and item:
                return item
            if isinstance(item, dict) and item.get("url"):
                return item["url"]
    return None


async def _post_queue(s, payload: dict, primary_key: str, *, allow_b64: bool = False) -> bytes | None:
    """POST GMI's request-queue envelope, resolve the asset URL from `outcome`, fetch bytes.

    GMI's request-queue API is NOT OpenAI-compatible: POST the base URL with a nested
    {model, payload} envelope and read the signed asset URL back out of `outcome`.
    """
    headers = {
        "Authorization": f"Bearer {s.gmi_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(s.gmi_media_base_url, headers=headers, json=payload)
        r.raise_for_status()
        # `or {}` guards an explicit {"outcome": null} (queue pending/error), which a
        # `.get("outcome", {})` default would NOT catch — it only fills a missing key.
        outcome = r.json().get("outcome") or {}
        url = _extract_asset_url(outcome, primary_key)
        if not url:
            b64 = outcome.get("b64_json") if allow_b64 else None
            return base64.b64decode(b64) if b64 else None
        asset = await client.get(url)
        asset.raise_for_status()
        return asset.content


async def _fetch_image(s, prompt: str, aspect: str = "16:9", *, provider: str = "gmi") -> bytes | None:
    if provider == "tokenrouter":
        return await _fetch_image_tokenrouter(s, prompt, aspect)
    payload = {
        "model": s.gmi_image_model,
        "payload": {
            "prompt": prompt,
            "size": _aspect_to_size(aspect),
            "quality": "medium",
        },
    }
    return await _post_queue(s, payload, "image_url", allow_b64=True)


def _extract_gemini_image_bytes(data: dict) -> bytes | None:
    """Pull the first inline image out of a Gemini-style generateContent response.

    Google's REST JSON mapping uses camelCase (`inlineData`); tolerate a snake_case
    proxy too. Logs the block reason when the model refused instead of returning image parts.
    """
    for candidate in data.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    block_reason = (data.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        logger.warning("TokenRouter image request blocked: %s", block_reason)
    return None


async def _fetch_image_tokenrouter(s, prompt: str, aspect: str = "16:9") -> bytes | None:
    """POST TokenRouter's Gemini-style `models/{model}:generateContent` endpoint."""
    url = f"{s.tokenrouter_base_url.rstrip('/')}/{s.tokenrouter_image_model}:generateContent"
    headers = {
        "Authorization": f"Bearer {s.tokenrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect, "imageSize": "1K"},
        },
    }
    timeout_s = float(getattr(s, "image_timeout_seconds", 300.0) or 300.0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=30.0)) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return _extract_gemini_image_bytes(r.json())


async def _audio_bytes(text: str, kind: str = "speech") -> bytes | None:
    """Generate audio TTS bytes using GMI Cloud request queue."""
    s = get_settings()
    if not s.gmi_api_key:
        return None

    path = _aud_cache_path(text)
    if path.exists():
        return path.read_bytes()

    lock = _inflight_aud.setdefault(path.name, asyncio.Lock())
    async with lock:
        if path.exists():
            return path.read_bytes()
        try:
            data = await _fetch_audio(s, text)
        except Exception as exc:
            logger.warning("Audio generation failed for text %.60r: %s", text, exc)
            return None
        if data:
            _AUD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _inflight_aud.pop(path.name, None)
        return data


async def _fetch_audio(s, text: str) -> bytes | None:
    payload = {
        "model": s.gmi_tts_model,
        "payload": {
            "text": text,
            "voice_id": "Dennis",
            "audio_encoding": "MP3",
            "sample_rate_hertz": 22050,
            "speaking_rate": 1.0,
            "temperature": 1.1,
            "timestamp_type": "WORD",
        },
    }
    return await _post_queue(s, payload, "audio_url")


class GMIMedia:
    """MediaProvider over GMI Cloud's request-queue image/audio APIs (disk-cached)."""

    name = "gmi"

    async def generate_image(self, prompt: str, aspect: str = "16:9") -> bytes | None:
        return await _image_bytes(prompt, aspect, provider="gmi")

    async def generate_audio(self, text: str, kind: str = "speech") -> bytes | None:
        return await _audio_bytes(text, kind)


class TokenRouterMedia:
    """MediaProvider: images via TokenRouter's Gemini-style generateContent API.

    Audio still goes through GMI Cloud TTS (`_audio_bytes`) — TokenRouter has no
    speech recipe here yet.
    """

    name = "tokenrouter"

    async def generate_image(self, prompt: str, aspect: str = "16:9") -> bytes | None:
        return await _image_bytes(prompt, aspect, provider="tokenrouter")

    async def generate_audio(self, text: str, kind: str = "speech") -> bytes | None:
        return await _audio_bytes(text, kind)
