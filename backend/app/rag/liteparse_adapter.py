"""LiteParse → canonical Markdown + parse_manifest (rag-context Phase 1).

Live PDF parses go through LiteParse when `RAG_LITEPARSE_ENABLED`. Markdown/text
uploads use a deterministic adapter that emits the same MD + manifest contract.
Tests inject `FakeLiteParse` by monkeypatching `get_liteparse_engine`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ParseFigure:
    image_id: str
    page: int | None
    data: bytes
    format: str = "png"
    md_ref: str = ""
    element_id: str | None = None


@dataclass
class CanonicalParse:
    """Canonical evidence produced by LiteParse or the MD/TXT adapter."""

    document_md: str
    manifest: dict
    figures: list[ParseFigure] = field(default_factory=list)
    page_count: int = 1
    source_hash: str = ""
    parser_name: str = "liteparse"
    parser_version: str = "unknown"
    kind: str = "pdf"  # pdf | text | markdown
    quality: dict = field(default_factory=dict)


class LiteParseEngine(Protocol):
    def parse_pdf(self, data: bytes, *, max_pages: int, ocr_enabled: bool) -> CanonicalParse: ...


def source_hash_of(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sanitize(text: str) -> str:
    return text.replace("\x00", "") if text else text


def _detect_kind(mime_type: str, filename: str) -> str:
    m = (mime_type or "").lower()
    f = (filename or "").lower()
    if "pdf" in m or f.endswith(".pdf"):
        return "pdf"
    if "markdown" in m or f.endswith((".md", ".markdown")):
        return "markdown"
    return "text"


def _resolve_ocr(ocr_setting: str, data: bytes, engine: Any) -> bool:
    """Map RAG_OCR_ENABLED to a bool for LiteParse.

    `auto` prefers a cheap `is_complex` probe when the engine supports it; unknown
    engines default OCR off so offline/deploy without OCR deps stay quiet.
    """
    v = (ocr_setting or "auto").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    # auto
    probe = getattr(engine, "needs_ocr", None)
    if callable(probe):
        try:
            return bool(probe(data))
        except Exception:  # noqa: BLE001 — never block parse on complexity probe
            return False
    return False


class LiveLiteParseEngine:
    """Thin wrapper over the real `liteparse.LiteParse` package."""

    def needs_ocr(self, data: bytes) -> bool:
        from liteparse import LiteParse

        pages = LiteParse(quiet=True).is_complex(data)
        return any(getattr(p, "needs_ocr", False) for p in pages)

    def parse_pdf(self, data: bytes, *, max_pages: int, ocr_enabled: bool) -> CanonicalParse:
        import liteparse
        from liteparse import LiteParse

        parser = LiteParse(
            output_format="markdown",
            image_mode="embed",
            ocr_enabled=ocr_enabled,
            max_pages=max_pages,
            quiet=True,
            extract_links=True,
        )
        result = parser.parse(data)
        md = _sanitize(result.text or "")
        page_count = int(getattr(result, "num_pages", None) or len(result.pages or []) or 1)
        elements, heading_path = _elements_from_liteparse(result, md)
        figures: list[ParseFigure] = []
        for img in result.images or []:
            image_id = f"image_{img.id}" if not str(img.id).startswith("image_") else str(img.id)
            ext = (img.format or "png").lstrip(".").lower() or "png"
            md_ref = f"{image_id}.{ext}" if "." not in image_id else image_id
            figures.append(
                ParseFigure(
                    image_id=image_id.replace(".", "_") if image_id.endswith(f".{ext}") else image_id,
                    page=getattr(img, "page", None),
                    data=img.bytes or b"",
                    format=ext,
                    md_ref=md_ref if md_ref.endswith(f".{ext}") else f"{image_id}.{ext}",
                )
            )
        # Normalize figure ids to `image_pN_K` style without double extensions in storage keys.
        for fig in figures:
            raw_id = fig.image_id
            if raw_id.endswith((".png", ".jpg", ".jpeg", ".webp")):
                fig.image_id = raw_id.rsplit(".", 1)[0]
            if not fig.md_ref:
                fig.md_ref = f"{fig.image_id}.{fig.format}"

        version = getattr(liteparse, "__version__", None) or "2.5.0"
        confidences = [
            float(e["confidence"])
            for e in elements
            if isinstance(e.get("confidence"), (int, float))
        ]
        quality = {
            "low_text": len(md.strip()) < 200,
            "ocr_enabled": ocr_enabled,
            "ocr_confidence": (sum(confidences) / len(confidences)) if confidences else None,
            "warnings": [],
            "figure_count": len(figures),
        }
        manifest = {
            "version": 1,
            "source_hash": "",  # filled by caller
            "parser": {"name": "liteparse", "version": str(version)},
            "elements": elements,
            "figures": [
                {
                    "figure_id": f.image_id,
                    "element_id": f.element_id,
                    "page": f.page,
                    "md_ref": f.md_ref,
                    # storage_key filled when artifacts are written
                }
                for f in figures
            ],
            "heading_hints": heading_path,
        }
        return CanonicalParse(
            document_md=md,
            manifest=manifest,
            figures=figures,
            page_count=page_count,
            parser_name="liteparse",
            parser_version=str(version),
            kind="pdf",
            quality=quality,
        )


def _elements_from_liteparse(result: Any, md: str) -> tuple[list[dict], list[str]]:
    """Build manifest elements with markdown offsets from LiteParse pages/text_items."""
    elements: list[dict] = []
    heading_hints: list[str] = []
    cursor = 0
    el_i = 0
    for page in result.pages or []:
        page_num = int(getattr(page, "page_num", 0) or 0)
        items = list(getattr(page, "text_items", None) or [])
        if not items:
            page_md = _sanitize(getattr(page, "markdown", None) or getattr(page, "text", "") or "")
            if not page_md:
                continue
            start = md.find(page_md, cursor)
            if start < 0:
                start = cursor
            end = start + len(page_md)
            el_i += 1
            elements.append(
                {
                    "element_id": f"el-{el_i:04d}",
                    "markdown_start": start,
                    "markdown_end": end,
                    "page": page_num or None,
                    "bbox": None,
                    "heading_path": list(heading_hints),
                    "kind": "paragraph",
                    "confidence": 1.0,
                }
            )
            cursor = end
            continue
        for item in items:
            text = _sanitize(getattr(item, "text", "") or "")
            if not text.strip():
                continue
            start = md.find(text, cursor)
            if start < 0:
                start = cursor
            end = start + len(text)
            x = float(getattr(item, "x", 0) or 0)
            y = float(getattr(item, "y", 0) or 0)
            w = float(getattr(item, "width", 0) or 0)
            h = float(getattr(item, "height", 0) or 0)
            font_size = float(getattr(item, "font_size", 0) or 0)
            kind = "paragraph"
            # Heuristic heading: larger font → treat as heading for path hints
            if font_size >= 14 and len(text) < 120:
                kind = "heading"
                heading_hints = [text.strip()]
            el_i += 1
            conf = getattr(item, "confidence", None)
            elements.append(
                {
                    "element_id": f"el-{el_i:04d}",
                    "markdown_start": start,
                    "markdown_end": end,
                    "page": page_num or None,
                    "bbox": [x, y, x + w, y + h],
                    "heading_path": list(heading_hints),
                    "kind": kind,
                    "confidence": float(conf) if conf is not None else 1.0,
                }
            )
            cursor = max(cursor, end)
    if not elements and md.strip():
        elements.append(
            {
                "element_id": "el-0001",
                "markdown_start": 0,
                "markdown_end": len(md),
                "page": 1,
                "bbox": None,
                "heading_path": [],
                "kind": "paragraph",
                "confidence": 1.0,
            }
        )
    return elements, [h for h in heading_hints if h]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)


def parse_text_canonical(data: bytes, *, kind: str) -> CanonicalParse:
    """Deterministic MD/TXT → same canonical contract (no pages/bbox)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    text = _sanitize(text)
    elements: list[dict] = []
    heading_path: list[str] = []
    el_i = 0
    # Split into blocks separated by blank lines; attach heading_path from ATX headings.
    pos = 0
    for block in re.split(r"(\n\s*\n)", text):
        if not block or not block.strip():
            pos += len(block)
            continue
        m = _HEADING_RE.match(block.strip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            heading_path = heading_path[: level - 1] + [title]
            kind_el = "heading"
        else:
            kind_el = "paragraph"
        start = pos
        end = pos + len(block)
        el_i += 1
        elements.append(
            {
                "element_id": f"el-{el_i:04d}",
                "markdown_start": start,
                "markdown_end": end,
                "heading_path": list(heading_path),
                "kind": kind_el,
                "confidence": 1.0,
            }
        )
        pos = end
    if not elements and text:
        elements.append(
            {
                "element_id": "el-0001",
                "markdown_start": 0,
                "markdown_end": len(text),
                "heading_path": [],
                "kind": "paragraph",
                "confidence": 1.0,
            }
        )
    manifest = {
        "version": 1,
        "source_hash": "",
        "parser": {"name": "text_adapter", "version": "1"},
        "elements": elements,
        "figures": [],
    }
    return CanonicalParse(
        document_md=text,
        manifest=manifest,
        figures=[],
        page_count=1,
        parser_name="text_adapter",
        parser_version="1",
        kind=kind,
        quality={"low_text": len(text.strip()) < 200, "ocr_enabled": False, "warnings": []},
    )


def get_liteparse_engine() -> LiteParseEngine:
    """Return the live LiteParse engine. Tests monkeypatch this to FakeLiteParse."""
    return LiveLiteParseEngine()


def parse_canonical(
    data: bytes,
    mime_type: str = "",
    filename: str = "",
    *,
    max_pages: int = 400,
    max_bytes: int | None = None,
    ocr_setting: str = "auto",
    engine: LiteParseEngine | None = None,
) -> CanonicalParse:
    """Produce document.md + parse_manifest (+ figures) for any allowed upload type."""
    if max_bytes is not None and len(data) > max_bytes:
        raise ValueError(f"source exceeds max bytes ({len(data)} > {max_bytes})")
    kind = _detect_kind(mime_type, filename)
    h = source_hash_of(data)
    if kind != "pdf":
        out = parse_text_canonical(data, kind=kind)
        out.source_hash = h
        out.manifest["source_hash"] = h
        return out

    eng = engine or get_liteparse_engine()
    ocr = _resolve_ocr(ocr_setting, data, eng)
    out = eng.parse_pdf(data, max_pages=max_pages, ocr_enabled=ocr)
    out.source_hash = h
    out.manifest["source_hash"] = h
    out.kind = "pdf"
    return out


def canonical_to_parsed_document(canon: CanonicalParse):
    """Adapt CanonicalParse into the legacy ParsedDocument shape for the chunker."""
    from .parse import ParsedDocument, ParsedPage

    md = canon.document_md
    # Prefer page-scoped slices from the manifest when pages are present.
    by_page: dict[int, list[tuple[int, int]]] = {}
    for el in canon.manifest.get("elements") or []:
        page = el.get("page")
        if page is None:
            continue
        by_page.setdefault(int(page), []).append((int(el["markdown_start"]), int(el["markdown_end"])))
    pages: list[ParsedPage] = []
    if by_page:
        for page_num in sorted(by_page):
            spans = by_page[page_num]
            start = min(s for s, _ in spans)
            end = max(e for _, e in spans)
            pages.append(ParsedPage(page_number=page_num, text=md[start:end]))
    else:
        pages = [ParsedPage(page_number=1, text=md)]
    return ParsedDocument(
        pages=pages,
        full_text=md,
        page_count=canon.page_count or len(pages),
        kind=canon.kind,
        meta={
            "source_hash": canon.source_hash,
            "parser": canon.parser_name,
            "parser_version": canon.parser_version,
        },
    )


def dump_manifest(manifest: dict) -> bytes:
    return json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
