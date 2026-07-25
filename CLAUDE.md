# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository. It assumes you know nothing about the project. `AGENTS.md` is a near-mirror of
this file for other coding agents — keep the two in sync when updating either.

## Project overview

Hi Tuto turns a topic (or an uploaded PDF/video source) into a structured, interactive
course. Lessons are generated just-in-time as untrusted HTML "capsules" rendered in
sandboxed iframes, plus an AI text tutor and a real-time voice instructor.

- **Backend** (`backend/`): FastAPI + LangGraph, Python >= 3.11, deps managed by `uv`
  (`uv.lock` committed, package name `hituto-backend`).
- **Frontend** (`frontend/`): React 18 + Vite 5 + TypeScript + Tailwind 3.
- **Whiteboard viewer** (`whiteboard-viewer/`): separate minimal Excalidraw SPA embedded by
  the tutor/voice whiteboard widget via iframe + postMessage.
- The root `README.md` is an exhaustive architecture reference — read it for deep dives on
  any subsystem, but it can lag recent migrations; **the code wins**.
- `specs/` holds design documents (`studio_v2`, `insights`, `course_gen`, `fast_gen`,
  `design_agents`, `learner_profile`, `onboarding`, `audience_gating`, `frontend`, …). Some
  are proposals, not descriptions of shipped behavior — check the code before treating a
  spec as current.

## Build, run, and test commands

The root `Makefile` is a **stub** — do not rely on `make install`/`make dev`/`make test`.
Use these instead.

**Backend** (run from `backend/`):
```bash
uv sync --all-extras                       # install (extras: postgres, documents, voice; dev group has pytest)
uv run uvicorn app.main:app --reload --port 8078   # dev server — see the port note below
uv run ruff check app                       # lint (CI runs `ruff check backend/app`; line-length 100)
uv run pytest                               # run tests (asyncio_mode=auto, testpaths=["tests"])
uv run pytest tests/test_foo.py::test_bar   # single test
uv run pytest -m "not live"                 # skip tests that hit real OpenAI Realtime (need RUN_LIVE_VOICE=1)
uv run langgraph dev                        # LangSmith Studio Agent Server (graphs from app/studio.py via langgraph.json)
```

> **Port discrepancy (real, as of this writing):** `frontend/vite.config.ts` proxies API
> routes to `http://127.0.0.1:8078`, while `README.md`, `frontend/.env.example`, and the
> default in `backend/scripts/render_start.sh` say **8077**. Run the dev server on 8078 to
> match the live Vite proxy (IPv4 loopback matters — `localhost` can resolve to `::1` and
> break the proxy), or change the proxy target in `vite.config.ts` to 8077.

**Frontend** (run from `frontend/`):
```bash
npm install
npm run dev        # Vite dev server on :5173
npm run build      # tsc -b && vite build — this is also the only typecheck; no lint/test script
```
The dev proxy forwards `/courses` (with WebSocket upgrade), `/sources`, `/shared`,
`/insights`, `/profile`, `/billing`, `/gen`, `/image`, `/audio`, `/mesh`, `/maps`,
`/health` to the backend.

**Whiteboard viewer** (run from `whiteboard-viewer/`):
```bash
npm run dev        # :5174; point the frontend at it with VITE_WHITEBOARD_VIEWER_URL=http://localhost:5174
npm run build && rsync -a --delete --exclude _headers dist/ ../frontend/public/whiteboard/   # ship with the main frontend
```

**Local auth-free demo**: set `AUTH_DISABLED=1` in `backend/.env` and
`VITE_AUTH_DISABLED=1` in `frontend/.env` — all requests then run as `user_id="dev"`.

**CI** (`.github/workflows/ci.yml`) only lints (`ruff check backend/app`) and calls the
no-op `make test-backend` stub; there is no frontend job. So run `uv run pytest` and
`npm run build` yourself before considering a change done.

## Architecture: the boundaries that matter

The backend enforces a strict layering (`CONTRIBUTING.md` calls this out). Violating it is
the most common way to break the design:

- **API layer** `app/api/v1/` — thin HTTP/WS/SSE handlers only, no business logic. `v1` is
  a *Python package path, not a URL prefix* — each sub-router keeps its own path
  (`/courses`, `/sources`, `/insights`, `/profile`, `/billing`, …) so public URLs have no
  `/v1`.
- **Service layer** `app/services/` — orchestration, projections, state transitions.
- **Agent layer** — `coursegen/`, `tutor/`, `voice/`, `insights/`, `lesson_edit/`. Agents **must never
  import each other.**
- **Protocol layer** — `rag/`, `a2ui/`, `capsule/`, `surface/`. Shared contracts that
  **must never import an agent.** `surface/` builds the design-agnostic `LessonSurface`
  (per-kind grounding digest + capabilities) that tutor/voice ground on.
- **Infrastructure** — `core/` (config, db, auth, progress, tasks, tracing), `models/`,
  `providers/`. Providers are the only place external services (LLM, search, media, mesh,
  embeddings, storage, transcription) are called; agents/services go through them.

### The two-engine course generator (`coursegen/`)
Entry point is `app/coursegen/__init__.py` (`run_generation`, `run_syllabus_planning`,
`resume_generation`, `recover_orphaned_generations`). Two implementations sit behind it,
selected by `DEEP_AGENTS_ENABLED`:
- **LangGraph pipeline** (`graph.py`) — the default/production path: a deterministic
  6-stage state machine `interpret → research → asset_plan → generate → post_process →
  persist`, with a repair loop retrying `generate ↔ post_process` up to `MAX_GEN_RETRIES`
  (2). Typed state is `state.py:GenState`. The `generate` node dispatches authoring to a
  per-design agent (`coursegen/designs/` registry — `page` covers page/slide + A2UI + the
  fast_gen section fan-out, `studio` the manifest path, `reading` the document-grounded
  annotated-source design gated by `READING_DESIGN_ENABLED`; unknown modes fail closed to
  `page`). Pipeline speed/streaming behavior (skeleton + fragment SSE frames, parallel
  interpret, async mesh with late-join, hedged retries, per-stage model tiers) is specced
  in `specs/fast_gen/` and flag-gated via `GEN_*` env vars (see `.env.example`). An
  optional chapter-outline human-in-the-loop review (`knobs.review_outline`,
  `MAX_OUTLINE_REVISIONS`) lets users revise the outline before generation spends credits.
- **Deep Agent** (`agents/orchestrator.py`) — flag-gated; a `deepagents` orchestrator
  delegating to role subagents (`agents/roles/`). On failure it falls back to the LangGraph
  path. **Fail-closed is the rule everywhere**: any invalid agent output degrades to plain
  text/the deterministic path, never a broken render.

**Studio v2 presentations**: `presentation.py` resolves each lesson to `studio | page |
slide` (explicit knobs win; `auto` picks studio for spatial/3D topics). Studio lessons
don't let the LLM write HTML — the model fills a Pydantic-validated `StudioManifest`
(`studio_manifest.py`; modes like `specimen`, `simulation`, `process-cutaway`) which
`studio_renderer.py` renders through server-owned templates/runtime under
`coursegen/skills/ui-studio-style/`. The rendered HTML still passes the capsule gate like
any other lesson. Design spec: `specs/studio_v2/`.

### Untrusted-HTML security gate (`capsule/`)
All generated lesson HTML is untrusted. `capsule/postprocess.py` is the gate every capsule
must pass before it can be served: it rejects parent/storage access and placeholder tokens,
normalizes images to a lazy loader, and appends the only two first-party scripts allowed to
talk to the parent — the Hi-Tuto **lesson bridge** (edit mode, learning events, HTML
export, iframe auto-sizing; parent side in `frontend/src/lib/lessonBridge.ts`) and the
**GuideBridge iframe runtime** (agent page control, next section). The result is served
under a strict CSP (`capsule/csp.py`) inside a `sandbox="allow-scripts"` iframe. If you
touch lesson output, it flows through here.

### GuideBridge page control (`app/agentbridge.py`)
Agent-driven page control (observe/click/type/highlight + the tutor cursor) runs on the
external `guidebridge` SDK, not the hand-rolled lesson bridge: `app/agentbridge.py` holds
one process-wide `guidebridge.AgentBridge` exposing a WebSocket at
`/courses/{course_id}/lessons/{lesson_id}/agent-bridge/ws` (its router is re-exported by
`api/v1/agentbridge.py`). The bridge session id is `{user_id}:{lesson_id}`, derived
server-side from the `?access_token=` JWT plus a course/lesson ownership check — a
client's claimed session id is verified, never trusted. The voice agent's page tools call
`bridge.call_tool(...)`; the browser side is `@guidebridge/react`'s `useAgentFrame` in
`features/lesson/Viewer.tsx`; the in-iframe half is the runtime injected by the capsule
gate above.

### Trusted UI vs. untrusted UI (tutor & voice)
The tutor/voice agents answer via LLM function-calling with **two rendering paths**:
- `render_ui` → **A2UI** (`a2ui/`): a Pydantic-validated JSON tree of typed nodes rendered
  from a fixed React registry (`frontend/src/components/A2UIRenderer.tsx`). No raw HTML
  reaches the DOM. Invalid tree → `None` → fallback. This is the preferred path.
- `generate_ui` → untrusted HTML escape hatch, stored ephemerally
  (`capsule/generative_ui.py`) and served through the same capsule gate into a sandboxed
  iframe.

The tutor streams over SSE as AG-UI frames (`RUN_STARTED → TEXT_MESSAGE_CONTENT →
TOOL_CALL_* → RUN_FINISHED`). Voice (`voice/`, off unless `VOICE_ENABLED=true` +
`OPENAI_REALTIME_API_KEY`) is a FastAPI WebSocket bridged to OpenAI Realtime S2S; the
legacy Deepgram cascade files are kept importable for manual recovery but are not a runtime
fallback. Voice shares the same widget tool defs but adds **page tools** that drive the
live capsule through GuideBridge (`scroll_to`, `highlight`, `click`, `set_value`,
`observe_page`).

One shared widget is the **whiteboard**: tutor/voice `show_whiteboard`/`update_whiteboard`
tools persist scenes as `WhiteboardSession` rows (`models/course.py`) through
`services/whiteboard_service.py`, so both agents ground on the same board; the frontend
renders it by embedding the `whiteboard-viewer` SPA (`frontend/src/lib/whiteboardContext.ts`
carries board state into tutor/voice prompts).

### Learning insights (`insights/`)
Private, user-owned learning analytics. The frontend batches client events
(`frontend/src/lib/learningEvents.ts` → `POST /insights/events/batch`);
`services/insight_service.py` aggregates them into deterministic snapshots
(`models/insight.py`), refreshed in the background via `core/tasks.py:spawn`.
`insights/agent.py` is an optional, tightly-constrained LangChain agent that rewrites the
narrative of a deterministic report — evidence-bound, fail-closed (returns `None` unless
`INSIGHTS_AGENT_ENABLED` + key), never invents claims. Design spec: `specs/insights/`.

### Surgical lesson edit (`lesson_edit/` + `specs/a2ui_surgical_edit/`)
Targeted refine uses a dedicated **lesson-edit agent** (`app/lesson_edit/`, LLM via
`LESSON_EDIT_LLM_*` → coursegen → global) — not coursegen authoring. It receives **one
unit only** (HTML section outerHTML or A2UI section/node JSON), never the full capsule.
Preserve-UI prompts keep zinc/Tailwind consistency. Slash inserts (`/quiz` `/map` …) and
`PATCH …/a2ui/sections/{id}` / `…/html/sections/{id}` go through this agent.
`SURGICAL_EDIT_ENABLED` default on; `COURSEGEN_A2UI_LESSONS` stays opt-in for authoring.


### Learner profile (`models/profile.py` + `services/profile_service.py`)
Onboarding-captured learning preferences (goal, modalities, structure, pacing, practice,
prior knowledge — the first-run dialog asks only the four highest-signal ones, so
pacing/practice usually stay at defaults) — the semantic/declarative agent memory shared by
the content agents. Thin router `api/v1/profile.py` (`GET`/`PUT /profile`); the frontend
pops a first-run onboarding dialog over the app after signup
(`features/onboarding/OnboardingPage.tsx`) and prefills course-creation defaults from its
`hints`. Coursegen gets a **snapshot** (`course.knobs["learner_profile"]`, injected in
`course_service.create_course`, rendered by `coursegen/prompt.py` and the syllabus
planners); the tutor gets a **live read** (`tutor/context.py` →
`prompts_util.build_system_prompt`). One mapping (`profile_service.prompt_lines`) keeps
both agents in sync; everything is fail-closed (no profile → byte-identical prompts).
Deleted with `DELETE /insights/data`. Design spec: `specs/learner_profile/`.

### Billing / course credits (`api/v1/billing.py` + `services/billing_*.py`)
Course-creation is metered in credits. Allowances come from the Clerk Billing plan on the
session JWT (`pla` claim, parsed in `core/auth.py`; plan slugs normalized in
`services/billing_plans.py`); spend is recorded as credit-event rows (`models/billing.py`)
when generation starts — outline review stays free. `GET /billing/usage` reports remaining
credits. Fail-open by default: creation is only blocked at zero remaining when
`BILLING_ENFORCE` is set; `BILLING_PLAN_NAME`/`BILLING_COURSE_CREDITS` only rename/resize
the free tier when the JWT carries no plan.

### Config & providers
- **One `Settings` object** — `app/core/config.py` (Pydantic Settings, reads
  `backend/.env`; no env prefix, so var names map directly). Each agent can override its
  LLM independently via `TUTOR_LLM_*`, `COURSEGEN_LLM_*`, `VOICE_LLM_*`, `INSIGHTS_LLM_*`,
  `LESSON_EDIT_LLM_*` (each falls back to the global `LLM_*`), and coursegen additionally has per-stage tiers
  (`COURSEGEN_PLANNER_LLM_*`, `COURSEGEN_REVIEW_LLM_*`, …). Media providers are similarly
  pluggable (`IMAGE_PROVIDER`, `MESH_PROVIDER`, `SEARCH_PROVIDER`, …). Most features are
  flag/key-gated and degrade gracefully — see `README.md` "Environment Variables" and
  `backend/.env.example` for the full list.
- Fire-and-forget background work goes through `core/tasks.py:spawn` (holds a strong task
  reference) — never bare `asyncio.create_task`, which can be garbage-collected mid-flight.
- In-memory generation/ingestion tasks don't survive a restart; `main.py`'s lifespan
  requeues orphaned generations, video ingestions, and document ingestions at boot.
- Production validates required provider keys at startup and raises if missing; tests set
  `SKIP_PROVIDER_VALIDATION=1` and patch fakes in `tests/conftest.py`.

### Auth (Clerk) + InsForge platform
Auth is **Clerk**: the frontend wraps the app in `ClerkProvider` (`main.tsx` — boot throws
without `VITE_CLERK_PUBLISHABLE_KEY`) and registers a per-request token getter in
`lib/authToken.ts`; the backend (`core/auth.py`) verifies the RS256 session JWT against
Clerk's JWKS (`CLERK_JWT_ISSUER`; optional `CLERK_JWKS_URL` override and
`CLERK_AUTHORIZED_PARTIES` `azp` allow-list) — the backend only ever sees a `user_id`
(`sub` claim) plus an optional Billing plan slug. SSE/EventSource and WebSocket requests
pass the token as `?access_token=`. Clerk skills (`clerk-setup`, `clerk-custom-ui`, …) are
pinned in `skills-lock.json` — use them before hand-rolling Clerk calls.

[InsForge](https://insforge.dev) (project **TrailLearn**) is no longer the auth provider
but remains the platform for storage buckets (`STORAGE_BUCKET`, `MESH_STORAGE_BUCKET`), the
waitlist table (`frontend/src/lib/insforge.ts`, anon key only), and frontend hosting;
root-level `migrations/` holds InsForge SQL migrations (CLI format). Use the installed
`insforge`/`insforge-cli`/`insforge-debug` skills before hand-rolling any InsForge API
call; app keys live in `.env` files, CLI credentials in `.insforge/project.json` — never
hardcode or commit keys.

### Persistence
- **Dev = SQLite** (`sqlite:///./hituto.db`). `init_db()` runs `create_all()` then
  `_ensure_added_columns()` — a hand-rolled additive migration that ALTERs in new nullable
  columns (SQLite only), so **adding a nullable column to a model needs no migration in
  dev**.
- **Prod = Postgres + pgvector** (`DATABASE_URL`, `VECTOR_STORE=pgvector`) via Alembic —
  migration history lives in `backend/alembic/versions/` (initial schema through learner
  profiles, whiteboard sessions, share tokens, credit events, and more); new Postgres
  schema changes need a new revision there. On SQLite, RAG embeddings fall back to keyword
  search.
- ORM models: `models/course.py` (Course→Lessons→Artifacts + WhiteboardSession, cascade
  delete), `models/insight.py` (learning events/snapshots/preferences), `models/profile.py`
  (LearnerProfile), `models/billing.py` (credit events), and `models/source.py`
  (document-grounding tables). Artifacts are **versioned and never overwritten**.
  `lessons.share_token` is the one field granting anonymous read access.

## Code style guidelines

- Python: 4-space indent, 100-char lines, ruff-clean (`CONTRIBUTING.md`). New backend tests
  go under `backend/tests/` as `test_*.py`.
- Respect the import boundaries above — they're the architecture, not a suggestion.
- Make new code read like the code around it; match the surrounding file's naming and
  comment density. Keep edits minimal and scoped.
- **Frontend design work**: invoke the repo's `hituto-design` skill before
  creating/modifying anything under `frontend/`, but treat `frontend/tailwind.config.js`
  (see its token-role comments) and `src/index.css` as the live source of truth — the
  palette has moved from the warm-cream "Thinkby" look to a minimalist zinc-neutral system
  with a single green accent (legacy names `plum`/`lilac`/`cobalt` now alias neutrals), and
  the skill/`ui_ux_design/` docs may lag that shift.
- Frontend source is organized as `features/<area>/` (auth, billing, courses, insights,
  landing, lesson, marketing, onboarding, roadmap) plus shared `components/`, `lib/`, and
  `context/`.
- Progress to the frontend goes through the in-memory SSE broker (`core/progress.py`) —
  it's process-local (no cross-process pub/sub).

## Testing instructions

- Tests live in `backend/tests/` (`test_*.py`); run with `uv run pytest` from `backend/`
  (`asyncio_mode=auto` — async tests need no decorator).
- `tests/conftest.py` sets `SKIP_PROVIDER_VALIDATION=1` and autouse-patches fake providers,
  so the suite runs fully offline. Markers: `live` (hits real OpenAI Realtime; needs creds
  + `RUN_LIVE_VOICE=1`, skipped by default) and `no_fakes` (disables the fake provider
  patches for registry unit tests).
- **CI does not run the test suite** — it only lints. Always run `uv run pytest` (backend)
  and `npm run build` (frontend typecheck+bundle) locally before calling a change done.
- There is no frontend unit-test setup; `npm run build` (`tsc -b && vite build`) is the
  only frontend gate.

## Deployment

- **API**: Render native Python (no Docker) — root `render.yaml` blueprint +
  `backend/scripts/render_build.sh` (installs with `uv sync --frozen --all-extras
  --no-dev`) and `render_start.sh` (Postgres → `alembic upgrade head`; SQLite → optional
  seed dump from `backend/seed/`; then `uvicorn app.main:app` on `$PORT`, default 8077).
  Note the blueprint currently sets `AUTH_DISABLED=1` (demo deploy — no JWT verification);
  remove it and configure `CLERK_JWT_ISSUER` before exposing real users.
- `app/main.py` also mounts a built SPA from `backend/static` (override with `SPA_DIST`)
  same-origin when present, so a single-container deploy can serve the frontend too.
- **Frontend hosting, storage buckets, and the waitlist** stay on InsForge; root-level
  `migrations/` holds InsForge CLI-format SQL migrations.
- **Whiteboard viewer**: build and rsync into `frontend/public/whiteboard/` so it deploys
  with the main frontend (see the command above).

## Security considerations

- **All generated lesson HTML is untrusted** and must pass the capsule gate
  (`capsule/postprocess.py`) and ship under the strict CSP (`capsule/csp.py`) inside a
  `sandbox="allow-scripts"` iframe. Never bypass the gate or inject new first-party scripts
  into capsule output; the lesson bridge and GuideBridge runtime are the only sanctioned
  parent↔iframe channels.
- Prefer the A2UI (`render_ui`) path for agent-generated UI — validated typed JSON, no raw
  HTML in the DOM. `generate_ui` HTML is the escape hatch and must stay behind the capsule
  gate.
- Server-side identity is derived from the verified Clerk JWT only; a client-claimed
  session/user id (e.g. on the agent-bridge WebSocket) is verified against course/lesson
  ownership, never trusted.
- `AUTH_DISABLED=1` skips all JWT verification and runs everything as `user_id="dev"` —
  local demo (and, currently, the Render blueprint) only; never enable it for real users.
- Secrets live in `.env` files (backend) / `.env.local` (frontend) and
  `.insforge/project.json` (InsForge CLI) — none are committed; never hardcode keys. Only
  the InsForge **anon** key reaches the browser.
- `lessons.share_token` grants anonymous read access to a lesson — treat it as a
  capability URL.
- Voice/audio routes and the OpenAI Realtime key are server-side only; the browser talks to
  the backend WebSocket, never to OpenAI directly.

<!-- INSFORGE:START -->
## InsForge backend

This project uses [InsForge](https://insforge.dev): a Postgres-based backend (BaaS) that gives this app a database, authentication, file storage, edge functions, realtime, an AI model gateway, and payments through one platform.

- **Project:** **TrailLearn** (API base `https://8xdj824y.us-east.insforge.app`)
- **Skills:** these InsForge skills are installed for supported coding agents. Reach for them before implementing any InsForge feature instead of guessing the API:
  - `insforge`: app code with the `@insforge/sdk` client (database CRUD, auth, storage, edge functions, realtime, AI, email, and Stripe payments).
  - `insforge-cli`: backend and infrastructure via the `insforge` CLI (projects, SQL, migrations, RLS policies, storage buckets, functions, secrets, payment setup, schedules, deploys).
  - `insforge-debug`: diagnosing failures (SDK/HTTP errors, RLS denials, auth and OAuth issues) and running security or performance audits.
  - `insforge-integrations`: wiring external auth providers (Clerk, Auth0, WorkOS, Better Auth, etc.) for JWT-based RLS, or the OKX x402 payment facilitator.
  - `find-skills`: discovering additional skills on demand.
- **Credentials:** app code reads keys from `.env.local`; the CLI reads `.insforge/project.json`. Never hardcode or commit keys.

Key patterns:

- Database inserts take an array: `insert([{ ... }])`.
- Reference users with `auth.users(id)`; use `auth.uid()` in RLS policies.
- For storage uploads, persist both the returned `url` and `key`.
<!-- INSFORGE:END -->
