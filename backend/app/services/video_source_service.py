"""Video-source ingestion and synchronized learning-guide orchestration."""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..core.tasks import spawn
from ..coursegen.video_checkpoints import plan_video_checkpoints
from ..models import SourceDocument
from ..providers import storage
from ..providers.transcription import (
    TranscriptSegment,
    parse_timed_transcript,
    transcribe_recorded_media,
    transcribe_recorded_url,
)
from ..rag.ingest import run_source_ingestion

VIDEO_INGEST_STATUSES = (
    "uploaded",
    "transcribing",
    "checkpointing",
    "parsing",
    "outlining",
    "mapping",
    "chunking",
    "indexing",
)

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _upload_dir() -> Path:
    directory = Path(get_settings().upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _video_locator(doc: SourceDocument) -> str | None:
    source_map = doc.source_map or {}
    video = source_map.get("video") or {}
    return (
        video.get("media_storage_key")
        or video.get("media_stored_path")
        or source_map.get("storage_key")
        or source_map.get("stored_path")
    )


def _transcript_locator(doc: SourceDocument) -> str | None:
    video = (doc.source_map or {}).get("video") or {}
    return video.get("transcript_storage_key") or video.get("transcript_stored_path")


async def _read_media(locator: str, *, bucket: str | None = None) -> bytes:
    path = Path(locator)
    if path.exists():
        return path.read_bytes()
    return await storage.download(locator, bucket=bucket)


def _video_title(filename: str) -> str:
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return (title or "Training video")[:160]


def video_link_details(url: str) -> tuple[str, str | None]:
    """Return playback kind and provider id for a supported public link."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("video link must be a public http or https URL")
    host = parsed.netloc.lower().split(":", 1)[0]
    host = host.removeprefix("www.").removeprefix("m.")
    video_id: str | None = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "youtube-nocookie.com"}:
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
                video_id = parts[1]
    if host in {"youtu.be", "youtube.com", "youtube-nocookie.com"}:
        if not video_id or not _YOUTUBE_ID_RE.fullmatch(video_id):
            raise ValueError("could not find a valid YouTube video id in this link")
        return "youtube", video_id
    return "native", None


def _transcript_markdown(title: str, segments: list[TranscriptSegment]) -> str:
    lines = [f"# {title}", ""]
    current_bucket = -1
    for segment in segments:
        bucket = int(segment.start // 240)
        if bucket != current_bucket:
            start = bucket * 240
            end = start + 240
            lines.extend(
                [
                    f"## Transcript {_clock(start)}-{_clock(end)}",
                    "",
                ]
            )
            current_bucket = bucket
        lines.append(f"**[{_clock(segment.start)}]** {segment.text.strip()}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _clock(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _stored_segments(video: dict) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for raw in video.get("segments") or []:
        try:
            text = str(raw.get("text") or "").strip()
            if text:
                segments.append(
                    TranscriptSegment(
                        start=max(0.0, float(raw.get("start") or 0)),
                        end=max(0.0, float(raw.get("end") or 0)),
                        text=text,
                    )
                )
        except (AttributeError, TypeError, ValueError):
            continue
    return segments


async def _store_transcript(doc: SourceDocument, markdown: str) -> tuple[str, dict]:
    data = markdown.encode("utf-8")
    local_path = _upload_dir() / "video-transcripts" / f"{doc.id}.md"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)
    video_update: dict = {"transcript_stored_path": str(local_path)}
    locator = str(local_path)
    if storage.is_configured():
        key = f"sources/{doc.id}/video/transcript.md"
        try:
            result = await storage.upload(key, data, "text/markdown")
            locator = result.get("key", key)
            video_update["transcript_storage_key"] = locator
        except Exception as exc:  # noqa: BLE001 - durable local fallback
            video_update["transcript_storage_error"] = str(exc)
    return locator, video_update


async def save_video_source(
    db: Session,
    *,
    user_id: str,
    filename: str | None,
    content_type: str | None,
    ext: str,
    staged_path: Path,
    size_bytes: int,
) -> SourceDocument:
    doc = SourceDocument(
        user_id=user_id,
        filename=filename or "training-video",
        mime_type=content_type or "application/octet-stream",
        source_type="video",
        status="uploaded",
        title=_video_title(filename or "training-video"),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    source_map: dict = {}
    video: dict = {
        "ingest_kind": "upload",
        "content_type": doc.mime_type,
        "size_bytes": size_bytes,
        "original_filename": doc.filename,
    }
    locator: str | None = None
    if storage.is_configured():
        key = f"sources/{doc.id}/video/original{ext or '.bin'}"
        try:
            result = await storage.upload_file(key, staged_path, doc.mime_type)
            locator = result.get("key", key)
            source_map["storage_key"] = locator
            source_map["storage_bucket"] = get_settings().storage_bucket
            video["media_storage_key"] = locator
            video["media_storage_url"] = result.get("url")
        except Exception as exc:  # noqa: BLE001 - local fallback keeps upload usable
            video["media_storage_error"] = str(exc)

    if locator is None:
        path = _upload_dir() / f"{doc.id}{ext or '.bin'}"
        staged_path.replace(path)
        locator = str(path)
        source_map["stored_path"] = locator
        video["media_stored_path"] = locator

    source_map["video"] = video
    doc.source_map = source_map
    db.commit()
    spawn(run_video_ingestion(doc.id), name=f"video-ingest:{doc.id}")
    return doc


async def save_video_link_source(
    db: Session,
    *,
    user_id: str,
    url: str,
    title: str | None,
    provided_transcript: str | None,
) -> SourceDocument:
    playback_kind, youtube_video_id = video_link_details(url)
    transcript = (provided_transcript or "").strip()
    if playback_kind == "youtube" and not transcript:
        raise ValueError(
            "YouTube links need timed captions. Paste the video's transcript with timestamps."
        )
    if transcript:
        parse_timed_transcript(transcript)

    parsed = urlparse(url)
    linked_title = (title or "").strip()
    if not linked_title:
        linked_title = (
            "YouTube training"
            if playback_kind == "youtube"
            else _video_title(Path(parsed.path).name or parsed.netloc)
        )
    filename = (
        f"youtube-{youtube_video_id}"
        if youtube_video_id
        else Path(parsed.path).name or "linked-training-video"
    )
    mime_type = mimetypes.guess_type(parsed.path)[0] or (
        "video/youtube" if playback_kind == "youtube" else "application/octet-stream"
    )
    doc = SourceDocument(
        user_id=user_id,
        filename=filename[:255],
        mime_type=mime_type,
        source_type="video",
        status="uploaded",
        title=linked_title[:160],
        source_map={
            "video": {
                "ingest_kind": "link",
                "playback_kind": playback_kind,
                "external_url": url,
                "youtube_video_id": youtube_video_id,
                "provided_transcript": transcript or None,
                "content_type": mime_type,
            }
        },
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    spawn(run_video_ingestion(doc.id), name=f"video-link-ingest:{doc.id}")
    return doc


async def run_video_ingestion(source_id: str) -> None:
    db = SessionLocal()
    transcript_locator: str | None = None
    try:
        doc = db.get(SourceDocument, source_id)
        if not doc:
            return
        source_map = dict(doc.source_map or {})
        video = dict(source_map.get("video") or {})
        transcript_locator = _transcript_locator(doc)
        if transcript_locator is None:
            media_locator = _video_locator(doc)
            external_url = str(video.get("external_url") or "").strip()
            provided_transcript = str(video.get("provided_transcript") or "").strip()
            if not media_locator and not external_url and not provided_transcript:
                raise ValueError("video source has no stored media or external link")
            doc.status = "transcribing"
            doc.error = None
            db.commit()

            if provided_transcript:
                transcript = parse_timed_transcript(provided_transcript)
            elif external_url:
                transcript = await transcribe_recorded_url(external_url)
            else:
                assert media_locator is not None
                data = await _read_media(media_locator, bucket=source_map.get("storage_bucket"))
                max_bytes = get_settings().max_video_upload_mb * 1024 * 1024
                if len(data) > max_bytes:
                    raise ValueError(
                        f"video exceeds max upload size ({len(data)} > {max_bytes})"
                    )
                transcript = await transcribe_recorded_media(data, doc.mime_type)
            markdown = _transcript_markdown(doc.title or doc.filename, transcript.segments)
            transcript_locator, transcript_storage = await _store_transcript(doc, markdown)
            video.update(transcript_storage)
            video.update(
                {
                    "duration_seconds": round(transcript.duration_seconds, 3),
                    "language": transcript.language,
                    "transcript_provider": transcript.provider,
                    "segments": [
                        {
                            "start": round(segment.start, 3),
                            "end": round(segment.end, 3),
                            "text": segment.text,
                        }
                        for segment in transcript.segments
                    ],
                }
            )
            video.pop("provided_transcript", None)
            source_map["video"] = video
            doc.source_map = source_map
            doc.abstract = transcript.transcript[:1000]
            doc.extraction_quality = {
                "ok": True,
                "transcript_segment_count": len(transcript.segments),
                "transcript_provider": transcript.provider,
            }
            db.commit()

        segments = _stored_segments(video)
        duration_seconds = float(video.get("duration_seconds") or 0)
        if not video.get("checkpoints") and segments:
            doc.status = "checkpointing"
            db.commit()
            checkpoints, generated_by = await plan_video_checkpoints(
                title=doc.title or doc.filename,
                segments=segments,
                duration_seconds=duration_seconds,
                timeout_seconds=get_settings().video_checkpoint_timeout_s,
            )
            source_map = dict(doc.source_map or {})
            video = dict(source_map.get("video") or {})
            video["checkpoints"] = [item.model_dump() for item in checkpoints]
            video["checkpoint_generated_by"] = generated_by
            source_map["video"] = video
            doc.source_map = source_map
            quality = dict(doc.extraction_quality or {})
            quality["checkpoint_generated_by"] = generated_by
            doc.extraction_quality = quality
            db.commit()
    except Exception as exc:  # noqa: BLE001 - persist actionable ingestion failure
        db.rollback()
        doc = db.get(SourceDocument, source_id)
        if doc:
            doc.status = "failed"
            doc.error = str(exc)[:2000]
            db.commit()
        return
    finally:
        db.close()

    assert transcript_locator is not None
    await run_source_ingestion(
        source_id,
        transcript_locator,
        "text/markdown",
        f"{Path(source_id).stem}-transcript.md",
    )
    with SessionLocal() as final_db:
        doc = final_db.get(SourceDocument, source_id)
        if doc:
            doc.source_type = "video"
            doc.page_count = None
            video = (doc.source_map or {}).get("video") or {}
            quality = dict(doc.extraction_quality or {})
            quality.update(
                {
                    "transcript_segment_count": len(video.get("segments") or []),
                    "transcript_provider": video.get("transcript_provider", "deepgram"),
                    "checkpoint_generated_by": video.get(
                        "checkpoint_generated_by", "deterministic"
                    ),
                }
            )
            doc.extraction_quality = quality
            final_db.commit()


def recover_orphaned_video_ingestions() -> int:
    requeued = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(SourceDocument).where(
                SourceDocument.source_type == "video",
                SourceDocument.status.in_(VIDEO_INGEST_STATUSES),
            )
        ).all()
        for doc in rows:
            video = (doc.source_map or {}).get("video") or {}
            if (
                _video_locator(doc)
                or _transcript_locator(doc)
                or video.get("external_url")
                or video.get("provided_transcript")
            ):
                spawn(run_video_ingestion(doc.id), name=f"video-reingest:{doc.id}")
                requeued += 1
            else:
                doc.status = "failed"
                doc.error = "video ingestion interrupted and no stored media is available"
        db.commit()
    return requeued
