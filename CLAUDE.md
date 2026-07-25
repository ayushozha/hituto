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
  `design_agents`, `learner_profile`, `onboarding`, `audience_gating`, `frontend`, …) — but
  it is **gitignored** ("Local design specs (not shared via git)"), so it is absent from a
  fresh clone and the `specs/…` paths cited below and in code docstrings often won't
  resolve. When present, treat it as proposals, not shipped behavior — the code wins.
- `mcp-apps/` (`coding-lab`, `whiteboard`): standalone npm/Vite packages that re-expose two
  lesson widgets as portable MCP Apps for external MCP hosts. Nothing in `backend/` imports
  them — the in-product surfaces are the native tutor/voice widgets, and these mirror the
  same AG-UI event contract (`frontend/src/lib/codingLabAgUi.ts`).
- `ui_ux_design/` holds the **platform** (React app chrome) design system —
  `hituto-design/SKILL.md` + mascot assets. `.claude/` is gitignored, so no skill is
  actually installed in-repo; read that SKILL.md directly (agents that have it installed
  know it as `build-hituto-ui`).

## Build, run, and test commands

The root `Makefile` is a **stub** — do not rely on `make install`/`make dev`/`make test`.
Use these instead.

**Backend** (run from `backend/`):
```bash
uv sync --all-extras                       # install (extras: postgres, documents, voice; dev group has pytest)
uv run uvicorn app.main:app --reload --port 8077   # dev server — see the port note below
uv run ruff check app                       # lint (CI runs `ruff check backend/app`; line-length 100)
uv run pytest                               # run tests (asyncio_mode=auto, testpaths=["tests"])
uv run pytest tests/test_foo.py::test_bar   # single test
uv run pytest -m "not live"                 # skip tests that hit real OpenAI Realtime (need RUN_LIVE_VOICE=1)
uv run langgraph dev                        # LangSmith Studio Agent Server (graphs from app/studio.py via langgraph.json)
```

> **Port 8077 everywhere:** `frontend/vite.config.ts`, `README.md`, and
> `frontend/.env.example` all use **8077** — run the dev server on 8077 to match the Vite
> proxy. The proxy targets IPv4 loopback (`http://127.0.0.1:8077`) on purpose: uvicorn
> binds `127.0.0.1`, and `localhost` can resolve to `::1` first and break the proxy, so
> keep it as the literal IPv4 address.

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

**Authoring prompts are markdown, not Python strings**: `coursegen/prompt.py` builds the
`SYSTEM` prompt from `coursegen/prompts/lesson_system.md` (with the Three.js/GLTF/Chart.js
CDN URLs substituted from `capsule/postprocess.py`, so prompt ↔ allowlist ↔ CSP can't
drift) plus `coursegen/skills/hituto-generated-lesson-design/SKILL.md`; deep-agent roles
inject further packs from `coursegen/skills/` (`capsule-authoring`, `ui-page-style`,
`ui-slide-deck`, `ui-studio-style`, `visualization`, `simulation`, `subjects`, …) via
`agents/prompt_loader.py`. Changing how lessons look or behave is usually a SKILL.md edit —
and `tests/test_generated_lesson_design.py` asserts on those files' contents (design
tokens, "no fixed sidebar", skill ordering), so update the assertions alongside the prompt.

### Untrusted-HTML security gate (`capsule/`)
All generated lesson HTML is untrusted. `capsule/postprocess.py` is the gate every capsule
must pass before it can be served: it rejects parent/storage access and placeholder tokens,
normalizes images to a lazy loader, and appends the only two first-party scripts allowed to
talk to the parent — the Hi-Tuto **lesson bridge** (edit mode, learning events, HTML
export, iframe auto-sizing; parent side in `frontend/src/lib/lessonBridge.ts`) and the
**GuideBridge iframe runtime** (agent page control, next section). The result is served
under a strict CSP (`capsule/csp.py`) inside a `sandbox="allow-scripts"` iframe. If you
touch lesson output, it flows through here.

Capsules also never embed third-party asset URLs — they point at the first-party **tool
server** (`api/v1/tools.py`): `/gen` (prompt → image), `/image` (query → image), `/audio`
(TTS), `/mesh` (3D), `/maps/geocode` + `/maps/tiles/{z}/{x}/{y}.png`. With no provider keys
these return deterministic placeholder SVG/WAV rather than failing, so a keyless dev box
still renders complete lessons — and because every asset is same-origin, the capsule CSP
gets away with `default-src 'none'` + `img-src 'self'` (no third-party media origins). This
is what those paths in the Vite proxy list are for.

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

Two widgets are **durable and shared by both agents** (state in the DB, not the transcript,
so tutor and voice ground on the same thing):
- **whiteboard** — `show_whiteboard`/`update_whiteboard` persist scenes as
  `WhiteboardSession` rows (`models/course.py`) via `services/whiteboard_service.py`; the
  frontend embeds the `whiteboard-viewer` SPA and
  `frontend/src/lib/whiteboardContext.ts` carries board state into tutor/voice prompts.
- **coding lab** — `show_coding_lab` opens a multi-file editor+runner backed by
  `CodingLabSession` rows via `services/coding_lab_service.py`; run/check results flow as
  AG-UI events (`frontend/src/lib/codingLabAgUi.ts`, runners in `codingLabRunners.ts`).
  Prefer it over the simpler `show_code_exercise` textarea.

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
`SURGICAL_EDIT_ENABLED` default on. `COURSEGEN_A2UI_LESSONS` **defaults off** —
course chapters use **HTML section fan-out** with live `gen_fragment` streaming into
GenerationTheater (the better authoring UX). A2UI remains available for tutor/voice
widgets and surgical section edits; set `COURSEGEN_A2UI_LESSONS=1` only to experiment
with A2UI-authored lesson trees (not the product path).


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
  (`COURSEGEN_PLANNER_LLM_*`, `COURSEGEN_REVIEW_LLM_*`, …).
- **LLM** goes through one OpenAI-compatible client (`providers/llm.py`); the backend
  (base URL + key + model) is selected purely by env, so swapping providers is code-free.
  The default is now **Anthropic's OpenAI-compat endpoint** —
  `LLM_BASE_URL=https://api.anthropic.com/v1`, `LLM_MODEL=claude-sonnet-5`, key via
  `LLM_API_KEY`/`ANTHROPIC_API_KEY` (legacy `GMI_*`/`NEBIUS_*` aliases still resolve).
  Agents are tiered by what they're for: coursegen authors capsules on `claude-opus-5`,
  the SSE tutor answers on `claude-haiku-4-5`, everything else inherits the global Sonnet.
- **Media** (`providers/media.py`) now runs on **OpenAI**: images via
  `POST /v1/images/generations` (`gpt-image-1.5`), lesson TTS via `POST /v1/audio/speech`
  (`gpt-4o-mini-tts`), keyed by `OPENAI_IMAGE_API_KEY` → falls back to `OPENAI_API_KEY` /
  `OPENAI_REALTIME_API_KEY`. The old GMI request-queue / TokenRouter image backends are
  removed — their `GMI_*`/`TOKENROUTER_*` config fields survive as inert stubs and
  `GMIMedia`/`TokenRouterMedia` are back-compat aliases of `OpenAIMedia`, so `IMAGE_PROVIDER`
  is effectively always `openai`. `MESH_PROVIDER`/`SEARCH_PROVIDER` remain pluggable. Most
  features are flag/key-gated and degrade gracefully — see `README.md` "Environment
  Variables" and `backend/.env.example` for the full list.
- Fire-and-forget background work goes through `core/tasks.py:spawn` (holds a strong task
  reference) — never bare `asyncio.create_task`, which can be garbage-collected mid-flight.
- In-memory generation/ingestion tasks don't survive a restart; `main.py`'s lifespan
  requeues orphaned generations, video ingestions, and document ingestions at boot.
- Production validates required provider keys at startup and raises if missing; tests set
  `SKIP_PROVIDER_VALIDATION=1` and patch fakes in `tests/conftest.py`.

### Auth (Clerk) + InsForge platform
Auth is **Clerk**: the frontend wraps the app in `ClerkProvider` (`main.tsx` — boot throws
on a missing `VITE_CLERK_PUBLISHABLE_KEY` unless `VITE_AUTH_DISABLED=1`; the provider still
mounts whenever a key *is* present, so landing/dashboard Clerk components don't crash,
while `AuthContext.tsx` splits into `ClerkAuthProvider` vs a `DevAuthProvider` that
short-circuits to the synthetic `dev` user and calls no Clerk hooks) and registers a
per-request token getter in `lib/authToken.ts`; the backend (`core/auth.py`) verifies the RS256 session JWT against
Clerk's JWKS (`CLERK_JWT_ISSUER`; optional `CLERK_JWKS_URL` override and
`CLERK_AUTHORIZED_PARTIES` `azp` allow-list) — the backend only ever sees a `user_id`
(`sub` claim) plus an optional Billing plan slug. SSE/EventSource and WebSocket requests
pass the token as `?access_token=`. Clerk skills (`clerk-setup`, `clerk-custom-ui`, …) are
pinned in `skills-lock.json` — use them before hand-rolling Clerk calls.

[InsForge](https://insforge.dev) (project **HiTuto**) is no longer the auth provider
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
- **Two separate design systems — don't cross them.** The React app chrome is governed by
  `frontend/tailwind.config.js` (read its token-role comments) + `src/index.css`, the live
  source of truth: zinc-neutral ground (`paper #FAFAFA` / `sand` / `line`), `ink #18181B`
  text, **amber** `brand #D97706` for app chrome/links/selection, and `lime #16A34A`
  reserved for learning progress/success and the mascot (legacy `plum`/`lilac`/`cobalt` now
  alias neutrals). Generated lesson capsules have their own contract in
  `backend/app/coursegen/skills/hituto-generated-lesson-design/SKILL.md` (its own inline
  Tailwind token block, Plus Jakarta Sans / JetBrains Mono, no amber, no host chrome — the
  trusted shell owns title/progress/tutor). Prose docs in `ui_ux_design/` can lag both.
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

- **API**: no hosted blueprint in-repo — run FastAPI yourself (`uv sync --all-extras`,
  then `uvicorn app.main:app` on port 8077). Prod uses Postgres (`DATABASE_URL` +
  `alembic upgrade head`, `VECTOR_STORE=pgvector`); local uses SQLite. Configure
  `CLERK_JWT_ISSUER` for real users; never enable `AUTH_DISABLED=1` outside local demo.
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
  local demo only; never enable it for real users.
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

- **Project:** **HiTuto** (API base `https://nse4cp27.us-east.insforge.app`)
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
