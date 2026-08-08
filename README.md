# SAT Live Tutor

A standalone SAT tutor that solves a pasted or uploaded SAT question, verifies the answer, then teaches it aloud while building a live visual explanation. The student can interrupt by text or voice and ask for a different explanation.

## Working MVP

- Public landing page with a real product demonstration and clear beta positioning
- Authenticated student dashboard with the real current lesson or an honest empty state
- Chat classroom with two named modes: ask a question, or check your own working
- "Check my work": the student writes their steps and the tutor marks the first one that
  breaks, hands back a hint rather than the answer, and says so honestly when it cannot judge
- An Excalidraw whiteboard to write those steps on, or the text box if you prefer
- Sessions bound to the account that created them
- PNG/JPEG question upload
- Private-beta pricing page with no fake checkout or invented paid plan
- SAT Math and Reading & Writing questions with answer choices
- Fireworks DeepSeek V4 Flash for text questions and Qwen3.7 Plus for image questions
- Independent reviewer and correction pass before a lesson is taught, and before a
  diagnosis of the student's work is shown
- Evaluation suites over 16 lesson questions and 12 pieces of student working
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
cd backend && uv run pytest -q
uv run mypy --config-file .mypy.ini backend/src backend/tests api

cd web && npm test -- --run && npm run build
```

Tests cannot see a quality regression — a worse lesson is still valid data. After any
prompt, schema, or model change, run the evaluation suites as well:

```bash
uv run python backend/eval/run_eval.py            # both suites; calls a real provider
uv run python backend/eval/run_eval.py --trials 3 # single runs are noisy
```

See [backend/eval/README.md](./backend/eval/README.md). Most recent run: 16/16 lessons
served with the correct answer and no beat left unwritten; 12/12 diagnoses correct with the
exact error step and zero false accusations on correct working.

Browser passes have covered a typed geometry lesson with an enlarged teaching diagram, a
quadratic, Deepgram token delivery, a student interruption, and the check-my-work loop end to
end — steps written on the whiteboard, read back, and the first wrong one marked.

## Commercial launch boundary

This is a commercial beta shell around a validated tutoring MVP, not yet a public paid service. It does not pretend otherwise: beta access is $0 and there is no checkout. Sessions are now owned, and an SAT evaluation set exists. Before charging users, complete
the remaining launch gates in [TODO.md](./TODO.md): a production OAuth provider (the app
still runs with `prod=None`), usage quotas and rate limits, billing and entitlements,
monitoring and cost visibility, privacy terms and account deletion, and TLS deployment.
