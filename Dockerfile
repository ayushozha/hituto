# syntax=docker/dockerfile:1
# Hi Tuto — single-container production image (hituto.com).
# Stage 1 builds the Vite SPA; stage 2 runs the FastAPI backend and co-serves the
# built SPA from backend/static (see backend/app/main.py), so the whole app is one
# origin behind one port (8077). backend/Dockerfile stays the API-only image used
# for InsForge compute; this root image is what the VPS/Coolify deploy builds.

# ---------- Stage 1: build the React/Vite frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /fe

# Vite inlines VITE_* at build time, so they must be present during `npm run build`.
# Coolify passes these as --build-arg from the app's build-time env vars.
ARG VITE_API_BASE_URL=
ARG VITE_AUTH_DISABLED=0
# Clerk — the frontend hard-fails ("Missing VITE_CLERK_PUBLISHABLE_KEY") when auth
# is enabled without this, so it must be set for any real deploy.
ARG VITE_CLERK_PUBLISHABLE_KEY=
# InsForge — waitlist + storage only (auth is Clerk).
ARG VITE_INSFORGE_URL=
ARG VITE_INSFORGE_ANON_KEY=
ARG VITE_WHITEBOARD_VIEWER_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_AUTH_DISABLED=$VITE_AUTH_DISABLED \
    VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY \
    VITE_INSFORGE_URL=$VITE_INSFORGE_URL \
    VITE_INSFORGE_ANON_KEY=$VITE_INSFORGE_ANON_KEY \
    VITE_WHITEBOARD_VIEWER_URL=$VITE_WHITEBOARD_VIEWER_URL

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: FastAPI backend runtime ----------
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

# uv for reproducible installs from the committed uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Build toolchain for any wheels without prebuilt binaries (liteparse, etc.).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Install dependencies first (cache layer), then the app.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --all-extras --no-dev --no-install-project

# Whole backend tree: app/, alembic/, game_kits/ (served by api/v1/tools.py), seed/.
COPY backend/ ./
RUN uv sync --frozen --all-extras --no-dev

# Built SPA co-served same-origin (backend/app/main.py mounts ./static at /).
COPY --from=frontend /fe/dist ./static

# Writable dir for the SQLite DB (mount a persistent volume here in prod).
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/hituto.db \
    PORT=8077

EXPOSE 8077
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8077/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8077"]
