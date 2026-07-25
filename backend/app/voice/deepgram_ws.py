"""Small compatibility helpers for Deepgram WebSocket clients."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


async def connect_websocket(url: str, *, headers: Mapping[str, str], **kwargs: Any) -> Any:
    """Connect with websockets across versions that renamed the headers kwarg."""
    import websockets

    try:
        return await websockets.connect(url, additional_headers=dict(headers), **kwargs)
    except TypeError:
        return await websockets.connect(url, extra_headers=dict(headers), **kwargs)
