"""Deterministic document outline from Markdown + parse manifest (rag-context Phase 2).

Never LLM-authored. Preserves heading hierarchy when reliable; otherwise builds
bounded atomic evidence units (page / paragraph groups) under RAG_SOURCE_UNIT_TOKENS.
"""
from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
_WS_RE = re.compile(r"\s+")


def _approx_tokens(text: str) -> int:
    return max(1, len(_WS_RE.findall(text or "")) or (1 if (text or "").strip() else 0))


def _slug(title: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "").strip().lower()).strip("-")
    return (s[:48] or fallback)


def build_document_outline(
    document_md: str,
    manifest: dict,
    *,
    source_unit_tokens: int = 1200,
) -> dict[str, Any]:
    """Return `{version, nodes, warnings}` ready for `source_map.document_outline`."""
    md = document_md or ""
    elements = list((manifest or {}).get("elements") or [])
    warnings: list[str] = []

    heading_els = [e for e in elements if e.get("kind") == "heading"]
    # Prefer AT headings when they exist in the MD (more reliable than font heuristics).
    md_headings = list(_HEADING_RE.finditer(md))
    use_md_headings = len(md_headings) >= 1

    nodes: list[dict] = []
    if use_md_headings:
        nodes = _outline_from_md_headings(md, md_headings, elements, source_unit_tokens, warnings)
    elif heading_els:
        nodes = _outline_from_manifest_headings(md, elements, source_unit_tokens, warnings)
    else:
        nodes = _outline_atomic_units(md, elements, source_unit_tokens, warnings)

    # Ensure every non-empty doc has at least one node.
    if not nodes and md.strip():
        nodes = [
            {
                "id": "sec-root",
                "parent_id": None,
                "order": 1,
                "title": "Document",
                "level": 1,
                "markdown_start": 0,
                "markdown_end": len(md),
                "element_ids": [e.get("element_id") for e in elements if e.get("element_id")],
                "page_start": _min_page(elements),
                "page_end": _max_page(elements),
                "token_count": _approx_tokens(md),
            }
        ]
        warnings.append("fallback_single_root")

    return {"version": 1, "nodes": nodes, "warnings": warnings}


def _min_page(elements: list[dict]) -> int | None:
    pages = [int(e["page"]) for e in elements if e.get("page") is not None]
    return min(pages) if pages else None


def _max_page(elements: list[dict]) -> int | None:
    pages = [int(e["page"]) for e in elements if e.get("page") is not None]
    return max(pages) if pages else None


def _elements_in_span(elements: list[dict], start: int, end: int) -> list[str]:
    ids: list[str] = []
    for e in elements:
        eid = e.get("element_id")
        if not eid:
            continue
        es = int(e.get("markdown_start", -1))
        ee = int(e.get("markdown_end", -1))
        if ee <= start or es >= end:
            continue
        ids.append(str(eid))
    return ids


def _split_oversized_span(
    md: str,
    start: int,
    end: int,
    elements: list[dict],
    *,
    parent_id: str | None,
    level: int,
    order_base: int,
    title_prefix: str,
    source_unit_tokens: int,
    warnings: list[str],
) -> list[dict]:
    """Split [start,end) into ≤ source_unit_tokens leaves (or warn if indivisible)."""
    text = md[start:end]
    tokens = _approx_tokens(text)
    if tokens <= source_unit_tokens or (end - start) < 80:
        if tokens > source_unit_tokens:
            warnings.append(f"oversize_indivisible:{title_prefix}:{tokens}")
        return [
            {
                "id": f"unit-{order_base}",
                "parent_id": parent_id,
                "order": order_base,
                "title": title_prefix,
                "level": level,
                "markdown_start": start,
                "markdown_end": end,
                "element_ids": _elements_in_span(elements, start, end),
                "page_start": _page_for_offset(elements, start),
                "page_end": _page_for_offset(elements, max(start, end - 1)),
                "token_count": tokens,
            }
        ]

    # Prefer element boundaries; if that still yields one oversized span (single huge
    # paragraph / notes blob), hard-split by characters (~4 chars/token).
    spans: list[tuple[int, int]] = []
    in_range = [
        e
        for e in elements
        if int(e.get("markdown_end", 0)) > start and int(e.get("markdown_start", 0)) < end
    ]
    if in_range:
        cur_s = start
        cur_tok = 0
        for e in sorted(in_range, key=lambda x: int(x.get("markdown_start", 0))):
            es = max(start, int(e["markdown_start"]))
            ee = min(end, int(e["markdown_end"]))
            if ee <= es:
                continue
            t = _approx_tokens(md[es:ee])
            if cur_tok and cur_tok + t > source_unit_tokens:
                spans.append((cur_s, es))
                cur_s = es
                cur_tok = 0
            cur_tok += t
        if cur_s < end:
            spans.append((cur_s, end))

    need_char_split = (
        not spans
        or len(spans) == 1
        and _approx_tokens(md[spans[0][0] : spans[0][1]]) > source_unit_tokens
    )
    if need_char_split:
        spans = []
        approx_chars = max(200, source_unit_tokens * 4)
        pos = start
        while pos < end:
            nxt = min(end, pos + approx_chars)
            # Prefer breaking on paragraph boundaries when nearby.
            if nxt < end:
                para = md.rfind("\n\n", pos + 50, nxt + 80)
                if para > pos:
                    nxt = para + 2
            spans.append((pos, nxt))
            pos = nxt

    out: list[dict] = []
    for i, (s, e) in enumerate(spans):
        if e <= s:
            continue
        out.append(
            {
                "id": f"unit-{order_base}-{i + 1}",
                "parent_id": parent_id,
                "order": order_base + i,
                "title": f"{title_prefix} ({i + 1})" if len(spans) > 1 else title_prefix,
                "level": level,
                "markdown_start": s,
                "markdown_end": e,
                "element_ids": _elements_in_span(elements, s, e),
                "page_start": _page_for_offset(elements, s),
                "page_end": _page_for_offset(elements, max(s, e - 1)),
                "token_count": _approx_tokens(md[s:e]),
            }
        )
    return out


def _page_for_offset(elements: list[dict], offset: int) -> int | None:
    for e in elements:
        if int(e.get("markdown_start", -1)) <= offset < int(e.get("markdown_end", -1)):
            p = e.get("page")
            return int(p) if p is not None else None
    return None


def _outline_from_md_headings(
    md: str,
    matches: list[re.Match],
    elements: list[dict],
    source_unit_tokens: int,
    warnings: list[str],
) -> list[dict]:
    # Build section spans: each heading owns content until the next heading of ≤ level.
    sections: list[dict] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.start()
        end = len(md)
        for j in range(i + 1, len(matches)):
            if len(matches[j].group(1)) <= level:
                end = matches[j].start()
                break
        sections.append({"level": level, "title": title, "start": start, "end": end, "idx": i})

    nodes: list[dict] = []
    stack: list[tuple[int, str]] = []  # (level, node_id)
    used_ids: set[str] = set()
    order = 0
    for sec in sections:
        while stack and stack[-1][0] >= sec["level"]:
            stack.pop()
        parent_id = stack[-1][1] if stack else None
        order += 1
        base_id = f"sec-{_slug(sec['title'], str(order))}"
        nid = base_id
        n = 2
        while nid in used_ids:
            nid = f"{base_id}-{n}"
            n += 1
        used_ids.add(nid)
        body_start = sec["start"]
        body_end = sec["end"]
        tokens = _approx_tokens(md[body_start:body_end])
        node = {
            "id": nid,
            "parent_id": parent_id,
            "order": order,
            "title": sec["title"],
            "level": sec["level"],
            "markdown_start": body_start,
            "markdown_end": body_end,
            "element_ids": _elements_in_span(elements, body_start, body_end),
            "page_start": _page_for_offset(elements, body_start),
            "page_end": _page_for_offset(elements, max(body_start, body_end - 1)),
            "token_count": tokens,
        }
        nodes.append(node)
        stack.append((sec["level"], nid))

        # If a leaf section (no nested heading in span) is oversized, add atomic children.
        has_child_heading = any(
            s["start"] > body_start and s["start"] < body_end and s["level"] > sec["level"]
            for s in sections
        )
        if not has_child_heading and tokens > source_unit_tokens:
            children = _split_oversized_span(
                md,
                body_start,
                body_end,
                elements,
                parent_id=nid,
                level=sec["level"] + 1,
                order_base=1,
                title_prefix=sec["title"],
                source_unit_tokens=source_unit_tokens,
                warnings=warnings,
            )
            # Parent keeps span; children are the evidence units for teaching-map fallback.
            for i, ch in enumerate(children):
                ch["id"] = f"{nid}-u{i + 1}"
                nodes.append(ch)

    return nodes


def _outline_from_manifest_headings(
    md: str,
    elements: list[dict],
    source_unit_tokens: int,
    warnings: list[str],
) -> list[dict]:
    headings = [e for e in elements if e.get("kind") == "heading"]
    # Synthesize AT-like match objects by injecting offsets into the MD heading builder path.
    # Simpler: treat each heading element as a section boundary.
    sections = []
    for i, h in enumerate(sorted(headings, key=lambda e: int(e.get("markdown_start", 0)))):
        start = int(h.get("markdown_start", 0))
        title = (md[start : int(h.get("markdown_end", start))] or f"Section {i + 1}").strip()
        title = title.lstrip("# ").strip() or f"Section {i + 1}"
        end = len(md)
        for j in range(i + 1, len(headings)):
            nxt = headings[j]
            end = int(nxt.get("markdown_start", end))
            break
        if i + 1 < len(headings):
            end = int(headings[i + 1].get("markdown_start", end))
        sections.append({"level": 1, "title": title, "start": start, "end": end})

    # Reuse MD path via synthetic matches is awkward; build nodes directly.
    nodes: list[dict] = []
    used: set[str] = set()
    for i, sec in enumerate(sections):
        order = i + 1
        base = f"sec-{_slug(sec['title'], str(order))}"
        nid = base
        n = 2
        while nid in used:
            nid = f"{base}-{n}"
            n += 1
        used.add(nid)
        tokens = _approx_tokens(md[sec["start"] : sec["end"]])
        node = {
            "id": nid,
            "parent_id": None,
            "order": order,
            "title": sec["title"],
            "level": 1,
            "markdown_start": sec["start"],
            "markdown_end": sec["end"],
            "element_ids": _elements_in_span(elements, sec["start"], sec["end"]),
            "page_start": _page_for_offset(elements, sec["start"]),
            "page_end": _page_for_offset(elements, max(sec["start"], sec["end"] - 1)),
            "token_count": tokens,
        }
        nodes.append(node)
        if tokens > source_unit_tokens:
            for j, ch in enumerate(
                _split_oversized_span(
                    md,
                    sec["start"],
                    sec["end"],
                    elements,
                    parent_id=nid,
                    level=2,
                    order_base=1,
                    title_prefix=sec["title"],
                    source_unit_tokens=source_unit_tokens,
                    warnings=warnings,
                )
            ):
                ch["id"] = f"{nid}-u{j + 1}"
                nodes.append(ch)
    if nodes:
        return nodes
    return _outline_atomic_units(md, elements, source_unit_tokens, warnings)


def _outline_atomic_units(
    md: str,
    elements: list[dict],
    source_unit_tokens: int,
    warnings: list[str],
) -> list[dict]:
    """Heading-poor path: page containers when available, else sequential token-bounded units."""
    by_page: dict[int, list[dict]] = {}
    for e in elements:
        p = e.get("page")
        if p is None:
            continue
        by_page.setdefault(int(p), []).append(e)

    nodes: list[dict] = []
    if by_page:
        for page_num, els in sorted(by_page.items()):
            start = min(int(e["markdown_start"]) for e in els)
            end = max(int(e["markdown_end"]) for e in els)
            parent_id = f"page-{page_num}"
            parent = {
                "id": parent_id,
                "parent_id": None,
                "order": page_num,
                "title": f"Page {page_num}",
                "level": 1,
                "markdown_start": start,
                "markdown_end": end,
                "element_ids": [str(e["element_id"]) for e in els if e.get("element_id")],
                "page_start": page_num,
                "page_end": page_num,
                "token_count": _approx_tokens(md[start:end]),
            }
            nodes.append(parent)
            children = _split_oversized_span(
                md,
                start,
                end,
                elements,
                parent_id=parent_id,
                level=2,
                order_base=1,
                title_prefix=f"Page {page_num}",
                source_unit_tokens=source_unit_tokens,
                warnings=warnings,
            )
            if len(children) > 1 or (children and children[0]["token_count"] > source_unit_tokens):
                for j, ch in enumerate(children):
                    ch["id"] = f"{parent_id}-u{j + 1}"
                    nodes.append(ch)
        return nodes

    # No pages: group elements sequentially.
    if not elements and md.strip():
        return _split_oversized_span(
            md,
            0,
            len(md),
            elements,
            parent_id=None,
            level=1,
            order_base=1,
            title_prefix="Unit 1",
            source_unit_tokens=source_unit_tokens,
            warnings=warnings,
        )

    ordered = sorted(elements, key=lambda e: int(e.get("markdown_start", 0)))
    units: list[dict] = []
    cur_ids: list[str] = []
    cur_s: int | None = None
    cur_e: int | None = None
    cur_tok = 0
    unit_i = 0

    def flush():
        nonlocal unit_i, cur_ids, cur_s, cur_e, cur_tok
        if cur_s is None or cur_e is None:
            return
        unit_i += 1
        units.append(
            {
                "id": f"unit-{unit_i}",
                "parent_id": None,
                "order": unit_i,
                "title": f"Unit {unit_i}",
                "level": 1,
                "markdown_start": cur_s,
                "markdown_end": cur_e,
                "element_ids": list(cur_ids),
                "page_start": None,
                "page_end": None,
                "token_count": cur_tok,
            }
        )
        cur_ids, cur_s, cur_e, cur_tok = [], None, None, 0

    for e in ordered:
        es, ee = int(e["markdown_start"]), int(e["markdown_end"])
        t = _approx_tokens(md[es:ee])
        if cur_s is not None and cur_tok + t > source_unit_tokens:
            flush()
        if cur_s is None:
            cur_s = es
        cur_e = ee
        cur_tok += t
        if e.get("element_id"):
            cur_ids.append(str(e["element_id"]))
    flush()
    if not units and md.strip():
        warnings.append("empty_elements_fallback")
        return _split_oversized_span(
            md,
            0,
            len(md),
            elements,
            parent_id=None,
            level=1,
            order_base=1,
            title_prefix="Unit 1",
            source_unit_tokens=source_unit_tokens,
            warnings=warnings,
        )
    return units


def outline_node_index(outline: dict) -> dict[str, dict]:
    return {n["id"]: n for n in (outline or {}).get("nodes") or [] if n.get("id")}
