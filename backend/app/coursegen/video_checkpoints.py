"""Transcript-grounded learning checkpoints for synchronized training video."""
from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence

from ..providers.registry import get_coursegen_llm
from ..providers.transcription import TranscriptSegment
from ..schemas import VideoCheckpoint, VideoCheckpointPlan

_SYSTEM = """You design active-learning checkpoints for a training video.
Every checkpoint must be supported by the timestamped transcript. Place it only after the
instructor has explained the relevant idea. Mix concise readings, visual concept summaries, and
multiple-choice retrieval questions. Never invent facts, quotes, or examples absent from the
transcript. Quiz distractors must be plausible but unambiguously wrong based on the transcript.
Return 4-8 checkpoints for an ordinary video, fewer for a short clip. Cover the full timeline."""


def _clock(seconds: float) -> str:
    whole = max(0, int(seconds))
    return f"{whole // 60:02d}:{whole % 60:02d}"


def _transcript_prompt(segments: Sequence[TranscriptSegment], limit: int = 60_000) -> str:
    lines = [
        f"[{_clock(segment.start)}-{_clock(segment.end)}] {segment.text.strip()}"
        for segment in segments
        if segment.text.strip()
    ]
    if sum(len(line) for line in lines) <= limit:
        return "\n".join(lines)
    stride = max(1, math.ceil(len(lines) / 180))
    sampled = lines[::stride]
    return "\n".join(sampled)[:limit]


def _fallback_checkpoints(
    segments: Sequence[TranscriptSegment], duration_seconds: float
) -> list[VideoCheckpoint]:
    if not segments:
        return []
    count = min(6, max(2, round(max(duration_seconds, 120) / 300)))
    positions = [(index + 1) / (count + 1) for index in range(count)]
    checkpoints: list[VideoCheckpoint] = []
    for index, position in enumerate(positions):
        target = duration_seconds * position
        segment = min(segments, key=lambda item: abs(item.end - target))
        kind = "visual" if index % 2 else "reading"
        summary = segment.text.strip()[:650]
        checkpoints.append(
            VideoCheckpoint(
                id=f"checkpoint-{index + 1}",
                at_seconds=max(0, segment.end),
                kind=kind,
                title=f"Checkpoint at {_clock(segment.end)}",
                prompt="Pause and connect this idea to the lesson goal.",
                body=summary,
                visual_points=[part.strip() for part in summary.split(",")[:3] if part.strip()]
                if kind == "visual"
                else [],
            )
        )
    return checkpoints


def normalize_checkpoints(
    raw: Sequence[VideoCheckpoint], duration_seconds: float
) -> list[VideoCheckpoint]:
    normalized: list[VideoCheckpoint] = []
    for checkpoint in sorted(raw, key=lambda item: item.at_seconds):
        at_seconds = min(max(0.0, checkpoint.at_seconds), max(0.0, duration_seconds))
        if normalized and at_seconds - normalized[-1].at_seconds < 12:
            continue
        item = checkpoint.model_copy(
            update={
                "id": f"checkpoint-{len(normalized) + 1}",
                "at_seconds": round(at_seconds, 2),
            }
        )
        normalized.append(item)
        if len(normalized) == 10:
            break
    return normalized


async def plan_video_checkpoints(
    *,
    title: str,
    segments: Sequence[TranscriptSegment],
    duration_seconds: float,
    timeout_seconds: float = 60,
) -> tuple[list[VideoCheckpoint], str]:
    fallback = _fallback_checkpoints(segments, duration_seconds)
    user = (
        f"Video title: {title}\n"
        f"Duration: {_clock(duration_seconds)}\n\n"
        "Timestamped transcript:\n"
        f"{_transcript_prompt(segments)}"
    )
    try:
        plan = await asyncio.wait_for(
            get_coursegen_llm().generate_json(_SYSTEM, user, VideoCheckpointPlan),
            timeout=max(0.01, timeout_seconds),
        )
        checkpoints = normalize_checkpoints(plan.checkpoints, duration_seconds)
        if checkpoints:
            return checkpoints, "agent"
    except Exception:  # noqa: BLE001 - deterministic checkpoint fallback is intentional
        pass
    return fallback, "deterministic"
