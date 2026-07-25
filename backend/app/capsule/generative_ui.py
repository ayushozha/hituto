"""Ephemeral, process-global store for tutor-generated HTML UI capsules (Path B / generate_ui).

`generate_ui` produces UNTRUSTED HTML. We run it through the SAME security gate as lesson
capsules (`capsule.postprocess.postprocess`) and, only on pass, stash the sanitized HTML
in-memory keyed by an unguessable `ui_id`. The iframe `GET` (a SEPARATE HTTP request, not part of
the chat/WS turn) fetches it by `ui_id`, and the route re-verifies the requester owns the tagged
lesson — `ui_id` unguessability is not the only guard on an authed route.

In-memory + process-local + single-worker, matching the SSE/progress brokers. A TTL bounds
lifetime; entries are purged lazily on access. Persistence beyond the live session is a non-goal.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from .postprocess import postprocess
from .shell import assemble_generate_ui

# 30-minute lifetime: long enough for a learner to interact, short enough to bound memory.
_TTL_SECONDS = 30 * 60
_MAX_ENTRIES = 256


@dataclass
class _Entry:
    html: str
    user_id: str
    lesson_id: str
    expires_at: float


_STORE: dict[str, _Entry] = {}
_LOCK = Lock()


def _purge_locked(now: float) -> None:
    for key in [k for k, e in _STORE.items() if e.expires_at <= now]:
        _STORE.pop(key, None)
    # Hard cap: if still over, evict the soonest-to-expire entries.
    if len(_STORE) > _MAX_ENTRIES:
        overflow = len(_STORE) - _MAX_ENTRIES
        for key in sorted(_STORE, key=lambda k: _STORE[k].expires_at)[:overflow]:
            _STORE.pop(key, None)


def sanitize_and_store_with_checks(
    html: str, *, user_id: str, lesson_id: str
) -> tuple[Optional[str], dict]:
    """Run the capsule security gate; return (`ui_id`, checks).

    Model HTML is first wrapped in the server-owned zinc design shell (tokens, overflow
    clamps, control chrome), then gated — same assemble-then-sandbox pattern as lesson
    section fan-out. `ui_id` is None when `postprocess` fails closed.
    """
    assembled = assemble_generate_ui(html or "")
    clean, checks = postprocess(assembled)
    if not checks.get("passed"):
        return None, checks
    ui_id = secrets.token_urlsafe(16)
    now = time.monotonic()
    with _LOCK:
        _purge_locked(now)
        _STORE[ui_id] = _Entry(
            html=clean, user_id=user_id, lesson_id=lesson_id, expires_at=now + _TTL_SECONDS
        )
    return ui_id, checks


def sanitize_and_store(html: str, *, user_id: str, lesson_id: str) -> Optional[str]:
    """Run the capsule security gate; on pass, store sanitized HTML and return a `ui_id`."""
    ui_id, _checks = sanitize_and_store_with_checks(html, user_id=user_id, lesson_id=lesson_id)
    return ui_id


def get_ui_html(ui_id: str, *, user_id: str, lesson_id: str) -> Optional[str]:
    """Return sanitized HTML iff the entry exists, is unexpired, and matches owner + lesson."""
    now = time.monotonic()
    with _LOCK:
        _purge_locked(now)
        entry = _STORE.get(ui_id)
        if entry is None or entry.user_id != user_id or entry.lesson_id != lesson_id:
            return None
        return entry.html


def _clear_for_tests() -> None:
    with _LOCK:
        _STORE.clear()
