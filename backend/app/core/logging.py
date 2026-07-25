"""Centralized logging configuration.

Plain stdlib logging — structured logging / tracing / metrics are intentionally
out of scope (kept as a future ops concern). Call `configure_logging()` once at
startup; use `get_logger(__name__)` everywhere else.
"""
from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
