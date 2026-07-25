"""3D mesh providers — Pixal3D, self-hosted Hunyuan, Tencent Cloud, GMI, Atlas.

Pixal3D (PIXAL3D_BASE_URL):
  Health:   GET  /health
  Generate: POST /v1/generate (multipart image, synchronous binary GLB response)
  The service runs one GPU job at a time, so HTTP 409 is retried with a bounded wait.

Self-hosted api_publish.py (MESH_BASE_URL, e.g. http://host:8080):
  Health:   GET  /api/v1/health
  Submit:   POST /api/v1/generate/async (multipart image required)
  Poll:     GET  /api/v1/jobs/{job_id}
  Download: GET  /api/v1/jobs/{job_id}/download
  Image-to-3D only — text prompts are turned into a reference image via GMI first.

Tencent Cloud intl (fallback):
  Host: hunyuan.intl.tencentcloudapi.com
  Auth: TC3-HMAC-SHA256 (SecretId + SecretKey)
  Submit: SubmitHunyuanTo3DProJob | SubmitHunyuanTo3DRapidJob
  Query:  QueryHunyuanTo3DProJob  | QueryHunyuanTo3DRapidJob
  Params: Prompt | ImageUrl | ImageBase64, EnablePBR, FaceCount, GenerateType
  Docs: https://www.tencentcloud.com/zh/document/product/1284/75976

GMI / Atlas kept as optional fallbacks (MESH_PROVIDER=gmi|atlas).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from ..core.config import get_settings
from .media import _extract_asset_url

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
_MESH_CACHE_DIR = _CACHE_DIR / "meshes"
_inflight_mesh: dict[str, asyncio.Lock] = {}

_POLL_INTERVAL_S = 5.0
_POLL_TIMEOUT_S = 600.0

_ATLAS_SUBMIT = "/api/v1/model/generateImage"
_ATLAS_MODEL_TEXT = "tencent/hunyuan3d-pro/text-to-3d"
_ATLAS_MODEL_IMAGE = "tencent/hunyuan3d-pro/image-to-3d"

_TENCENT_HOST = "hunyuan.intl.tencentcloudapi.com"
_TENCENT_SERVICE = "hunyuan"
_TENCENT_VERSION = "2023-09-01"

# Self-hosted API face-count bounds (api_server_publish.py).
_SELFHOSTED_FACE_MIN = 1_000
_SELFHOSTED_FACE_MAX = 200_000
_PIXAL_FACE_MIN = 1_000
_PIXAL_FACE_MAX = 1_000_000
_MESH_REF_IMAGE_CONTRACT_VERSION = "reconstruction-safe-v3"


def _mesh_cache_path(
    *,
    provider: str,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
    generate_type: str,
) -> Path:
    raw = f"{provider}|{prompt or ''}|{image_url or ''}|{enable_pbr}|{face_count}|{generate_type}"
    key = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return _MESH_CACHE_DIR / f"{key}.glb"


def mesh_cache_key_for_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def write_mesh_cache(data: bytes, key: str) -> Path:
    _MESH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _MESH_CACHE_DIR / f"{key}.glb"
    path.write_bytes(data)
    return path


def read_mesh_cache(key: str) -> bytes | None:
    path = _MESH_CACHE_DIR / f"{key}.glb"
    return path.read_bytes() if path.exists() else None


def mesh_storage_object_key(key: str) -> str:
    """Object key inside MESH_STORAGE_BUCKET (content-hash.glb)."""
    return f"{key}.glb"


async def sync_mesh_to_storage(key: str, data: bytes) -> None:
    """Best-effort upload so Fly/compute can serve meshes generated on another host."""
    from . import storage

    if not storage.is_configured() or not data:
        return
    bucket = get_settings().mesh_storage_bucket or "meshes"
    try:
        await storage.upload(
            mesh_storage_object_key(key),
            data,
            "model/gltf-binary",
            bucket=bucket,
        )
    except Exception as exc:  # noqa: BLE001 — never block lesson generation
        logger.warning("Mesh storage upload failed for %s: %s", key, exc)


async def load_mesh_bytes(key: str) -> bytes | None:
    """Local disk first, then InsForge storage (populate local on remote hit)."""
    local = read_mesh_cache(key)
    if local:
        return local

    from . import storage

    if not storage.is_configured():
        return None
    bucket = get_settings().mesh_storage_bucket or "meshes"
    try:
        data = await storage.download(mesh_storage_object_key(key), bucket=bucket)
    except Exception as exc:  # noqa: BLE001
        logger.info("Mesh storage miss for %s: %s", key, exc)
        return None
    if data:
        write_mesh_cache(data, key)
    return data


async def _download_url(client: httpx.AsyncClient, url: str) -> bytes:
    asset = await client.get(url)
    asset.raise_for_status()
    return asset.content


class MeshProvider(Protocol):
    name: str

    async def generate_mesh(
        self,
        *,
        prompt: str | None = None,
        image_url: str | None = None,
        enable_pbr: bool = True,
        face_count: int = 500_000,
        generate_type: str = "Normal",
    ) -> bytes | None: ...


class SelfHostedMesh:
    """Hunyuan 3D via self-hosted api_publish.py (image-to-3D under /api/v1)."""

    name = "selfhosted"

    async def generate_mesh(
        self,
        *,
        prompt: str | None = None,
        image_url: str | None = None,
        enable_pbr: bool = True,
        face_count: int = 500_000,
        generate_type: str = "Normal",
    ) -> bytes | None:
        s = get_settings()
        if not (s.mesh_base_url or "").strip():
            return None
        return await _mesh_bytes_cached(
            provider="selfhosted",
            prompt=prompt,
            image_url=image_url,
            enable_pbr=enable_pbr,
            face_count=face_count,
            generate_type=generate_type,
            fetcher=lambda: _selfhosted_submit_and_fetch(
                s,
                prompt=prompt,
                image_url=image_url,
                enable_pbr=enable_pbr,
                face_count=face_count,
            ),
        )


class Pixal3DMesh:
    """Pixal3D image-to-GLB pipeline running on the private H200 service."""

    name = "pixal3d"

    async def generate_mesh(
        self,
        *,
        prompt: str | None = None,
        image_url: str | None = None,
        enable_pbr: bool = True,
        face_count: int = 500_000,
        generate_type: str = "Normal",
    ) -> bytes | None:
        s = get_settings()
        if not (s.pixal3d_base_url or "").strip():
            return None
        resolution = int(getattr(s, "pixal3d_resolution", 1536) or 1536)
        seed = int(getattr(s, "pixal3d_seed", 0) or 0)
        manual_fov = float(getattr(s, "pixal3d_manual_fov", -1.0))
        texture_size = int(getattr(s, "pixal3d_texture_size", 4096) or 4096)
        provider_key = (
            f"pixal3d:{resolution}:{seed}:{manual_fov}:{texture_size}:"
            f"{_MESH_REF_IMAGE_CONTRACT_VERSION}"
        )
        return await _mesh_bytes_cached(
            provider=provider_key,
            prompt=prompt,
            image_url=image_url,
            enable_pbr=enable_pbr,
            face_count=face_count,
            generate_type=generate_type,
            fetcher=lambda: _pixal3d_submit_and_fetch(
                s,
                prompt=prompt,
                image_url=image_url,
                face_count=face_count,
            ),
        )


class TencentMesh:
    """Hunyuan 3D via Tencent Cloud intl API (TC3 signed)."""

    name = "tencent"

    async def generate_mesh(
        self,
        *,
        prompt: str | None = None,
        image_url: str | None = None,
        enable_pbr: bool = True,
        face_count: int = 500_000,
        generate_type: str = "Normal",
    ) -> bytes | None:
        s = get_settings()
        if not (s.tencentcloud_secret_id and s.tencentcloud_secret_key):
            return None
        edition = (s.tencent_hunyuan_edition or "rapid").lower()
        if edition not in ("pro", "rapid"):
            edition = "rapid"
        return await _mesh_bytes_cached(
            # Include edition so Rapid never reuses a cached Pro GLB (or vice versa).
            provider=f"tencent:{edition}",
            prompt=prompt,
            image_url=image_url,
            enable_pbr=enable_pbr,
            face_count=face_count,
            generate_type=generate_type,
            fetcher=lambda: _tencent_submit_and_fetch(
                s,
                prompt=prompt,
                image_url=image_url,
                enable_pbr=enable_pbr,
                face_count=face_count,
                generate_type=generate_type,
            ),
        )


class AtlasMesh:
    """Hunyuan 3D Pro via Atlas Cloud predictions API."""

    name = "atlas"

    async def generate_mesh(
        self,
        *,
        prompt: str | None = None,
        image_url: str | None = None,
        enable_pbr: bool = True,
        face_count: int = 500_000,
        generate_type: str = "Normal",
    ) -> bytes | None:
        s = get_settings()
        if not s.atlascloud_api_key:
            return None
        return await _mesh_bytes_cached(
            provider="atlas",
            prompt=prompt,
            image_url=image_url,
            enable_pbr=enable_pbr,
            face_count=face_count,
            generate_type=generate_type,
            fetcher=lambda: _atlas_submit_and_fetch(
                s,
                prompt=prompt,
                image_url=image_url,
                enable_pbr=enable_pbr,
                face_count=face_count,
                generate_type=generate_type,
            ),
        )


class GMIMesh:
    """Hunyuan 3D Pro via GMI Cloud request-queue."""

    name = "gmi"

    async def generate_mesh(
        self,
        *,
        prompt: str | None = None,
        image_url: str | None = None,
        enable_pbr: bool = True,
        face_count: int = 500_000,
        generate_type: str = "Normal",
    ) -> bytes | None:
        s = get_settings()
        if not s.gmi_api_key:
            return None
        return await _mesh_bytes_cached(
            provider="gmi",
            prompt=prompt,
            image_url=image_url,
            enable_pbr=enable_pbr,
            face_count=face_count,
            generate_type=generate_type,
            fetcher=lambda: _gmi_submit_and_fetch(
                s,
                prompt=prompt,
                image_url=image_url,
                enable_pbr=enable_pbr,
                face_count=face_count,
                generate_type=generate_type,
            ),
        )


async def _mesh_bytes_cached(
    *,
    provider: str,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
    generate_type: str,
    fetcher,
) -> bytes | None:
    path = _mesh_cache_path(
        provider=provider,
        prompt=prompt,
        image_url=image_url,
        enable_pbr=enable_pbr,
        face_count=face_count,
        generate_type=generate_type,
    )
    if path.exists():
        return path.read_bytes()

    lock = _inflight_mesh.setdefault(path.name, asyncio.Lock())
    async with lock:
        if path.exists():
            return path.read_bytes()
        try:
            data = await fetcher()
        except Exception as exc:
            logger.warning(
                "Mesh generation failed (%s) for prompt %.60r: %s", provider, prompt, exc
            )
            return None
        if data:
            _MESH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _inflight_mesh.pop(path.name, None)
        return data


def _bearer_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _selfhosted_base(s) -> str:
    """Host root, e.g. http://192.241.160.204:8080 (no /api/v1 suffix)."""
    return (s.mesh_base_url or "").strip().rstrip("/")


def _selfhosted_api_base(s) -> str:
    return f"{_selfhosted_base(s)}/api/v1"


def _guess_image_filename(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name if path else ""
    if name and "." in name:
        return name
    return "input.png"


def _image_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")


def _is_glb(data: bytes) -> bool:
    if len(data) < 12 or data[:4] != b"glTF":
        return False
    version, declared_length = struct.unpack_from("<II", data, 4)
    return version == 2 and declared_length == len(data)


def _mesh_ref_image_prompt(prompt: str) -> str:
    return (
        "Create an input image for single-object image-to-3D reconstruction. "
        f"SUBJECT: {prompt}. "
        "Render exactly one complete subject, fully visible and centered, occupying about 80% "
        "of the square frame. Show one single three-quarter camera view only with weak perspective "
        "and even studio lighting. Use a uniform pure white background with no floor, cast shadow, "
        "horizon, scenery, or environmental context. Keep one clean outer silhouette. Every visible "
        "part must be physically connected to the main body or fully contained inside it. Make thin "
        "appendages deliberately thick, separated, continuous, and easy to reconstruct. The subject's "
        "own cohesive anatomy is allowed, but do not add any separate objects or floating "
        "fragments, flowers, tools, props, hands, containers, pedestals, or decorative elements. "
        "Do not create a collage, turnaround sheet, split panel, diagram, cutaway inset, or multiple "
        "views. Do not use transparent ghost layers or overlapping duplicate silhouettes. Use matte "
        "materials with clear color separation. No text, labels, arrows, borders, captions, or "
        "watermark. Any descriptive context in "
        "the subject request defines its appearance only; never illustrate that context as a scene. "
        "Output only the isolated subject image."
    )


async def _selfhosted_resolve_image(
    client: httpx.AsyncClient,
    *,
    prompt: str | None,
    image_url: str | None,
) -> tuple[bytes, str] | None:
    """Return (image_bytes, filename). Prefer image_url; else synthesize via GMI."""
    if image_url:
        data = await _download_url(client, image_url)
        return data, _guess_image_filename(image_url)
    if not prompt:
        return None
    s = get_settings()
    # Lazy import avoids registry↔mesh cycle at module load.
    from .media import get_image_media, resolve_image_provider

    provider = resolve_image_provider(s)
    needed_key = s.tokenrouter_api_key if provider == "tokenrouter" else s.gmi_api_key
    if not (needed_key or "").strip():
        logger.warning(
            "Self-hosted mesh is image-to-3D only; set %s to synthesize a ref image",
            "TOKENROUTER_API_KEY" if provider == "tokenrouter" else "GMI_API_KEY",
        )
        return None

    data = await get_image_media(s).generate_image(_mesh_ref_image_prompt(prompt), aspect="1:1")
    if not data:
        logger.warning("Failed to synthesize ref image for mesh prompt %.60r", prompt)
        return None
    return data, "ref.png"


async def _selfhosted_poll(client: httpx.AsyncClient, api_base: str, job_id: str) -> bytes | None:
    status_url = f"{api_base}/jobs/{job_id}"
    download_url = f"{api_base}/jobs/{job_id}/download"
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        r = await client.get(status_url)
        r.raise_for_status()
        body = r.json()
        status = str(body.get("status") or "").lower()
        if status in ("completed", "succeeded", "success", "done"):
            # Prefer absolute/relative download_url from the job payload when present.
            rel = body.get("download_url")
            url = download_url
            if isinstance(rel, str) and rel.strip():
                if rel.startswith("http://") or rel.startswith("https://"):
                    url = rel
                elif rel.startswith("/"):
                    # /api/v1/jobs/.../download → join with host root
                    root = api_base.rsplit("/api/v1", 1)[0]
                    url = f"{root}{rel}"
            asset = await client.get(url)
            asset.raise_for_status()
            return asset.content
        if status in ("failed", "fail", "error", "cancelled"):
            logger.warning(
                "Self-hosted mesh job %s failed: %s",
                job_id,
                body.get("error") or body,
            )
            return None
        await asyncio.sleep(_POLL_INTERVAL_S)
    logger.warning("Self-hosted mesh job %s timed out", job_id)
    return None


async def _selfhosted_submit_and_fetch(
    s,
    *,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
) -> bytes | None:
    api_base = _selfhosted_api_base(s)
    if not _selfhosted_base(s):
        return None
    if not image_url and not prompt:
        return None

    # api_publish.py multipart fields (image required).
    form: list[tuple[str, tuple]] = [
        (
            "num_inference_steps",
            (None, str(int(getattr(s, "mesh_steps", 30) or 30))),
        ),
        (
            "octree_resolution",
            (None, str(int(getattr(s, "mesh_octree_resolution", 256) or 256))),
        ),
        ("generate_texture", (None, "true" if enable_pbr else "false")),
        ("remove_background", (None, "true")),
        (
            "face_count",
            (
                None,
                str(max(_SELFHOSTED_FACE_MIN, min(_SELFHOSTED_FACE_MAX, int(face_count)))),
            ),
        ),
        ("output_format", (None, "glb")),
    ]
    async with httpx.AsyncClient(timeout=120) as client:
        resolved = await _selfhosted_resolve_image(
            client, prompt=prompt, image_url=image_url
        )
        if not resolved:
            return None
        image_bytes, filename = resolved
        form.append(("image", (filename, image_bytes, "application/octet-stream")))

        r = await client.post(f"{api_base}/generate/async", files=form)
        r.raise_for_status()
        body = r.json()
        job_id = body.get("job_id") or body.get("id")
        if not job_id:
            logger.warning("Self-hosted submit missing job_id: %s", body)
            return None
        return await _selfhosted_poll(client, api_base, str(job_id))


async def _pixal3d_submit_and_fetch(
    s,
    *,
    prompt: str | None,
    image_url: str | None,
    face_count: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes | None:
    base = (s.pixal3d_base_url or "").strip().rstrip("/")
    if not base or (not image_url and not prompt):
        return None

    timeout_s = float(getattr(s, "pixal3d_timeout_seconds", 900.0) or 900.0)
    timeout = httpx.Timeout(timeout_s, connect=min(30.0, timeout_s))
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        # Fail before paying for a reconstruction image when the private GPU service is down
        # or its models have not finished loading. Older compatible deployments may omit the
        # JSON readiness fields, so an otherwise healthy 2xx response remains acceptable.
        health = await client.get(f"{base}/health", timeout=httpx.Timeout(5.0))
        health.raise_for_status()
        try:
            readiness = health.json()
        except ValueError:
            readiness = {}
        if readiness.get("status") not in (None, "ok") or readiness.get("model_loaded") is False:
            logger.warning("Pixal3D is not ready: %s", readiness)
            return None

        resolved = await _selfhosted_resolve_image(
            client,
            prompt=prompt,
            image_url=image_url,
        )
        if not resolved:
            return None
        image_bytes, filename = resolved
        form = {
            "seed": str(int(getattr(s, "pixal3d_seed", 0) or 0)),
            "resolution": str(int(getattr(s, "pixal3d_resolution", 1536) or 1536)),
            "manual_fov": str(float(getattr(s, "pixal3d_manual_fov", -1.0))),
            "skip_preprocess": (
                "true" if bool(getattr(s, "pixal3d_skip_preprocess", False)) else "false"
            ),
            "decimation_target": str(
                max(_PIXAL_FACE_MIN, min(_PIXAL_FACE_MAX, int(face_count)))
            ),
            "texture_size": str(int(getattr(s, "pixal3d_texture_size", 4096) or 4096)),
            "return_json": "false",
        }
        files = {"image": (filename, image_bytes, _image_content_type(filename))}
        retries = int(getattr(s, "pixal3d_busy_retries", 3) or 0)
        retry_seconds = float(getattr(s, "pixal3d_busy_retry_seconds", 20.0) or 20.0)

        for attempt in range(retries + 1):
            response = await client.post(f"{base}/v1/generate", data=form, files=files)
            if response.status_code != 409:
                response.raise_for_status()
                data = response.content
                if not _is_glb(data):
                    logger.warning(
                        "Pixal3D returned an invalid GLB (%s, %d bytes)",
                        response.headers.get("content-type", "unknown"),
                        len(data),
                    )
                    return None
                logger.info(
                    "Pixal3D job %s completed in %ss (%d bytes)",
                    response.headers.get("X-Job-Id", "unknown"),
                    response.headers.get("X-Elapsed-Sec", "unknown"),
                    len(data),
                )
                return data

            if attempt >= retries:
                logger.warning("Pixal3D is busy after %d attempt(s)", attempt + 1)
                return None
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(120.0, max(0.1, float(retry_after or retry_seconds)))
            except ValueError:
                delay = retry_seconds
            logger.info("Pixal3D is busy; retrying in %.1fs", delay)
            await asyncio.sleep(delay)
    return None


def _tencent_sign(
    secret_id: str, secret_key: str, *, action: str, payload: dict, region: str
) -> tuple[dict, bytes]:
    """Build TC3-HMAC-SHA256 headers + JSON body for Hunyuan intl API."""
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    ct = "application/json; charset=utf-8"
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    body = payload_json.encode("utf-8")
    hashed_payload = hashlib.sha256(body).hexdigest()
    canonical_headers = f"content-type:{ct}\nhost:{_TENCENT_HOST}\nx-tc-action:{action.lower()}\n"
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    credential_scope = f"{date}/{_TENCENT_SERVICE}/tc3_request"
    string_to_sign = (
        f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _hmac(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac(secret_date, _TENCENT_SERVICE)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": ct,
        "Host": _TENCENT_HOST,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": _TENCENT_VERSION,
        "X-TC-Region": region,
    }
    return headers, body


async def _tencent_call(s, *, action: str, payload: dict) -> dict:
    headers, body = _tencent_sign(
        s.tencentcloud_secret_id,
        s.tencentcloud_secret_key,
        action=action,
        payload=payload,
        region=s.tencentcloud_region or "ap-singapore",
    )
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"https://{_TENCENT_HOST}", headers=headers, content=body)
        r.raise_for_status()
        return r.json()


def _pick_glb_url(files: list) -> str | None:
    for f in files or []:
        if not isinstance(f, dict):
            continue
        if str(f.get("Type") or "").upper() == "GLB" and f.get("Url"):
            return f["Url"]
    for f in files or []:
        if isinstance(f, dict) and f.get("Url"):
            return f["Url"]
    return None


async def _tencent_poll(s, *, job_id: str, edition: str) -> bytes | None:
    query = "QueryHunyuanTo3DRapidJob" if edition == "rapid" else "QueryHunyuanTo3DProJob"
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        body = await _tencent_call(s, action=query, payload={"JobId": job_id})
        resp = body.get("Response") or {}
        if resp.get("Error"):
            logger.warning("Tencent query error for %s: %s", job_id, resp["Error"])
            return None
        status = str(resp.get("Status") or "").upper()
        if status == "DONE":
            url = _pick_glb_url(resp.get("ResultFile3Ds") or [])
            if not url:
                logger.warning("Tencent job %s DONE with no GLB: %s", job_id, resp)
                return None
            async with httpx.AsyncClient(timeout=120) as client:
                return await _download_url(client, url)
        if status == "FAIL":
            logger.warning(
                "Tencent job %s failed: %s %s",
                job_id,
                resp.get("ErrorCode"),
                resp.get("ErrorMessage"),
            )
            return None
        await asyncio.sleep(_POLL_INTERVAL_S)
    logger.warning("Tencent job %s timed out", job_id)
    return None


async def _tencent_submit_and_fetch(
    s,
    *,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
    generate_type: str,
) -> bytes | None:
    edition = (s.tencent_hunyuan_edition or "rapid").lower()
    if edition not in ("pro", "rapid"):
        edition = "rapid"

    payload: dict = {"EnablePBR": bool(enable_pbr)}
    if image_url:
        payload["ImageUrl"] = image_url
    elif prompt:
        payload["Prompt"] = prompt
    else:
        return None

    if edition == "rapid":
        payload["ResultFormat"] = "GLB"
        action = "SubmitHunyuanTo3DRapidJob"
    else:
        payload["FaceCount"] = max(3_000, min(1_500_000, int(face_count)))
        payload["GenerateType"] = generate_type or "Normal"
        action = "SubmitHunyuanTo3DProJob"

    body = await _tencent_call(s, action=action, payload=payload)
    resp = body.get("Response") or {}
    if resp.get("Error"):
        logger.warning("Tencent submit error: %s", resp["Error"])
        return None
    job_id = resp.get("JobId")
    if not job_id:
        logger.warning("Tencent submit missing JobId: %s", body)
        return None
    return await _tencent_poll(s, job_id=str(job_id), edition=edition)


async def _atlas_poll(client: httpx.AsyncClient, s, prediction_id: str) -> bytes | None:
    poll_url = f"{s.atlascloud_base_url.rstrip('/')}/api/v1/model/prediction/{prediction_id}"
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        r = await client.get(poll_url, headers=_bearer_headers(s.atlascloud_api_key))
        r.raise_for_status()
        body = r.json()
        data = body.get("data") or {}
        status = str(data.get("status") or "").lower()
        if status in ("completed", "succeeded", "success"):
            outputs = data.get("outputs") or []
            if not outputs:
                logger.warning(
                    "Atlas prediction %s completed with no outputs: %s", prediction_id, body
                )
                return None
            url = outputs[0] if isinstance(outputs[0], str) else outputs[0].get("url")
            if not url:
                return None
            return await _download_url(client, url)
        if status in ("failed", "error", "cancelled"):
            logger.warning("Atlas prediction %s failed: %s", prediction_id, body)
            return None
        await asyncio.sleep(_POLL_INTERVAL_S)
    logger.warning("Atlas prediction %s timed out", prediction_id)
    return None


async def _atlas_submit_and_fetch(
    s,
    *,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
    generate_type: str,
) -> bytes | None:
    body: dict = {
        "generate_type": generate_type,
        "enable_pbr": enable_pbr,
        "face_count": max(40_000, min(1_500_000, int(face_count))),
    }
    if image_url:
        body["model"] = _ATLAS_MODEL_IMAGE
        body["image"] = image_url
    elif prompt:
        body["model"] = _ATLAS_MODEL_TEXT
        body["prompt"] = prompt
    else:
        return None

    submit_url = f"{s.atlascloud_base_url.rstrip('/')}{_ATLAS_SUBMIT}"
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(submit_url, headers=_bearer_headers(s.atlascloud_api_key), json=body)
        r.raise_for_status()
        result = r.json()
        prediction_id = (result.get("data") or {}).get("id")
        if not prediction_id:
            logger.warning("Atlas submit missing prediction id: %s", result)
            return None
        return await _atlas_poll(client, s, str(prediction_id))


async def _gmi_poll(client: httpx.AsyncClient, s, request_id: str) -> bytes | None:
    base = s.gmi_media_base_url.rstrip("/")
    status_url = f"{base}/{request_id}"
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    headers = _bearer_headers(s.gmi_api_key)
    while time.monotonic() < deadline:
        r = await client.get(status_url, headers=headers)
        r.raise_for_status()
        body = r.json()
        status = (body.get("status") or body.get("state") or "").lower()
        if status == "success":
            outcome = body.get("outcome") or {}
            url = _extract_asset_url(outcome, "mesh_url") or _extract_asset_url(outcome, "media_url")
            if not url:
                return None
            return await _download_url(client, url)
        if status in ("failed", "error", "cancelled"):
            logger.warning("GMI mesh request %s failed: %s", request_id, body)
            return None
        await asyncio.sleep(_POLL_INTERVAL_S)
    logger.warning("GMI mesh request %s timed out", request_id)
    return None


def _hunyuan_payload(
    *,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
    generate_type: str,
) -> dict | None:
    payload: dict = {
        "generate_type": generate_type,
        "enable_pbr": enable_pbr,
        "face_count": max(40_000, min(1_500_000, int(face_count))),
    }
    if image_url:
        payload["image"] = image_url
        payload["image_url"] = image_url
    elif prompt:
        payload["prompt"] = prompt
    else:
        return None
    return payload


async def _gmi_submit_and_fetch(
    s,
    *,
    prompt: str | None,
    image_url: str | None,
    enable_pbr: bool,
    face_count: int,
    generate_type: str,
) -> bytes | None:
    payload_body = _hunyuan_payload(
        prompt=prompt,
        image_url=image_url,
        enable_pbr=enable_pbr,
        face_count=face_count,
        generate_type=generate_type,
    )
    if not payload_body:
        return None

    envelope = {"model": "hunyuan-3d-pro", "payload": payload_body}
    headers = _bearer_headers(s.gmi_api_key)
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(s.gmi_media_base_url, headers=headers, json=envelope)
        r.raise_for_status()
        body = r.json()
        outcome = body.get("outcome") or {}
        url = _extract_asset_url(outcome, "mesh_url") or _extract_asset_url(outcome, "media_url")
        if url:
            return await _download_url(client, url)
        request_id = body.get("request_id") or body.get("id")
        if request_id:
            return await _gmi_poll(client, s, str(request_id))
    return None


def resolve_mesh_provider() -> MeshProvider:
    """Resolve the configured 3D provider; auto prefers a configured Pixal3D service."""
    s = get_settings()
    pref = (s.mesh_provider or "auto").lower()
    has_pixal3d = bool((getattr(s, "pixal3d_base_url", "") or "").strip())
    has_selfhosted = bool((s.mesh_base_url or "").strip())
    has_tencent = bool(
        (s.tencentcloud_secret_id or "").strip() and (s.tencentcloud_secret_key or "").strip()
    )
    has_atlas = bool((s.atlascloud_api_key or "").strip())
    has_gmi = bool((s.gmi_api_key or "").strip())
    if pref in ("pixal", "pixal3d") or (pref == "auto" and has_pixal3d):
        return Pixal3DMesh()
    if pref in ("selfhosted", "local", "hunyuan") or (pref == "auto" and has_selfhosted):
        return SelfHostedMesh()
    if pref == "tencent" or (pref == "auto" and has_tencent):
        return TencentMesh()
    if pref == "gmi" or (pref == "auto" and has_gmi):
        return GMIMesh()
    if pref == "atlas" or (pref == "auto" and has_atlas):
        return AtlasMesh()
    if has_pixal3d:
        return Pixal3DMesh()
    if has_selfhosted:
        return SelfHostedMesh()
    return TencentMesh()
