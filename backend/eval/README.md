# Evaluation suites

Prompt and schema changes fail *silently*. A lesson still renders — it is just
worse. Nothing in `pytest` can tell you that the planner stopped writing on the
board, or that a diagram is upside down, because both are valid data.

These suites run the real pipelines against cases with known answers.

## Running

```bash
uv run python backend/eval/run_eval.py                        # both suites
uv run python backend/eval/run_eval.py --suite lessons
uv run python backend/eval/run_eval.py --suite diagnoses
uv run python backend/eval/run_eval.py --trials 3             # one sample proves little
uv run python backend/eval/run_eval.py --min-accuracy 0.9     # exit 1 below threshold
uv run python backend/eval/run_eval.py --json /tmp/eval.json  # raw results
```

Needs `LLM_API_KEY` and `OPENAI_MODEL`, read from the repository `.env`.
Exit codes: `0` pass, `1` below `--min-accuracy`, `2` no credentials.

This calls a real provider and costs tokens, so it is deliberately **not** part
of `pytest`. A full run is roughly 30 model calls.

## The suites

**`cases/lessons.json`** — 16 questions across algebra (linear, systems,
quadratic, exponential), probability, statistics, sets, geometry, trigonometry,
ratios, and four Reading & Writing types. Runs planner → `_normalize_lesson` →
reviewer → correction → re-review, exactly as `prepare_lesson` does.

Watch `first pass wrote nothing`: it counts lessons whose opening pass produced
beats with no writing at all. It was 8/16 before the write/draw split.

**`cases/diagnoses.json`** — 18 pieces of student working, half correct and half with a
planted error at a known step. Twelve Math, six Reading & Writing (subject
identification, transition logic, evidence selection, tone). Runs diagnostician →
verifier → correction.

The Reading & Writing cases exist because a step-located verdict looked like a poor fit
for verbal reasoning. Measurement disagreed — they score the same as the Math ones — so
keep them: the assumption was wrong once and could be wrong again after a prompt change.

The number that matters is `FALSE ACCUSATIONS` — telling a student their correct
work is wrong. Half the cases are correct submissions specifically so this is
measurable. It should always be 0.

## Adding a case

Append to the JSON. Lesson cases take `accept`, a list of acceptable answer
forms — answers are compared with typography normalized (Unicode minus, `·`
versus `*`, `π` versus `pi`, whitespace), because grading on one exact substring
produces false failures. Diagnosis cases take the true `verdict` and the
1-indexed `error_step` (`0` when the work is correct).

## Interpreting a run

Single runs are noisy: identical configurations have swung 14/16 → 16/16 → 15/16.
Use `--trials 3` before believing a pass rate moved, and prefer the structural
counters (false accusations, silent first passes, degenerate segments) over the
headline — those are enforced by code, not luck.
