# SAT Live Tutor — Release Checklist

## Product MVP — complete

- [x] Public landing page with an in-product voice-and-board demonstration.
- [x] Authenticated dashboard backed by the current durable lesson snapshot.
- [x] Dedicated classroom with one text composer and no tool picker.
- [x] Honest private-beta pricing surface without a fake checkout.
- [x] Responsive desktop and mobile product shell.
- [x] Fireworks DeepSeek V4 Flash structured planner.
- [x] Fireworks Qwen3.7 Plus image planner/reviewer with structured-output repair.
- [x] Independent reviewer and one correction cycle.
- [x] Durable Reboot lesson/replan workflows and generation guards.
- [x] No false browser timeout for late durable results.
- [x] Authenticated browser calls plus app-internal scheduled workflow authorization.
- [x] Natural Deepgram TTS, Flux STT, captions, pause, replay, and interruption.
- [x] KaTeX notes and bounded geometry commands.
- [x] Function curves with real numeric point markers.
- [x] Deterministic numeric bar charts.
- [x] Deterministic two-set Venn diagrams.
- [x] One visual panel with replacement semantics.
- [x] Invalid highlight-reference normalization.
- [x] Student-friendly verification errors.
- [x] PNG/JPEG question upload with validation, preview, aspect-correct source rendering, and overlays.
- [x] Unsupported PDF/camera scope shown honestly.
- [x] Real API browser tests for image upload, graph, Venn, distribution, and replan.
- [x] Backend tests, mypy, frontend tests, and production build pass.

## Required before charging users

- [ ] Choose and configure the production Reboot OAuth provider.
- [ ] Store the authenticated owner on every session and enforce ownership.
- [ ] Add account-level daily/monthly usage quotas.
- [ ] Add request rate limits and automated abuse protection.
- [ ] Add billing, subscription status, and entitlement checks.
- [ ] Replace private-beta pricing copy with validated plans only after product pricing is decided.
- [ ] Add an operator view for usage, errors, model spend, and Deepgram spend.
- [ ] Add structured logging, tracing, latency percentiles, and alerts.
- [ ] Add retry/circuit-breaker product behavior for provider outages.
- [ ] Create a representative SAT Math and Reading & Writing evaluation set.
- [ ] Set and meet an accuracy threshold before marketing answer reliability.
- [ ] Measure first-lesson, first-audio, and barge-in latency.
- [ ] Add privacy policy, terms, retention policy, and account deletion.
- [ ] Deploy backend and frontend behind TLS; verify WSS and microphone permissions.
- [ ] Configure secrets, environment separation, backup, and rollback.
- [ ] Review the transitive moderate `@hono/node-server` Windows advisory; do not use the incompatible npm downgrade suggested by `npm audit`.

## Product improvements after first paid cohort

- [ ] Add PDF and camera ingestion only after defining their preprocessing and retention rules.
- [ ] Add deterministic number-line and table commands.
- [ ] Persist board playback position, not only the prepared lesson.
- [ ] Stream/prepare the first teaching beat earlier to reduce perceived latency.
- [ ] Add selected-board-element follow-up questions.
- [ ] Add lesson history and targeted practice only after core tutoring metrics are strong.
