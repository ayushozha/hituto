"""fast_gen Phase 3 (GEN_ASYNC_ASSETS): background mesh generation with late-join.

`asset_plan` spawns a mesh job instead of awaiting the (up to minutes-long) Hunyuan
poll; the pipeline proceeds and v1 ships with the studio procedural fallback.

Join points, in preference order:

1. `take_ready()` at `generate` — cached/fast meshes land in v1 exactly as the
   synchronous path would have produced.
2. Late-join after persist (studio lessons only): once the mesh lands, the job
   deterministically re-renders the studio manifest with the mesh catalog, passes
   the capsule gate, writes a **new artifact version** (never overwrites), and emits
   a `mesh_ready` progress frame so the open viewer can upgrade in place. Studio
   re-rendering is template work — no LLM — which is what makes this safe.

Non-studio lessons have no manifest to re-render, so a slow mesh only warms the
content-addressed cache for future regenerations.

Registry state lives in-process, like the SSE broker — consistent with the
one-process deployment model (`core/progress.py`).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..core.db import SessionLocal
from ..core.progress import ProgressEvent, broker
from ..core.tasks import spawn
from ..models import Artifact

logger = logging.getLogger(__name__)

_LATE_JOIN_WAIT_S = 300.0  # after the mesh lands, wait up to 5 min for persist's ctx
_POLL_S = 2.0

MeshResult = tuple[Any, Any]  # (MeshArtifact | None, mesh_catalog list | None)


@dataclass
class _MeshJob:
    task: asyncio.Task | None = None
    result: MeshResult | None = None
    done: bool = False
    merged: bool = False  # result consumed (by generate) or late-joined
    late_ctx: dict | None = None  # {course_id, plan, knobs} set by persist


_jobs: dict[str, _MeshJob] = {}


def start_mesh_job(
    *,
    course_id: str,
    lesson_id: str,
    concept: str,
    archetype: str,
    knobs: dict | None,
    specialist_name: str | None,
    topic: str | None,
) -> None:
    """Kick off mesh generation in the background for this lesson (replaces any prior job)."""
    job = _MeshJob()
    _jobs[lesson_id] = job
    job.task = spawn(
        _run(
            job,
            course_id=course_id,
            lesson_id=lesson_id,
            concept=concept,
            archetype=archetype,
            knobs=dict(knobs or {}),
            specialist_name=specialist_name,
            topic=topic,
        ),
        name=f"mesh-job:{lesson_id}",
    )


def _has_mesh(result: MeshResult | None) -> bool:
    return bool(result) and (result[0] is not None or bool(result[1]))


def take_ready(lesson_id: str) -> MeshResult | None:
    """(mesh, catalog) if the job finished with a mesh and nobody consumed it yet."""
    job = _jobs.get(lesson_id)
    if not job or not job.done or job.merged or not _has_mesh(job.result):
        return None
    job.merged = True
    return job.result


def awaiting_join(lesson_id: str) -> bool:
    """True while an unconsumed mesh is still coming (or landed but wasn't merged)."""
    job = _jobs.get(lesson_id)
    if not job or job.merged:
        return False
    return not job.done or _has_mesh(job.result)


def enable_late_join(lesson_id: str, *, course_id: str, plan: dict, knobs: dict) -> None:
    """Called by persist when v1 shipped without the mesh: authorizes the job to
    re-render the studio artifact and persist an upgraded version when the mesh lands."""
    job = _jobs.get(lesson_id)
    if job and not job.merged:
        job.late_ctx = {
            "course_id": course_id,
            "plan": dict(plan or {}),
            "knobs": dict(knobs or {}),
        }


async def _run(
    job: _MeshJob,
    *,
    course_id: str,
    lesson_id: str,
    concept: str,
    archetype: str,
    knobs: dict,
    specialist_name: str | None,
    topic: str | None,
) -> None:
    try:
        from .agents.roles import run_mesh_stage

        job.result = await run_mesh_stage(
            concept=concept,
            archetype=archetype,
            knobs=knobs,
            specialist_name=specialist_name,
            topic=topic,
        )
        job.done = True
        if not _has_mesh(job.result) or job.merged:
            return
        # Wait for the pipeline to either consume the result (generate) or authorize
        # a late-join (persist). A crashed pipeline sets neither → time out quietly.
        for _ in range(int(_LATE_JOIN_WAIT_S / _POLL_S)):
            if job.merged:
                return
            if job.late_ctx:
                await _late_join(job, lesson_id)
                return
            await asyncio.sleep(_POLL_S)
        logger.info("mesh job for %s finished but no artifact joined it", lesson_id)
    except Exception:  # noqa: BLE001 — assets never take a lesson down
        logger.exception("mesh job failed for lesson %s", lesson_id)
    finally:
        if _jobs.get(lesson_id) is job:
            del _jobs[lesson_id]


async def _late_join(job: _MeshJob, lesson_id: str) -> None:
    """Deterministically re-render the studio artifact with the finished mesh.

    Template work only (build_studio_manifest → render_studio_manifest), then the full
    capsule gate — same trust path as the synchronous flow, no LLM involved.
    """
    from ..capsule.postprocess import postprocess
    from .mesh import MeshArtifact, inline_mesh_catalog_in_html, inline_mesh_urls_in_html
    from .studio_manifest import build_studio_manifest
    from .studio_renderer import render_studio_manifest

    job.merged = True
    ctx = job.late_ctx or {}
    course_id = str(ctx.get("course_id") or "")
    plan = dict(ctx.get("plan") or {})
    knobs = dict(ctx.get("knobs") or {})
    mesh_art, catalog = job.result or (None, None)

    plan.pop("mesh_fallback", None)
    mesh_meta = None
    if mesh_art is not None:
        mesh_meta = mesh_art.model_dump(exclude={"data_b64"})
        plan["mesh_artifact"] = mesh_meta
        plan["mesh_url"] = mesh_art.path
    if catalog:
        plan["mesh_catalog"] = catalog
        plan["studio_subjects"] = catalog

    manifest = build_studio_manifest(plan, knobs)
    html = render_studio_manifest(manifest)
    html, checks = postprocess(html)
    if not checks.get("passed"):
        logger.warning(
            "mesh late-join for %s failed the capsule gate: %s",
            lesson_id,
            checks.get("failed"),
        )
        return
    checks.update(
        {
            "presentation": "studio",
            "studio_mode": manifest.mode,
            "studio_manifest_version": manifest.model_dump().get("schema_version", "2.0"),
            "mesh_late_join": True,
        }
    )
    if mesh_meta:
        html = inline_mesh_urls_in_html(html, MeshArtifact.model_validate(mesh_meta))
    if catalog:
        html = inline_mesh_catalog_in_html(html, catalog)

    with SessionLocal() as db:
        if mesh_meta and course_id:
            try:
                from ..services import billing_service
                from ..models import Course as CourseModel

                course = db.get(CourseModel, course_id)
                if course is not None:
                    billing_service.spend_lab_credit(
                        db, course.user_id, course_id=course.id
                    )
            except Exception:  # noqa: BLE001
                logger.exception("billing: failed to record lab credit on late-join")
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
                kind="html",
                html=html,
                a2ui=None,
                checks=checks,
            )
        )
        db.commit()

    await broker.publish(
        course_id,
        ProgressEvent(
            stage="mesh_ready",
            detail="3D model ready — lesson upgraded.",
            pct=100,
            data={"lesson_id": lesson_id, "version": version},
        ),
    )
