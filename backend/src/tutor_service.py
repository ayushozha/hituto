from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from lesson_engine import (
    _assistant_message_text,
    _compile_diagram,
    _diagnosis_to_lesson,
    _inject_diagram,
    _might_be_a_topic,
    _normalize_lesson,
    _safe_error,
    _same_answer,
    _source_content,
)
from lesson_models import ImageQuestionAnalysis, LessonPlan, WorkDiagnosis
from observability import log_event
from session_store import SessionView, SQLiteSessionStore
from tutor_agents import (
    diagnosis_reviewer_agent,
    diagnostician_agent,
    llm_configuration_message,
    planner_agent,
    replanner_agent,
    reviewer_agent,
    topic_agent,
    vision_configuration_message,
    vision_diagram_agent,
    vision_planner_agent,
    vision_replanner_agent,
    vision_reviewer_agent,
)


logger = logging.getLogger(__name__)
PROVIDER_TIMEOUT_SECONDS = int(os.environ.get("PROVIDER_DEADLINE_MINUTES", "5")) * 60
RETRYABLE_STATUSES = {408, 409, 425, 429}


def _is_transient(error: Exception) -> bool:
    if isinstance(error, ModelHTTPError):
        return error.status_code in RETRYABLE_STATUSES or error.status_code >= 500
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    return isinstance(error, ModelAPIError)


async def _run(agent: Any, prompt: Any) -> Any:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PROVIDER_TIMEOUT_SECONDS
    for attempt in range(3):
        try:
            result = await asyncio.wait_for(
                agent.run(prompt),
                timeout=max(0.01, deadline - loop.time()),
            )
            return result.output
        except Exception as error:
            if attempt == 2 or not _is_transient(error):
                raise
            delay = min(2**attempt, deadline - loop.time())
            if delay <= 0:
                raise
            await asyncio.sleep(delay)
    raise RuntimeError("Provider retry loop ended unexpectedly")


class TutorService:
    """Application service used by the FastAPI routes and unit tests."""

    def __init__(self, store: SQLiteSessionStore) -> None:
        self.store = store

    def view(self, session_id: str) -> SessionView:
        return self.store.view(session_id)

    def reset(self, session_id: str) -> SessionView:
        return self.store.reset(session_id)

    def forget(self, session_id: str) -> int:
        erased = self.store.forget(session_id)
        log_event("session.forgotten", session=session_id, messages_erased=erased)
        return erased

    async def start_lesson(
        self,
        session_id: str,
        *,
        question_text: str,
        source_kind: str,
        source_media_type: str = "",
        source_base64: str = "",
    ) -> SessionView:
        question_text = question_text.strip()
        source_kind = "image" if source_base64 else (source_kind or "text")
        begun = self.store.begin_lesson(
            session_id,
            question_text=question_text,
            source_kind=source_kind,
        )
        if not begun.allowed:
            return self.view(session_id)
        if not question_text and not source_base64:
            self.store.fail(session_id, begun.generation, "Paste a question or upload a clear PNG or JPEG image.")
            return self.view(session_id)

        started = time.monotonic()
        try:
            lesson, effective_question, corrected = await self._prepare_lesson(
                session_id=session_id,
                generation=begun.generation,
                question_text=question_text,
                source_kind=source_kind,
                source_media_type=source_media_type,
                source_base64=source_base64,
            )
            self.store.complete(
                session_id,
                begun.generation,
                lesson_json=lesson.model_dump_json(),
                assistant_text=_assistant_message_text(lesson),
                question_text=effective_question,
            )
            log_event(
                "lesson.prepared",
                session=session_id,
                generation=begun.generation,
                source=source_kind,
                ms=round((time.monotonic() - started) * 1000),
                beats=len(lesson.beats),
                commands=sum(len(beat.commands) for beat in lesson.beats),
                corrected=corrected,
            )
        except Exception as error:
            self._store_error(session_id, begun.generation, error, "lesson")
        return self.view(session_id)

    async def _prepare_lesson(
        self,
        *,
        session_id: str,
        generation: int,
        question_text: str,
        source_kind: str,
        source_media_type: str,
        source_base64: str,
    ) -> tuple[LessonPlan, str, bool]:
        has_image = bool(source_base64)
        planner = vision_planner_agent if has_image else planner_agent
        reviewer = vision_reviewer_agent if has_image else reviewer_agent
        if planner is None or reviewer is None or (has_image and vision_diagram_agent is None):
            raise RuntimeError(
                vision_configuration_message() if has_image else llm_configuration_message()
            )

        diagram_analysis: ImageQuestionAnalysis | None = None
        diagram_commands: list[dict[str, Any]] = []
        if not has_image and topic_agent is not None and _might_be_a_topic(question_text):
            resolved = await _run(
                topic_agent,
                "Decide what the student typed and, if it is a topic, write one representative "
                f"SAT question on it.\n\nStudent typed:\n{question_text}",
            )
            if not resolved.is_complete_question:
                question_text = resolved.sat_question
                self.store.set_topic_question(session_id, generation, question_text)
                log_event("topic.resolved", session=session_id, generation=generation, topic=resolved.topic)

        student_material = question_text
        effective_question = question_text
        if has_image:
            assert vision_diagram_agent is not None
            analysis_prompt = (
                "Extract the complete SAT question and create a faithful enlarged semantic copy of any "
                "diagram needed to solve it. Optional student context:\n"
                f"{question_text or '[none]'}"
            )
            diagram_analysis = await _run(
                vision_diagram_agent,
                _source_content(analysis_prompt, source_media_type, source_base64),
            )
            diagram_commands = _compile_diagram(diagram_analysis)
            effective_question = question_text or diagram_analysis.extracted_question
            student_material = (
                f"{question_text}\n\nImage transcription:\n{diagram_analysis.extracted_question}"
                if question_text
                else diagram_analysis.extracted_question
            )

        prompt = (
            "Prepare a verified, visual SAT lesson for the following student submission.\n\n"
            f"Student material:\n{student_material}\n\nSource kind: {source_kind}\n\n"
            + (
                "A trusted renderer will insert the enlarged diagram from this vision summary:\n"
                f"{diagram_analysis.diagram_summary}\nDo not emit space='diagram' commands, graph, "
                "bar_chart, or venn. Use concise flowing board notes."
                if diagram_analysis and diagram_analysis.should_reconstruct
                else ""
            )
        )
        plan_content = _source_content(prompt, source_media_type, source_base64) if has_image else prompt
        planned = await _run(planner, plan_content)
        lesson = _inject_diagram(
            _normalize_lesson(
                planned.to_plan(), source_has_image=has_image, question_text=student_material
            ),
            diagram_commands,
        )
        review_prompt = (
            "Verify this proposed SAT lesson against the original submission.\n\n"
            f"Student material:\n{student_material}\n\nProposed lesson JSON:\n{lesson.model_dump_json()}"
        )
        review_content = _source_content(review_prompt, source_media_type, source_base64) if has_image else review_prompt
        review = await _run(reviewer, review_content)
        corrected = not review.approved
        if review.approved:
            return lesson, effective_question, False

        issues = "; ".join(review.issues[:3]) or "the solution could not be verified"
        logger.warning("Initial SAT lesson was rejected: %s", issues)
        log_event("lesson.rejected", session=session_id, generation=generation, pass_number=1)
        if has_image and diagram_analysis and diagram_analysis.should_reconstruct:
            assert vision_diagram_agent is not None
            correction = (
                "Correct this diagram extraction using every verifier issue. Return one clean replacement "
                f"ImageQuestionAnalysis.\n\nVerifier issues:\n{issues}\n\nPrior analysis:\n"
                f"{diagram_analysis.model_dump_json()}"
            )
            diagram_analysis = await _run(
                vision_diagram_agent,
                _source_content(correction, source_media_type, source_base64),
            )
            diagram_commands = _compile_diagram(diagram_analysis)
            effective_question = question_text or diagram_analysis.extracted_question
            student_material = (
                f"{question_text}\n\nImage transcription:\n{diagram_analysis.extracted_question}"
                if question_text
                else diagram_analysis.extracted_question
            )

        correction_prompt = (
            "Correct the proposed SAT lesson using every reviewer issue below. Return a complete "
            "replacement lesson and keep the correct final answer.\n\n"
            f"Student material:\n{student_material}\n\nReviewer issues:\n{issues}\n\n"
            f"Rejected lesson JSON:\n{lesson.model_dump_json()}\n\n"
            "Delete every criticized visual command unless you can correct it confidently. "
            "Do not emit image-derived diagram, graph, bar_chart, or venn commands."
        )
        correction_content = _source_content(correction_prompt, source_media_type, source_base64) if has_image else correction_prompt
        corrected_plan = await _run(planner, correction_content)
        lesson = _inject_diagram(
            _normalize_lesson(
                corrected_plan.to_plan(), source_has_image=has_image, question_text=student_material
            ),
            diagram_commands,
        )
        rereview_prompt = (
            "Verify this corrected SAT lesson against the original submission and prior issues.\n\n"
            f"Student material:\n{student_material}\n\nPrior issues:\n{issues}\n\n"
            f"Corrected lesson JSON:\n{lesson.model_dump_json()}"
        )
        rereview_content = _source_content(rereview_prompt, source_media_type, source_base64) if has_image else rereview_prompt
        rereview = await _run(reviewer, rereview_content)
        if not rereview.approved:
            raise ValueError(
                "I couldn’t verify this explanation confidently. Try the question again or paste a little more context."
            )
        return lesson, effective_question, corrected

    async def replan(
        self,
        session_id: str,
        *,
        student_message: str,
        completed_beat_index: int,
        source_media_type: str = "",
        source_base64: str = "",
    ) -> SessionView:
        current = self.store.snapshot(session_id)
        student_message = student_message.strip()
        begun = self.store.begin_replan(session_id, student_message=student_message)
        if not begun.allowed:
            return self.view(session_id)
        if not student_message or not current.lesson_json:
            message = "Tell the tutor what is confusing." if not student_message else "Start a lesson before asking a follow-up."
            self.store.fail(session_id, begun.generation, message)
            return self.view(session_id)
        agent = vision_replanner_agent if source_base64 else replanner_agent
        if agent is None:
            self.store.fail(session_id, begun.generation, llm_configuration_message())
            return self.view(session_id)
        prompt = (
            f"Student interruption: {student_message}\nCompleted beat index: {completed_beat_index}\n"
            f"Original question: {current.question_text}\nCurrent verified lesson: {current.lesson_json}\n"
            "Create a focused replacement explanation that directly resolves the interruption."
        )
        try:
            content = _source_content(prompt, source_media_type, source_base64) if source_base64 else prompt
            output = await _run(agent, content)
            lesson = _normalize_lesson(
                output.to_plan(), source_has_image=bool(source_base64), question_text=current.question_text
            )
            old_answer = LessonPlan.model_validate_json(current.lesson_json).final_answer
            if not _same_answer(lesson.final_answer, old_answer):
                retry_prompt = (
                    f"{prompt}\n\nYour previous attempt changed the verified answer to '{lesson.final_answer}'. "
                    f"The verified answer is '{old_answer}' and must not change. Explain it differently."
                )
                retry_content = _source_content(retry_prompt, source_media_type, source_base64) if source_base64 else retry_prompt
                lesson = _normalize_lesson(
                    (await _run(agent, retry_content)).to_plan(),
                    source_has_image=bool(source_base64),
                    question_text=current.question_text,
                )
                if not _same_answer(lesson.final_answer, old_answer):
                    raise ValueError("I couldn't re-explain that without changing the verified answer.")
            self.store.complete(
                session_id,
                begun.generation,
                lesson_json=lesson.model_dump_json(),
                assistant_text=_assistant_message_text(lesson),
            )
        except Exception as error:
            self._store_error(session_id, begun.generation, error, "replan")
        return self.view(session_id)

    async def check_work(
        self,
        session_id: str,
        *,
        student_work: str,
        question_text: str = "",
    ) -> SessionView:
        current = self.store.snapshot(session_id)
        student_work = student_work.strip()
        begun = self.store.begin_check(session_id, student_work=student_work)
        if not begun.allowed:
            return self.view(session_id)
        if not student_work:
            self.store.fail(session_id, begun.generation, "Type the steps you tried and I'll check them.")
            return self.view(session_id)
        if diagnostician_agent is None or diagnosis_reviewer_agent is None:
            self.store.fail(session_id, begun.generation, llm_configuration_message())
            return self.view(session_id)
        question = question_text.strip() or current.question_text.strip() or "The student did not paste the original question."
        started = time.monotonic()
        try:
            prompt = f"Diagnose this student's own working.\n\nQuestion:\n{question}\n\nStudent's work:\n{student_work}"
            diagnosis: WorkDiagnosis = await _run(diagnostician_agent, prompt)
            review_prompt = (
                "Verify this diagnosis of the student's work.\n\n"
                f"Question:\n{question}\n\nStudent's work:\n{student_work}\n\n"
                f"Proposed diagnosis JSON:\n{diagnosis.model_dump_json()}"
            )
            review = await _run(diagnosis_reviewer_agent, review_prompt)
            if not review.approved:
                issues = "; ".join(review.issues[:3]) or "the diagnosis could not be verified"
                corrected_prompt = (
                    "Your diagnosis was rejected. Produce one corrected replacement. If you cannot judge "
                    "confidently, return verdict='unclear'.\n\n"
                    f"Question:\n{question}\n\nStudent's work:\n{student_work}\n\n"
                    f"Verifier issues:\n{issues}\n\nRejected diagnosis:\n{diagnosis.model_dump_json()}"
                )
                diagnosis = await _run(diagnostician_agent, corrected_prompt)
                rereview = await _run(
                    diagnosis_reviewer_agent,
                    f"Verify this corrected diagnosis.\n\nQuestion:\n{question}\n\nStudent's work:\n"
                    f"{student_work}\n\nPrior issues:\n{issues}\n\nCorrected diagnosis JSON:\n"
                    f"{diagnosis.model_dump_json()}",
                )
                if not rereview.approved:
                    raise ValueError(
                        "I couldn’t check this confidently enough to tell you where it goes wrong. "
                        "Paste the original question with your steps and I’ll try again."
                    )
            lesson = _normalize_lesson(_diagnosis_to_lesson(diagnosis, question), question_text=question)
            self.store.complete(
                session_id,
                begun.generation,
                lesson_json=lesson.model_dump_json(),
                assistant_text=_assistant_message_text(lesson),
                question_text=question if question_text.strip() else None,
            )
            log_event(
                "work.diagnosed",
                session=session_id,
                generation=begun.generation,
                ms=round((time.monotonic() - started) * 1000),
                verdict=diagnosis.verdict,
                error_step=diagnosis.first_error_step,
                confidence=round(diagnosis.confidence, 2),
                steps=len(diagnosis.restated_steps),
            )
        except Exception as error:
            self._store_error(session_id, begun.generation, error, "diagnosis")
        return self.view(session_id)

    async def voice_token(self) -> dict[str, Any]:
        api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        tts_model = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en").strip()
        if not api_key:
            return {"ok": False, "message": "Add DEEPGRAM_API_KEY to the project .env file."}
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(
                    "https://api.deepgram.com/v1/auth/grant",
                    headers={"Authorization": f"Token {api_key}"},
                    json={"ttl_seconds": 60},
                )
            response.raise_for_status()
            access_token = str(response.json().get("access_token", ""))
            if not access_token:
                raise ValueError("Deepgram did not return an access token")
            return {
                "ok": True,
                "accessToken": access_token,
                "expiresIn": 60,
                "ttsModel": tts_model,
                "message": "Voice ready",
            }
        except Exception as error:
            logger.warning("Could not grant a temporary Deepgram token: %s", error)
            return {
                "ok": False,
                "message": "Voice is unavailable right now. Captions and the board still work.",
            }

    def _store_error(self, session_id: str, generation: int, error: Exception, stage: str) -> None:
        if _is_transient(error) or isinstance(error, asyncio.TimeoutError):
            message = "I couldn't reach the lesson service. Please try again in a few minutes."
            log_event("provider.gave_up", session=session_id, generation=generation, stage=stage, error=type(error).__name__)
        elif isinstance(error, ValueError) and str(error).startswith("I"):
            message = str(error)
        else:
            message = _safe_error(error)
        self.store.fail(session_id, generation, message)
        log_event("student.error", session=session_id, generation=generation, stage=stage)
