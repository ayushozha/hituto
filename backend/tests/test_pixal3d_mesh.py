from __future__ import annotations

import struct
from types import SimpleNamespace

import httpx

from app.providers import mesh


def _glb() -> bytes:
    data = b"glTF" + struct.pack("<II", 2, 20) + struct.pack("<I4s", 0, b"JSON")
    return data


def _settings(**overrides):
    values = {
        "pixal3d_base_url": "https://pixal.test",
        "pixal3d_resolution": 1536,
        "pixal3d_seed": 7,
        "pixal3d_manual_fov": -1.0,
        "pixal3d_skip_preprocess": False,
        "pixal3d_texture_size": 4096,
        "pixal3d_timeout_seconds": 900.0,
        "pixal3d_busy_retries": 0,
        "pixal3d_busy_retry_seconds": 20.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def test_pixal3d_uploads_expected_fields_and_accepts_binary_glb():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "model_loaded": True})
        if request.method == "GET":
            return httpx.Response(200, content=b"png-data", headers={"Content-Type": "image/png"})
        body = await request.aread()
        assert b'name="image"; filename="subject.png"' in body
        assert b'name="resolution"' in body and b"1536" in body
        assert b'name="seed"' in body and b"7" in body
        assert b'name="decimation_target"' in body and b"1000000" in body
        assert b'name="texture_size"' in body and b"4096" in body
        assert b'name="return_json"' in body and b"false" in body
        return httpx.Response(
            200,
            content=_glb(),
            headers={"Content-Type": "model/gltf-binary", "X-Job-Id": "demo-job"},
        )

    result = await mesh._pixal3d_submit_and_fetch(
        _settings(),
        prompt=None,
        image_url="https://images.test/subject.png",
        face_count=1_000_000,
        transport=httpx.MockTransport(handler),
    )

    assert result == _glb()
    assert [request.method for request in requests] == ["GET", "GET", "POST"]


async def test_pixal3d_retries_one_busy_response(monkeypatch):
    post_count = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "model_loaded": True})
        if request.method == "GET":
            return httpx.Response(200, content=b"png-data")
        post_count += 1
        if post_count == 1:
            return httpx.Response(409, headers={"Retry-After": "0.1"})
        return httpx.Response(200, content=_glb())

    async def no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(mesh.asyncio, "sleep", no_sleep)
    result = await mesh._pixal3d_submit_and_fetch(
        _settings(pixal3d_busy_retries=1),
        prompt=None,
        image_url="https://images.test/subject.png",
        face_count=150_000,
        transport=httpx.MockTransport(handler),
    )

    assert result == _glb()
    assert post_count == 2
    assert sleeps == [0.1]


async def test_pixal3d_unready_service_skips_reference_image_generation(monkeypatch):
    generated: list[str] = []

    class FakeMedia:
        async def generate_image(self, prompt: str, aspect: str = "1:1"):
            generated.append(prompt)
            return b"image-data"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "starting", "model_loaded": False})

    from app.providers import media

    monkeypatch.setattr(media, "get_image_media", lambda _settings: FakeMedia())
    result = await mesh._pixal3d_submit_and_fetch(
        _settings(tokenrouter_api_key="image-key", gmi_api_key=""),
        prompt="one isolated orchid bee",
        image_url=None,
        face_count=1_000_000,
        transport=httpx.MockTransport(handler),
    )

    assert result is None
    assert generated == []


def test_auto_provider_prefers_configured_pixal3d(monkeypatch):
    settings = SimpleNamespace(
        mesh_provider="auto",
        pixal3d_base_url="http://pixal.internal:8000",
        mesh_base_url="",
        tencentcloud_secret_id="",
        tencentcloud_secret_key="",
        atlascloud_api_key="",
        gmi_api_key="",
    )
    monkeypatch.setattr(mesh, "get_settings", lambda: settings)

    assert isinstance(mesh.resolve_mesh_provider(), mesh.Pixal3DMesh)
