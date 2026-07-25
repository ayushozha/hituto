"""GuideBridge integration: voice agent page tools route through app.agentbridge.

The SDK's own suite covers the WebSocket mechanics (authorize binding, stale-id
retry, iframe relay); these tests cover the Hi-Tuto glue — session identity,
tool routing from the voice agent, and the authorizer's decisions.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from guidebridge.session import BridgeSession

from app import agentbridge
from app.voice.agent_langchain import (
    PAGE_TOOL_NAMES,
    LangChainVoiceAgent,
    _openai_tool_specs,
)

SNAPSHOT = {
    "url": "/lesson",
    "title": "Waves",
    "scrollY": 0,
    "scrollHeight": 2000,
    "viewportHeight": 800,
    "targets": [
        {"id": "gb-ctl-1", "slug": "reset-sim", "label": "Reset simulation", "role": "button", "visible": True}
    ],
    "sections": [{"id": "gb-sec-1", "slug": "intro", "title": "Introduction", "summary": "", "visible": True}],
    "headings": [],
    "customActions": [],
    "recentEvents": [],
}


class ScriptedWire:
    """Stands in for the lesson tab: answers observe/action frames instantly."""

    def __init__(self):
        self.session: BridgeSession | None = None
        self.frames: list[dict] = []

    async def send(self, frame: dict) -> None:
        self.frames.append(frame)
        rid = frame["requestId"]
        if frame["type"] == "observe.request":
            self.session.handle_frame(
                {"type": "observe.result", "requestId": rid, "payload": SNAPSHOT}
            )
        elif frame["type"] == "action.request":
            self.session.handle_frame(
                {
                    "type": "action.result",
                    "requestId": rid,
                    "payload": {"success": True, "action": frame["action"]["type"]},
                }
            )


@pytest.fixture
def connected_session():
    """Register a scripted lesson-tab session for user u1 / lesson l1."""
    wire = ScriptedWire()
    session = BridgeSession(
        agentbridge.page_session_id("u1", "l1"), wire.send, timeout_s=0.5
    )
    wire.session = session
    agentbridge.bridge._register(session)
    yield wire
    agentbridge.bridge._unregister(session)


def make_agent() -> LangChainVoiceAgent:
    async def send_frame(_frame: dict) -> None:
        pass

    return LangChainVoiceAgent(
        lesson_context={
            "user_id": "u1",
            "lesson_id": "l1",
            "course_id": "c1",
            "course_title": "t",
            "lesson_title": "t",
        },
        send_frame=send_frame,
    )


async def test_observe_page_routes_through_guidebridge(connected_session):
    agent = make_agent()
    raw = await agent.execute_tool("observe_page", {})
    snapshot = json.loads(raw)
    assert snapshot["targets"][0]["slug"] == "reset-sim"
    assert connected_session.frames[0]["type"] == "observe.request"


async def test_highlight_routes_to_the_matching_session(connected_session):
    agent = make_agent()
    result = json.loads(await agent.execute_tool("highlight", {"target_id": "gb-ctl-1"}))
    assert result == {"success": True, "action": "highlight"}
    frame = connected_session.frames[0]
    assert frame["type"] == "action.request"
    assert frame["action"] == {"type": "highlight", "targetId": "gb-ctl-1"}


async def test_page_tools_degrade_gracefully_without_a_tab():
    agent = make_agent()  # no session registered for u1:l1
    reply = await agent.execute_tool("click", {"target_id": "x"})
    assert "browser" in reply or "did not respond" in reply  # sentinel, not an exception


def test_tool_specs_expose_sdk_page_tools_with_teaching_descriptions():
    specs = {s["function"]["name"]: s["function"] for s in _openai_tool_specs()}
    assert PAGE_TOOL_NAMES <= set(specs)
    assert "set_value" not in specs
    assert "Tutor cursor" in specs["highlight"]["description"]
    # SDK schemas came through (guidebridge arg names).
    assert "target_id" in specs["click"]["parameters"]["properties"]


async def test_authorizer_binds_token_identity_to_session_id(monkeypatch):
    monkeypatch.setattr(agentbridge, "get_user_id_from_websocket", lambda ws: "u1")
    monkeypatch.setattr(
        agentbridge,
        "check_lesson_access",
        lambda _course_id, _lesson_id, _user_id: True,
    )
    ws = SimpleNamespace(path_params={"course_id": "c1", "lesson_id": "l1"})
    assert await agentbridge._authorize(ws) == "u1:l1"


async def test_authorizer_rejects_non_owner(monkeypatch):
    monkeypatch.setattr(agentbridge, "get_user_id_from_websocket", lambda ws: "intruder")
    monkeypatch.setattr(
        agentbridge,
        "check_lesson_access",
        lambda _course_id, _lesson_id, _user_id: False,
    )
    ws = SimpleNamespace(path_params={"course_id": "c1", "lesson_id": "l1"})
    assert await agentbridge._authorize(ws) is False
