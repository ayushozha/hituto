# SAT Live Tutor Development Notes

## Commands

```bash
uv sync
uv run uvicorn main:app --app-dir backend/src --reload --reload-dir backend/src --port 8000
cd web && npm install && npm run dev

uv run pytest -q
uv run mypy --config-file .mypy.ini backend/src backend/tests
cd web && npm test -- --run && npm run build
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`. Override it with `VITE_API_PROXY_TARGET` when needed.

## Backend architecture

- `main.py`: FastAPI models, anonymous HttpOnly browser cookie, CORS, and routes.
- `session_store.py`: SQLite schema, ordered messages, quotas, and generation-guarded writes.
- `tutor_service.py`: lesson, replan, work-check, and Deepgram token orchestration.
- `lesson_engine.py`: deterministic normalization, diagram compilation, and work-feedback rendering.
- `lesson_models.py`: strict Pydantic contracts for plans and scene commands.
- `tutor_agents.py`: provider configuration and prompts.

An unverified answer is never taught. The lesson path is planner → reviewer → optional correction → re-review. Replans must preserve the verified final answer. Work diagnoses have an independent reviewer and return `unclear` instead of guessing.

SQLite state belongs to a random `sat_session` cookie scoped to one browser. This is not user authentication. Any commercial deployment needs real accounts and server-side ownership checks.

## Frontend architecture

- `App.tsx`: routing and classroom interaction state.
- `lib/tutorApi.ts`: typed REST calls and session refresh.
- `types/lesson.ts`: Zod mirror of the Python lesson contract.
- `lib/scene.ts`: deterministic scene reducer.
- `components/TeachingCanvas.tsx`: lesson renderer.
- `components/ProductPages.tsx`: landing, pricing, dashboard, and local-session copy.

Keep `lesson_models.py` and `types/lesson.ts` in sync. New scene commands must also be handled by backend normalization, the scene reducer, renderer, and tests.

## Security and quality boundaries

Permanent provider keys never enter the browser. Deepgram temporary tokens are returned immediately and are not stored. Logs must not contain questions, student working, or lesson narration.

Unit tests never call paid providers. Run `backend/eval/run_eval.py --trials 3` after changing prompts, models, output schemas, or normalization rules. Preserve reviewer gates, answer-drift checks, image size/type validation, and generation checks.
