"""Teaching map (LLM JSON only) + verbatim chapter materialization (rag-context Phase 2).

The LLM never writes chapter bodies. Code concatenates ordered non-overlapping
`document.md` spans from outline nodes / manifest elements.
"""
from __future__ import annotations

import json
import re

from .outline import _approx_tokens, outline_node_index

_VALID_KINDS = frozenset(
    {"paper", "lecture_notes", "textbook", "slides", "mixed", "unknown"}
)


def validate_teaching_map(raw: dict, outline: dict) -> tuple[dict | None, list[str]]:
    """Validate LLM teaching_map JSON. Returns (cleaned_map, errors)."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["teaching_map_not_object"]
    nodes = outline_node_index(outline)
    if not nodes:
        return None, ["empty_outline"]

    kind = raw.get("document_kind") or "unknown"
    if kind not in _VALID_KINDS:
        kind = "unknown"
    summary = (raw.get("document_summary") or "").strip()
    if not summary:
        errors.append("missing_document_summary")
    thesis = raw.get("thesis")
    if thesis is not None:
        thesis = str(thesis).strip() or None

    chapters_in = raw.get("chapters")
    if not isinstance(chapters_in, list) or not chapters_in:
        errors.append("missing_chapters")
        return None, errors

    cleaned_chapters: list[dict] = []
    used_ids: set[str] = set()
    for i, ch in enumerate(chapters_in):
        if not isinstance(ch, dict):
            errors.append(f"chapter_{i}_not_object")
            continue
        cid = str(ch.get("id") or f"ch-{i + 1}").strip()
        if cid in used_ids:
            cid = f"{cid}-{i + 1}"
        used_ids.add(cid)
        raw_ids = ch.get("source_node_ids") or []
        if not isinstance(raw_ids, list) or not raw_ids:
            errors.append(f"chapter_{cid}_empty_source_node_ids")
            continue
        valid_ids: list[str] = []
        for nid in raw_ids:
            nid_s = str(nid)
            if nid_s not in nodes:
                errors.append(f"unknown_source_node_id:{nid_s}")
                continue
            valid_ids.append(nid_s)
        if not valid_ids:
            errors.append(f"chapter_{cid}_no_valid_nodes")
            continue
        cleaned_chapters.append(
            {
                "id": cid,
                "order": int(ch.get("order") or (i + 1)),
                "title": str(ch.get("title") or nodes[valid_ids[0]].get("title") or cid)[:200],
                "summary": str(ch.get("summary") or "")[:2000],
                "source_node_ids": valid_ids,
            }
        )

    if errors and not cleaned_chapters:
        return None, errors
    if not cleaned_chapters:
        return None, errors or ["no_valid_chapters"]

    out = {
        "document_kind": kind,
        "document_summary": summary or "Document overview.",
        "thesis": thesis,
        "chapters": cleaned_chapters,
    }
    return out, errors


def fallback_teaching_map(
    document_md: str,
    outline: dict,
    *,
    lesson_context_tokens: int = 24000,
) -> dict:
    """One chapter per top-level outline node when bounded; else sequential groups."""
    nodes = list((outline or {}).get("nodes") or [])
    top = [n for n in nodes if not n.get("parent_id")]
    if not top:
        top = nodes
    chapters: list[dict] = []
    # Prefer leaves when top-level is oversized and has children.
    leaves = [n for n in nodes if not any(c.get("parent_id") == n["id"] for c in nodes)]
    candidates = top
    if any(int(n.get("token_count") or 0) > lesson_context_tokens for n in top) and leaves:
        candidates = leaves

    bucket: list[str] = []
    bucket_tokens = 0
    bucket_i = 0

    def flush_bucket(title_hint: str | None = None):
        nonlocal bucket, bucket_tokens, bucket_i
        if not bucket:
            return
        bucket_i += 1
        first = outline_node_index(outline).get(bucket[0], {})
        title = title_hint or first.get("title") or f"Unit {bucket_i}"
        span_text = _preview_for_nodes(document_md, outline, bucket)
        chapters.append(
            {
                "id": f"ch-{_slug_ch(title, bucket_i)}",
                "order": bucket_i,
                "title": title,
                "summary": span_text[:500],
                "source_node_ids": list(bucket),
            }
        )
        bucket, bucket_tokens = [], 0

    for n in candidates:
        tok = int(n.get("token_count") or _approx_tokens(
            document_md[int(n["markdown_start"]) : int(n["markdown_end"])]
        ))
        if tok <= lesson_context_tokens and not bucket:
            chapters.append(
                {
                    "id": f"ch-{_slug_ch(n.get('title') or n['id'], len(chapters) + 1)}",
                    "order": len(chapters) + 1,
                    "title": n.get("title") or f"Unit {len(chapters) + 1}",
                    "summary": _preview_for_nodes(document_md, outline, [n["id"]])[:500],
                    "source_node_ids": [n["id"]],
                }
            )
            continue
        if bucket and bucket_tokens + tok > lesson_context_tokens:
            flush_bucket()
        bucket.append(n["id"])
        bucket_tokens += tok
    flush_bucket()

    if not chapters and nodes:
        ids = [n["id"] for n in nodes[:1]]
        chapters = [
            {
                "id": "ch-1",
                "order": 1,
                "title": nodes[0].get("title") or "Unit 1",
                "summary": _preview_for_nodes(document_md, outline, ids)[:500],
                "source_node_ids": ids,
            }
        ]

    return {
        "version": 1,
        "status": "fallback",
        "schema_version": 1,
        "map_model": None,
        "document_kind": "unknown",
        "document_summary": (document_md.strip().split("\n", 1)[0][:240] or "Document overview."),
        "thesis": None,
        "chapters": chapters,
    }


def _slug_ch(title: str, order: int) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "").strip().lower()).strip("-")
    return (s[:40] or f"unit-{order}")


def _preview_for_nodes(document_md: str, outline: dict, node_ids: list[str]) -> str:
    idx = outline_node_index(outline)
    parts: list[str] = []
    for nid in node_ids:
        n = idx.get(nid)
        if not n:
            continue
        parts.append(document_md[int(n["markdown_start"]) : int(n["markdown_end"])])
    text = "\n".join(parts).strip()
    words = text.split()
    return " ".join(words[:120])


def materialize_chapter_md(
    document_md: str,
    outline: dict,
    source_node_ids: list[str],
) -> tuple[str, list[tuple[int, int]], list[str]]:
    """Concatenate ordered unique non-overlapping MD spans for the given outline nodes.

    Returns (chapter_md, spans, element_ids). Nested parent/child overlap never duplicates text.
    Every returned segment is byte-equal to `document_md[start:end]`.
    """
    idx = outline_node_index(outline)
    # Collect raw spans from nodes; parent covering child → keep finest (prefer children).
    raw: list[tuple[int, int, str]] = []  # start, end, node_id
    for nid in source_node_ids:
        n = idx.get(nid)
        if not n:
            continue
        raw.append((int(n["markdown_start"]), int(n["markdown_end"]), nid))

    # If both parent and child are listed, drop parent spans that fully cover a selected child.
    selected = set(source_node_ids)
    filtered: list[tuple[int, int, str]] = []
    for s, e, nid in raw:
        children = [
            c
            for c in (outline.get("nodes") or [])
            if c.get("parent_id") == nid and c.get("id") in selected
        ]
        if children:
            # Parent selected with children → skip parent body; children cover evidence.
            continue
        filtered.append((s, e, nid))

    if not filtered and raw:
        # Only parents were selected (no children in the list) — keep parents.
        filtered = raw

    # Sort and union non-overlapping.
    filtered.sort(key=lambda t: (t[0], t[1]))
    spans: list[tuple[int, int]] = []
    for s, e, _ in filtered:
        if e <= s:
            continue
        if spans and s < spans[-1][1]:
            # Overlap: extend if needed, never rewind (no duplicate).
            if e > spans[-1][1]:
                spans[-1] = (spans[-1][0], e)
            continue
        spans.append((s, e))

    parts = [document_md[s:e] for s, e in spans]
    chapter = "".join(parts)
    # Verify verbatim
    for s, e in spans:
        assert document_md[s:e] == document_md[s:e]

    element_ids: list[str] = []
    seen: set[str] = set()
    for s, e, nid in filtered:
        n = idx.get(nid) or {}
        for eid in n.get("element_ids") or []:
            if eid not in seen:
                seen.add(eid)
                element_ids.append(eid)
    return chapter, spans, element_ids


def attach_materialized_chapters(
    teaching_map: dict,
    document_md: str,
    outline: dict,
    *,
    lesson_context_tokens: int = 24000,
) -> dict:
    """Fill per-chapter token_count; split oversized chapters into scoped units (no truncate)."""
    chapters = list(teaching_map.get("chapters") or [])
    out_chapters: list[dict] = []
    for ch in chapters:
        md, spans, _el = materialize_chapter_md(
            document_md, outline, list(ch.get("source_node_ids") or [])
        )
        tokens = _approx_tokens(md)
        ch = dict(ch)
        ch["token_count"] = tokens
        ch["span_count"] = len(spans)
        if tokens <= lesson_context_tokens:
            out_chapters.append(ch)
            continue
        # Split by individual source nodes into scoped teaching units.
        node_ids = list(ch.get("source_node_ids") or [])
        if len(node_ids) <= 1:
            out_chapters.append(ch)  # indivisible; caller may warn
            continue
        for j, nid in enumerate(node_ids):
            sub_md, _, _ = materialize_chapter_md(document_md, outline, [nid])
            out_chapters.append(
                {
                    "id": f"{ch['id']}-p{j + 1}",
                    "order": ch.get("order", 1) * 100 + j + 1,
                    "title": f"{ch.get('title', ch['id'])} ({j + 1})",
                    "summary": (ch.get("summary") or "")[:200],
                    "source_node_ids": [nid],
                    "token_count": _approx_tokens(sub_md),
                    "split_from": ch["id"],
                }
            )
    teaching_map = dict(teaching_map)
    teaching_map["chapters"] = out_chapters
    return teaching_map


def ocr_quality_below_threshold(
    quality: dict | None,
    *,
    min_confidence: float = 0.55,
    ocr_was_enabled: bool = False,
) -> bool:
    """True when OCR ran (or scanned path) and confidence/coverage fail the gate."""
    q = quality or {}
    if q.get("low_text") and ocr_was_enabled:
        return True
    conf = q.get("ocr_confidence")
    if conf is not None and ocr_was_enabled and float(conf) < min_confidence:
        return True
    return False


def wrap_teaching_map(validated: dict, *, status: str, map_model: str | None = None) -> dict:
    return {
        "version": 1,
        "status": status,
        "schema_version": 1,
        "map_model": map_model,
        "document_kind": validated.get("document_kind", "unknown"),
        "document_summary": validated.get("document_summary", ""),
        "thesis": validated.get("thesis"),
        "chapters": validated.get("chapters") or [],
    }


_TEACHING_MAP_SYSTEM = (
    "You extract a teaching curriculum map over an existing document outline. "
    "Return JSON only with keys: document_kind, document_summary, thesis (optional), "
    "chapters (list of {id, order, title, summary, source_node_ids}). "
    "Every source_node_id MUST be an id from the outline. Never invent nodes or rewrite bodies."
)

_TEACHING_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "document_kind": {"type": "string"},
        "document_summary": {"type": "string"},
        "thesis": {"type": "string"},
        "chapters": {"type": "array"},
    },
}


def effective_full_limit(
    *,
    full_tokens: int = 80000,
    context_window: int = 128000,
    output_reserve: int = 8192,
    system_prompt_tokens: int = 400,
) -> int:
    """Model-aware input budget for teaching-map extraction (rag-context §6)."""
    window_budget = max(1024, int(context_window) - int(system_prompt_tokens) - int(output_reserve))
    return max(1024, min(int(full_tokens), window_budget))


def _outline_brief(nodes: list[dict]) -> list[dict]:
    return [
        {
            "id": n["id"],
            "parent_id": n.get("parent_id"),
            "title": n.get("title"),
            "level": n.get("level"),
            "token_count": n.get("token_count"),
        }
        for n in nodes
    ]


def _prompt_tokens(system: str, user: str) -> int:
    return _approx_tokens(system) + _approx_tokens(user)


def _batch_outline_nodes(nodes: list[dict], *, max_nodes: int) -> list[list[dict]]:
    if not nodes:
        return []
    size = max(1, int(max_nodes))
    return [nodes[i : i + size] for i in range(0, len(nodes), size)]


async def _llm_teaching_json(llm, system: str, user: str) -> dict | None:
    try:
        if hasattr(llm, "generate_json"):
            raw = await llm.generate_json(system, user, _TEACHING_MAP_SCHEMA)
        else:
            text = await llm.generate_html(system, user)
            raw = json.loads(text)
    except Exception:  # noqa: BLE001
        return None
    return raw if isinstance(raw, dict) else None


async def extract_teaching_map_llm(
    *,
    document_md: str,
    outline: dict,
    llm,
    model_name: str | None = None,
    full_token_budget: int = 80000,
    context_window: int = 128000,
    output_reserve: int = 8192,
) -> dict | None:
    """Ask the LLM for teaching_map JSON only. Map-reduces when over effective_full_limit."""
    from ..core.tracing import traceable_run

    @traceable_run(
        "rag_teaching_map",
        tags=["agent:rag", "rag", "teaching_map"],
        metadata={"agent": "rag"},
    )
    async def _extract() -> dict | None:
        return await _extract_teaching_map_llm_impl(
            document_md=document_md,
            outline=outline,
            llm=llm,
            model_name=model_name,
            full_token_budget=full_token_budget,
            context_window=context_window,
            output_reserve=output_reserve,
        )

    return await _extract()


async def _extract_teaching_map_llm_impl(
    *,
    document_md: str,
    outline: dict,
    llm,
    model_name: str | None = None,
    full_token_budget: int = 80000,
    context_window: int = 128000,
    output_reserve: int = 8192,
) -> dict | None:
    """Ask the LLM for teaching_map JSON only. Map-reduces when over effective_full_limit."""
    nodes = list((outline or {}).get("nodes") or [])
    if not nodes:
        return None

    limit = effective_full_limit(
        full_tokens=full_token_budget,
        context_window=context_window,
        output_reserve=output_reserve,
        system_prompt_tokens=_approx_tokens(_TEACHING_MAP_SYSTEM),
    )
    outline_brief = _outline_brief(nodes)
    # ~4 chars/token for MD preview budget after outline JSON.
    outline_json = json.dumps({"outline_nodes": outline_brief}, ensure_ascii=False)
    outline_tok = _approx_tokens(outline_json)
    preview_budget_tok = max(500, limit - outline_tok - 200)
    preview_chars = min(len(document_md), preview_budget_tok * 4)
    user = json.dumps(
        {
            "outline_nodes": outline_brief,
            "document_preview": document_md[:preview_chars],
        },
        ensure_ascii=False,
    )

    # Single pass when the full outline + preview fits; else map-reduce by node batches.
    if _prompt_tokens(_TEACHING_MAP_SYSTEM, user) <= limit and outline_tok < limit * 0.7:
        raw = await _llm_teaching_json(llm, _TEACHING_MAP_SYSTEM, user)
        cleaned, errs = validate_teaching_map(raw or {}, outline)
        if cleaned is None:
            return None
        wrapped = wrap_teaching_map(cleaned, status="llm", map_model=model_name)
        wrapped["_validation_warnings"] = errs
        wrapped["_map_mode"] = "single"
        return wrapped

    # Map: batch outline nodes; each batch returns partial chapters.
    # Keep batches small enough that titles+ids fit comfortably under the limit.
    max_nodes = max(4, min(40, limit // 80))
    batches = _batch_outline_nodes(nodes, max_nodes=max_nodes)
    partial_chapters: list[dict] = []
    kind_votes: list[str] = []
    summaries: list[str] = []
    theses: list[str] = []

    map_system = (
        _TEACHING_MAP_SYSTEM
        + " This is a MAP pass over a subset of outline nodes; only use ids from this batch."
    )
    for bi, batch in enumerate(batches):
        brief = _outline_brief(batch)
        # Local MD preview: union of batch node spans (bounded).
        spans = [
            (int(n.get("markdown_start") or 0), int(n.get("markdown_end") or 0)) for n in batch
        ]
        if spans:
            start = min(s for s, _ in spans)
            end = max(e for _, e in spans)
            local_preview = document_md[start:end][: max(2000, (limit // len(batches)) * 2)]
        else:
            local_preview = document_md[:2000]
        map_user = json.dumps(
            {
                "batch_index": bi,
                "batch_count": len(batches),
                "outline_nodes": brief,
                "document_preview": local_preview,
            },
            ensure_ascii=False,
        )
        raw = await _llm_teaching_json(llm, map_system, map_user)
        if not raw:
            continue
        # Validate against full outline so unknown ids are dropped, not rejected wholesale.
        cleaned, _errs = validate_teaching_map(
            {
                "document_kind": raw.get("document_kind") or "unknown",
                "document_summary": raw.get("document_summary") or f"Batch {bi + 1} overview.",
                "thesis": raw.get("thesis"),
                "chapters": raw.get("chapters") or [],
            },
            outline,
        )
        if cleaned is None:
            # Soft fallback for this batch: one chapter per top-level node in the batch.
            for n in batch:
                if n.get("parent_id"):
                    continue
                partial_chapters.append(
                    {
                        "id": f"ch-map-{n['id']}",
                        "order": len(partial_chapters) + 1,
                        "title": n.get("title") or n["id"],
                        "summary": "",
                        "source_node_ids": [n["id"]],
                    }
                )
            continue
        kind_votes.append(str(cleaned.get("document_kind") or "unknown"))
        if cleaned.get("document_summary"):
            summaries.append(str(cleaned["document_summary"]))
        if cleaned.get("thesis"):
            theses.append(str(cleaned["thesis"]))
        for ch in cleaned.get("chapters") or []:
            partial_chapters.append(ch)

    if not partial_chapters:
        return None

    # Reduce: ask the model to merge partial chapters, or deterministically concat if reduce fails.
    reduce_system = (
        "You merge partial teaching_map chapter lists into one coherent curriculum map. "
        "Return JSON only with keys: document_kind, document_summary, thesis (optional), "
        "chapters (list of {id, order, title, summary, source_node_ids}). "
        "Every source_node_id MUST appear in allowed_node_ids. Do not invent nodes."
    )
    reduce_user = json.dumps(
        {
            "allowed_node_ids": [n["id"] for n in nodes],
            "partial_chapters": partial_chapters,
            "document_kind_votes": kind_votes,
            "partial_summaries": summaries[:8],
            "partial_theses": theses[:4],
        },
        ensure_ascii=False,
    )
    reduced = await _llm_teaching_json(llm, reduce_system, reduce_user)
    if reduced:
        cleaned, errs = validate_teaching_map(reduced, outline)
        if cleaned is not None:
            wrapped = wrap_teaching_map(cleaned, status="llm", map_model=model_name)
            wrapped["_validation_warnings"] = errs
            wrapped["_map_mode"] = "map_reduce"
            return wrapped

    # Deterministic reduce: keep partial chapters in order, re-number.
    merged = {
        "document_kind": (kind_votes[0] if kind_votes else "unknown"),
        "document_summary": (summaries[0] if summaries else "Document overview."),
        "thesis": theses[0] if theses else None,
        "chapters": [
            {**ch, "order": i + 1, "id": ch.get("id") or f"ch-{i + 1}"}
            for i, ch in enumerate(partial_chapters)
        ],
    }
    cleaned, errs = validate_teaching_map(merged, outline)
    if cleaned is None:
        return None
    wrapped = wrap_teaching_map(cleaned, status="llm", map_model=model_name)
    wrapped["_validation_warnings"] = errs
    wrapped["_map_mode"] = "map_reduce_deterministic"
    return wrapped


def build_teaching_map_for_ingest(
    document_md: str,
    outline: dict,
    *,
    tree_enabled: bool = True,
    llm_map: dict | None = None,
    lesson_context_tokens: int = 24000,
) -> dict:
    """Prefer validated LLM map; else fallback. Always attach token_counts / splits."""
    if tree_enabled and llm_map and llm_map.get("chapters"):
        status = llm_map.get("status") or "llm"
        base = {
            "version": 1,
            "status": status,
            "schema_version": 1,
            "map_model": llm_map.get("map_model"),
            "document_kind": llm_map.get("document_kind", "unknown"),
            "document_summary": llm_map.get("document_summary", ""),
            "thesis": llm_map.get("thesis"),
            "chapters": llm_map.get("chapters") or [],
        }
    else:
        base = fallback_teaching_map(
            document_md, outline, lesson_context_tokens=lesson_context_tokens
        )
    return attach_materialized_chapters(
        base, document_md, outline, lesson_context_tokens=lesson_context_tokens
    )
