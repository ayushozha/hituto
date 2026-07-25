"""Recorded-media transcription provider.

External speech-to-text calls stay in providers. The service layer owns storage,
checkpoint planning, and source state transitions.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

import httpx

from ..core.config import get_settings


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class RecordedTranscript:
    transcript: str
    segments: list[TranscriptSegment]
    duration_seconds: float
    language: str | None = None
    provider: str = "deepgram"


_TIMESTAMP = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"
_CUE_RE = re.compile(rf"^(?P<start>{_TIMESTAMP})\s*-->\s*(?P<end>{_TIMESTAMP})")
_TIMED_LINE_RE = re.compile(rf"^(?P<start>{_TIMESTAMP})(?:\s+(?P<text>.+))?$")


def _bounded_time(value: object) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _timestamp_seconds(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError as exc:
        raise ValueError(f"invalid caption timestamp: {value}") from exc
    raise ValueError(f"invalid caption timestamp: {value}")


def _clean_caption_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", value).strip()


def parse_timed_transcript(value: str) -> RecordedTranscript:
    """Parse WebVTT, SRT, or copied YouTube transcript timestamps."""
    lines = value.replace("\ufeff", "").replace("\r\n", "\n").split("\n")
    raw_segments: list[tuple[float, float | None, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        cue = _CUE_RE.match(line)
        timed = _TIMED_LINE_RE.match(line)
        if cue:
            start = _timestamp_seconds(cue.group("start"))
            end = _timestamp_seconds(cue.group("end"))
            index += 1
            body: list[str] = []
            while index < len(lines) and lines[index].strip():
                body.append(lines[index].strip())
                index += 1
            text = _clean_caption_text(" ".join(body))
            if text:
                raw_segments.append((start, end, text))
            continue
        if timed:
            start = _timestamp_seconds(timed.group("start"))
            text = _clean_caption_text(timed.group("text") or "")
            index += 1
            if not text:
                body = []
                while index < len(lines):
                    candidate = lines[index].strip()
                    if _CUE_RE.match(candidate) or _TIMED_LINE_RE.match(candidate):
                        break
                    index += 1
                    if candidate and not candidate.isdigit() and candidate != "WEBVTT":
                        body.append(candidate)
                text = _clean_caption_text(" ".join(body))
            if text:
                raw_segments.append((start, None, text))
            continue
        index += 1

    raw_segments.sort(key=lambda item: item[0])
    segments: list[TranscriptSegment] = []
    for position, (start, explicit_end, text) in enumerate(raw_segments):
        next_start = (
            raw_segments[position + 1][0] if position + 1 < len(raw_segments) else None
        )
        estimated_end = start + max(3.0, min(15.0, len(text.split()) / 2.5))
        end = explicit_end or next_start or estimated_end
        if next_start is not None:
            end = min(end, next_start)
        segments.append(TranscriptSegment(start, max(start + 0.25, end), text))

    if not segments:
        raise ValueError(
            "Timed captions are required. Paste WebVTT, SRT, or transcript lines like "
            "'01:24 Explanation'."
        )
    return RecordedTranscript(
        transcript=" ".join(segment.text for segment in segments),
        segments=segments,
        duration_seconds=max(segment.end for segment in segments),
        provider="provided_captions",
    )


def _segments_from_words(words: list[dict]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    current: list[dict] = []
    segment_start = 0.0
    for word in words:
        start = _bounded_time(word.get("start"))
        if not current:
            segment_start = start
        current.append(word)
        end = _bounded_time(word.get("end"))
        sentence_end = str(word.get("punctuated_word") or word.get("word") or "").endswith(
            (".", "?", "!")
        )
        if end - segment_start >= 24 or (sentence_end and end - segment_start >= 8):
            text = " ".join(
                str(item.get("punctuated_word") or item.get("word") or "").strip()
                for item in current
            ).strip()
            if text:
                segments.append(TranscriptSegment(segment_start, end, text))
            current = []
    if current:
        end = _bounded_time(current[-1].get("end"))
        text = " ".join(
            str(item.get("punctuated_word") or item.get("word") or "").strip()
            for item in current
        ).strip()
        if text:
            segments.append(TranscriptSegment(segment_start, end, text))
    return segments


def parse_deepgram_transcript(payload: dict) -> RecordedTranscript:
    """Normalize Deepgram's prerecorded response into a small stable contract."""
    results = payload.get("results") or {}
    channels = results.get("channels") or []
    channel = channels[0] if channels else {}
    alternatives = channel.get("alternatives") or []
    alternative = alternatives[0] if alternatives else {}
    transcript = str(alternative.get("transcript") or "").strip()

    segments: list[TranscriptSegment] = []
    for utterance in results.get("utterances") or []:
        text = str(utterance.get("transcript") or "").strip()
        if text:
            segments.append(
                TranscriptSegment(
                    _bounded_time(utterance.get("start")),
                    _bounded_time(utterance.get("end")),
                    text,
                )
            )
    if not segments:
        segments = _segments_from_words(alternative.get("words") or [])

    metadata = payload.get("metadata") or {}
    duration = _bounded_time(metadata.get("duration"))
    if not duration and segments:
        duration = max(segment.end for segment in segments)
    if not segments and transcript:
        segments = [TranscriptSegment(0.0, duration, transcript)]
    if not transcript and segments:
        transcript = " ".join(segment.text for segment in segments)
    if not transcript:
        raise ValueError("video transcription returned no speech")

    language = channel.get("detected_language") or metadata.get("language")
    return RecordedTranscript(
        transcript=transcript,
        segments=segments,
        duration_seconds=duration,
        language=str(language) if language else None,
    )


async def transcribe_recorded_media(
    data: bytes,
    content_type: str,
    *,
    model: str | None = None,
) -> RecordedTranscript:
    settings = get_settings()
    if not settings.deepgram_api_key.strip():
        raise RuntimeError("Video transcription requires DEEPGRAM_API_KEY")

    params = {
        "model": model or settings.video_transcription_model,
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
        "paragraphs": "true",
        "detect_language": "true",
        "mip_opt_out": "true",
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": content_type or "application/octet-stream",
    }
    timeout = httpx.Timeout(1800, connect=30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            headers=headers,
            content=data,
        )
        response.raise_for_status()
        return parse_deepgram_transcript(response.json())


async def transcribe_recorded_url(
    url: str,
    *,
    model: str | None = None,
) -> RecordedTranscript:
    """Ask Deepgram to read a public direct media URL without storing it in Hi Tuto."""
    settings = get_settings()
    if not settings.deepgram_api_key.strip():
        raise RuntimeError("Video transcription requires DEEPGRAM_API_KEY")
    params = {
        "model": model or settings.video_transcription_model,
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
        "paragraphs": "true",
        "detect_language": "true",
        "mip_opt_out": "true",
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(1800, connect=30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            headers=headers,
            json={"url": url},
        )
        response.raise_for_status()
        return parse_deepgram_transcript(response.json())
