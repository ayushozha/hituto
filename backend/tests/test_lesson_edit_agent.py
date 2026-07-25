"""Lesson-edit agent is separate from coursegen."""
from types import SimpleNamespace

from app.lesson_edit.prompts import A2UI_SECTION_SYSTEM, HTML_SECTION_SYSTEM
from app.lesson_edit import style_fingerprint
from app.providers.registry import get_coursegen_llm, get_lesson_edit_llm


def test_html_prompt_is_preserve_first_not_coursegen_author() -> None:
    assert "lesson-edit" in HTML_SECTION_SYSTEM
    assert "PRESERVE" in HTML_SECTION_SYSTEM or "Preserve" in HTML_SECTION_SYSTEM
    assert "NOT the course generator" in HTML_SECTION_SYSTEM
    assert "lesson-edit" in A2UI_SECTION_SYSTEM


def test_style_fingerprint_extracts_classes() -> None:
    html = (
        '<section class="rounded-3xl bg-white p-8">'
        '<div class="text-ink bg-mint">x</div></section>'
    )
    fp = style_fingerprint(html)
    assert "rounded-3xl" in fp
    assert "bg-mint" in fp


def test_lesson_edit_llm_falls_back_to_coursegen(monkeypatch) -> None:
    s = SimpleNamespace(
        resolved_lesson_edit_llm_base_url=lambda: "https://example.test/v1",
        resolved_lesson_edit_llm_api_key=lambda: "k-edit",
        resolved_lesson_edit_llm_model=lambda: "coursegen-model",
        resolved_coursegen_llm_base_url=lambda: "https://example.test/v1",
        resolved_coursegen_llm_api_key=lambda: "k-cg",
        resolved_coursegen_llm_model=lambda: "coursegen-model",
    )
    monkeypatch.setattr("app.providers.registry.get_settings", lambda: s)
    assert get_lesson_edit_llm().model == "coursegen-model"
    assert get_coursegen_llm().model == "coursegen-model"


def test_lesson_edit_llm_can_override(monkeypatch) -> None:
    s = SimpleNamespace(
        resolved_lesson_edit_llm_base_url=lambda: "https://example.test/v1",
        resolved_lesson_edit_llm_api_key=lambda: "k-edit",
        resolved_lesson_edit_llm_model=lambda: "edit-model",
        resolved_coursegen_llm_base_url=lambda: "https://example.test/v1",
        resolved_coursegen_llm_api_key=lambda: "k-cg",
        resolved_coursegen_llm_model=lambda: "coursegen-model",
    )
    monkeypatch.setattr("app.providers.registry.get_settings", lambda: s)
    assert get_lesson_edit_llm().model == "edit-model"
    assert get_coursegen_llm().model == "coursegen-model"


def test_resolved_lesson_edit_chain() -> None:
    from app.core.config import Settings

    # Bypass env file: construct with explicit fields via model_validate + _env_file=None
    s = Settings.model_construct(
        llm_model="global-model",
        coursegen_llm_model="coursegen-model",
        lesson_edit_llm_model="",
        llm_base_url="https://x",
        coursegen_llm_base_url="",
        lesson_edit_llm_base_url="",
        llm_api_key="k",
        coursegen_llm_api_key="",
        lesson_edit_llm_api_key="",
    )
    assert s.resolved_lesson_edit_llm_model() == "coursegen-model"
    s2 = Settings.model_construct(
        llm_model="global-model",
        coursegen_llm_model="coursegen-model",
        lesson_edit_llm_model="edit-only",
        llm_base_url="https://x",
        coursegen_llm_base_url="",
        lesson_edit_llm_base_url="",
        llm_api_key="k",
        coursegen_llm_api_key="",
        lesson_edit_llm_api_key="",
    )
    assert s2.resolved_lesson_edit_llm_model() == "edit-only"
