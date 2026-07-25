"""Validated Studio v2 manifest and deterministic mode/asset routing."""
from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StudioMode = Literal[
    "specimen",
    "simulation",
    "process-cutaway",
    "systems-map",
    "telemetry-map",
    "configurator",
]
MilestoneStudioMode = Literal["specimen", "simulation", "process-cutaway"]
StudioAssetKind = Literal[
    "generated_mesh",
    "image_specimen",
    "procedural_specimen",
    "procedural_simulation",
    "procedural_cutaway",
    "multi_part_glb",
]
StudioTheme = Literal["default", "field-guide"]
StudioCapability = Literal[
    "orbit",
    "zoom",
    "focus_anchor",
    "isolate",
    "parameterize",
    "playback",
    "timeline",
    "reset",
]
StudioControlKind = Literal["button", "range", "select", "toggle", "playback", "timeline"]
StudioProceduralKind = Literal[
    "plant-cell",
    "animal-cell",
    "bacteria",
    "neuron",
    "muscle-fiber",
]

MILESTONE_STUDIO_MODES: tuple[MilestoneStudioMode, ...] = (
    "specimen",
    "simulation",
    "process-cutaway",
)

_PROCESS_RE = re.compile(
    r"\b(jet\s*engine|engine|pump|turbine|compressor|combustion|manufactur|assembly|"
    r"cutaway|cross-?section|pipeline|water\s+cycle|digestive|circulation|blood\s+flow|"
    r"process|stages?|workflow)\b",
    re.I,
)
_SIMULATION_RE = re.compile(
    r"\b(simulat|motion|force|orbit|wave|gait|kinematic|trajectory|velocity|gravity|"
    r"pendulum|collision|feedback\s+loop|dynamic|parameter)\b",
    re.I,
)
_PROCEDURAL_SPECIMEN_RE = re.compile(
    r"\b(planet|solar\s+system|molecule|atom|orbit|field|spacetime|constellation)\b",
    re.I,
)
_FIELD_GUIDE_RE = re.compile(r"\b(pollinat(?:or|ion|ors)?|orchid\s+bee)\b", re.I)
_TAGS_RE = re.compile(r"<[^>]+>")
_ID_RE = re.compile(r"[^a-z0-9]+")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StudioLesson(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    objective: str = Field(min_length=1, max_length=500)
    estimated_minutes: int = Field(default=10, ge=1, le=90)


class StudioAsset(StrictModel):
    kind: StudioAssetKind
    src: str | None = Field(default=None, max_length=500)
    fallback: str = Field(min_length=1, max_length=80)
    capabilities: list[StudioCapability] = Field(min_length=1)

    @field_validator("src")
    @classmethod
    def validate_src(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("/build/mesh/", "/mesh?key=")):
            raise ValueError("Studio mesh src must use a managed mesh path")
        return value

    @model_validator(mode="after")
    def validate_mesh_source(self) -> "StudioAsset":
        if self.kind in ("generated_mesh", "multi_part_glb") and not self.src:
            raise ValueError(f"{self.kind} requires src")
        if self.kind.startswith("procedural_") and self.src:
            raise ValueError("procedural assets cannot declare a mesh src")
        return self


class StudioCamera(StrictModel):
    preset: Literal["three_quarter", "front", "top", "system"] = "three_quarter"
    allow_orbit: bool = False
    allow_zoom: bool = False


class StudioStage(StrictModel):
    asset: StudioAsset
    camera: StudioCamera = Field(default_factory=StudioCamera)


class StudioFieldNote(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=320)


class StudioSubject(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str = Field(min_length=1, max_length=100)
    subtitle: str = Field(default="", max_length=160)
    mesh_src: str | None = Field(default=None, max_length=500)
    procedural_kind: StudioProceduralKind | None = None
    stage_image_query: str = Field(default="", max_length=500)
    initial_yaw: float | None = Field(default=None, ge=-6.28319, le=6.28319)
    initial_pitch: float | None = Field(default=None, ge=-1.5, le=1.5)
    image_query: str = Field(default="", max_length=400)
    tags: list[str] = Field(default_factory=list, max_length=6)
    field_notes: list[StudioFieldNote] = Field(default_factory=list, max_length=6)
    flower_query: str = Field(default="", max_length=300)
    default_part_id: str | None = Field(default=None, max_length=64)

    @field_validator("mesh_src")
    @classmethod
    def validate_mesh_src(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("/build/mesh/", "/mesh?key=")):
            raise ValueError("subject mesh_src must use a managed mesh path")
        return value


class StudioPart(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=320)
    detail: str = Field(default="", max_length=500)
    anchor: tuple[float, float, float] | None = None
    mesh_node: str | None = Field(default=None, max_length=120)
    evidence_ids: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("anchor")
    @classmethod
    def validate_anchor(
        cls, value: tuple[float, float, float] | None
    ) -> tuple[float, float, float] | None:
        if value is not None and any(not -1.0 <= coordinate <= 1.0 for coordinate in value):
            raise ValueError("anchor coordinates must be normalized to -1..1")
        return value


class StudioControl(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    kind: StudioControlKind
    label: str = Field(min_length=1, max_length=100)
    capability: StudioCapability
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    value: float | str | bool | None = None
    unit: str = Field(default="", max_length=24)
    options: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_control_shape(self) -> "StudioControl":
        if self.kind in ("range", "timeline"):
            if self.minimum is None or self.maximum is None or self.minimum >= self.maximum:
                raise ValueError(f"{self.kind} requires an increasing minimum and maximum")
            if self.step is None or self.step <= 0:
                raise ValueError(f"{self.kind} requires a positive step")
        if self.kind == "select" and len(self.options) < 2:
            raise ValueError("select requires at least two options")
        return self


class StudioEvidence(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    claim: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=1000)
    source_label: str = Field(default="Lesson evidence", min_length=1, max_length=100)


class StudioManifest(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    theme: StudioTheme = "default"
    mode: MilestoneStudioMode
    lesson: StudioLesson
    stage: StudioStage
    subjects: list[StudioSubject] = Field(min_length=1, max_length=12)
    parts: list[StudioPart] = Field(min_length=1, max_length=8)
    controls: list[StudioControl] = Field(min_length=1, max_length=10)
    evidence: list[StudioEvidence] = Field(default_factory=list, max_length=6)
    learning_events: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_capabilities_and_references(self) -> "StudioManifest":
        capabilities = set(self.stage.asset.capabilities)
        unsupported = [control.id for control in self.controls if control.capability not in capabilities]
        if unsupported:
            raise ValueError(f"controls require unsupported capabilities: {', '.join(unsupported)}")

        if any(part.mesh_node for part in self.parts) and "isolate" not in capabilities:
            raise ValueError("mesh_node requires isolate capability")

        evidence_ids = {item.id for item in self.evidence}
        missing = sorted(
            {
                evidence_id
                for part in self.parts
                for evidence_id in part.evidence_ids
                if evidence_id not in evidence_ids
            }
        )
        if missing:
            raise ValueError(f"parts reference unknown evidence: {', '.join(missing)}")

        control_kinds = {control.kind for control in self.controls}
        if self.mode == "simulation" and not {"range", "playback"}.issubset(control_kinds):
            raise ValueError("simulation requires range and playback controls")
        if self.mode == "process-cutaway" and "timeline" not in control_kinds:
            raise ValueError("process-cutaway requires a timeline control")
        if self.mode == "specimen" and "button" not in control_kinds:
            raise ValueError("specimen requires a reset button")
        return self


def resolve_studio_mode(
    plan: dict[str, Any] | None = None, knobs: dict[str, Any] | None = None
) -> MilestoneStudioMode:
    """Choose a shipped Studio mode; explicit user choice wins."""
    plan = plan or {}
    knobs = knobs or {}
    requested = str(knobs.get("studio_mode") or plan.get("studio_mode") or "auto").strip().lower()
    if requested in MILESTONE_STUDIO_MODES:
        return requested  # type: ignore[return-value]

    haystack = " ".join(
        str(value)
        for value in (
            plan.get("title"),
            plan.get("subtitle"),
            plan.get("topic"),
            knobs.get("subject"),
        )
        if value
    )
    if _PROCESS_RE.search(haystack):
        return "process-cutaway"
    if str(plan.get("archetype") or knobs.get("archetype") or "").lower() == "simulation":
        return "simulation"
    if _SIMULATION_RE.search(haystack):
        return "simulation"
    return "specimen"


def prepare_studio_plan(plan: dict[str, Any], knobs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add deterministic Studio routing metadata before asset planning."""
    result = dict(plan)
    result["presentation"] = "studio"
    result["studio_mode"] = resolve_studio_mode(result, knobs)
    if result["studio_mode"] == "simulation":
        result["archetype"] = "simulation"
    return result


def build_studio_manifest(
    plan: dict[str, Any], knobs: dict[str, Any] | None = None
) -> StudioManifest:
    """Project a lesson plan and its planned assets into the Studio v2 contract."""
    mode = resolve_studio_mode(plan, knobs)
    title = _text(plan.get("title"), "Interactive Studio", 180)
    objective = _text(
        plan.get("subtitle") or plan.get("objective"),
        f"Explore {title} through a live learning model.",
        500,
    )
    evidence = _evidence(plan)
    parts = _parts(plan, evidence)
    if mode == "process-cutaway" and len(parts) == 1:
        parts.append(
            StudioPart(
                id="outcome",
                label="Outcome",
                summary="Observe what the process produces after the transformation.",
                detail="Compare the output with the starting state and trace what changed.",
                anchor=(0.7, 0.0, 0.0),
                evidence_ids=parts[0].evidence_ids,
            )
        )
    subjects = _subjects(plan, title, parts)
    asset = _asset(plan, mode, subjects)
    theme: StudioTheme = "field-guide" if _FIELD_GUIDE_RE.search(title) else "default"

    if mode == "simulation":
        controls = [
            StudioControl(
                id="system-rate",
                kind="range",
                label="System rate",
                capability="parameterize",
                minimum=0.25,
                maximum=2.0,
                step=0.25,
                value=1.0,
                unit="×",
            ),
            StudioControl(
                id="playback",
                kind="playback",
                label="Play",
                capability="playback",
                value=False,
            ),
            StudioControl(
                id="reset",
                kind="button",
                label="Reset",
                capability="reset",
            ),
        ]
        events = [
            "studio_mode_opened",
            "studio_control_changed",
            "studio_playback_completed",
            "studio_reset",
        ]
    elif mode == "process-cutaway":
        controls = [
            StudioControl(
                id="process-stage",
                kind="timeline",
                label="Process stage",
                capability="timeline",
                minimum=0,
                maximum=max(1, len(parts) - 1),
                step=1,
                value=0,
            ),
            StudioControl(
                id="playback",
                kind="playback",
                label="Play",
                capability="playback",
                value=False,
            ),
            StudioControl(
                id="reset",
                kind="button",
                label="Reset",
                capability="reset",
            ),
        ]
        events = [
            "studio_mode_opened",
            "studio_part_selected",
            "studio_control_changed",
            "studio_playback_completed",
            "studio_reset",
        ]
    else:
        controls = [
            StudioControl(
                id="reset-view",
                kind="button",
                label="Reset view",
                capability="reset",
            )
        ]
        events = [
            "studio_mode_opened",
            "studio_part_selected",
            "studio_reset",
            "studio_degraded",
        ]

    return StudioManifest(
        theme=theme,
        mode=mode,
        lesson=StudioLesson(
            title=title,
            objective=objective,
            estimated_minutes=_duration_minutes(plan.get("estimated_duration")),
        ),
        stage=StudioStage(
            asset=asset,
            camera=StudioCamera(
                preset="system" if mode == "simulation" else "three_quarter",
                allow_orbit="orbit" in asset.capabilities,
                allow_zoom="zoom" in asset.capabilities,
            ),
        ),
        subjects=subjects,
        parts=parts,
        controls=controls,
        evidence=evidence,
        learning_events=events,
    )


def _asset(
    plan: dict[str, Any], mode: MilestoneStudioMode, subjects: list[StudioSubject]
) -> StudioAsset:
    if mode == "simulation":
        return StudioAsset(
            kind="procedural_simulation",
            fallback="procedural_simulation",
            capabilities=["parameterize", "playback", "reset"],
        )
    if mode == "process-cutaway":
        return StudioAsset(
            kind="procedural_cutaway",
            fallback="procedural_cutaway",
            capabilities=["focus_anchor", "playback", "timeline", "reset"],
        )

    mesh_src = next((subject.mesh_src for subject in subjects if subject.mesh_src), None)
    if mesh_src:
        return StudioAsset(
            kind="generated_mesh",
            src=mesh_src,
            fallback="image_reference"
            if any(subject.stage_image_query for subject in subjects)
            else "procedural_specimen",
            capabilities=["orbit", "zoom", "focus_anchor", "reset"],
        )

    if any(subject.stage_image_query for subject in subjects):
        return StudioAsset(
            kind="image_specimen",
            fallback="image_reference",
            capabilities=["zoom", "focus_anchor", "reset"],
        )
    haystack = f"{plan.get('title', '')} {plan.get('subtitle', '')}"
    fallback = "procedural_orbital" if _PROCEDURAL_SPECIMEN_RE.search(haystack) else "procedural_specimen"
    return StudioAsset(
        kind="procedural_specimen",
        fallback=fallback,
        capabilities=["orbit", "zoom", "focus_anchor", "reset"],
    )


def _subject_default_part(
    entry: dict[str, Any], label: str, index: int, parts: list[StudioPart]
) -> str:
    requested = _identifier(entry.get("default_part"), "")
    if requested and any(part.id == requested for part in parts):
        return requested

    # Match names such as "Bacteria Cell" to "Bacterial Cells" while ignoring the
    # generic word "cell". This keeps each specimen paired with its relevant lesson focus.
    roots = [
        token[:6]
        for token in re.findall(r"[a-z0-9]+", label.lower())
        if token not in {"cell", "cells", "the", "a", "an"} and len(token) >= 4
    ]
    if roots:
        scored = []
        for part in parts:
            label_haystack = part.label.lower()
            summary_haystack = part.summary.lower()
            detail_haystack = part.detail.lower()
            score = sum(
                8
                if root in label_haystack
                else 3
                if root in summary_haystack
                else 1
                if root in detail_haystack
                else 0
                for root in roots
            )
            scored.append((score, part.id))
        score, part_id = max(scored, key=lambda item: item[0])
        if score:
            return part_id
    if len(parts) == 1:
        return parts[0].id
    return parts[min(index, len(parts) - 1)].id


def _subjects(plan: dict[str, Any], title: str, parts: list[StudioPart]) -> list[StudioSubject]:
    catalog = plan.get("mesh_catalog") or plan.get("studio_subjects") or []
    subjects: list[StudioSubject] = []
    for index, entry in enumerate(catalog[:12]):
        if not isinstance(entry, dict):
            continue
        label = _text(entry.get("name"), f"Subject {index + 1}", 100)
        subjects.append(
            StudioSubject(
                id=_identifier(entry.get("id") or label, f"subject-{index + 1}"),
                label=label,
                subtitle=_text(entry.get("subtitle"), "", 160),
                mesh_src=entry.get("meshSrc") or entry.get("path"),
                procedural_kind=entry.get("procedural_kind"),
                stage_image_query=_text(entry.get("stage_image_query"), "", 500),
                initial_yaw=entry.get("initial_yaw"),
                initial_pitch=entry.get("initial_pitch"),
                image_query=_text(
                    entry.get("image_query"),
                    f"Single isolated {label}, accurate educational anatomy reference, one "
                    "three-quarter view, plain white background, no other subjects, no comparison "
                    "chart, no text or labels",
                    400,
                ),
                tags=[_text(tag, "", 40) for tag in (entry.get("tags") or [])[:6] if tag],
                field_notes=entry.get("field_notes") or [],
                flower_query=_text(entry.get("flower_query"), "", 300),
                default_part_id=_subject_default_part(entry, label, index, parts),
            )
        )
    if not subjects:
        subjects.append(
            StudioSubject(
                id="primary",
                label=title,
                subtitle="Primary learning object",
                mesh_src=(plan.get("mesh_artifact") or {}).get("path") or plan.get("mesh_url"),
                image_query=(
                    f"Single isolated {title}, accurate educational reference, one three-quarter "
                    "view, plain white background, no other subjects, no text or labels"
                )[:400],
                default_part_id=parts[0].id,
            )
        )
    return subjects


def _parts(plan: dict[str, Any], evidence: list[StudioEvidence]) -> list[StudioPart]:
    sections = [section for section in (plan.get("sections") or []) if isinstance(section, dict)]
    evidence_ids = [item.id for item in evidence]
    parts: list[StudioPart] = []
    for index, section in enumerate(sections[:6]):
        label = _text(section.get("title"), f"Focus {index + 1}", 100)
        summary = _text(
            section.get("objective") or section.get("body"),
            f"Explore the role of {label} in this system.",
            320,
        )
        detail = _text(section.get("body"), summary, 500)
        attached = [evidence_ids[index % len(evidence_ids)]] if evidence_ids else []
        parts.append(
            StudioPart(
                id=_identifier(section.get("id") or label, f"focus-{index + 1}"),
                label=label,
                summary=summary,
                detail=detail,
                anchor=(round(-0.7 + index * 0.28, 2), round(0.35 - index * 0.12, 2), 0.0),
                evidence_ids=attached,
            )
        )
    if not parts:
        title = _text(plan.get("title"), "the learning object", 100)
        parts.append(
            StudioPart(
                id="overview",
                label="Overview",
                summary=f"Inspect the main structure and behavior of {title}.",
                detail=_text(plan.get("subtitle"), f"Explore {title} from multiple views.", 500),
                anchor=(0.0, 0.0, 0.0),
                evidence_ids=evidence_ids[:1],
            )
        )
    return parts


def _evidence(plan: dict[str, Any]) -> list[StudioEvidence]:
    evidence: list[StudioEvidence] = []
    for index, fact in enumerate((plan.get("facts") or [])[:6]):
        if not isinstance(fact, dict):
            continue
        claim = _text(fact.get("claim"), "", 500)
        if not claim:
            continue
        source_url = str(fact.get("source_url") or "").strip() or None
        evidence.append(
            StudioEvidence(
                id=f"e{index + 1}",
                claim=claim,
                source_url=source_url,
                source_label=_source_label(source_url),
            )
        )
    return evidence


def _source_label(source_url: str | None) -> str:
    if not source_url:
        return "Lesson evidence"
    if source_url.startswith("source:"):
        return "Uploaded source"
    host = urlparse(source_url).hostname
    return host.removeprefix("www.") if host else "Lesson evidence"


def _identifier(value: Any, fallback: str) -> str:
    result = _ID_RE.sub("-", str(value or "").lower()).strip("-")
    return (result or fallback)[:64].rstrip("-")


def _text(value: Any, fallback: str, limit: int) -> str:
    text = _TAGS_RE.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return (text or fallback)[:limit].strip()


def _duration_minutes(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        return 10
    return max(1, min(90, int(match.group())))
