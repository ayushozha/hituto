# SAT Live Tutor

A standalone SAT tutor that solves a pasted or uploaded SAT question, verifies the answer, then teaches it aloud while building a live visual explanation. The student can interrupt by text or voice and ask for a different explanation.

## Working MVP

- Public landing page with a real product demonstration and clear beta positioning
- Authenticated student dashboard with the real current lesson or an honest empty state
- Dedicated live classroom with one question box, PNG/JPEG upload, and no teaching-tool picker
- Private-beta pricing page with no fake checkout or invented paid plan
- SAT Math and Reading & Writing questions with answer choices
- Fireworks DeepSeek V4 Flash for text questions and Qwen3.7 Plus for image questions
- Independent reviewer and correction pass before a lesson is taught
- Natural Deepgram streaming speech, captions, pause, replay, and barge-in
- Deterministic SVG function graphs with real coordinate markers
- Deterministic probability bar charts and two-set Venn diagrams
- KaTeX equations and bounded geometry primitives
- Durable Reboot lesson workflows with late-result recovery and generation guards
- Reboot OAuth sign-in and authenticated external calls
- Student-friendly failure states; an unverified answer is never taught

For an image question, upload one clear PNG or JPEG up to 4 MB. The original image stays visible on the teaching canvas so the tutor can point to its real diagram, passage, and labels. PDF and camera capture are not included in this MVP.

## Configure

Copy the template and add the real backend-only credentials:

```bash
cp .env.example .env
```

```dotenv
LLM_API_KEY=...
OPENAI_MODEL=accounts/fireworks/models/deepseek-v4-flash-0731
VISION_MODEL=accounts/fireworks/models/qwen3p7-plus
LLM_BASE_URL=https://api.fireworks.ai/inference/v1
DEEPGRAM_API_KEY=...
DEEPGRAM_TTS_MODEL=aura-2-thalia-en
APP_ORIGIN=http://localhost:5173
```

The permanent LLM and Deepgram keys never enter the browser. The backend exchanges the Deepgram key for a short-lived token, encrypts it at rest with Reboot Ciphertext, and releases it once to the active browser session.

## Run locally

```bash
uv sync
uv run rbt dev run
```

In a second terminal:

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The public site links to `/pricing`; starting a lesson opens `/app`, and signing in also unlocks `/dashboard`.

## Verify

```bash
cd backend
uv run pytest -q
MYPYPATH=src:api:../api uv run mypy src tests ../api

cd ../web
npm test -- --run
npm run build
```

The live E2E pass verified the [commercial landing page](./output/playwright/commercial-landing.png), [student dashboard](./output/playwright/commercial-dashboard.png), mobile layouts, the local OAuth flow, an [uploaded geometry question with source-image overlays](./output/playwright/image-upload-lesson.png), a [quadratic with actual point markers](./output/playwright/mvp-quadratic-live.png), a [two-set Venn problem](./output/playwright/mvp-venn-live.png), a [discrete probability distribution](./output/playwright/mvp-probability-live.png), Deepgram token delivery, and a student interruption.

## Commercial launch boundary

This is a commercial beta shell around a validated tutoring MVP, not yet a public paid service. It does not pretend otherwise: beta access is $0 and there is no checkout. Before charging users, complete the launch gates in [TODO.md](./TODO.md): production OAuth, account ownership, lesson history, rate/usage limits, billing and entitlements, monitoring, SAT evaluation, privacy terms, and deployment.
