"""Document parsers.

PDF via LiteParse (canonical MD + manifest when ingestion uses the LiteParse path).
Plain text / Markdown via the stdlib. Returns page-aware `ParsedDocument` for the chunker.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    page_number: int  # 1-based
    text: str


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    full_text: str
    page_count: int
    kind: str  # pdf | text | markdown
    meta: dict = field(default_factory=dict)


def _sanitize(text: str) -> str:
    """Strip characters that Postgres ``text`` columns reject."""
    return text.replace("\x00", "") if text else text


def _detect_kind(mime_type: str, filename: str) -> str:
    m = (mime_type or "").lower()
    f = (filename or "").lower()
    if "pdf" in m or f.endswith(".pdf"):
        return "pdf"
    if "markdown" in m or f.endswith((".md", ".markdown")):
        return "markdown"
    return "text"


def parse_document(data: bytes, mime_type: str = "", filename: str = "") -> ParsedDocument:
    """Parse upload bytes. PDFs go through LiteParse; MD/TXT use the text adapter.

    Tests may monkeypatch `get_liteparse_engine` to FakeLiteParse.
    """
    kind = _detect_kind(mime_type, filename)
    if kind == "pdf":
        return _parse_pdf(data, mime_type=mime_type, filename=filename)
    return _parse_text(data, kind)


def _parse_pdf(data: bytes, *, mime_type: str, filename: str) -> ParsedDocument:
    from ..core.config import get_settings
    from .liteparse_adapter import canonical_to_parsed_document, get_liteparse_engine, parse_canonical

    settings = get_settings()
    canon = parse_canonical(
        data,
        mime_type,
        filename or "upload.pdf",
        max_pages=settings.max_pages,
        ocr_setting=settings.rag_ocr_enabled,
        engine=get_liteparse_engine(),
    )
    return canonical_to_parsed_document(canon)


def _parse_text(data: bytes, kind: str) -> ParsedDocument:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    text = _sanitize(text)
    page = ParsedPage(page_number=1, text=text)
    return ParsedDocument(pages=[page], full_text=text, page_count=1, kind=kind)
