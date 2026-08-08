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

## Since the MVP — complete

- [x] Split the planner's command union into `write` and `draw`; beats with nothing written
      on the board went from 8/16 to 0/16 of the evaluation set.
- [x] Centre absolute labels on the point they name, measure them from the real text, and
      separate overlapping ones.
- [x] Snap near-coincident diagram vertices so shared corners actually meet.
- [x] Drop zero-length "label" segments and duplicate charts before review.
- [x] Convert question coordinates into the panel's y-down space; diagrams no longer render
      upside down.
- [x] "Check my work": a diagnostician behind its own reviewer gate, which never asserts an
      unverified verdict and asks instead of guessing when the working is unclear.
- [x] An Excalidraw whiteboard for the student's steps, with two named composer modes.
- [x] Evaluation suites in `backend/eval/`, with an accuracy gate and a JSON artifact.
- [x] Bind every session to the account that created it; a second identity is denied.

## Required before charging users

- [ ] Choose the production OAuth provider and supply its credentials. The wiring is done:
      set `OAUTH_PROVIDER` to google, github, auth0, or ory with `OAUTH_CLIENT_ID` /
      `OAUTH_CLIENT_SECRET` (and `OAUTH_DOMAIN` for auth0/ory), then register
      `<APP_ORIGIN>/__/oauth/callback` with that provider. Until then sign-in stays on the
      development account picker and ownership is only enforced there.
- [x] Store the authenticated owner on every session and enforce ownership. Sessions created
      before this carry no owner and stay claimable — expunge dev state before relying on it.
- [x] Add account-level daily usage quotas and a per-minute burst limit, enforced on the
      three paths that spend provider calls. Tune with DAILY_LESSON_LIMIT,
      DAILY_CHECK_LIMIT, and BURST_LIMIT.
- [ ] Add automated abuse protection beyond per-account limits (a single actor with many
      accounts is still uncapped).
- [ ] Add billing, subscription status, and entitlement checks.
- [ ] Replace private-beta pricing copy with validated plans only after product pricing is decided.
- [ ] Add an operator view for usage, errors, model spend, and Deepgram spend.
- [x] Add structured logging: one JSON event per line on `sat_tutor.events`, carrying
      durations and outcomes with student content withheld.
- [ ] Ship those events somewhere that computes percentiles and alerts. They are only
      written to stdout today.
- [x] Stop swallowing transient provider failures. Reboot already replays a workflow step
      that raises, reusing memoized results for completed steps; a blanket `except`
      defeated it and turned a passing 503 into a dead lesson.
- [ ] Bound the retry. A total provider outage now leaves the student in 'thinking'
      indefinitely, because nothing gives up. Needs a replay-safe deadline.
- [x] Create a representative SAT Math and Reading & Writing evaluation set.
- [ ] Set and meet an accuracy threshold before marketing answer reliability. The gate exists
      (`run_eval.py --min-accuracy`); the number has not been chosen.
- [ ] Extend the diagnosis suite beyond Math. All 12 cases are Math, and "step 2 is wrong"
      maps badly onto a Reading & Writing question.
- [ ] Measure first-audio and barge-in latency. Lesson preparation is now timed
      server-side (`lesson.prepared`, `work.diagnosed`); both of the others are
      client-side and still unmeasured.
- [x] Account deletion: `TutorSession.forget` overwrites the question, working, lessons,
      and every chat message, then crypto-shreds the session's ciphertext scope so any
      encrypted remnant is permanently undecryptable. Erases in pages of 100; the
      response reports whether more remain.
- [x] Expose deletion in the product: a "Your data" panel on the dashboard with a
      two-step confirmation, reporting how much was erased.
- [ ] Add a privacy policy, terms, and a stated retention period. These are legal
      documents and need review, not just drafting.
- [ ] Deploy backend and frontend behind TLS; verify WSS and microphone permissions.
- [ ] Configure secrets, environment separation, backup, and rollback.
- [ ] Review the transitive moderate `@hono/node-server` Windows advisory; do not use the incompatible npm downgrade suggested by `npm audit`.

## Product improvements after first paid cohort

- [ ] Add PDF and camera ingestion only after defining their preprocessing and retention rules.
- [ ] Add deterministic number-line and table commands.
- [ ] Persist board playback position, not only the prepared lesson.
- [ ] Stream/prepare the first teaching beat earlier to reduce perceived latency.
- [ ] Add selected-board-element follow-up questions.
- [ ] Render tutor feedback onto the student's own whiteboard instead of a second board.
- [ ] Lay the board and the conversation side by side; stacked, the thread is snug on short
      screens even with the board collapsed.
- [ ] Add lesson history and targeted practice only after core tutoring metrics are strong.
