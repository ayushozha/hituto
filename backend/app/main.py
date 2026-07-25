"""FastAPI entrypoint for the Generative UI Learning Platform backend."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.v1 import api_router
from .core.config import get_settings
from .core.db import init_db
from .core.logging import configure_logging
from .core.middleware import register_middleware
from .core.tracing import configure_tracing
from .providers.registry import validate_provider_config
from .coursegen import recover_orphaned_generations
from .rag.ingest import recover_orphaned_ingestions
from .services.video_source_service import recover_orphaned_video_ingestions


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_tracing()
    validate_provider_config(get_settings())
    init_db()
    # In-memory generation/ingestion tasks don't survive a restart; requeue any rows a
    # previous process left stranded so they never get stuck "In Queue"/"ingesting" forever.
    recover_orphaned_generations()
    recover_orphaned_video_ingestions()
    # Runs inside the event loop: re-downloads durable uploads from storage and re-ingests.
    recover_orphaned_ingestions()
    yield


app = FastAPI(title="Hi Tuto", version="0.1.0", lifespan=lifespan)

register_middleware(app)

app.include_router(api_router)


@app.get("/health")
def health():
    s = get_settings()
    from urllib.parse import urlparse

    return {
        "ok": True,
        "llm": s.llm_provider,
        "llm_endpoint": urlparse(s.llm_base_url).hostname or "",
        "llm_model": s.llm_model,
        "search": s.search_provider,
        "embedding": s.embedding_provider,
        "vector_store": s.vector_store,
        "voice": {"enabled": s.voice_ready(), "brain": s.voice_brain},
    }


# Serve the built React SPA same-origin when a build is present (production single-container
# deploy). The dashboard and the lesson iframes call relative routes (/courses, /gen, /image,
# ...), so co-serving the SPA keeps everything same-origin. Mounted LAST so the API routers
# above always win; skipped in local dev where no build dir exists (the Vite proxy handles it).
_spa_dir = os.getenv(
    "SPA_DIST", os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
)
if os.path.isdir(_spa_dir):
    app.mount("/", StaticFiles(directory=_spa_dir, html=True), name="spa")
