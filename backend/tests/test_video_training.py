import asyncio
import io
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.v1.sources import _requested_range, _stage_bounded_upload
from app.core.db import Base
from app.coursegen import graph as coursegen_graph
from app.coursegen.graph import persist_artifact
from app.coursegen.video_checkpoints import normalize_checkpoints, plan_video_checkpoints
from app.models import Course, CourseSource, Lesson, LessonSourcePack, SourceDocument
from app.providers import storage
from app.providers.transcription import (
    TranscriptSegment,
    parse_deepgram_transcript,
    parse_timed_transcript,
)
from app.schemas import VideoCheckpoint
from app.services import course_service
from app.services.video_source_service import video_link_details


def test_parse_copied_youtube_transcript_with_timestamps():
    transcript = parse_timed_transcript(
        """0:00 Welcome to linear regression
0:12 A model fits a line through examples
1:02 Now compare its prediction with the target"""
    )

    assert transcript.provider == "provided_captions"
    assert [segment.start for segment in transcript.segments] == [0, 12, 62]
    assert transcript.segments[0].end == 12
    assert transcript.transcript.startswith("Welcome to linear regression")


def test_parse_srt_captions_preserves_explicit_end_times():
    transcript = parse_timed_transcript(
        """1
00:00:01,000 --> 00:00:04,500
Welcome to the lesson.

2
00:00:05,000 --> 00:00:08,250
This is the first concept.
"""
    )

    assert [(segment.start, segment.end) for segment in transcript.segments] == [
        (1, 4.5),
        (5, 8.25),
    ]


def test_parse_timed_transcript_rejects_plain_text():
    with pytest.raises(ValueError, match="Timed captions are required"):
        parse_timed_transcript("A transcript without timestamps is not synchronized.")


@pytest.mark.parametrize(
    ("url", "expected_id"),
    [
        ("https://www.youtube.com/watch?v=M7lc1UVf-VE", "M7lc1UVf-VE"),
        ("https://youtu.be/M7lc1UVf-VE?t=12", "M7lc1UVf-VE"),
        ("https://youtube.com/shorts/M7lc1UVf-VE", "M7lc1UVf-VE"),
        ("https://www.youtube-nocookie.com/embed/M7lc1UVf-VE", "M7lc1UVf-VE"),
    ],
)
def test_video_link_details_extracts_youtube_id(url, expected_id):
    assert video_link_details(url) == ("youtube", expected_id)


def test_video_link_details_uses_native_player_for_direct_media():
    assert video_link_details("https://cdn.example.com/training/module-1.mp4") == (
        "native",
        None,
    )


def test_video_link_details_rejects_invalid_youtube_url():
    with pytest.raises(ValueError, match="YouTube video id"):
        video_link_details("https://youtube.com/watch?feature=share")


async def test_failed_optional_companion_keeps_video_course_ready(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'video-course.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        db.add(
            Course(
                id="video-course",
                user_id="dev",
                topic="Video training",
                title="Video training",
                status="generating",
                knobs={"video_sync": True},
            )
        )
        db.add(
            Lesson(
                id="video-lesson",
                course_id="video-course",
                ordinal=0,
                title="Video training",
                status="generating",
            )
        )
        db.commit()

    async def ignore_progress(*_args, **_kwargs):
        return None

    monkeypatch.setattr(coursegen_graph, "SessionLocal", session_factory)
    monkeypatch.setattr(coursegen_graph, "_emit", ignore_progress)
    status = await persist_artifact(
        course_id="video-course",
        lesson_id="video-lesson",
        plan={"title": "Optional deep dive", "archetype": "explainer"},
        checks={"passed": False, "failed": ["grounding: no source citations"]},
        html="",
    )

    assert status == "failed"
    with session_factory() as db:
        course = db.get(Course, "video-course")
        lesson = db.get(Lesson, "video-lesson")
        assert course is not None and course.status == "ready" and course.error is None
        assert lesson is not None and lesson.status == "failed"
        assert lesson.error == "grounding: no source citations"


def test_parse_deepgram_transcript_prefers_timestamped_utterances():
    transcript = parse_deepgram_transcript(
        {
            "metadata": {"duration": 18.4},
            "results": {
                "channels": [
                    {
                        "detected_language": "en",
                        "alternatives": [{"transcript": "First idea. Second idea."}],
                    }
                ],
                "utterances": [
                    {"start": 0.2, "end": 6.1, "transcript": "First idea."},
                    {"start": 7.0, "end": 14.8, "transcript": "Second idea."},
                ],
            },
        }
    )

    assert transcript.transcript == "First idea. Second idea."
    assert transcript.duration_seconds == 18.4
    assert transcript.language == "en"
    assert [(item.start, item.end) for item in transcript.segments] == [
        (0.2, 6.1),
        (7.0, 14.8),
    ]


def test_parse_deepgram_transcript_builds_segments_from_words():
    transcript = parse_deepgram_transcript(
        {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "Linear regression fits a line.",
                                "words": [
                                    {
                                        "start": 0.0,
                                        "end": 2.0,
                                        "word": "Linear",
                                        "punctuated_word": "Linear",
                                    },
                                    {
                                        "start": 2.0,
                                        "end": 4.0,
                                        "word": "regression",
                                        "punctuated_word": "regression",
                                    },
                                    {
                                        "start": 4.0,
                                        "end": 8.5,
                                        "word": "fits",
                                        "punctuated_word": "fits",
                                    },
                                    {
                                        "start": 8.5,
                                        "end": 10.0,
                                        "word": "a line",
                                        "punctuated_word": "a line.",
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        }
    )

    assert transcript.duration_seconds == 10.0
    assert transcript.segments[0].text == "Linear regression fits a line."


def test_parse_deepgram_transcript_rejects_silent_media():
    with pytest.raises(ValueError, match="no speech"):
        parse_deepgram_transcript({"results": {"channels": []}})


def test_append_video_source_creates_grounded_next_chapter(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'append-video.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    started: list[str] = []

    def record_generation(_db, _course, lesson, **_kwargs):
        started.append(lesson.id)
        lesson.status = "generating"
        _db.commit()
        return True

    monkeypatch.setattr(course_service, "start_generation", record_generation)

    with session_factory() as db:
        primary = SourceDocument(
            id="video-one",
            user_id="dev",
            filename="one.youtube",
            title="Neural networks",
            source_type="video",
            status="ready",
            source_map={"video": {"duration_seconds": 240}},
        )
        added_source = SourceDocument(
            id="video-two",
            user_id="dev",
            filename="two.youtube",
            title="Gradient descent",
            source_type="video",
            status="ready",
            abstract="How gradients guide a model toward a lower loss.",
            source_map={
                "video": {
                    "duration_seconds": 510,
                    "playback_kind": "youtube",
                    "youtube_video_id": "gradient123",
                    "checkpoints": [],
                },
                "teaching_map": {"chapters": [{"id": "gradient-chapter"}]},
            },
        )
        course = Course(
            id="video-course",
            user_id="dev",
            topic="Neural network course",
            title="Neural network course",
            status="ready",
            knobs={
                "video_sync": True,
                "source_document_id": primary.id,
                "lesson_scopes": {"0": {"chapter_ids": ["neural-chapter"]}},
            },
        )
        first = Lesson(
            id="lesson-one",
            course_id=course.id,
            ordinal=0,
            title="Neural networks",
            completed=True,
            status="ready",
            module_ordinal=0,
            module_title="Chapter 1: Neural networks",
        )
        db.add_all([primary, added_source, course, first])
        db.flush()
        db.add(
            CourseSource(
                course_id=course.id,
                source_document_id=primary.id,
                mode="video_companion",
            )
        )
        db.commit()

        lesson = course_service.append_video_source(
            db,
            course,
            added_source,
            description="Practice following the gradient from loss to a better set of weights.",
        )

        assert lesson.ordinal == 1
        assert lesson.module_ordinal == 1
        assert lesson.module_title == "Chapter 2: Gradient descent"
        assert lesson.estimated_duration == "9m"
        assert lesson.objective == (
            "Practice following the gradient from loss to a better set of weights."
        )
        assert lesson.status == "generating"
        assert started == [lesson.id]
        assert course.knobs["source_document_ids"] == ["video-one", "video-two"]
        assert course.knobs["lesson_scopes"]["1"]["chapter_ids"] == ["gradient-chapter"]

        pack = db.scalars(
            select(LessonSourcePack).where(LessonSourcePack.lesson_id == lesson.id)
        ).one()
        assert pack.source_document_id == "video-two"
        assert pack.chapter_ids == ["gradient-chapter"]

        guide = course_service.video_guide(db, course, lesson.id)
        assert guide is not None
        assert guide.source_id == "video-two"
        assert guide.youtube_video_id == "gradient123"

        with pytest.raises(ValueError, match="already in the course"):
            course_service.append_video_source(db, course, added_source)


def test_checkpoint_timing_is_sorted_clamped_and_spaced():
    checkpoints = [
        VideoCheckpoint(at_seconds=200, kind="reading", title="Late"),
        VideoCheckpoint(at_seconds=20, kind="reading", title="First"),
        VideoCheckpoint(at_seconds=25, kind="visual", title="Too close"),
        VideoCheckpoint(at_seconds=80, kind="visual", title="Middle"),
    ]

    result = normalize_checkpoints(checkpoints, duration_seconds=120)

    assert [item.title for item in result] == ["First", "Middle", "Late"]
    assert [item.at_seconds for item in result] == [20, 80, 120]
    assert [item.id for item in result] == [
        "checkpoint-1",
        "checkpoint-2",
        "checkpoint-3",
    ]


async def test_checkpoint_planner_times_out_to_deterministic_guide(monkeypatch):
    class SlowLLM:
        async def generate_json(self, _system, _user, _schema):
            await asyncio.sleep(1)

    monkeypatch.setattr(
        "app.coursegen.video_checkpoints.get_coursegen_llm",
        lambda: SlowLLM(),
    )

    checkpoints, generated_by = await plan_video_checkpoints(
        title="Linear regression",
        segments=[
            TranscriptSegment(
                0,
                90,
                "Linear regression fits a line to numeric examples.",
            )
        ],
        duration_seconds=90,
        timeout_seconds=0.01,
    )

    assert generated_by == "deterministic"
    assert checkpoints


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=10-19", (10, 19)),
        ("bytes=90-", (90, 99)),
        ("bytes=-12", (88, 99)),
        ("bytes=-0", None),
        ("bytes=100-110", None),
    ],
)
def test_requested_range_supports_video_seeking(header, expected):
    assert _requested_range(header, total=100) == expected


class _MemoryUpload:
    filename = "training.mp4"

    def __init__(self, data: bytes):
        self._buffer = io.BytesIO(data)

    async def read(self, size: int) -> bytes:
        return self._buffer.read(size)


async def test_video_upload_is_staged_without_exceeding_the_bound(tmp_path):
    path, size = await _stage_bounded_upload(
        _MemoryUpload(b"video-bytes"),  # type: ignore[arg-type]
        max_bytes=32,
        directory=tmp_path,
    )

    assert size == 11
    assert path.read_bytes() == b"video-bytes"


async def test_oversized_video_upload_removes_partial_stage_file(tmp_path):
    with pytest.raises(HTTPException) as exc:
        await _stage_bounded_upload(
            _MemoryUpload(b"too-large"),  # type: ignore[arg-type]
            max_bytes=4,
            directory=tmp_path,
        )

    assert exc.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


async def test_storage_range_stream_reaches_cdn_without_leaking_admin_key(monkeypatch):
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "insforge.test":
            return httpx.Response(302, headers={"Location": "https://cdn.test/signed-video"})
        return httpx.Response(
            206,
            content=b"range-bytes",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": "11",
                "Content-Range": "bytes 10-20/100",
                "Content-Type": "video/mp4",
            },
        )

    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: SimpleNamespace(
            insforge_base_url="https://insforge.test",
            insforge_api_key="admin-secret",
            storage_bucket="sources",
        ),
    )
    stream = await storage.open_download_stream(
        "source/video.mp4",
        range_header="bytes=10-20",
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = b"".join([chunk async for chunk in stream.iter_bytes()])
    finally:
        await stream.aclose()

    assert payload == b"range-bytes"
    assert stream.status_code == 206
    assert requests[0].headers["x-api-key"] == "admin-secret"
    assert "x-api-key" not in requests[1].headers
    assert requests[1].headers["range"] == "bytes=10-20"


def test_generation_start_is_idempotent(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'generation-claim.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    scheduled: list[str] = []

    def fake_spawn(coro, *, name=None):
        scheduled.append(name or "")
        coro.close()
        return None

    monkeypatch.setattr(course_service, "spawn", fake_spawn)
    with session_factory() as db:
        course = Course(id="course", user_id="dev", topic="Video", status="ready")
        lesson = Lesson(
            id="lesson",
            course_id="course",
            ordinal=0,
            title="Video",
            status="pending",
        )
        db.add_all([course, lesson])
        db.commit()

        assert course_service.start_generation(db, course, lesson) is True
        assert course_service.start_generation(db, course, lesson) is False
        assert db.get(Lesson, "lesson").status == "generating"

    assert scheduled == ["gen:lesson"]
