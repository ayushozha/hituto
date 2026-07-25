"""GuideBridge page-control WebSocket endpoint.

The route path (with course/lesson params for the ownership check) is defined
on the AgentBridge instance in ``app/agentbridge.py``; guidebridge builds the
websocket route, so this module only re-exports its router for inclusion.
"""
from __future__ import annotations

from ...agentbridge import bridge

router = bridge.router
