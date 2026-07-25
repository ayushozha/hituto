"""LangGraph generation pipeline (design.md §3).

interpret/plan -> research -> asset-plan -> generate -> post-process -> persist
with a bounded generate<->post-process repair loop. Emits progress events for SSE.
"""
from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..models import Artifact, Citation, Course, Lesson, LessonSourcePack, SourceDocument
from ..rag.context import get_chapter_context, resolve_visual_candidates
from ..rag.ensure import ensure_knowledge_tree
from ..rag.retrieve import retrieve_passages, search_source_pack
from ..core.progress import ProgressEvent, broker
from ..providers.registry import get_coursegen_llm, get_search
from .checkpoint import generation_thread_id, get_checkpointer
from .planner import build_lesson_plan
from ..capsule.postprocess import postprocess, validate_artifact_runtime
from .state import GenState
from ..core.tracing import agent_run_config

logger = logging.getLogger(__name__)

# Alias used by conftest monkeypatches and internal nodes.
get_llm = get_coursegen_llm


def _lesson_chapter_ids(course: Course, lesson: Lesson) -> list[str]:
    scopes = (course.knobs or {}).get("lesson_scopes") or {}
    scope = scopes.get(str(lesson.ordinal)) or scopes.get(lesson.ordinal) or {}
    return list(scope.get("chapter_ids") or [])


async def _emit(course_id: str, stage: str, detail: str, pct: int) -> None:
    await broker.publish(course_id, ProgressEvent(stage=stage, detail=detail, pct=pct))


class _FragmentStreamer:
    """Throttles LLM token deltas into `gen_fragment` SSE frames (fast_gen §4.3 Mode B).

    Frames are ephemeral theater for the generating user's shell iframe: transient in the
    broker (never replayed to late subscribers) and never persisted. `length` lets the
    client detect a gap (missed frames) and simply keep what it has — the gated artifact
    replaces everything at the end regardless.
    """

    MIN_CHARS = 280
    MIN_INTERVAL_S = 0.45

    def __init__(
        self,
        course_id: str,
        lesson_id: str,
        attempt: int,
        section_id: str | None = None,
    ) -> None:
        self._course_id = course_id
        self._lesson_id = lesson_id
        self._attempt = attempt
        self._section_id = section_id
        self._pending = ""
        self._sent = 0
        self._seq = 0
        self._last = 0.0

    async def on_delta(self, delta: str) -> None:
        self._pending += delta
        now = asyncio.get_running_loop().time()
        if len(self._pending) < self.MIN_CHARS and (now - self._last) < self.MIN_INTERVAL_S:
            return
        await self.flush()

    async def flush(self, final: bool = False) -> None:
        if not self._pending and not final:
            return
        frag, self._pending = self._pending, ""
        self._last = asyncio.get_running_loop().time()
        self._seq += 1
        self._sent += len(frag)
        await broker.publish(
            self._course_id,
            ProgressEvent(
                stage="gen_fragment",
                pct=65,
                data={
                    "lesson_id": self._lesson_id,
                    "attempt": self._attempt,
                    "section_id": self._section_id,
                    "seq": self._seq,
                    "delta": frag,
                    "length": self._sent,
                    "done": final,
                },
            ),
        )


async def _search_facts(cid: str, title: str) -> tuple[list[dict], list[dict]]:
    """Best-effort web facts for ungrounded lessons — never blocks generation."""
    facts: list[dict] = []
    citations: list[dict] = []
    try:
        search = get_search()
        results = await search.search(title, n=4)
        for r in results:
            if r.get("url"):
                claim = (r.get("text") or r.get("title") or "")[:200]
                facts.append({"claim": claim, "source_url": r["url"]})
                citations.append({"claim": claim, "source_url": r["url"]})
    except Exception as e:  # research is best-effort; never block generation on it
        await _emit(cid, "researching", f"(search skipped: {e})", 35)
    return facts, citations


async def interpret(state: GenState) -> GenState:
    cid = state["course_id"]
    lid = state["lesson_id"]
    
    with SessionLocal() as db:
        course = db.get(Course, cid)
        lesson = db.get(Lesson, lid)
        if not course or not lesson:
            raise ValueError("Course or Lesson not found in database")
        course_title = course.title or course.topic
        lesson_title = lesson.title
        objective = lesson.objective
        archetype = lesson.archetype
        difficulty = course.knobs.get("difficulty", "intermediate")
        style_theme = course.knobs.get("style_theme")
        # Learner profile snapshot injected at course creation (specs/learner_profile).
        learner_profile = (course.knobs or {}).get("learner_profile")
        from .presentation import knobs_design_mode

        presentation = knobs_design_mode(course.knobs)
        lesson_pack = db.scalars(
            select(LessonSourcePack)
            .where(LessonSourcePack.lesson_id == lesson.id)
            .order_by(LessonSourcePack.created_at.desc())
            .limit(1)
        ).first()
        source_document_id = (
            lesson_pack.source_document_id
            if lesson_pack
            else course.knobs.get("source_document_id")
        )
        user_id = course.user_id
        chapter_ids = (
            list(lesson_pack.chapter_ids or [])
            if lesson_pack
            else _lesson_chapter_ids(course, lesson)
        )

    await _emit(cid, "planning", f"Designing lesson '{lesson_title}'…", 10)

    plan_call = build_lesson_plan(
        course_title=course_title,
        lesson_title=lesson_title,
        objective=objective,
        archetype=archetype,
        difficulty=difficulty,
        style_theme=style_theme,
        presentation=presentation,
        learner_profile=learner_profile,
    )
    research_out: GenState = {}
    if get_settings().gen_parallel_interpret and not source_document_id:
        # fast_gen §2.1: the web-search query is the lesson title, known before the plan
        # LLM returns — run research concurrently with planning. Document-grounded
        # lessons keep the serial research node (retrieval reads the plan's scope).
        plan, (facts, citations) = await asyncio.gather(
            plan_call, _search_facts(cid, lesson_title)
        )
        plan["facts"] = facts
        research_out = {"citations": citations, "research_done": True}
    else:
        plan = await plan_call

    # Carry the learner-profile snapshot into the plan so build_user_prompt can render it.
    if learner_profile:
        plan["learner_profile"] = learner_profile

    # fast_gen §4.1: skeleton BEFORE research/asset_plan specialist work so the theater
    # paints an outline immediately (parallel interpret may already have finished search).
    if get_settings().gen_streaming_enabled:
        sections = [
            {
                "id": str(s.get("id") or f"s{i}"),
                "icon": str(s.get("icon") or ""),
                "title": str(s.get("title") or ""),
            }
            for i, s in enumerate(plan.get("sections") or [])
            if isinstance(s, dict)
        ]
        await broker.publish(
            cid,
            ProgressEvent(
                stage="skeleton",
                detail=f"Outline ready for '{lesson_title}'",
                pct=15,
                data={
                    "lesson_id": lid,
                    "title": plan.get("title") or lesson_title,
                    "subtitle": plan.get("subtitle") or "",
                    "sections": sections,
                },
            ),
        )

    with SessionLocal() as db:
        lesson = db.get(Lesson, lid)
        if lesson:
            lesson.status = "generating"
            db.commit()

    return {
        "plan": plan,
        "attempts": 0,
        "source_document_id": source_document_id,
        "user_id": user_id,
        "source_query": f"{lesson_title}. {objective}",
        "chapter_ids": chapter_ids,
        **research_out,
    }


async def research(state: GenState) -> GenState:
    if state.get("research_done"):
        return {}
    cid = state["course_id"]
    plan = state["plan"]
    sid = state.get("source_document_id")
    chapter_ids = list(state.get("chapter_ids") or [])

    # Document-grounded: prefer verbatim teaching-map chapter context (rag-context Phase 3).
    if sid:
        await _emit(cid, "researching", "Retrieving grounded source excerpts…", 30)
        limit = get_settings().max_chunks_per_source_pack
        query = state.get("source_query") or plan["title"]
        pack, citations, chunk_ids = [], [], []
        settings = get_settings()
        with SessionLocal() as db:
            doc = db.get(SourceDocument, sid)
            used_chapter = False
            if (
                doc
                and settings.rag_teaching_map_planner
                and chapter_ids
                and (doc.source_map or {}).get("teaching_map")
            ):
                try:
                    # Primary chapter; concat neighbors only as titles (not bodies) to avoid bloat.
                    primary = chapter_ids[0]
                    ctx = await get_chapter_context(db, doc=doc, chapter_id=primary)
                    # Oversized chapter: if it was already split into teaching units at ingest,
                    # scopes should already point at a scoped unit. Still never blind-truncate.
                    body = ctx.markdown
                    pack = [
                        {
                            "id": primary[:8],
                            "page_start": None,
                            "page_end": None,
                            "section_title": ctx.title,
                            "text": body,
                            "chapter_id": primary,
                            "token_count": ctx.token_count,
                            "document_summary": ctx.document_summary,
                            "thesis": ctx.thesis,
                            "neighbor_titles": ctx.neighbor_titles,
                            "figure_storage_keys": ctx.figure_storage_keys,
                        }
                    ]
                    # Optional: append additional scoped chapter ids in the lesson scope.
                    for extra_id in chapter_ids[1:]:
                        try:
                            extra = await get_chapter_context(db, doc=doc, chapter_id=extra_id)
                            pack.append(
                                {
                                    "id": extra_id[:8],
                                    "section_title": extra.title,
                                    "text": extra.markdown,
                                    "chapter_id": extra_id,
                                    "token_count": extra.token_count,
                                }
                            )
                        except ValueError:
                            continue
                    citations = [
                        {
                            "claim": (p.get("text") or "")[:200],
                            "source_url": f"source:{sid}#chapter={p.get('chapter_id')}",
                        }
                        for p in pack
                    ]
                    figures = resolve_visual_candidates(doc, chapter_ids)
                    plan["source_figures"] = figures
                    plan["source_document_id"] = sid
                    used_chapter = True
                except ValueError:
                    used_chapter = False

            if not used_chapter:
                # Lazy-upgrade then chapter / passage retrieve (no concept_dag).
                if doc:
                    try:
                        doc = await ensure_knowledge_tree(db, doc)
                        db.refresh(doc)
                    except Exception:  # noqa: BLE001
                        pass
                    scope_ids = chapter_ids or []
                    if not scope_ids:
                        tm_chs = ((doc.source_map or {}).get("teaching_map") or {}).get("chapters") or []
                        scope_ids = [c["id"] for c in tm_chs[:1] if c.get("id")]
                    if scope_ids and (doc.source_map or {}).get("teaching_map"):
                        try:
                            ctx = await get_chapter_context(db, doc=doc, chapter_id=scope_ids[0])
                            pack = [
                                {
                                    "id": scope_ids[0][:8],
                                    "section_title": ctx.title,
                                    "text": ctx.markdown,
                                    "chapter_id": scope_ids[0],
                                    "token_count": ctx.token_count,
                                    "document_summary": ctx.document_summary,
                                    "figure_storage_keys": ctx.figure_storage_keys,
                                }
                            ]
                            citations = [
                                {
                                    "claim": (ctx.markdown or "")[:200],
                                    "source_url": f"source:{sid}#chapter={scope_ids[0]}",
                                }
                            ]
                            plan["source_figures"] = resolve_visual_candidates(doc, scope_ids)
                            chapter_ids = scope_ids
                            used_chapter = True
                        except ValueError:
                            used_chapter = False

                if not used_chapter:
                    full = doc.full_text if doc else None
                    if full and len(full) < settings.small_doc_char_threshold:
                        pack = [
                            {
                                "id": "full",
                                "page_start": 1,
                                "page_end": doc.page_count if doc else None,
                                "section_title": "(full source)",
                                "text": full[: settings.small_doc_char_threshold],
                            }
                        ]
                        citations = [{"claim": full[:200], "source_url": f"source:{sid}#full"}]
                    else:
                        # Passage / keyword shim — never DAG.
                        excerpts = await retrieve_passages(
                            db,
                            source_document_id=sid,
                            user_id=state.get("user_id", "dev"),
                            query=query,
                            chapter_ids=chapter_ids or None,
                            limit=limit,
                        )
                        if not excerpts:
                            chunks = await search_source_pack(
                                db,
                                source_document_id=sid,
                                user_id=state.get("user_id", "dev"),
                                query=query,
                                limit=limit,
                            )
                            for c in chunks:
                                page = c.page_start or 1
                                pack.append(
                                    {
                                        "id": c.id[:8],
                                        "page_start": c.page_start,
                                        "page_end": c.page_end,
                                        "section_title": c.section_title,
                                        "text": c.text or "",
                                    }
                                )
                                citations.append(
                                    {
                                        "claim": (c.text or "")[:200],
                                        "source_url": f"source:{sid}#page={page}",
                                    }
                                )
                                chunk_ids.append(c.id)
                        else:
                            for e in excerpts:
                                pack.append(
                                    {
                                        "id": (e.chunk_id or "pass")[:8],
                                        "page_start": e.page_start,
                                        "page_end": e.page_end,
                                        "section_title": e.section_title,
                                        "text": e.text,
                                        "chapter_id": e.chapter_id,
                                        "element_ids": list(e.element_ids or []),
                                        "ref_label": e.ref_label,
                                    }
                                )
                                citations.append(
                                    {
                                        "claim": (e.text or "")[:200],
                                        "source_url": (
                                            f"source:{sid}#chapter={e.chapter_id}"
                                            if e.chapter_id
                                            else f"source:{sid}#page={e.page_start or 1}"
                                        ),
                                    }
                                )
                                if e.chunk_id:
                                    chunk_ids.append(e.chunk_id)
                    if doc:
                        plan.setdefault(
                            "source_figures",
                            resolve_visual_candidates(doc, chapter_ids or []),
                        )
        plan["source_pack"] = pack
        plan["facts"] = [
            {
                "claim": (p.get("text") or "")[:160],
                "source_url": f"source:{sid}#chapter={p['chapter_id']}"
                if p.get("chapter_id")
                else f"source:{sid}#page={p.get('page_start') or 1}",
            }
            for p in pack
        ]
        return {
            "plan": plan,
            "citations": citations,
            "source_pack_chunk_ids": chunk_ids,
            "chapter_ids": chapter_ids,
        }

    await _emit(cid, "researching", f"Searching for facts about {plan['title']}…", 30)
    facts, citations = await _search_facts(cid, plan["title"])
    plan["facts"] = facts
    return {"plan": plan, "citations": citations}


async def asset_plan(state: GenState) -> GenState:
    """Best-effort compute pipeline: data-synthesizer → viz-engineer (simulation/game only).

    Runs after interpret's skeleton frame so the theater is already visible during any
    specialist / mesh work. Page explainers without 3D skip the specialist theater noise.
    """
    plan = dict(state.get("plan") or {})
    knobs = dict(state.get("knobs") or {})
    from .presentation import resolve_presentation
    from .studio_manifest import prepare_studio_plan

    presentation = resolve_presentation(plan, knobs)
    if presentation == "studio":
        plan = prepare_studio_plan(plan, knobs)
        if plan["studio_mode"] == "specimen":
            if knobs.get("needs_3d") is not False:
                knobs["needs_3d"] = True
        else:
            knobs["needs_3d"] = False
    archetype = (plan.get("archetype") or state.get("knobs", {}).get("archetype") or "explainer")
    concept = plan.get("title") or state.get("topic") or "concept"
    course_topic = state.get("topic") or ""
    arch_l = str(archetype).lower()

    # Fast path: HTML page lessons (explainer/narrative/tool) don't need compute assets.
    # Skip specialist consulting so generate (and section streaming) starts sooner.
    if presentation != "studio" and arch_l in ("explainer", "narrative", "tool"):
        from .mesh import needs_3d_mesh

        if not needs_3d_mesh(
            concept=concept,
            archetype=str(archetype),
            knobs=knobs,
            specialist_name=None,
            topic=course_topic,
        ):
            await _emit(
                state["course_id"],
                "researching",
                "Outline locked — authoring interactive sections…",
                50,
            )
            return {"plan": plan}

    await _emit(state["course_id"], "researching", "Planning visuals…", 45)
    out: GenState = {}
    try:
        from .agents.registry import resolve_specialist
        from .agents.roles import run_asset_plan_pipeline

        specialist = resolve_specialist(
            state.get("topic") or concept,
            subject_knob=(state.get("knobs") or {}).get("subject"),
        )
        specialist_name = specialist.name if specialist else None
        if specialist:
            plan["subject_specialist"] = specialist.name
            await _emit(
                state["course_id"],
                "researching",
                f"Consulting {specialist.name}…",
                46,
            )

        from .mesh import needs_3d_mesh

        mesh_wanted = needs_3d_mesh(
            concept=concept,
            archetype=str(archetype),
            knobs=knobs,
            specialist_name=specialist_name,
            topic=course_topic,
        )
        if mesh_wanted:
            plan["needs_3d"] = True

        async_mesh = get_settings().gen_async_assets
        if async_mesh:
            # fast_gen §2.2: mesh generation (Hunyuan polls, up to minutes) runs as a
            # background job; the pipeline proceeds on the procedural fallback and the
            # mesh joins at generate, persist, or as a late-join artifact version.
            from . import assets

            assets.start_mesh_job(
                course_id=state["course_id"],
                lesson_id=state["lesson_id"],
                concept=concept,
                archetype=str(archetype),
                knobs=knobs,
                specialist_name=specialist_name,
                topic=course_topic,
            )
            if mesh_wanted or plan.get("studio_mode") == "specimen":
                plan["mesh_fallback"] = True
                await _emit(
                    state["course_id"],
                    "researching",
                    "3D model rendering in the background — the lesson won't wait for it",
                    47,
                )
            from .agents.roles import run_compute_stage

            art = run_compute_stage(
                concept=concept,
                archetype=str(archetype),
                knobs=knobs,
                seed=(state.get("knobs") or {}).get("compute_seed"),
                topic=course_topic,
            )
            mesh_art, mesh_catalog = None, None
        else:
            art, mesh_art, mesh_catalog = await run_asset_plan_pipeline(
                concept=concept,
                archetype=str(archetype),
                seed=(state.get("knobs") or {}).get("compute_seed"),
                knobs=knobs,
                specialist_name=specialist_name,
                topic=course_topic,
            )
        if mesh_catalog:
            plan["mesh_catalog"] = mesh_catalog
            plan["studio_subjects"] = mesh_catalog
        if mesh_art is not None:
            # Never put data_b64 into plan — it is multi‑MB and blows the LLM context.
            mesh_meta = mesh_art.model_dump(exclude={"data_b64"})
            plan["mesh_artifact"] = mesh_meta
            plan["mesh_url"] = mesh_art.path
            out["mesh_artifact"] = mesh_meta  # cache_key only — bytes live on disk
            try:
                from ..services import billing_service

                with SessionLocal() as db:
                    course = db.get(Course, state["course_id"])
                    if course is not None:
                        billing_service.spend_lab_credit(
                            db, course.user_id, course_id=course.id
                        )
            except Exception:  # noqa: BLE001 — never block generation on metering
                logger.exception("billing: failed to record lab credit")
            await _emit(
                state["course_id"],
                "researching",
                f"3D mesh ready ({', '.join(mesh_art.role_log[:2])})",
                47,
            )
        elif mesh_wanted and not async_mesh:
            plan["mesh_fallback"] = True
            await _emit(
                state["course_id"],
                "researching",
                "3D mesh unavailable — using procedural studio fallback",
                47,
            )
        if art is not None:
            plan["simulation_trace"] = art.trace.model_dump() if art.trace else None
            plan["compute_artifact"] = art.model_dump()
            if art.chart_spec:
                plan["chart_spec"] = art.chart_spec
            if art.assets:
                # Hint capsule-author to embed scratch paths (inlined at persist).
                plan["compute_plot_paths"] = [a.path for a in art.assets]
            out["compute_artifact"] = art.model_dump()
            await _emit(
                state["course_id"],
                "researching",
                f"Compute assets ready ({', '.join(art.role_log[:3])})",
                48,
            )
    except Exception as exc:  # noqa: BLE001 — never block generation
        await _emit(state["course_id"], "researching", f"(compute skipped: {exc})", 48)
    out["plan"] = plan
    return out


async def generate(state: GenState) -> GenState:
    cid = state["course_id"]
    attempt = state.get("attempts", 0) + 1
    plan = state.get("plan") or {}
    settings = get_settings()

    # fast_gen §2.2: a fast/cached background mesh joins v1 here, pre-render — same
    # outcome as the old synchronous path, without having waited for slow meshes.
    merged_assets: GenState = {}
    if settings.gen_async_assets:
        from . import assets

        ready = assets.take_ready(state["lesson_id"])
        if ready:
            mesh_art, mesh_catalog = ready
            plan = dict(plan)
            plan.pop("mesh_fallback", None)
            if mesh_catalog:
                plan["mesh_catalog"] = mesh_catalog
                plan["studio_subjects"] = mesh_catalog
            if mesh_art is not None:
                mesh_meta = mesh_art.model_dump(exclude={"data_b64"})
                plan["mesh_artifact"] = mesh_meta
                plan["mesh_url"] = mesh_art.path
                merged_assets["mesh_artifact"] = mesh_meta
            await _emit(cid, "generating", "3D assets ready — folding them into the lesson", 58)

    # Design-family dispatch (specs/design_agents §4): the router resolves the mode, the
    # registry picks the agent, and authoring strategy lives inside the agent. Unknown
    # modes and refinements (which transform existing HTML) go to the page agent.
    from .designs import AuthorContext, get_design_agent
    from .presentation import resolve_presentation

    knobs = state.get("knobs") or {}
    mode = resolve_presentation(plan, knobs)
    if state.get("previous_html"):
        mode = "page"
    agent = get_design_agent(mode)

    lid = state["lesson_id"]

    def _streamer(section_id: str | None = None) -> _FragmentStreamer | None:
        if not settings.gen_streaming_enabled:
            return None
        return _FragmentStreamer(cid, lid, attempt, section_id=section_id)

    async def _scoped_emit(stage: str, detail: str, pct: int) -> None:
        await _emit(cid, stage, detail, pct)

    out = await agent.author(
        AuthorContext(
            course_id=cid,
            lesson_id=lid,
            attempt=attempt,
            plan=plan,
            knobs=knobs,
            state=state,
            llm=get_llm(),
            streamer_factory=_streamer,
            emit=_scoped_emit,
        )
    )
    return {
        "plan": out.plan or plan,
        "html": out.html,
        "a2ui": out.a2ui,
        "artifact_kind": out.kind,
        "attempts": attempt,
        **merged_assets,
    }


async def post_process(state: GenState) -> GenState:
    # Reading lessons are a trusted annotation tree over verbatim source prose — no
    # untrusted markup exists, so the capsule gate does not apply; re-validate the tree.
    if state.get("artifact_kind") == "reading":
        await _emit(state["course_id"], "finalizing", "Validating reading companion…", 80)
        from .designs.reading import validate_reading_doc

        doc = validate_reading_doc(state.get("a2ui"))
        if doc:
            return {
                "a2ui": doc,
                "artifact_kind": "reading",
                "html": "",
                "checks": {"passed": True, "failed": [], "kind": "reading"},
            }
        return {
            "checks": {"passed": False, "failed": ["reading: invalid doc"], "kind": "reading"},
            "artifact_kind": "reading",
        }

    # A2UI lessons skip HTML postprocess — tree was already normalized by capsule-author.
    if state.get("artifact_kind") == "a2ui" and state.get("a2ui"):
        await _emit(state["course_id"], "finalizing", "Validating A2UI lesson…", 80)
        from ..a2ui import normalize_render_ui

        recheck = normalize_render_ui(state["a2ui"])
        if recheck:
            return {
                "a2ui": recheck,
                "artifact_kind": "a2ui",
                "html": "",
                "checks": {"passed": True, "failed": [], "kind": "a2ui"},
            }
        return {
            "checks": {"passed": False, "failed": ["a2ui: invalid component tree"], "kind": "a2ui"},
            "artifact_kind": "a2ui",
        }

    await _emit(state["course_id"], "finalizing", "Repairing & wiring up images…", 80)
    html, checks = postprocess(state["html"])

    # fast_gen Phase 1: browser validation (Playwright) and the grounding-review LLM both
    # consume the same finished HTML and are independent — run them concurrently.
    settings = get_settings()
    plan = state.get("plan", {})
    pack = plan.get("source_pack", [])
    needs_review = bool(state.get("source_document_id")) and settings.course_tier in (
        "standard",
        "high",
    )
    review = None
    if needs_review:
        from ..rag.citations import review_grounding

        checks, review = await asyncio.gather(
            validate_artifact_runtime(html, checks),
            review_grounding(html, pack),
        )
    else:
        checks = await validate_artifact_runtime(html, checks)
    manifest = (state.get("plan") or {}).get("studio_manifest")
    if isinstance(manifest, dict):
        checks.update(
            {
                "presentation": "studio",
                "studio_mode": manifest.get("mode"),
                "studio_manifest_version": manifest.get("schema_version", "2.0"),
            }
        )
    else:
        from .studio_renderer import studio_artifact_metadata

        checks.update(studio_artifact_metadata(html))
    out: GenState = {"html": html, "checks": checks, "artifact_kind": "html"}

    # Grounding validation for source-grounded lessons (tasks.md #34, #35, #37).
    if state.get("source_document_id"):
        from ..rag.citations import build_repair_brief, check_grounding

        grounding = check_grounding(html, pack, state.get("citations", []))
        checks["grounding"] = grounding
        # Enforce only with a real LLM (the stub can't cite) and only in standard/high tiers
        # (R14.3). `review` was produced concurrently with browser validation above.
        if review is not None:
            grounding["unsupported_claims"] = review.unsupported_claims
            grounding["unsupported_answers"] = review.unsupported_answers
            soft = [*review.unsupported_claims, *review.unsupported_answers]
            attempts = state.get("attempts", 0)
            will_retry = attempts < settings.max_gen_retries
            # Hard deterministic violations always block (and can fail on exhaustion). Soft
            # unsupported claims/answers block only while retry budget remains, then degrade
            # gracefully: ship with a low-confidence badge rather than hard-failing the lesson.
            blocking = list(grounding["failed"])
            if soft and will_retry:
                blocking.append(f"{len(soft)} unsupported claim/answer(s)")
            grounding["low_confidence"] = bool(soft) and not grounding["failed"]
            if blocking:
                checks["failed"] = [*checks.get("failed", []), *[f"grounding: {b}" for b in blocking]]
                checks["passed"] = not checks["failed"]
                out["grounding_repair"] = build_repair_brief(grounding)
    return out


def _after_post(state: GenState) -> str:
    if state["checks"]["passed"]:
        return "persist"
    if state.get("attempts", 0) >= get_settings().max_gen_retries:
        return "persist"  # ship best-effort; persist records the failed checks
    return "generate"


def _require_teacher_review(state: GenState) -> bool:
    knobs = state.get("knobs") or {}
    return bool(knobs.get("require_teacher_review"))


async def persist(state: GenState) -> GenState | Command:
    cid = state["course_id"]
    lid = state["lesson_id"]
    plan = state["plan"]
    checks = state.get("checks", {})

    # Teacher HITL: pause after successful checks; durable checkpointer holds the interrupt.
    # Side effects before interrupt() re-run on resume — keep them idempotent.
    if _require_teacher_review(state) and checks.get("passed"):
        with SessionLocal() as db:
            lesson = db.get(Lesson, lid)
            if lesson and lesson.status != "awaiting_review":
                lesson.status = "awaiting_review"
                lesson.error = None
                db.commit()
        await _emit(
            cid,
            "awaiting_review",
            f"Lesson '{plan.get('title', lid)}' is ready for teacher review.",
            95,
        )
        decision = interrupt(
            {
                "course_id": cid,
                "lesson_id": lid,
                "title": plan.get("title"),
                "checks_passed": True,
            }
        )
        if not isinstance(decision, dict):
            decision = {"action": "approve"}
        action = str(decision.get("action") or "approve").lower()
        if action == "reject":
            msg = (decision.get("message") or "").strip() or "Teacher rejected; revise the lesson."
            with SessionLocal() as db:
                lesson = db.get(Lesson, lid)
                if lesson:
                    lesson.status = "generating"
                    lesson.error = None
                    db.commit()
            await _emit(cid, "generating", "Teacher requested changes — regenerating…", 40)
            return Command(
                goto="generate",
                update={
                    "grounding_repair": msg,
                    "review_decision": decision,
                },
            )

    # fast_gen §2.2: v1 may ship while the background mesh is still rendering — flag the
    # artifact so the viewer listens for the mesh_ready upgrade, then authorize the job
    # to late-join a re-rendered studio version once the mesh lands.
    mesh_late = False
    if get_settings().gen_async_assets:
        from . import assets

        # Only studio artifacts can late-join (deterministic re-render); a slow mesh on
        # any other design just warms the cache, so don't make the viewer listen.
        if assets.awaiting_join(lid) and checks.get("presentation") == "studio":
            mesh_late = True
            checks = {**checks, "mesh_pending": True}

    status = await persist_artifact(
        course_id=cid,
        lesson_id=lid,
        plan=plan,
        checks=checks,
        html=state.get("html") or "",
        kind=state.get("artifact_kind") or "html",
        a2ui_doc=state.get("a2ui"),
        compute_artifact=state.get("compute_artifact") or plan.get("compute_artifact"),
        mesh_artifact=state.get("mesh_artifact") or plan.get("mesh_artifact"),
        mesh_catalog=plan.get("mesh_catalog") or plan.get("studio_subjects"),
        citations=state.get("citations", []),
        source_document_id=state.get("source_document_id"),
        source_pack_chunk_ids=state.get("source_pack_chunk_ids", []),
        chapter_ids=list(state.get("chapter_ids") or []),
        source_query=state.get("source_query", ""),
    )
    if status == "missing":
        return {"status": "failed", "error": "course or lesson missing"}
    if mesh_late and status == "ready" and checks.get("presentation") == "studio":
        from . import assets

        assets.enable_late_join(lid, course_id=cid, plan=plan, knobs=state.get("knobs") or {})
    return {"status": status}


async def persist_artifact(
    *,
    course_id: str,
    lesson_id: str,
    plan: dict,
    checks: dict,
    html: str = "",
    kind: str = "html",
    a2ui_doc: dict | None = None,
    compute_artifact: dict | None = None,
    mesh_artifact: dict | None = None,
    mesh_catalog: list[dict] | None = None,
    citations: list[dict] | None = None,
    source_document_id: str | None = None,
    source_pack_chunk_ids: list | None = None,
    chapter_ids: list | None = None,
    source_query: str = "",
) -> str:
    """Inline compute/mesh assets into HTML, write the versioned Artifact (+ citations and
    source pack), update lesson/course status, and emit the terminal SSE.

    Shared by `persist` (LangGraph node) and the Deep Agent lesson path so both write
    through one code path. Returns "ready" | "failed" | "missing" (course/lesson row gone).
    """
    citations = citations or []
    # `a2ui_doc` carries any trusted doc kind (A2UI tree or ReadingDoc).
    a2ui_doc = a2ui_doc if kind in ("a2ui", "reading") else None
    # Inline ephemeral compute plots as data: URLs before writing the durable artifact.
    if kind not in ("a2ui", "reading"):
        if compute_artifact:
            try:
                from .compute import ComputeArtifact, inline_compute_assets_in_html

                art = ComputeArtifact.model_validate(compute_artifact)
                html = inline_compute_assets_in_html(html, art)
            except Exception:  # noqa: BLE001 — never block persist
                pass
        if mesh_artifact:
            try:
                from .mesh import MeshArtifact, inline_mesh_urls_in_html, persist_mesh_bytes_async

                mesh = MeshArtifact.model_validate(mesh_artifact)
                if mesh.data_b64 and not mesh.cache_key:
                    import base64

                    mesh.cache_key = await persist_mesh_bytes_async(
                        base64.b64decode(mesh.data_b64)
                    )
                elif mesh.cache_key:
                    # Mirror already-cached local GLBs to InsForge storage. `/mesh?key=`
                    # serves the local cache first, so the mirror is durability-only —
                    # fast_gen Phase 1 moves the upload off the persist critical path.
                    from ..core.tasks import spawn
                    from ..providers.mesh import read_mesh_cache, sync_mesh_to_storage

                    cached = read_mesh_cache(mesh.cache_key)
                    if cached:
                        spawn(
                            sync_mesh_to_storage(mesh.cache_key, cached),
                            name=f"mesh-sync:{mesh.cache_key[:8]}",
                        )
                html = inline_mesh_urls_in_html(html, mesh)
            except Exception:  # noqa: BLE001 — never block persist
                pass
        if mesh_catalog:
            try:
                from .mesh import inline_mesh_catalog_in_html

                html = inline_mesh_catalog_in_html(html, mesh_catalog)
            except Exception:  # noqa: BLE001
                pass
    status = "ready" if checks.get("passed") else "failed"

    with SessionLocal() as db:
        course = db.get(Course, course_id)
        lesson = db.get(Lesson, lesson_id)
        if course is None or lesson is None:
            return "missing"

        lesson.status = status
        lesson.error = None if status == "ready" else "; ".join(checks.get("failed", []))

        if not course.title:
            course.title = plan["title"]
        if not course.cover_prompt:
            course.cover_prompt = plan.get("cover_prompt")
        if not course.tagline:
            course.tagline = plan.get("subtitle")

        # Course becomes ready when the very first lesson is built successfully
        if lesson.ordinal == 0:
            video_sync = bool((course.knobs or {}).get("video_sync"))
            course.status = "ready" if video_sync else status
            course.error = (
                None
                if video_sync or status == "ready"
                else f"First lesson failed: {lesson.error}"
            )
            if status == "ready":
                course.title = course.title or plan["title"]
                course.archetype = plan["archetype"]
                course.cover_prompt = course.cover_prompt or plan.get("cover_prompt")
                course.tagline = course.tagline or plan.get("subtitle")

        latest = db.scalars(
            select(Artifact)
            .where(Artifact.lesson_id == lesson_id)
            .order_by(Artifact.version.desc())
            .limit(1)
        ).first()
        version = (latest.version + 1) if latest else 1

        db.add(
            Artifact(
                lesson_id=lesson_id,
                version=version,
                kind=kind if kind in ("html", "a2ui", "reading") else "html",
                html=html if kind not in ("a2ui", "reading") else "",
                a2ui=a2ui_doc,
                checks=checks,
            )
        )
        for c in citations:
            db.add(Citation(course_id=course_id, claim=c["claim"], source_url=c["source_url"]))
        # Document-grounded: record the lesson's source pack for the viewer drawer (task 27, R7.6).
        if source_document_id:
            db.add(
                LessonSourcePack(
                    lesson_id=lesson_id,
                    source_document_id=source_document_id,
                    chunk_ids=source_pack_chunk_ids or [],
                    chapter_ids=list(chapter_ids or []),
                    passage_ids=[],
                    retrieval_query=source_query or "",
                    citations=citations,
                )
            )
        db.commit()

    await _emit(
        course_id,
        status,
        f"Lesson '{plan['title']}' is ready!"
        if status == "ready"
        else f"Generation failed for lesson '{plan['title']}'.",
        100,
    )
    return status


async def build_graph():
    """Compile the generation graph with a durable checkpointer (required for HITL)."""
    checkpointer = await get_checkpointer()
    g = StateGraph(GenState)
    g.add_node("interpret", interpret)
    g.add_node("research", research)
    g.add_node("asset_plan", asset_plan)
    g.add_node("generate", generate)
    g.add_node("post_process", post_process)
    g.add_node("persist", persist)

    g.add_edge(START, "interpret")
    g.add_edge("interpret", "research")
    g.add_edge("research", "asset_plan")
    g.add_edge("asset_plan", "generate")
    g.add_edge("generate", "post_process")
    g.add_conditional_edges("post_process", _after_post, {"generate": "generate", "persist": "persist"})
    g.add_edge("persist", END)
    return g.compile(checkpointer=checkpointer)


_GRAPH = None


async def get_graph():
    """Compiled graph bound to the current event loop's checkpointer."""
    global _GRAPH
    # Always rebuild when the checkpointer/loop may have changed (tests use asyncio.run).
    from .checkpoint import get_checkpointer

    cp = await get_checkpointer()
    if _GRAPH is None or getattr(_GRAPH, "_hituto_cp_id", None) != id(cp):
        _GRAPH = await build_graph()
        _GRAPH._hituto_cp_id = id(cp)  # type: ignore[attr-defined]
    return _GRAPH


def reset_graph_for_tests() -> None:
    """Drop compiled graph so the next run picks up a fresh checkpointer."""
    global _GRAPH
    _GRAPH = None


def _run_config(course_id: str, lesson_id: str) -> dict:
    cfg = agent_run_config(
        "coursegen",
        run_name="lesson_generation",
        extra_tags=["generation"],
        course_id=course_id,
        lesson_id=lesson_id,
    )
    cfg["configurable"] = {"thread_id": generation_thread_id(lesson_id)}
    cfg["durability"] = "sync"
    return cfg


async def run_generation(
    course_id: str,
    lesson_id: str,
    topic: str,
    knobs: dict,
    refinement: str | None = None,
    target_id: str | None = None,
    target_html: str | None = None,
) -> None:
    """Entry point invoked to generate/regenerate a single lesson."""
    try:
        graph = await get_graph()
        prompt = topic if not refinement else f"{topic}\n\nChange request: {refinement}"
        previous_html = None
        if refinement:
            with SessionLocal() as db:
                latest = db.scalars(
                    select(Artifact)
                    .where(Artifact.lesson_id == lesson_id)
                    .order_by(Artifact.version.desc())
                    .limit(1)
                ).first()
                if latest:
                    previous_html = latest.html
        await graph.ainvoke(
            {
                "course_id": course_id,
                "lesson_id": lesson_id,
                "topic": prompt,
                "knobs": knobs,
                "previous_html": previous_html,
                "target_id": target_id,
                "target_html": target_html,
            },
            config=_run_config(course_id, lesson_id),
        )
    except Exception as e:
        with SessionLocal() as db:
            course = db.get(Course, course_id)
            lesson = db.get(Lesson, lesson_id)
            if lesson and lesson.status != "awaiting_review":
                lesson.status = "failed"
                lesson.error = str(e)
            if (
                course
                and lesson
                and lesson.ordinal == 0
                and lesson.status != "awaiting_review"
            ):
                video_sync = bool((course.knobs or {}).get("video_sync"))
                course.status = "ready" if video_sync else "failed"
                course.error = None if video_sync else str(e)
            db.commit()
        # Interrupt surfaces as a normal return with __interrupt__; real failures only here.
        if "Interrupt" not in type(e).__name__:
            await broker.publish(course_id, ProgressEvent(stage="failed", detail=str(e), pct=100))


async def resume_generation(
    course_id: str,
    lesson_id: str,
    *,
    action: str,
    message: str | None = None,
) -> None:
    """Resume a graph paused at teacher review (`approve` | `reject`)."""
    graph = await get_graph()
    decision = {"action": action, "message": message or ""}
    await graph.ainvoke(
        Command(resume=decision),
        config=_run_config(course_id, lesson_id),
    )


def recover_orphaned_generations() -> int:
    """Reset rows stranded in 'generating' by a previous process.

    Generation runs as in-memory asyncio tasks (fired via asyncio.create_task). A
    process restart — e.g. uvicorn --reload on a file save, or a crash — kills any
    in-flight job while its DB row stays 'generating' forever (no error, no artifact),
    so the lesson shows "In Queue" indefinitely. On startup we requeue these so they
    become actionable again.

    `awaiting_review` is a legitimate long-lived state (HITL) and must NOT be requeued —
    the durable checkpointer still holds the interrupt for POST …/review.
    """
    with SessionLocal() as db:
        lessons = db.scalars(select(Lesson).where(Lesson.status == "generating")).all()
        for lesson in lessons:
            lesson.status = "pending"
            lesson.error = None
        # Explicitly leave awaiting_review untouched (design §9.1). Courses in
        # outline_review are likewise long-lived HITL state (course-authoring-flow §3):
        # the outline draft is in the DB, so a restart loses nothing — never requeue them.
        courses = db.scalars(select(Course).where(Course.status == "generating")).all()
        for course in courses:
            # With at least one lesson the roadmap is navigable; otherwise syllabus
            # planning itself was interrupted before any lesson row was created.
            if course.lessons:
                course.status = "ready"
            else:
                course.status = "failed"
                course.error = "Roadmap planning was interrupted — recreate the course."
        db.commit()
        return len(lessons)


async def run_syllabus_planning(course_id: str, topic: str, knobs: dict) -> None:
    """Generates the multi-lesson syllabus outline in the background."""
    from ..core.tracing import traceable_run

    @traceable_run(
        "syllabus_planning",
        tags=["agent:coursegen", "coursegen", "syllabus"],
        metadata={"agent": "coursegen", "course_id": course_id},
    )
    async def _run() -> None:
        await _emit(course_id, "planning", "Designing your course outline and roadmap…", 5)
        try:
            from .agents.syllabus_planner import plan_free_topic_syllabus

            plan = await plan_free_topic_syllabus(topic, knobs)

            from ..services.billing_plans import MAX_LESSONS_PER_COURSE_CREDIT

            try:
                cap = int((knobs or {}).get("max_lessons") or MAX_LESSONS_PER_COURSE_CREDIT)
            except (TypeError, ValueError):
                cap = MAX_LESSONS_PER_COURSE_CREDIT
            cap = max(1, min(MAX_LESSONS_PER_COURSE_CREDIT, cap))
            if isinstance(plan.get("lessons"), list):
                plan["lessons"] = plan["lessons"][:cap]

            # Outline HITL: park the plan for teacher review instead of creating lessons.
            if (knobs or {}).get("review_outline"):
                from ..services.outline_service import draft_outline

                with SessionLocal() as db:
                    course = db.get(Course, course_id)
                    if course is None:
                        raise ValueError("Course not found")
                    draft_outline(db, course, plan)
                await _emit(
                    course_id, "outline_review", "Outline drafted — review the chapters to continue.", 10
                )
                return

            first_lesson_id = None
            with SessionLocal() as db:
                course = db.get(Course, course_id)
                if course is None:
                    raise ValueError("Course not found")

                course.title = plan["title"]
                course.cover_prompt = plan.get("cover_prompt") or (
                    f"hyperreal abstract illustration representing {plan['title']}, "
                    "dark cinematic background"
                )
                course.tagline = plan.get("subtitle")
                course.status = "generating"

                for idx, les in enumerate(plan["lessons"]):
                    lesson = Lesson(
                        course_id=course_id,
                        ordinal=idx,
                        title=les["title"],
                        objective=les["objective"],
                        archetype=les["archetype"],
                        estimated_duration=les.get("estimated_duration", "5m"),
                        status="pending",
                    )
                    db.add(lesson)
                db.commit()

                first_lesson = db.scalars(
                    select(Lesson)
                    .where(Lesson.course_id == course_id, Lesson.ordinal == 0)
                    .limit(1)
                ).first()
                if first_lesson:
                    first_lesson_id = first_lesson.id

            await _emit(course_id, "planning", "Roadmap planned! Starting first lesson generation…", 15)
            if first_lesson_id:
                await run_generation(course_id, first_lesson_id, topic, knobs)
        except Exception as e:
            with SessionLocal() as db:
                course = db.get(Course, course_id)
                if course:
                    course.status = "failed"
                    course.error = f"Syllabus generation failed: {e}"
                    db.commit()
                    from ..services import billing_service

                    billing_service.refund_course_credit(db, course_id)
            await _emit(course_id, "failed", f"Syllabus failed: {e}", 100)

    await _run()
