"""Media providers (image / audio) via OpenAI.

Images: POST /v1/images/generations (gpt-image-1.5 by default).
Audio:  POST /v1/audio/speech (OpenAI TTS). Falls back to silent WAV at the route.

Disk-caches generated files under backend/.cache to avoid re-billing on duplicates.
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

# GPT image models support these standard sizes.
_ASPECT_SIZES = {
    "16:9": "1536x1024",
    "3:2": "1536x1024",
    "4:3": "1536x1024",
    "1:1": "1024x1024",
    "3:4": "1024x1536",
    "2:3": "1024x1536",
    "9:16": "1024x1536",
}


def _img_cache_path(prompt: str, aspect: str, provider: str) -> Path:
    key = hashlib.sha256(f"{provider}|{prompt}|{aspect}".encode()).hexdigest()[:32]
    return _IMG_CACHE_DIR / f"{key}.jpg"


def _aud_cache_path(text: str) -> Path:
    key = hashlib.sha256(text.encode()).hexdigest()[:32]
    return _AUD_CACHE_DIR / f"{key}.mp3"


def _aspect_to_size(aspect: str) -> str:
    return _ASPECT_SIZES.get(aspect, "1024x1024")


def _extract_asset_url(outcome: dict, primary_key: str) -> str | None:
    """Pull a signed asset URL out of a request-queue `outcome` envelope.

    Used by mesh providers (GMI/Hunyuan-style queues). Tolerates a flat primary key
    plus list-shaped fallbacks whose entries may be {"url": ...} or bare URL strings.
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


def resolve_image_provider(s=None) -> str:
    """Always OpenAI for images (TokenRouter / GMI removed)."""
    return "openai"


def get_image_media(s=None) -> "OpenAIMedia":
    return OpenAIMedia()


def _openai_image_key(s) -> str:
    """Prefer dedicated image key; fall back to the Realtime / general OpenAI key."""
    for attr in ("openai_image_api_key", "openai_realtime_api_key"):
        val = getattr(s, attr, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _openai_base_url(s) -> str:
    raw = getattr(s, "openai_image_base_url", "") or "https://api.openai.com/v1"
    return str(raw).rstrip("/")


async def _image_bytes(prompt: str, aspect: str = "16:9") -> bytes | None:
    s = get_settings()
    if not _openai_image_key(s):
        return None

    path = _img_cache_path(prompt, aspect, "openai")
    if path.exists():
        return path.read_bytes()

    lock = _inflight_img.setdefault(path.name, asyncio.Lock())
    async with lock:
        if path.exists():
            return path.read_bytes()
        try:
            data = await _fetch_image_openai(s, prompt, aspect)
        except Exception as exc:
            logger.warning("Image generation failed for prompt %.60r: %s", prompt, exc)
            return None
        if data:
            _IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _inflight_img.pop(path.name, None)
        return data


async def _fetch_image_openai(s, prompt: str, aspect: str = "16:9") -> bytes | None:
    """POST OpenAI /v1/images/generations (GPT image models return b64_json)."""
    key = _openai_image_key(s)
    model = getattr(s, "openai_image_model", None) or "gpt-image-1.5"
    url = f"{_openai_base_url(s)}/images/generations"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": _aspect_to_size(aspect),
        "quality": getattr(s, "openai_image_quality", None) or "medium",
        "n": 1,
    }
    # GPT image models always return b64; request JPEG so /gen|/image Content-Type matches.
    if not str(model).startswith("dall-e"):
        payload["output_format"] = "jpeg"
    # dall-e needs explicit response_format.
    if str(model).startswith("dall-e"):
        payload["response_format"] = "b64_json"

    timeout_s = float(getattr(s, "image_timeout_seconds", 300.0) or 300.0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=30.0)) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        for item in data.get("data") or []:
            b64 = item.get("b64_json")
            if b64:
                return base64.b64decode(b64)
            # dall-e url fallback
            img_url = item.get("url")
            if img_url:
                asset = await client.get(img_url)
                asset.raise_for_status()
                return asset.content
    return None


async def _audio_bytes(text: str, kind: str = "speech") -> bytes | None:
    """Generate TTS via OpenAI /v1/audio/speech."""
    s = get_settings()
    if not _openai_image_key(s):
        return None

    path = _aud_cache_path(text)
    if path.exists():
        return path.read_bytes()

    lock = _inflight_aud.setdefault(path.name, asyncio.Lock())
    async with lock:
        if path.exists():
            return path.read_bytes()
        try:
            data = await _fetch_audio_openai(s, text)
        except Exception as exc:
            logger.warning("Audio generation failed for text %.60r: %s", text, exc)
            return None
        if data:
            _AUD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _inflight_aud.pop(path.name, None)
        return data


async def _fetch_audio_openai(s, text: str) -> bytes | None:
    key = _openai_image_key(s)
    model = getattr(s, "openai_tts_model", None) or "gpt-4o-mini-tts"
    voice = getattr(s, "openai_tts_voice", None) or "alloy"
    url = f"{_openai_base_url(s)}/audio/speech"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.content


class OpenAIMedia:
    """MediaProvider over OpenAI Images + TTS APIs (disk-cached)."""

    name = "openai"

    async def generate_image(self, prompt: str, aspect: str = "16:9") -> bytes | None:
        return await _image_bytes(prompt, aspect)

    async def generate_audio(self, text: str, kind: str = "speech") -> bytes | None:
        return await _audio_bytes(text, kind)


# Back-compat aliases so older imports/tests that referenced these names still resolve.
GMIMedia = OpenAIMedia
TokenRouterMedia = OpenAIMedia
