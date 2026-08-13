"""
Structured events for the tutor.

One JSON object per line on the `sat_tutor.events` logger, so latency
percentiles and failure rates can be computed from logs without a metrics
backend. Every field is a scalar or a short label.

Student content never appears here. A pasted SAT question, a student's
working, and a tutor's explanation are all private, and a log line is the
easiest place to leak them by accident — so long strings are replaced with
their length rather than trusted to the caller's discipline.
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

logger = logging.getLogger("sat_tutor.events")

# Anything longer than a label is treated as content and withheld.
MAX_VALUE_CHARS = 80


def _safe(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return f"<{len(value)} chars withheld>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: _safe(value) for key, value in fields.items()}}
    logger.info(json.dumps(payload, sort_keys=True))


@asynccontextmanager
async def timed(event: str, **fields: Any) -> AsyncIterator[dict[str, Any]]:
    """
    Time a block and emit one event when it finishes, success or not.

    Yields a dict the caller can add fields to before the event is written —
    useful for outcomes only known at the end, like whether a reviewer
    approved.

    Timing is observational only; nothing in this helper is persisted.
    """
    started = time.monotonic()
    extra: dict[str, Any] = {}
    outcome = "ok"
    try:
        yield extra
    except Exception as error:
        outcome = type(error).__name__
        raise
    finally:
        log_event(
            event,
            ms=round((time.monotonic() - started) * 1000),
            outcome=outcome,
            **{**fields, **extra},
        )
