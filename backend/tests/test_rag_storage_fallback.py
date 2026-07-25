"""Ingest/RAG locators: keep local mirrors usable when InsForge upload fails."""
from pathlib import Path

import pytest

from app.rag.context import _local_parse_mirror


def test_local_parse_mirror_maps_insforge_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        key = "sources/abc/parses/deadbeef/chapters/ch-01.md"
        assert _local_parse_mirror(key) == tmp_path / "parses" / "abc" / "deadbeef" / "chapters" / "ch-01.md"
        assert _local_parse_mirror("/absolute/local/path.md") is None
        assert _local_parse_mirror("not-a-sources-key") is None
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_store_bytes_returns_local_when_upload_fails(tmp_path, monkeypatch) -> None:
    import app.rag.ingest as ingest

    async def boom(*_a, **_k):
        raise RuntimeError("503 Service Temporarily Unavailable")

    monkeypatch.setattr(ingest.storage, "is_configured", lambda: True)
    monkeypatch.setattr(ingest.storage, "upload", boom)

    local = tmp_path / "document.md"
    loc = await ingest._store_bytes(
        "sources/x/parses/h/document.md", b"hello", "text/markdown", local_path=local
    )
    assert local.read_bytes() == b"hello"
    assert Path(loc).resolve() == local.resolve()
