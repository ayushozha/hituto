import json
import logging
import unittest

import pytest

from observability import log_event, timed


def _events(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [json.loads(record.message) for record in caplog.records]


def test_an_event_is_one_json_object(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="sat_tutor.events"):
        log_event("lesson.prepared", session="s1", ms=1234, beats=4)

    assert _events(caplog) == [
        {"event": "lesson.prepared", "session": "s1", "ms": 1234, "beats": 4}
    ]


def test_student_content_is_withheld(caplog: pytest.LogCaptureFixture) -> None:
    question = "Square ABCD has side length 6, " * 10
    with caplog.at_level(logging.INFO, logger="sat_tutor.events"):
        log_event("lesson.prepared", question=question)

    logged = _events(caplog)[0]["question"]
    # A pasted question is private; the log keeps its size, not its text.
    assert "Square ABCD" not in logged
    assert "chars withheld" in logged


def test_unexpected_types_do_not_smuggle_content(caplog: pytest.LogCaptureFixture) -> None:
    class Lesson:
        def __str__(self) -> str:
            return "the whole verified lesson"

    with caplog.at_level(logging.INFO, logger="sat_tutor.events"):
        log_event("lesson.prepared", lesson=Lesson())

    assert _events(caplog)[0]["lesson"] == "<Lesson>"


class TestTimed(unittest.IsolatedAsyncioTestCase):
    async def test_reports_duration_and_success(self) -> None:
        with self.assertLogs("sat_tutor.events", level=logging.INFO) as captured:
            async with timed("provider.call", model="deepseek") as event:
                event["tokens"] = 120

        logged = json.loads(captured.records[0].message)
        self.assertEqual(logged["outcome"], "ok")
        self.assertEqual(logged["model"], "deepseek")
        self.assertEqual(logged["tokens"], 120)
        self.assertGreaterEqual(logged["ms"], 0)

    async def test_records_the_failure_and_reraises(self) -> None:
        with self.assertLogs("sat_tutor.events", level=logging.INFO) as captured:
            with self.assertRaises(TimeoutError):
                async with timed("provider.call"):
                    raise TimeoutError("provider is slow")

        # A failure that is not logged is a failure nobody can alert on.
        self.assertEqual(json.loads(captured.records[0].message)["outcome"], "TimeoutError")
