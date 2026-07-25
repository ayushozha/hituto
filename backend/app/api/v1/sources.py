"""Sources API (tasks.md #5, #6): upload + list/get/delete + outline + course creation.

Thin handlers: request validation, ownership/404, and status codes here; ingestion and
projections live in `app.rag`; course planning/creation in `source_service`.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.auth import AuthPrincipal, get_current_principal, get_current_user_id, get_user_id_from_request
from ...core.config import get_settings
from ...core.db import get_db
from ...models import SourceDocument
from ...providers import storage
from ...rag.ingest import save_and_ingest
from ...rag.service import course_detail, course_ref, source_detail, source_out, source_outline
from ...schemas import (
    CourseDetail,
    CreateSourceCourse,
    CreateVideoLinkSource,
    SourceDetail,
    SourceOut,
    SourceOutline,
)
from ...services import source_service, video_source_service

router = APIRouter(prefix="/sources", tags=["sources"])

logger = logging.getLogger(__name__)

_ALLOWED_MIME = {"application/pdf", "text/plain", "text/markdown", "application/octet-stream"}
_ALLOWED_EXT = {".pdf", ".txt", ".md", ".markdown"}
_ALLOWED_VIDEO_MIME = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
}
_ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v", ".mp3", ".m4a", ".wav"}
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _owned_source(db: Session, source_id: str, user_id: str) -> SourceDocument:
    d = db.get(SourceDocument, source_id)
    if not d or d.user_id != user_id:
        raise HTTPException(status_code=404, detail="source not found")
    return d


async def _stage_bounded_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    directory: Path,
) -> tuple[Path, int]:
    """Copy an upload to disk in bounded chunks, rejecting it before memory can grow."""
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower() or ".bin"
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix="video-upload-",
        suffix=suffix,
        dir=directory,
        delete=False,
    )
    path = Path(handle.name)
    size = 0
    try:
        with handle:
            while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"video exceeds {max_bytes // (1024 * 1024)} MB limit",
                    )
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="empty video")
        return path, size
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.post("/upload", response_model=SourceOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    s = get_settings()
    if not s.doc_grounded_enabled:
        raise HTTPException(status_code=403, detail="document-grounded courses are disabled")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if file.content_type not in _ALLOWED_MIME and ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"unsupported file type: {file.content_type or ext}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"file exceeds {s.max_upload_mb} MB limit")

    doc = await save_and_ingest(
        db, user_id=user_id, filename=file.filename, content_type=file.content_type, ext=ext, data=data
    )
    return source_out(doc)


@router.post("/video/upload", status_code=410)
async def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Deprecated: video courses are created from public links only."""
    del file, db, user_id
    raise HTTPException(
        status_code=410,
        detail="video file upload is no longer supported; use /sources/video/link with a public URL",
    )


@router.post("/video/link", response_model=SourceOut, status_code=201)
async def link_video(
    body: CreateVideoLinkSource,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    settings = get_settings()
    if not settings.video_grounded_enabled:
        raise HTTPException(status_code=403, detail="video-grounded courses are disabled")
    try:
        doc = await video_source_service.save_video_link_source(
            db,
            user_id=user_id,
            url=str(body.url),
            title=body.title,
            provided_transcript=body.transcript,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return source_out(doc)


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    rows = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.user_id == user_id)
        .order_by(SourceDocument.created_at.desc())
    ).all()
    return [source_out(d) for d in rows]


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return source_detail(_owned_source(db, source_id, user_id))


async def _delete_parse_artifacts(sm: dict) -> None:
    """Best-effort delete of versioned parse tree (md, manifest, figures, chapters)."""
    from pathlib import Path

    from ...providers import storage

    parse = sm.get("parse") or {}
    keys: list[str] = []
    for k in ("document_md_key", "manifest_key"):
        if parse.get(k):
            keys.append(str(parse[k]))
    for fig in parse.get("figures") or []:
        if fig.get("storage_key"):
            keys.append(str(fig["storage_key"]))
    tm = sm.get("teaching_map") or {}
    for ch in tm.get("chapters") or []:
        if ch.get("md_key"):
            keys.append(str(ch["md_key"]))
    video = sm.get("video") or {}
    for key in ("transcript_storage_key", "transcript_stored_path"):
        if video.get(key):
            keys.append(str(video[key]))

    bucket = sm.get("storage_bucket")
    for key in keys:
        p = Path(key)
        if p.exists():
            try:
                p.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Local parse artifact delete failed for %s: %s", key, exc)
            continue
        if storage.is_configured():
            try:
                await storage.delete(key, bucket=bucket)
            except Exception as exc:
                logger.warning("Storage parse artifact delete failed for %s: %s", key, exc)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    d = _owned_source(db, source_id, user_id)
    sm = d.source_map or {}
    storage_key = sm.get("storage_key")
    if storage_key:
        try:
            from ...providers import storage

            await storage.delete(storage_key, bucket=sm.get("storage_bucket"))
        except Exception as exc:
            logger.warning("Storage delete failed for %s: %s", storage_key, exc)
    stored = sm.get("stored_path")
    if stored:
        try:
            from pathlib import Path

            Path(stored).unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Local file delete failed for %s: %s", stored, exc)
    await _delete_parse_artifacts(sm)
    db.delete(d)
    db.commit()


def _requested_range(value: str | None, total: int) -> tuple[int, int] | None:
    if not value or total <= 0:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match:
        return None
    raw_start, raw_end = match.groups()
    if not raw_start and not raw_end:
        return None
    if not raw_start:
        requested = int(raw_end)
        if requested <= 0:
            return None
        length = min(total, requested)
        return total - length, total - 1
    start = int(raw_start)
    if start >= total:
        return None
    end = min(int(raw_end), total - 1) if raw_end else total - 1
    return (start, max(start, end))


@router.get("/{source_id}/media")
async def get_source_media(
    source_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Stream private uploaded training media, including browser byte-range requests."""
    user_id = get_user_id_from_request(request)
    doc = _owned_source(db, source_id, user_id)
    if doc.source_type != "video":
        raise HTTPException(status_code=404, detail="video source not found")
    source_map = doc.source_map or {}
    video = source_map.get("video") or {}
    local_path = video.get("media_stored_path") or source_map.get("stored_path")
    if local_path and Path(str(local_path)).exists():
        return FileResponse(
            str(local_path),
            media_type=video.get("content_type") or doc.mime_type,
            filename=doc.filename,
            content_disposition_type="inline",
        )

    storage_key = video.get("media_storage_key") or source_map.get("storage_key")
    if not storage_key:
        raise HTTPException(status_code=404, detail="stored video is unavailable")
    try:
        stream = await storage.open_download_stream(
            str(storage_key),
            bucket=source_map.get("storage_bucket"),
            range_header=request.headers.get("range"),
        )
    except Exception as exc:
        logger.warning("Video read failed for %s: %s", source_id, exc)
        raise HTTPException(status_code=404, detail="stored video is unavailable") from exc

    headers = {"Accept-Ranges": stream.headers.get("accept-ranges", "bytes")}
    for name in ("content-length", "content-range", "etag", "last-modified"):
        if value := stream.headers.get(name):
            headers[name.title()] = value

    async def body():
        try:
            async for chunk in stream.iter_bytes():
                yield chunk
        finally:
            await stream.aclose()

    return StreamingResponse(
        body(),
        status_code=stream.status_code,
        media_type=stream.headers.get("content-type") or doc.mime_type,
        headers=headers,
    )


@router.get("/{source_id}/figures/{image_id}")
async def get_source_figure(
    source_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Authenticated figure bytes for a parse-time source image (owner only)."""
    from pathlib import Path

    from fastapi.responses import Response

    from ...providers import storage

    d = _owned_source(db, source_id, user_id)
    figures = ((d.source_map or {}).get("parse") or {}).get("figures") or []
    match = next(
        (
            f
            for f in figures
            if f.get("image_id") == image_id
            or f.get("md_ref") == image_id
            or str(f.get("md_ref") or "").startswith(image_id)
        ),
        None,
    )
    if not match or not match.get("storage_key"):
        raise HTTPException(status_code=404, detail="figure not found")
    key = str(match["storage_key"])
    p = Path(key)
    try:
        data = p.read_bytes() if p.exists() else await storage.download(key)
    except Exception as exc:
        logger.warning("Figure read failed for %s: %s", key, exc)
        raise HTTPException(status_code=404, detail="figure not found") from exc
    fmt = (match.get("format") or "png").lstrip(".")
    media = f"image/{fmt}" if fmt != "jpg" else "image/jpeg"
    return Response(content=data, media_type=media)


@router.get("/{source_id}/outline", response_model=SourceOutline)
def get_source_outline(
    source_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return source_outline(_owned_source(db, source_id, user_id))


@router.post("/{source_id}/courses", response_model=CourseDetail, status_code=201)
async def create_course_from_source(
    source_id: str,
    body: CreateSourceCourse,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    d = _owned_source(db, source_id, principal.user_id)
    if d.status != "ready":
        raise HTTPException(status_code=409, detail=f"source not ready (status={d.status})")
    try:
        course = await source_service.create_course_from_source(
            db, d, body, plan_slug=principal.plan_slug
        )
    except ValueError as e:
        msg = str(e)
        if "course credit" in msg.lower():
            raise HTTPException(status_code=402, detail=msg) from e
        raise HTTPException(status_code=422, detail=f"cannot sequence course: {e}") from e
    detail = course_detail(course)
    detail.source = course_ref(d)
    return detail