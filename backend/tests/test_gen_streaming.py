"""fast_gen §4 streaming: fragment throttling, broker transience, LLM stream fallback."""
import asyncio

from app.core.progress import ProgressEvent, broker
from app.coursegen.graph import _FragmentStreamer
from app.providers.llm import OpenAICompatLLM


async def _drain(q: asyncio.Queue) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


async def test_fragment_streamer_throttles_and_flushes() -> None:
    course_id = "c-stream-test"
    q = broker.subscribe(course_id)
    try:
        s = _FragmentStreamer(course_id, "l1", attempt=1)
        # First delta always flushes (last=0 → interval elapsed), even when tiny.
        await s.on_delta("<html>")
        # Small follow-ups buffer until the char threshold.
        await s.on_delta("a" * 10)
        events = await _drain(q)
        assert len(events) == 1
        assert events[0].stage == "gen_fragment"
        assert events[0].data["delta"] == "<html>"

        # A large delta crosses MIN_CHARS and flushes the buffered text with it.
        await s.on_delta("b" * _FragmentStreamer.MIN_CHARS)
        (ev,) = await _drain(q)
        assert ev.data["delta"] == "a" * 10 + "b" * _FragmentStreamer.MIN_CHARS
        assert ev.data["length"] == len("<html>") + 10 + _FragmentStreamer.MIN_CHARS

        # Final flush emits done=True even with an empty buffer.
        await s.flush(final=True)
        (ev,) = await _drain(q)
        assert ev.data["done"] is True
    finally:
        broker.unsubscribe(course_id, q)


async def test_gen_fragment_frames_are_not_replayed_to_late_subscribers() -> None:
    course_id = "c-transient-test"
    await broker.publish(course_id, ProgressEvent(stage="generating", detail="…", pct=60))
    await broker.publish(
        course_id,
        ProgressEvent(stage="gen_fragment", pct=65, data={"delta": "<p>x</p>"}),
    )
    q = broker.subscribe(course_id)
    try:
        replayed = await _drain(q)
        assert [e.stage for e in replayed] == ["generating"]
    finally:
        broker.unsubscribe(course_id, q)


async def test_generate_html_streams_deltas_prefix_consistently(monkeypatch) -> None:
    llm = OpenAICompatLLM()

    async def fake_stream(messages, *, temperature, max_tokens, on_delta):
        for part in ("<html><body>", "hi", "</body></html>"):
            res = on_delta(part)
            if asyncio.iscoroutine(res):
                await res
        return "<html><body>hi</body></html>", "stop"

    monkeypatch.setattr(llm, "_chat_stream", fake_stream)
    seen: list[str] = []
    html = await llm.generate_html("sys", "user", on_delta=seen.append)
    assert html == "<html><body>hi</body></html>"
    assert "".join(seen) == html


async def test_generate_html_stream_failure_resumes_via_buffered_continuation(
    monkeypatch,
) -> None:
    llm = OpenAICompatLLM()
    calls = {"stream": 0}

    async def failing_stream(messages, *, temperature, max_tokens, on_delta):
        calls["stream"] += 1
        if calls["stream"] == 1:
            res = on_delta("<html><body>par")
            if asyncio.iscoroutine(res):
                await res
            return "<html><body>par", "error"  # mid-stream drop with partial content
        return "", "error"  # subsequent stream attempts fail outright → buffered

    async def fake_chat(messages, *, temperature, max_tokens):
        # The continuation prompt must carry the streamed partial as assistant context.
        assert messages[-2] == {"role": "assistant", "content": "<html><body>par"}
        return {
            "choices": [
                {"message": {"content": "tial</body></html>"}, "finish_reason": "stop"}
            ]
        }

    monkeypatch.setattr(llm, "_chat_stream", failing_stream)
    monkeypatch.setattr(llm, "_chat", fake_chat)
    seen: list[str] = []
    html = await llm.generate_html("sys", "user", on_delta=seen.append)
    assert html == "<html><body>partial</body></html>"
    assert "".join(seen) == html
