"""Tool server (design.md §4): /gen, /image, /audio, /maps.

For the keyless slice these return deterministic placeholders so generated pages
never render broken elements (R6.5). Real providers (MiniMax image/audio, OSM
tiles) slot in behind the same routes.
"""
from __future__ import annotations

import hashlib
import wave
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

from ...core.config import get_settings
from ...providers.mesh import load_mesh_bytes
from ...providers.registry import get_media

router = APIRouter(tags=["tools"])

_ASPECTS = {"1:1": (512, 512), "4:3": (640, 480), "3:4": (480, 640), "16:9": (640, 360), "9:16": (360, 640)}


def _placeholder_svg(label: str, w: int, h: int) -> str:
    # Deterministic gradient from the prompt so repeated prompts look stable.
    # No text overlay — keeps covers/heroes clean in keyless dev mode.
    hue = int(hashlib.md5(label.encode()).hexdigest(), 16) % 360
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="hsl({hue},55%,24%)"/>
    <stop offset="1" stop-color="hsl({(hue+50)%360},60%,10%)"/>
  </linearGradient></defs>
  <rect width="{w}" height="{h}" fill="url(#g)"/>
</svg>"""


def _svg_response(label: str, aspect: str) -> Response:
    w, h = _ASPECTS.get(aspect, (640, 360))
    return Response(content=_placeholder_svg(label, w, h), media_type="image/svg+xml")


# Cache image bytes in-browser for a day; they're deterministic per prompt.
_IMG_HEADERS = {"Cache-Control": "public, max-age=86400"}


@router.get("/gen")
async def gen(prompt: str, aspect: str = "1:1"):
    """Generate an image for the prompt; gradient SVG on any failure."""
    data = await get_media().generate_image(prompt, aspect)
    if data:
        return Response(content=data, media_type="image/jpeg", headers=_IMG_HEADERS)
    return _svg_response(f"gen: {prompt}", aspect)


@router.get("/image")
async def image(query: str, aspect: str = "16:9"):
    """Retrieved-image slot; gradient SVG on failure."""
    prompt = f"photograph of {query}, realistic, high detail"
    data = await get_media().generate_image(prompt, aspect)
    if data:
        return Response(content=data, media_type="image/jpeg", headers=_IMG_HEADERS)
    return _svg_response(f"img: {query}", aspect)


@router.get("/audio")
async def audio(prompt: str = "", kind: str = "music"):
    """Generate TTS audio; silent WAV on failure."""
    data = await get_media().generate_audio(prompt) if prompt else None
    if data:
        return Response(content=data, media_type="audio/mpeg", headers=_IMG_HEADERS)

    # Fallback is a valid silent WAV.
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return Response(content=buf.getvalue(), media_type="audio/wav", headers=_IMG_HEADERS)


# Capsule iframes are sandboxed without allow-same-origin (opaque/"null" origin), so
# fetch()/GLTFLoader XHR to /mesh needs an explicit ACAO — <img src> does not.
_MESH_HEADERS = {
    "Cache-Control": "public, max-age=86400",
    "Access-Control-Allow-Origin": "*",
}


@router.get("/mesh")
async def mesh(key: str):
    """Serve a Hunyuan GLB by content hash — local cache, then InsForge storage."""
    data = await load_mesh_bytes(key)
    if data:
        return Response(content=data, media_type="model/gltf-binary", headers=_MESH_HEADERS)
    return Response(status_code=404)


# Curated CC0 game kits (Quaternius toon characters, etc.) for game-archetype capsules.
# Served with ACAO=* like /mesh so sandboxed iframes can GLTFLoader.fetch them.
_GAME_KITS_ROOT = Path(__file__).resolve().parents[3] / "game_kits"
_GAME_KIT_ALLOW = {
    "toon": frozenset(
        {
            "Character_Enemy.gltf",
            "Character_Hazmat.gltf",
            "Character_Soldier.gltf",
        }
    ),
}


@router.get("/game-kits/{kit}/{filename}")
async def game_kit_asset(kit: str, filename: str):
    """Serve a first-party game-kit glTF/GLB by kit name + filename (allow-listed)."""
    allowed = _GAME_KIT_ALLOW.get(kit)
    if not allowed or filename not in allowed:
        return Response(status_code=404)
    path = (_GAME_KITS_ROOT / kit / filename).resolve()
    try:
        path.relative_to((_GAME_KITS_ROOT / kit).resolve())
    except ValueError:
        return Response(status_code=404)
    if not path.is_file():
        return Response(status_code=404)
    media = (
        "model/gltf-binary"
        if path.suffix.lower() == ".glb"
        else "model/gltf+json"
    )
    return Response(content=path.read_bytes(), media_type=media, headers=_MESH_HEADERS)


@router.get("/maps/geocode")
async def geocode(q: str):
    s = get_settings()
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "hituto-learning/0.1"}) as c:
        r = await c.get(f"{s.nominatim_url}/search", params={"q": q, "format": "json", "limit": 1})
        r.raise_for_status()
        return r.json()


@router.get("/maps/tiles/{z}/{x}/{y}.png")
async def tiles(z: int, x: int, y: int):
    # Free OSM tile proxy (no key). Prod: cache in Redis + respect usage policy.
    s = get_settings()
    return RedirectResponse(url=f"{s.osm_tile_upstream}/{z}/{x}/{y}.png")
