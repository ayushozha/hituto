from unittest.mock import Mock

from app.voice.openai_realtime_session import OpenAIRealtimeVoiceSession


async def _noop(*_args, **_kwargs) -> None:
    return None


async def test_tool_parent_response_waits_for_final_voice_reply() -> None:
    session = object.__new__(OpenAIRealtimeVoiceSession)
    session._last_activity = 0.0
    session._active_response_id = "response-parent"
    session._active_output_item_id = None
    session._tool_parent_response_ids = {"response-parent"}
    session._finish_audio = _noop
    session._handle_response_done_function_calls = _noop
    session._repair_missing_tool_call = _noop
    session._notify_response_finished = Mock()

    await session._handle_realtime_event(
        {"type": "response.done", "response": {"id": "response-parent", "output": []}}
    )

    session._notify_response_finished.assert_not_called()
    assert session._tool_parent_response_ids == set()

    session._active_response_id = "response-final"
    await session._handle_realtime_event(
        {"type": "response.done", "response": {"id": "response-final", "output": []}}
    )

    session._notify_response_finished.assert_called_once_with()
