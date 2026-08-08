"""
Run the tutor's real pipelines against cases with known answers.

This exists because prompt and schema changes fail silently: a lesson still
renders, it is just worse. Every quality regression found so far — reasoning
effort, degenerate label segments, graph bounds, an over-strict prose rule,
upside-down diagrams — was caught here rather than by the test suite.

    uv run python backend/eval/run_eval.py                  # both suites
    uv run python backend/eval/run_eval.py --suite lessons
    uv run python backend/eval/run_eval.py --trials 3 --min-accuracy 0.9

Calls a real provider and costs tokens; it is deliberately not part of pytest.
"""
import argparse
import collections
import concurrent.futures
import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Callable, Optional, TypeVar

import httpx
import pydantic

T = TypeVar("T")

ROOT = pathlib.Path(__file__).resolve().parents[2]
# `backend/api` holds the generated Reboot bindings that tutor_servicer imports;
# run `uv run rbt generate` first if it is missing.
sys.path[:0] = [
    str(ROOT / "backend" / "src"),
    str(ROOT / "api"),
    str(ROOT / "backend" / "api"),
]

from lesson_models import (  # noqa: E402
    LessonDraft,
    LessonPlan,
    LessonReview,
    WorkDiagnosis,
)
import tutor_agents  # noqa: E402
from tutor_servicer import _diagnosis_to_lesson, _normalize_lesson  # noqa: E402

CASES = pathlib.Path(__file__).resolve().parent / "cases"


def load_env() -> dict[str, str]:
    """Read .env the way `rbt dev run --env-file` does, stripping each value.

    An unstripped trailing space in a key produces an illegal Authorization
    header, which surfaces as a connection error rather than an auth error.
    """
    env = dict(os.environ)
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*", line)
            if match and not line.lstrip().startswith("#"):
                env.setdefault(match.group(1), match.group(2))
    return {key: value.strip() for key, value in env.items() if isinstance(value, str)}


ENV = load_env()


def normalize(text: str) -> str:
    """Compare answers by content, not by typography."""
    lowered = text.lower()
    for dash in ("−", "–", "—"):
        lowered = lowered.replace(dash, "-")
    lowered = lowered.replace("·", "*").replace("×", "*").replace("π", "pi")
    return re.sub(r"\s+", "", lowered)


class Provider:
    def __init__(self) -> None:
        self.key = ENV.get("LLM_API_KEY", "")
        self.url = ENV.get("LLM_BASE_URL", "https://api.fireworks.ai/inference/v1") + "/chat/completions"
        self.model = ENV.get("OPENAI_MODEL", "")
        self.client = httpx.Client(timeout=300.0)

    def structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            self.url,
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "tools": [{
                    "type": "function",
                    "function": {"name": "final_result", "parameters": schema},
                }],
                "tool_choice": {"type": "function", "function": {"name": "final_result"}},
                "max_tokens": 8000,
            },
        )
        payload = response.json()
        if "choices" not in payload:
            raise RuntimeError(f"provider error {response.status_code}: {str(payload)[:180]}")
        calls = payload["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            raise RuntimeError(f"no tool call (finish={payload['choices'][0].get('finish_reason')})")
        return json.loads(calls[0]["function"]["arguments"])


def retrying(build: Callable[[], T], attempts: int = 3) -> T:
    """Mirror the agents' own `output_retries`."""
    last: Optional[Exception] = None
    for _ in range(attempts):
        try:
            return build()
        except pydantic.ValidationError as error:
            last = error
    raise RuntimeError(f"never produced a valid output: {str(last)[:200]}")


def lesson_stats(lesson: LessonPlan) -> dict[str, int]:
    kinds = collections.Counter(command.kind for beat in lesson.beats for command in beat.commands)
    degenerate = sum(
        1
        for beat in lesson.beats
        for command in beat.commands
        if command.kind in ("line", "arrow", "bracket")
        and (command.x, command.y) == (command.x2, command.y2)
    )
    return {
        "writes": kinds.get("text", 0) + kinds.get("math", 0),
        "semantic": kinds.get("graph", 0) + kinds.get("bar_chart", 0) + kinds.get("venn", 0),
        "degenerate": degenerate,
    }


def run_lesson_case(provider: Provider, case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    out: dict[str, Any] = {"id": case["id"]}
    question = case["question"]

    def plan(user: str) -> LessonPlan:
        return retrying(lambda: LessonDraft.model_validate(
            provider.structured(tutor_agents.PLANNER_PROMPT, user, LessonDraft.model_json_schema())
        ).to_plan())

    def review(lesson: LessonPlan, prior: str = "") -> LessonReview:
        return LessonReview.model_validate(provider.structured(
            tutor_agents.REVIEWER_PROMPT,
            "Verify this proposed SAT lesson against the original submission.\n\n"
            f"Student material:\n{question}\n\n"
            + (f"Prior issues:\n{prior}\n\n" if prior else "")
            + f"Proposed lesson JSON:\n{lesson.model_dump_json()}",
            LessonReview.model_json_schema(),
        ))

    try:
        lesson = _normalize_lesson(
            plan(
                "Prepare a verified, visual SAT lesson for the following student submission.\n\n"
                f"Student material:\n{question}\n\nSource kind: text"
            ),
            question_text=question,
        )
        out["first_pass"] = lesson_stats(lesson)
        verdict = review(lesson)
        out["cycles"] = 1
        if not verdict.approved:
            issues = "; ".join(verdict.issues[:3])
            out["issues"] = issues
            lesson = _normalize_lesson(
                plan(
                    "Correct the proposed SAT lesson using every reviewer issue below. Return a complete "
                    f"replacement lesson and keep the correct final answer.\n\nStudent material:\n{question}\n\n"
                    f"Reviewer issues:\n{issues}\n\nRejected lesson JSON:\n{lesson.model_dump_json()}"
                ),
                question_text=question,
            )
            verdict = review(lesson, issues)
            out["cycles"] = 2
        out["served"] = verdict.approved
        out["answer"] = lesson.final_answer
        out["correct"] = any(normalize(a) in normalize(lesson.final_answer) for a in case["accept"])
        out["final"] = lesson_stats(lesson)
    except Exception as error:
        out["error"] = str(error)[:200]
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def run_diagnosis_case(provider: Provider, case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    out: dict[str, Any] = {"id": case["id"], "want": case["verdict"]}
    question, work = case["question"], case["work"]

    def diagnose(user: str) -> WorkDiagnosis:
        return retrying(lambda: WorkDiagnosis.model_validate(
            provider.structured(tutor_agents.DIAGNOSTICIAN_PROMPT, user, WorkDiagnosis.model_json_schema())
        ))

    def verify(diagnosis: WorkDiagnosis) -> LessonReview:
        return LessonReview.model_validate(provider.structured(
            tutor_agents.DIAGNOSIS_REVIEWER_PROMPT,
            f"Verify this diagnosis of the student's work.\n\nQuestion:\n{question}\n\n"
            f"Student's work:\n{work}\n\nProposed diagnosis JSON:\n{diagnosis.model_dump_json()}",
            LessonReview.model_json_schema(),
        ))

    try:
        diagnosis = diagnose(
            f"Diagnose this student's own working.\n\nQuestion:\n{question}\n\nStudent's work:\n{work}"
        )
        verdict = verify(diagnosis)
        out["cycles"] = 1
        if not verdict.approved:
            issues = "; ".join(verdict.issues[:3])
            diagnosis = diagnose(
                "Your diagnosis was rejected by an independent verifier. Produce one corrected replacement "
                "diagnosis that resolves every issue. If the issues show you wrongly flagged a correct step, "
                "return verdict='correct'. If you cannot judge confidently, return verdict='unclear'.\n\n"
                f"Question:\n{question}\n\nStudent's work:\n{work}\n\nVerifier issues:\n{issues}\n\n"
                f"Rejected diagnosis:\n{diagnosis.model_dump_json()}"
            )
            verdict = verify(diagnosis)
            out["cycles"] = 2
        out["served"] = verdict.approved
        out["got"] = diagnosis.verdict
        out["verdict_ok"] = diagnosis.verdict == case["verdict"]
        out["step_ok"] = diagnosis.first_error_step == case["error_step"]
        # Told a student their correct work is wrong. The failure that matters.
        out["false_accusation"] = case["verdict"] == "correct" and diagnosis.verdict == "incorrect"
        _diagnosis_to_lesson(diagnosis, question)  # must render
    except Exception as error:
        out["error"] = str(error)[:200]
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


SUITES = {
    "lessons": ("lessons.json", run_lesson_case),
    "diagnoses": ("diagnoses.json", run_diagnosis_case),
}


def report_lessons(results: list[dict[str, Any]]) -> dict[str, Any]:
    print(f"\n{'case':30} {'served':7} {'answer':7} {'cyc':4} {'writes':7} {'degen':6} {'secs'}")
    print("-" * 74)
    for row in results:
        if "error" in row:
            print(f"{row['id']:30} {'CRASH':7} {'-':7} {'-':4} {'-':7} {'-':6} {row['seconds']}  {row['error'][:50]}")
            continue
        final = row["final"]
        print(f"{row['id']:30} {('yes' if row['served'] else 'NO'):7} "
              f"{('ok' if row['correct'] else 'WRONG'):7} {row['cycles']:<4} "
              f"{final['writes']:<7} {final['degenerate']:<6} {row['seconds']}")
    total = len(results)
    served = sum(1 for r in results if r.get("served"))
    correct = sum(1 for r in results if r.get("correct"))
    both = sum(1 for r in results if r.get("served") and r.get("correct"))
    silent = sum(1 for r in results if r.get("first_pass", {}).get("writes") == 0)
    print(f"\nserved a lesson:              {served}/{total}")
    print(f"answer correct:               {correct}/{total}")
    print(f"correct AND served:           {both}/{total}")
    print(f"first pass wrote nothing:     {silent}/{total}")
    return {"total": total, "served": served, "correct": correct, "both": both, "accuracy": both / total if total else 0.0}


def report_diagnoses(results: list[dict[str, Any]]) -> dict[str, Any]:
    print(f"\n{'case':32} {'want':10} {'got':10} {'step':6} {'served':7} {'secs'}")
    print("-" * 74)
    for row in results:
        if "error" in row:
            print(f"{row['id']:32} {row['want']:10} {'CRASH':10} {'-':6} {'-':7} {row['seconds']}  {row['error'][:40]}")
            continue
        flag = "   <<< FALSE ACCUSATION" if row["false_accusation"] else ""
        print(f"{row['id']:32} {row['want']:10} {row['got']:10} "
              f"{('ok' if row['step_ok'] else 'X'):6} {str(row['served']):7} {row['seconds']}{flag}")
    total = len(results)
    verdicts = sum(1 for r in results if r.get("verdict_ok"))
    steps = sum(1 for r in results if r.get("verdict_ok") and r.get("step_ok"))
    false_acc = sum(1 for r in results if r.get("false_accusation"))
    correct_cases = sum(1 for r in results if r["want"] == "correct")
    print(f"\nverdict correct:              {verdicts}/{total}")
    print(f"verdict + exact step:         {steps}/{total}")
    print(f"FALSE ACCUSATIONS:            {false_acc}/{correct_cases} correct submissions")
    return {"total": total, "verdicts": verdicts, "steps": steps,
            "false_accusations": false_acc, "accuracy": verdicts / total if total else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", choices=[*SUITES, "all"], default="all")
    parser.add_argument("--trials", type=int, default=1, help="repeat each suite N times; one sample proves little")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--min-accuracy", type=float, default=None, help="exit non-zero below this (0-1)")
    parser.add_argument("--json", type=pathlib.Path, default=None, help="write raw results here")
    args = parser.parse_args()

    provider = Provider()
    if not provider.key or not provider.model:
        print("LLM_API_KEY and OPENAI_MODEL must be set (see .env.example). This suite calls a real "
              "provider and costs tokens, so it is not part of pytest.", file=sys.stderr)
        return 2

    chosen = list(SUITES) if args.suite == "all" else [args.suite]
    everything: dict[str, Any] = {}
    worst = 1.0
    for suite in chosen:
        filename, runner = SUITES[suite]
        cases = json.loads((CASES / filename).read_text())["cases"]
        for trial in range(1, args.trials + 1):
            label = f"{suite} (trial {trial}/{args.trials})" if args.trials > 1 else suite
            print(f"\n=== {label}: {len(cases)} cases ===")
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(lambda case: runner(provider, case), cases))
            summary = (report_lessons if suite == "lessons" else report_diagnoses)(results)
            everything[f"{suite}-{trial}"] = {"summary": summary, "results": results}
            worst = min(worst, summary["accuracy"])

    if args.json:
        args.json.write_text(json.dumps(everything, indent=1))
        print(f"\nwrote {args.json}")

    if args.min_accuracy is not None and worst < args.min_accuracy:
        print(f"\nFAIL: worst suite accuracy {worst:.2f} is below --min-accuracy {args.min_accuracy:.2f}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
