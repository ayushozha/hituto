from pathlib import Path

from session_store import SQLiteSessionStore


def _store(path: Path, **limits: int) -> SQLiteSessionStore:
    return SQLiteSessionStore(path / "sessions.db", **limits)


def test_a_lesson_is_saved_with_ordered_messages(tmp_path: Path) -> None:
    store = _store(tmp_path)
    begun = store.begin_lesson(
        "browser-one",
        question_text="What is 2 + 2?",
        source_kind="text",
    )

    assert begun.allowed
    assert store.complete(
        "browser-one",
        begun.generation,
        lesson_json='{"finalAnswer":"4"}',
        assistant_text="Two plus two is four.",
    )

    view = store.view("browser-one")
    assert view.snapshot.status == "ready"
    assert view.snapshot.revision == 1
    assert [message.role for message in view.messages] == ["user", "assistant"]
    assert view.messages[1].lesson_json == '{"finalAnswer":"4"}'


def test_stale_generation_cannot_overwrite_a_newer_request(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.begin_lesson("browser-one", question_text="First", source_kind="text")
    second = store.begin_replan("browser-one", student_message="Explain it differently")

    assert not store.complete(
        "browser-one",
        first.generation,
        lesson_json="stale",
        assistant_text="stale",
    )
    assert store.complete(
        "browser-one",
        second.generation,
        lesson_json="current",
        assistant_text="current",
    )
    assert store.snapshot("browser-one").lesson_json == "current"


def test_limits_return_student_facing_state(tmp_path: Path) -> None:
    store = _store(tmp_path, burst_limit=2, daily_lesson_limit=10)

    assert store.begin_lesson("browser-one", question_text="One", source_kind="text").allowed
    assert store.begin_lesson("browser-one", question_text="Two", source_kind="text").allowed
    refused = store.begin_lesson("browser-one", question_text="Three", source_kind="text")

    assert not refused.allowed
    assert "minute" in store.snapshot("browser-one").error_message


def test_reset_and_forget_remove_student_content(tmp_path: Path) -> None:
    store = _store(tmp_path)
    begun = store.begin_lesson("browser-one", question_text="Private question", source_kind="text")
    store.complete(
        "browser-one",
        begun.generation,
        lesson_json="private lesson",
        assistant_text="private answer",
    )

    reset = store.reset("browser-one")
    assert reset.snapshot.question_text == ""
    assert reset.messages == []

    begun = store.begin_check("browser-one", student_work="private working")
    store.fail("browser-one", begun.generation, "try again")
    erased = store.forget("browser-one")

    assert erased == 2
    assert store.view("browser-one").messages == []
    assert store.snapshot("browser-one").last_student_message == ""


def test_message_window_keeps_the_most_recent_conversation(tmp_path: Path) -> None:
    store = _store(tmp_path, burst_limit=200, daily_lesson_limit=200)
    for index in range(45):
        begun = store.begin_lesson(
            "browser-one",
            question_text=f"Question {index}",
            source_kind="text",
        )
        store.complete(
            "browser-one",
            begun.generation,
            lesson_json=f"lesson {index}",
            assistant_text=f"Answer {index}",
        )

    messages = store.messages("browser-one")

    assert len(messages) == 80
    assert messages[0].text == "Question 5"
    assert messages[-1].text == "Answer 44"
