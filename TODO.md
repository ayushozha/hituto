# SAT Live Tutor — Release Checklist

## Product MVP — complete

- [x] Public landing page with an in-product voice-and-board demonstration.
- [x] Browser-local dashboard backed by the current SQLite lesson snapshot.
- [x] Dedicated classroom with one text composer and no tool picker.
- [x] Honest private-beta pricing surface without a fake checkout.
- [x] Responsive desktop and mobile product shell.
- [x] Fireworks DeepSeek V4 Flash structured planner.
- [x] Fireworks Qwen3.7 Plus image planner/reviewer with structured-output repair.
- [x] Independent reviewer and one correction cycle.
- [x] FastAPI lesson/replan endpoints with SQLite persistence and generation guards.
- [x] Bounded provider deadlines with clear terminal errors.
- [x] Anonymous HttpOnly browser sessions for the private beta.
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

- [x] Accept a topic, not just a question. "Teach me probability" had no verifiable
      answer, so the planner overflowed `final_answer` or wrote prose that any follow-up
      then contradicted — which is what surfaced as "the follow-up changed the verified
      answer". A topic now becomes one representative SAT question first.

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
- [x] Remove the heavyweight actor runtime and generated RPC bindings in favor of FastAPI REST.

## Required before charging users

- [ ] Choose and implement production authentication, then bind each SQLite session to the
      verified account. The current random browser cookie is not an identity boundary.
- [x] Add browser-session daily usage quotas and a per-minute burst limit, enforced on the
      three paths that spend provider calls. Tune with DAILY_LESSON_LIMIT,
      DAILY_CHECK_LIMIT, and BURST_LIMIT.
- [ ] Add automated abuse protection beyond browser-session limits; clearing cookies can
      currently reset an allowance.
- [ ] Resolve two high-severity transitive advisories introduced with Excalidraw:
      `lodash-es` (code injection via `_.template`, reached through the mermaid parser) and
      `nanoid` (predictable ids / non-terminating generation). `npm audit fix` does nothing;
      its suggested fix downgrades Excalidraw to 0.17.6, which is a semver-major step
      backwards and breaks the integration. Options are upstream, or dropping the
      whiteboard. Do not ship to paying users without deciding.
- [ ] Add billing, subscription status, and entitlement checks.
- [ ] Replace private-beta pricing copy with validated plans only after product pricing is decided.
- [ ] Add an operator view for usage, errors, model spend, and Deepgram spend.
- [x] Add structured logging: one JSON event per line on `sat_tutor.events`, carrying
      durations and outcomes with student content withheld.
- [ ] Ship those events somewhere that computes percentiles and alerts. They are only
      written to stdout today.
- [x] Classify transient provider failures so request-level retries can be bounded safely.
- [x] Bound provider work with `PROVIDER_DEADLINE_MINUTES` (default 5) and store a terminal
      student-facing error instead of leaving the lesson in `thinking`.
- [x] Create a representative SAT Math and Reading & Writing evaluation set.
- [ ] Set and meet an accuracy threshold before marketing answer reliability. The gate exists
      (`run_eval.py --min-accuracy`); the number has not been chosen.
- [x] Extend the diagnosis suite beyond Math. Six Reading & Writing cases added (subject
      identification, transition logic, evidence selection, tone). The worry that
      "step 2 is wrong" would not fit verbal reasoning did not survive measurement:
      18/18 verdicts across three runs, exact step in 17-18 of 18.
- [ ] Measure first-audio and barge-in latency. Lesson preparation is now timed
      server-side (`lesson.prepared`, `work.diagnosed`); both of the others are
      client-side and still unmeasured.
- [x] Browser-session deletion removes the snapshot, usage counters, and every chat message
      from SQLite. Temporary Deepgram tokens are never stored.
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
- [x] Lay the board and the conversation side by side. The board is a panel of its own
      rather than a paragraph inside a chat bubble, and past explanations can be pinned
      back into it.
- [ ] Add lesson history and targeted practice only after core tutoring metrics are strong.
