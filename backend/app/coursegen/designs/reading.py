"""Reading design agent (specs/design_agents §3, step 4).

For document-grounded lessons the right experience is often the source's own prose
with a learning layer on top. The model **annotates** — it never rewrites the source:
section bodies are copied verbatim from the research source pack, and a fast-tier LLM
produces a validated annotation layer (intent, per-section objectives, margin notes,
one comprehension check each, glossary). The result is a ``ReadingDoc`` tree rendered
by trusted React — like A2UI it never passes through the capsule gate because no
untrusted markup exists.

Fail-closed at every level: no source pack → delegate to the page agent; annotation
failure → ship the doc with the prose alone (still a real lesson).
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .base import AuthorContext, DesignOutput

logger = logging.getLogger(__name__)

MAX_SECTIONS = 8
MAX_BODY_CHARS = 24_000  # per section, verbatim source prose
_ANNOTATE_BODY_CHARS = 2_000  # per section, shown to the annotator


class ReadingNote(BaseModel):
    """A margin note: a short teaching aside anchored near a phrase of the prose."""

    anchor: str = ""  # optional verbatim phrase from the body the note attaches to
    text: str


class ReadingCheck(BaseModel):
    question: str
    answer: str  # revealed on demand in the renderer


class GlossaryTerm(BaseModel):
    term: str
    definition: str


class ReadingSection(BaseModel):
    id: str
    title: str
    objective: str = ""
    body_md: str  # SOURCE prose, verbatim — never model-authored
    notes: list[ReadingNote] = Field(default_factory=list)
    check: ReadingCheck | None = None


class ReadingDoc(BaseModel):
    kind: Literal["reading"] = "reading"
    schema_version: str = "1.0"
    title: str
    intent: str = ""
    source_document_id: str | None = None
    sections: list[ReadingSection]
    glossary: list[GlossaryTerm] = Field(default_factory=list)


class _SectionAnnotation(BaseModel):
    id: str
    objective: str = ""
    notes: list[str] = Field(default_factory=list)
    check_question: str = ""
    check_answer: str = ""


class ReadingAnnotations(BaseModel):
    """What the fast-tier annotator returns — everything optional, all fail-soft."""

    intent: str = ""
    sections: list[_SectionAnnotation] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)


def validate_reading_doc(raw: dict | None) -> dict | None:
    """Re-validate a stored/authored doc; None when structurally invalid."""
    if not raw:
        return None
    try:
        return ReadingDoc.model_validate(raw).model_dump()
    except ValidationError:
        return None


def _slug(value: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")
    return slug[:60] or f"part-{index + 1}"


def sections_from_pack(pack: list[dict]) -> list[ReadingSection]:
    """Deterministic sections from the research source pack — bodies verbatim."""
    sections: list[ReadingSection] = []
    for i, entry in enumerate(pack[:MAX_SECTIONS]):
        body = str(entry.get("text") or "").strip()
        if not body:
            continue
        title = str(entry.get("section_title") or f"Part {i + 1}").strip()
        sections.append(
            ReadingSection(
                id=_slug(entry.get("chapter_id") or entry.get("id") or title, i),
                title=title,
                body_md=body[:MAX_BODY_CHARS],
            )
        )
    return sections


_ANNOTATE_SYSTEM = (
    "You are a learning designer annotating a source text for a reading companion. "
    "You NEVER rewrite or summarize the source into new prose — you add a thin teaching "
    "layer: a one-line lesson intent, and per section a learning objective, one to three "
    "short margin notes (each ≤ 30 words, concrete, tied to the section), and ONE "
    "comprehension check (question + concise answer). Add up to 8 glossary terms actually "
    "used in the text. Use the section ids exactly as given."
)


async def _annotate(
    ctx: AuthorContext, sections: list[ReadingSection]
) -> ReadingAnnotations:
    from ...providers.registry import get_coursegen_planner_llm

    excerpt_blocks = "\n\n".join(
        f"[id={s.id}] {s.title}\n{s.body_md[:_ANNOTATE_BODY_CHARS]}" for s in sections
    )
    user = (
        f'Lesson: "{ctx.plan.get("title")}" (objective: {ctx.plan.get("subtitle") or ""}).\n'
        f"Annotate these {len(sections)} sections:\n\n{excerpt_blocks}"
    )
    try:
        llm = get_coursegen_planner_llm()
        result = await llm.generate_json(_ANNOTATE_SYSTEM, user, ReadingAnnotations)
        return (
            result
            if isinstance(result, ReadingAnnotations)
            else ReadingAnnotations.model_validate(result)
        )
    except Exception as exc:  # noqa: BLE001 — prose alone is still a real lesson
        logger.warning("reading annotation failed; shipping bare prose: %s", exc)
        return ReadingAnnotations()


def assemble(
    plan: dict, sections: list[ReadingSection], annotations: ReadingAnnotations
) -> ReadingDoc:
    by_id = {a.id: a for a in annotations.sections}
    for section in sections:
        note = by_id.get(section.id)
        if note is None:
            continue
        section.objective = note.objective[:200]
        section.notes = [ReadingNote(text=t[:300]) for t in note.notes[:3] if t.strip()]
        if note.check_question.strip() and note.check_answer.strip():
            section.check = ReadingCheck(
                question=note.check_question[:300], answer=note.check_answer[:600]
            )
    return ReadingDoc(
        title=str(plan.get("title") or "Reading"),
        intent=annotations.intent[:300],
        source_document_id=plan.get("source_document_id"),
        sections=sections,
        glossary=annotations.glossary[:8],
    )


class ReadingAgent:
    mode = "reading"

    async def author(self, ctx: AuthorContext) -> DesignOutput:
        sections = sections_from_pack(ctx.plan.get("source_pack") or [])
        if not sections:
            # Nothing to read — the universal page agent takes over (fail-closed).
            from .page import PageAgent

            await ctx.progress(
                "generating", "No readable source found — building a page lesson…", 58
            )
            return await PageAgent().author(ctx)

        await ctx.progress(
            "generating",
            f"Annotating the source reading ({len(sections)} sections)…",
            60,
        )
        annotations = await _annotate(ctx, sections)
        doc = assemble(ctx.plan, sections, annotations)
        return DesignOutput(kind="reading", a2ui=doc.model_dump(), html="", plan=ctx.plan)


# The grounding digester for reading docs lives in app/surface/digest.py — the protocol
# layer may never import this agent, so the pure dict-walking half is defined there.
