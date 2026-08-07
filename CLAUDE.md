# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SAT Live Tutor: a student pastes an SAT question (or uploads one PNG/JPEG), the backend solves it with an LLM, an **independent reviewer LLM verifies it before anything is taught**, and the browser then speaks the lesson (Deepgram TTS) while drawing it on a deterministic SVG board. The student can interrupt by text or voice to get a replacement explanation.

`README.md` / `SPEC.md` / `TODO.md` are the product spec and release gates. They describe v0.4; the classroom UI has since become a chat thread (`TutorMessage` actors + an `OrderedMap` index), which those documents do not yet cover — trust the code over the docs when they disagree.

## Commands

All commands assume the repo root `/Users/pramodthebe/Desktop/SAT/web_app` unless stated.

```bash
uv sync                          # Python deps into ./.venv
cp .env.example .env             # then fill LLM_API_KEY and DEEPGRAM_API_KEY

uv run rbt dev run               # backend on :9991; reads .rbtrc, loads .env, runs codegen, watches backend/
cd web && npm install && npm run dev   # frontend on :5173 (VITE_REBOOT_URL from web/.env.development)
```

Verification (all currently pass except the mypy note below):

```bash
cd backend && uv run pytest -q                                  # 14 tests, ~35s (each spins up a Reboot test harness)
cd backend && uv run pytest tests/tutor_servicer_test.py::TestTutorSession::test_student_interrupts_and_receives_a_replacement_explanation -q
uv run mypy --config-file .mypy.ini backend/src backend/tests api

cd web && npm test -- --run      # vitest (jsdom)
cd web && npx vitest run src/lib/scene.test.ts
cd web && npm run build          # tsc -b && vite build — this is the TS typecheck
```

All four are green. Note the README's mypy variant (`cd backend && MYPYPATH=... mypy src tests ../api`) does not pick up the root `.mypy.ini`, since mypy searches the cwd for config — prefer the `--config-file` form above.

Reboot lifecycle:

```bash
uv run rbt generate              # regenerate backend/api/ and web/src/api/ (rbt dev run does this for you)
uv run rbt dev expunge           # wipe durable state for application-name sat-live-tutor
uv run rbt inspect               # read live actor state from the CLI
```

`backend/api/` and `web/src/api/` are generated and gitignored — never edit them; edit `api/sat_tutor/v1/tutor.py` and regenerate.

## Architecture

### The one invariant

**An unverified answer is never taught.** `prepare_lesson` runs planner → reviewer → (if rejected) correction → re-review, and stores `status="error"` rather than a lesson if the second review still fails. A replan that changes `final_answer` is rejected outright (`tutor_servicer.py`, "Reject answer drift").

### Backend (Reboot actors, `backend/src/`)

- `api/sat_tutor/v1/tutor.py` — the pydantic API definition (state, request/response `Model`s, `Methods`). Two state types: `TutorSession` (one per random browser capability ID in `localStorage`) and `TutorMessage` (one per chat message).
- `tutor_servicer.py` (~1000 lines) — all servicer logic. `main.py` just wires servicers + `ciphertext_library()` + `ordered_map_library()` + dev OAuth.
- `tutor_agents.py` — the four system prompts (planner, reviewer, replanner, vision diagram extractor) and the `reboot.agents.pydantic_ai.Agent` instances. All agents are `Optional`: missing env vars leave them `None` and the servicer stores a "configure your .env" error instead of crashing.
- `lesson_models.py` — pydantic `LessonPlan` / `SceneCommand` union / `ImageQuestionAnalysis`. This is the structured-output contract with the LLM and is enforced with tight `Field` bounds (normalized 0–1 coordinates, ID charset, formula allowlist, graph bounds/marker containment).

Writer/transaction methods (`start_lesson`, `start_replan`, `request_voice_token`) bump a generation counter, set `status="thinking"`, and `schedule()` a durable workflow. Workflows (`prepare_lesson`, `replan_lesson`, `grant_voice_token`) do the slow LLM/HTTP work and write results back through `TutorSession.ref().per_workflow(alias).write(...)`.

Two patterns to preserve when editing workflows:

- **Generation guards.** Every workflow write starts with `if state.generation != request.generation: return`. A slow superseded workflow must never overwrite newer state.
- **Replay stability.** Reads inside a workflow that feed a prompt use `.per_workflow(alias)` (e.g. "Read original lesson for replan") so replay sees the same bytes; the comment there explains why an `.always()` read would corrupt the replay. `_append_assistant_message` deliberately uses `.always()` because it wants the *current* generation/index.

Schema evolution is additive-only once state exists: adding fields/methods is fine, but deleting or renaming a state type, method, or field tag makes the app refuse to boot. Use `rbt dev expunge` when you intentionally break compatibility in dev. See the reboot plugin's `python` skill (`references/api-schema-evolution.md`) before changing `api/sat_tutor/v1/tutor.py`.

### Secrets

`LLM_API_KEY` and `DEEPGRAM_API_KEY` never reach the browser. For voice, the backend calls Deepgram's `/v1/auth/grant` for a 60s token inside `at_least_once(...)`, encrypts it with Reboot `Ciphertext` (associated data bound to session ID + voice generation), and `consume_voice_token` decrypts and releases it exactly once, then clears it. Keep that shape if you touch voice.

### Chat persistence

`TutorSession` holds only `message_index_id` + counters; messages live in `TutorMessage` actors keyed `sat-message:<hash>:<revision>:<generation>:<role>`, indexed by an `OrderedMap` under key `f"{generation:020d}:{role_order}"` so ordering is user-then-assistant per generation. `reset()` bumps `chat_revision`, which mints a fresh index — old messages are orphaned, not deleted.

### Frontend (`web/src/`)

Routing is a `pathname` switch in `App.tsx` over the History API (`navigateTo` in `ProductPages.tsx`): `/` landing, `/pricing`, `/dashboard`, `/app` classroom. `/dashboard` and `/app` call `session.mutators.ensure(...)` first and render `SignInPage` on `PermissionDenied`/`Unauthenticated`.

- `App.tsx` — the whole classroom: `playLesson` walks beats, awaits Deepgram speech per beat, and applies scene commands on a timer. A `generation` ref cancels in-flight playback on interruption; a `lessonRequest` ref cancels stale polling. `waitForLesson` polls the reactive snapshot **with no timeout** — it only changes caption copy at 15/45/90s. Do not add a client deadline; a slow durable workflow finishing late is expected behavior.
- `lib/scene.ts` — the reducer. `applySceneCommand` is the single place a command mutates the board; note that applying a `graph`/`bar_chart`/`venn` evicts any existing one (one semantic visual panel at a time).
- `types/lesson.ts` — Zod mirror of `lesson_models.py`. **Change both together**, keeping field names snake_case on the wire (`lessonJson` is a JSON string field on the Reboot response; its contents stay snake_case).
- `components/TeachingCanvas.tsx` — renders a scene into a fixed 1200×760 SVG. Owns typography, flow layout, collision, and the `VISUAL_PANEL` rect.

### The visual contract (why the renderer looks over-engineered)

The LLM supplies *semantics only*; the renderer owns all geometry. This is a safety boundary — no model-authored HTML/SVG/JS ever reaches the DOM.

- Three coordinate spaces: `board` (full canvas), `source` (normalized over the fitted uploaded image), `diagram` (a square unit panel where equal coordinate deltas render as equal lengths — all constructed geometry must go here).
- `layout: "flow"` notes are measured and stacked by `FlowNotes`; x/y/width/height are ignored. `graph`/`bar_chart`/`venn` are `layout: "auto"` and get the reserved panel.
- `layout: "absolute"` labels are laid out collectively by `layoutLabels()`, not per-command: the coordinate is the **point the label names**, and the renderer centres the box on it, measures the real text, clamps it into its space, and nudges overlapping labels apart. Never reintroduce a fixed label box — the model cannot know rendered text width. The three prompts state this contract; keep them in sync with the renderer.
- A point is always a `marker`, never a constant curve; formulas are restricted to an allowlisted name set and evaluated with mathjs.
- `_normalize_lesson()` in `tutor_servicer.py` is the server-side gate: it drops highlights whose `target_id` doesn't match an earlier written note, drops Venn/bar charts whose keywords don't appear in the question, enforces one visual family per lesson, dedupes diagram commands, and — if a beat ends up with zero valid commands — substitutes the beat caption as a flow note so the verified lesson is still teachable. New command kinds must be handled here, not only in the schema.
- For uploaded images the vision model returns `ImageQuestionAnalysis` (semantic specs only), and `_compile_diagram()` compiles it into trusted `rebuild:*` scene commands; `_inject_diagram()` then strips any model-authored diagram/graph commands from the plan. The model is told not to emit them in the first place, but the code enforces it.

## Working notes

- This directory is not a git repository.
- `output/` and `.playwright-cli/` hold E2E artifacts and are gitignored; there is no automated Playwright suite in the repo — the live E2E pass referenced in the README was manual.
- Tests never call a real provider: `backend/tests/tutor_servicer_test.py` subclasses `TutorSessionServicer` and overrides the workflows with deterministic lessons. Do the same rather than mocking HTTP.
