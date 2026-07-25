"""Spoken acknowledgements for the voice tutor's widget tools.

Page control (observe/scroll/click/type/highlight + the Tutor cursor) moved to
the GuideBridge SDK: the voice agent calls ``app.agentbridge.bridge.call_tool``
and the browser side is guidebridge's own WebSocket + iframe runtime. The old
``PageToolRouter`` (page tools tunneled over the voice socket) is gone; its
stale-id fuzzy retry now lives inside guidebridge itself.
"""
from __future__ import annotations

_ACKS = {
    "create_quiz": "Here's a quick quiz. Try it on screen and I'll react to how you do.",
    "show_flashcards": "I've put flashcards on screen. Flip through them when you're ready.",
    "show_code_exercise": "Here's a coding exercise to try in the panel.",
    "create_game": "Let's use a quick game. It's on screen now.",
    "show_diagram": "Here's a diagram to make the idea easier to see.",
    "show_formula_calculator": "Here's a formula calculator. Try values and watch the steps.",
    "show_whiteboard": "I've opened a whiteboard sketch on screen. You can edit it.",
    "render_ui": "Here's an interactive breakdown on screen. Take a look.",
    "generate_ui": "Here's an interactive visual on screen. Take a look.",
}
