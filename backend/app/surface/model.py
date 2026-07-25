"""Lesson surface models (specs/design_agents §6).

A `LessonSurface` is the design-agnostic descriptor of a lesson's *consumable* form:
what text grounds an agent, what sections exist, and which control capabilities the
rendered surface actually offers. Tutor and voice depend on this — never on how the
lesson was authored.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SurfaceKind = Literal["capsule", "studio", "a2ui", "reading", "video"]


class SurfaceCapabilities(BaseModel):
    """What an agent can do to this lesson's live surface."""

    # GuideBridge iframe runtime present (capsule/studio HTML in a sandboxed iframe) —
    # page tools (observe/click/type/highlight) work.
    page_control: bool = False
    # Video guide surface — seek/play/pause make sense, page tools do not.
    seek: bool = False
    # Navigable section anchors exist (data-lesson-section markup).
    sections: bool = False
    # Whiteboard + widget tools are surface-independent and always available.
    whiteboard: bool = True


class SectionRef(BaseModel):
    id: str
    title: str = ""


class LessonSurface(BaseModel):
    kind: SurfaceKind
    # Design-appropriate plain-text grounding, capped (see digest.ARTIFACT_DIGEST_CHARS).
    digest: str = ""
    outline: list[SectionRef] = Field(default_factory=list)
    capabilities: SurfaceCapabilities = Field(default_factory=SurfaceCapabilities)
    artifact_version: int | None = None
