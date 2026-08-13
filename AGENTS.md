# Repository Guidelines

## Project Structure & Module Organization

The app has a FastAPI backend and a React/Vite frontend. Backend routes, orchestration, SQLite persistence, and lesson models live in `backend/src/`. Python tests are in `backend/tests/`; real-provider evaluation cases and tooling are in `backend/eval/`. Frontend components, hooks, types, styles, and colocated `*.test.ts(x)` files live in `web/src/`. Runtime data is written to `backend/data/`, while `web/dist/`, caches, and `.env` are generated or local-only.

## Build, Test, and Development Commands

- `uv sync` installs locked Python and development dependencies.
- `uv run uvicorn main:app --app-dir backend/src --reload --reload-dir backend/src --port 8000` starts FastAPI.
- `cd web && npm install && npm run dev` starts Vite at `http://localhost:5173`; `/api` proxies to FastAPI.
- `uv run pytest -q` runs backend tests.
- `uv run mypy --config-file .mypy.ini backend/src backend/tests` type-checks Python.
- `cd web && npm test -- --run` runs Vitest once.
- `cd web && npm run build` type-checks and builds the production frontend.
- `uv run python backend/eval/run_eval.py --trials 3` runs paid provider-quality evaluations.

## Coding Style & Naming Conventions

Use four spaces, type hints, `snake_case` names, and `PascalCase` classes in Python. Keep request validation in Pydantic models and persistence inside `session_store.py`. TypeScript uses strict mode, two spaces, double quotes, `PascalCase` components, and `camelCase` helpers. Keep `backend/src/lesson_models.py` and `web/src/types/lesson.ts` aligned. No global formatter is configured; match nearby code and rely on MyPy, TypeScript, and tests.

## Testing Guidelines

Name Python tests `*_test.py` and frontend tests `*.test.ts` or `*.test.tsx`. Add regression coverage at the affected boundary. Unit tests must not call paid providers; use `backend/eval/` for prompt, schema, or model-quality changes. Run both suites, MyPy, and the frontend build before review.

## Commit & Pull Request Guidelines

History uses short imperative subjects, for example `Stop an outage hanging forever`. Keep commits focused. PRs should explain user-visible behavior, list verification commands, link issues, and include screenshots or recordings for UI changes. Call out API, model, database, or environment-variable changes. Never commit `.env`, provider credentials, or `backend/data/`.
