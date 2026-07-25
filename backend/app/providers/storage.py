"""InsForge Storage REST client for durable source-document / mesh storage.

Uploaded documents land in the configured InsForge bucket (visible in the
dashboard / via `npx @insforge/cli storage list-objects`), instead of only on
local disk. When InsForge storage is not configured (offline/stub tests), callers
fall back to local disk — see `rag.ingest.save_and_ingest`.

REST shape (confirmed against the live API):
  PUT    {base}/api/storage/buckets/{bucket}/objects/{key}   multipart file=...
  GET    {base}/api/storage/buckets/{bucket}/objects/{key}   -> bytes (302 CDN)
  DELETE {base}/api/storage/buckets/{bucket}/objects/{key}
All authenticated with the project admin key via the `x-api-key` header.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote

import httpx

from ..core.config import get_settings


def is_configured() -> bool:
    s = get_settings()
    return bool(s.insforge_base_url and s.insforge_api_key)


def _headers() -> dict[str, str]:
    return {"x-api-key": get_settings().insforge_api_key}


def _object_url(bucket: str, key: str) -> str:
    base = get_settings().insforge_base_url.rstrip("/")
    # Encode the whole key (incl. slashes) into a single path segment, matching the API.
    return f"{base}/api/storage/buckets/{bucket}/objects/{quote(key, safe='')}"


def _bucket(bucket: str | None) -> str:
    return bucket or get_settings().storage_bucket


async def upload(key: str, data: bytes, content_type: str | None, *, bucket: str | None = None) -> dict:
    """Upload bytes to `key`, returning the API payload ({bucket, key, size, url, ...})."""
    filename = key.rsplit("/", 1)[-1] or "upload"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.put(
            _object_url(_bucket(bucket), key),
            headers=_headers(),
            files={"file": (filename, data, content_type or "application/octet-stream")},
        )
        resp.raise_for_status()
        return resp.json()


async def upload_file(
    key: str,
    path: Path,
    content_type: str | None,
    *,
    bucket: str | None = None,
) -> dict:
    """Upload a file without first copying the complete object into memory."""
    filename = key.rsplit("/", 1)[-1] or path.name or "upload"
    async with httpx.AsyncClient(timeout=120) as client:
        with path.open("rb") as handle:
            resp = await client.put(
                _object_url(_bucket(bucket), key),
                headers=_headers(),
                files={"file": (filename, handle, content_type or "application/octet-stream")},
            )
        resp.raise_for_status()
        return resp.json()


async def download(key: str, *, bucket: str | None = None) -> bytes:
    stream = await open_download_stream(key, bucket=bucket)
    try:
        return b"".join([chunk async for chunk in stream.iter_bytes()])
    finally:
        await stream.aclose()


@dataclass
class DownloadStream:
    """Open range-capable storage response whose lifetime follows the API response body."""

    status_code: int
    headers: httpx.Headers
    _client: httpx.AsyncClient
    _response: httpx.Response

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_bytes():
            yield chunk

    async def aclose(self) -> None:
        await self._response.aclose()
        await self._client.aclose()


async def open_download_stream(
    key: str,
    *,
    bucket: str | None = None,
    range_header: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DownloadStream:
    """Open an InsForge object stream, forwarding a browser byte-range request."""
    client = httpx.AsyncClient(timeout=120, transport=transport)
    headers = _headers()
    if range_header:
        headers["Range"] = range_header
    try:
        request = client.build_request("GET", _object_url(_bucket(bucket), key), headers=headers)
        response = await client.send(request, stream=True, follow_redirects=False)
        if response.is_redirect and response.headers.get("location"):
            # InsForge redirects to a signed CDN URL. Never forward the project admin key
            # across origins; the signed URL is already the authorization for this hop.
            location = response.url.join(response.headers["location"])
            await response.aclose()
            redirect_headers = {"Range": range_header} if range_header else {}
            redirect = client.build_request("GET", location, headers=redirect_headers)
            response = await client.send(redirect, stream=True, follow_redirects=True)
        if response.status_code not in (200, 206, 416):
            response.raise_for_status()
        return DownloadStream(
            status_code=response.status_code,
            headers=response.headers,
            _client=client,
            _response=response,
        )
    except Exception:
        await client.aclose()
        raise


async def delete(key: str, *, bucket: str | None = None) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.delete(_object_url(_bucket(bucket), key), headers=_headers())
        # A missing object is fine — deletion is idempotent from our side.
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
