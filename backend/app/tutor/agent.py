"""Tutor agent orchestration — LangGraph node + run_tutor_chat façade."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from ..core.tracing import agent_run_config
from . import client
from .prompts_util import _build_system_prompt, _flatten_history  # re-exported for tests
from .tools import GenerateUiTool, _TOOL_DEFS

logger = logging.getLogger(__name__)

# Re-exports for tests / shims that historically imported these from the tutor module.
__all__ = [
    "GenerateUiTool",
    "TutorState",
    "_TOOL_DEFS",
    "_flatten_history",
    "_openai_tool_chat",
    "_openai_tool_chat_stream",
    "build_tutor_graph",
    "run_tutor_chat",
    "tutor_chat_node",
]


class TutorState(TypedDict):
    messages: List[Dict[str, Any]]
    course_id: str
    lesson_id: str
    lesson_context: Dict[str, Any]
    response: Optional[Dict[str, Any]]


# Module-level aliases so monkeypatches on app.tutor.agent._openai_tool_chat still work
# when tests patch the agent module; production calls go through client.* below.
_openai_tool_chat = client._openai_tool_chat
_openai_tool_chat_stream = client._openai_tool_chat_stream


async def tutor_chat_node(state: TutorState) -> TutorState:
    messages = state["messages"]
    ctx = state["lesson_context"]
    lesson_title = ctx.get("lesson_title", "Current Lesson")
    lesson_obj = ctx.get("lesson_objective", "")
    lesson_arch = ctx.get("lesson_archetype", "explainer")

    system_prompt = _build_system_prompt(ctx)
    history = _flatten_history(messages)
    try:
        # Call through the client *module* so patches on client._openai_tool_chat apply.
        content, tool_call = await client._openai_tool_chat(system_prompt, history)
    except Exception:
        logger.exception("Tutor LLM call failed")
        state["response"] = {
            "role": "assistant",
            "content": (
                f"Sorry, I encountered an issue reaching the tutor service. Here is what I can tell "
                f"you about {lesson_title}: it focuses on '{lesson_obj}' and utilizes a {lesson_arch} interactive model."
            ),
        }
        return state

    state["response"] = {"role": "assistant", "content": content}
    if tool_call:
        if tool_call.get("name") == "show_whiteboard":
            import uuid

            from ..services import whiteboard_service

            args = tool_call.get("arguments") or {}
            session = whiteboard_service.create_session(
                lesson_id=state["lesson_id"],
                user_id=str(ctx.get("user_id") or ""),
                tool_call_id=f"tc_{uuid.uuid4().hex[:8]}",
                title=str(args.get("title") or "Whiteboard"),
                intent=str(args.get("intent") or ""),
                elements=args.get("elements"),
            )
            if session is not None:
                tool_call = {
                    **tool_call,
                    "arguments": {**args, "whiteboard_session_id": session.id},
                }
        elif tool_call.get("name") == "show_coding_lab":
            import uuid

            from ..services import coding_lab_service

            args = tool_call.get("arguments") or {}
            session = coding_lab_service.create_session(
                lesson_id=state["lesson_id"],
                user_id=str(ctx.get("user_id") or ""),
                tool_call_id=f"tc_{uuid.uuid4().hex[:8]}",
                title=str(args.get("title") or "Coding Lab"),
                language=str(args.get("language") or "javascript"),
                instructions=str(args.get("instructions") or ""),
                files=args.get("files"),
                entrypoint=args.get("entrypoint"),
                expected_stdout=args.get("expectedStdout"),
                hint=args.get("hint"),
            )
            if session is not None:
                tool_call = {
                    **tool_call,
                    "arguments": coding_lab_service.tool_args_from_session(session),
                }
        elif tool_call.get("name") == "update_coding_lab":
            from ..services import coding_lab_service

            args = tool_call.get("arguments") or {}
            session = coding_lab_service.update_session_from_tool_args(
                lesson_id=state["lesson_id"],
                user_id=str(ctx.get("user_id") or ""),
                args=args,
            )
            if session is not None:
                tool_call = {
                    **tool_call,
                    "arguments": coding_lab_service.tool_args_from_session(session),
                }
        state["response"]["tool_call"] = tool_call
    return state


def build_tutor_graph():
    g = StateGraph(TutorState)
    g.add_node("tutor_chat", tutor_chat_node)
    g.add_edge(START, "tutor_chat")
    g.add_edge("tutor_chat", END)
    return g.compile()


_TUTOR_GRAPH = None


async def run_tutor_chat(
    messages: List[Dict[str, Any]], course_id: str, lesson_id: str, lesson_context: Dict[str, Any]
) -> Dict[str, Any]:
    global _TUTOR_GRAPH
    if _TUTOR_GRAPH is None:
        _TUTOR_GRAPH = build_tutor_graph()

    result = await _TUTOR_GRAPH.ainvoke(
        {
            "messages": messages,
            "course_id": course_id,
            "lesson_id": lesson_id,
            "lesson_context": lesson_context,
            "response": None,
        },
        config=agent_run_config(
            "tutor",
            run_name="tutor_chat",
            course_id=course_id,
            lesson_id=lesson_id,
            surface="post",
        ),
    )
    return result.get("response") or {
        "role": "assistant",
        "content": "No response was generated by the tutor assistant.",
    }
