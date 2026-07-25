from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.insight import LearningEventIn


def _event(event_type: str, payload: dict) -> dict:
    return {
        "event_id": "studio-event-1234",
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc),
        "course_id": "course-1",
        "lesson_id": "lesson-1",
        "source": "capsule",
        "schema_version": 1,
        "payload": payload,
    }


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("studio_mode_opened", {"mode": "simulation", "manifest_version": "2.0"}),
        ("studio_part_selected", {"part_id": "compressor"}),
        ("studio_control_changed", {"control_id": "rate", "value": "1.5"}),
        ("studio_playback_completed", {"sequence_id": "primary-process"}),
        ("studio_reset", {"mode": "specimen"}),
        ("studio_degraded", {"reason_code": "mesh_timeout", "fallback_kind": "procedural"}),
    ],
)
def test_studio_capsule_events_are_bounded(event_type: str, payload: dict) -> None:
    parsed = LearningEventIn.model_validate(_event(event_type, payload))
    assert parsed.source == "capsule"


def test_studio_event_rejects_unknown_payload() -> None:
    with pytest.raises(ValidationError, match="unsupported payload fields"):
        LearningEventIn.model_validate(
            _event("studio_part_selected", {"part_id": "compressor", "camera": [1, 2, 3]})
        )
