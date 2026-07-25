"""ASGI middleware registration, kept out of main.py so the entrypoint stays thin."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings


def _cors_origins() -> list[str]:
    """FRONTEND_ORIGIN may be a single origin or a comma-separated allowlist."""
    raw = (get_settings().frontend_origin or "").strip()
    if not raw:
        return ["http://localhost:5173"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def register_middleware(app: FastAPI) -> None:
    """Wire CORS and private-cache controls for child report surfaces."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def private_report_cache_control(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            path == "/reports"
            or path.startswith("/reports/")
            or path == "/report-invitations"
            or path.startswith("/report-invitations/")
        ):
            response.headers["Cache-Control"] = "no-store, private"
        return response
