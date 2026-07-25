"""ASGI middleware registration, kept out of main.py so the entrypoint stays thin."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings


def _cors_origins() -> list[str]:
    """FRONTEND_ORIGIN may be a single origin or a comma-separated allowlist."""
    raw = (get_settings().frontend_origin or "").strip()
    if not raw:
        return ["http://localhost:5173"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def register_middleware(app: FastAPI) -> None:
    """Wire all app middleware. Currently just CORS (allowlist from FRONTEND_ORIGIN)."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
