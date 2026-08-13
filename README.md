# SAT Live Tutor

SAT Live Tutor turns a pasted question, uploaded image, or topic request into a verified voice-and-visual lesson. Students can interrupt for another explanation or submit their own working for targeted feedback.

## Stack

- React 18, TypeScript, and Vite
- FastAPI with an explicit JSON REST API under `/api`
- SQLite for browser-scoped lessons, messages, and usage limits
- PydanticAI with Fireworks-hosted text and vision models
- Deepgram streaming speech, captions, and microphone input
- Excalidraw, SVG, KaTeX, and MathJS for student and tutor visuals

The backend verifies each lesson or work diagnosis before returning it. Generation checks prevent a slow, superseded request from overwriting newer state. A random HttpOnly `sat_session` cookie identifies one browser; production user accounts are not implemented yet.

## Configure

```bash
cp .env.example .env
```

Add `LLM_API_KEY` and `DEEPGRAM_API_KEY` to `.env`. Provider secrets remain server-side. FastAPI exchanges the permanent Deepgram key for a short-lived token and returns it without persisting it.

## Run locally

Start the API:

```bash
uv sync
uv run uvicorn main:app --app-dir backend/src --reload --reload-dir backend/src --port 8000
```

Start the browser app in another terminal:

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to port 8000. If that port is occupied, start FastAPI on another port and launch Vite with, for example, `VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev`.

## Verify

```bash
uv run pytest -q
uv run mypy --config-file .mypy.ini backend/src backend/tests
cd web && npm test -- --run && npm run build
```

Prompt and model quality require real-provider evaluation:

```bash
uv run python backend/eval/run_eval.py --trials 3
```

See [backend/eval/README.md](./backend/eval/README.md) for suites and scoring.

## Data and launch boundary

SQLite defaults to `backend/data/sat_tutor.db`; override it with `SAT_TUTOR_DB`. “Delete my data” removes that browser session’s rows. The current private beta has daily and burst limits but no billing.

Before charging users, add real authentication and account ownership, automated abuse protection, billing and entitlements, monitoring and cost alerts, reviewed privacy/retention terms, backups, and TLS deployment. Track the complete list in [TODO.md](./TODO.md).
