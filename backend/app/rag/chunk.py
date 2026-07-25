"""Section-aware chunking (tasks.md #12).

Heading detection + section/page attribution is domain logic and stays here (LangChain's
splitters don't track document provenance). The token-accurate splitting and overlap are
delegated to LangChain's `RecursiveCharacterTextSplitter` (tiktoken-backed) instead of a
hand-rolled token buffer — so `size_tokens`/`overlap_tokens` are now real tokens, and the
splitting is boundary-aware (paragraph → line → word) rather than raw line accumulation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .parse import ParsedDocument

# Headings: markdown (#..), numbered ("2.3 Method"), or short ALL-CAPS lines.
_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s+\S.*|\d+(?:\.\d+)*\s+[A-Z]\S.{0,78}|[A-Z][A-Z0-9 \-]{3,58})\s*$"
)
_ENCODING = "cl100k_base"


@lru_cache(maxsize=1)
def _encoder() -> "tiktoken.Encoding":
    return tiktoken.get_encoding(_ENCODING)


@lru_cache(maxsize=8)
def _splitter(size_tokens: int, overlap_tokens: int) -> RecursiveCharacterTextSplitter:
    # from_tiktoken_encoder hard-caps each chunk at `size_tokens` real tokens.
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=_ENCODING,
        chunk_size=size_tokens,
        chunk_overlap=overlap_tokens,
    )


def _clean_heading(line: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+", "", line).strip()


def _is_heading(line: str) -> bool:
    return bool(line) and len(line) < 90 and bool(_HEADING_RE.match(line))


def detect_headings(text: str) -> list[str]:
    """All heading lines in order (deduped). Used for source structure — independent of chunk size,
    so a small one-chunk document still surfaces every section (task 11)."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if _is_heading(line):
            h = _clean_heading(line)
            if h and h not in out:
                out.append(h)
    return out


@dataclass
class Chunk:
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    section_title: str | None
    heading_path: list[str]
    token_count: int


@dataclass
class _Segment:
    section: str | None
    page_start: int
    page_end: int
    text: str


def _segments(doc: ParsedDocument) -> list[_Segment]:
    """Split the doc into section-bounded segments carrying their section title + page span.

    A new heading closes the current segment and opens the next, so every chunk derived from a
    segment inherits an accurate section title; the segment's page span covers all its lines.
    """
    segments: list[_Segment] = []
    lines: list[str] = []
    pages: list[int] = []
    section: str | None = None

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            segments.append(_Segment(section, min(pages), max(pages), text))

    for page in doc.pages:
        for raw in page.text.splitlines():
            line = raw.rstrip()
            if _is_heading(line):
                flush()
                lines, pages = [], []
                section = _clean_heading(line)
            lines.append(line)
            pages.append(page.page_number)
    flush()
    return segments


def chunk_document(
    doc: ParsedDocument, *, size_tokens: int = 1000, overlap_tokens: int = 150
) -> list[Chunk]:
    splitter = _splitter(size_tokens, overlap_tokens)
    enc = _encoder()
    chunks: list[Chunk] = []
    for seg in _segments(doc):
        for piece in splitter.split_text(seg.text):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    text=piece,
                    page_start=seg.page_start,
                    page_end=seg.page_end,
                    section_title=seg.section,
                    heading_path=[seg.section] if seg.section else [],
                    token_count=len(enc.encode(piece)),
                )
            )
    return chunks
