"""Validated GameManifest and deterministic game routing.

Mirrors Studio: the LLM never writes the Three.js loop. Plan fields fill a Pydantic
manifest; ``game_renderer`` injects it into a server-owned template + runtime. Capsules
still pass through ``capsule/postprocess``.

Modes:
- ``toon-gallery`` — orbit + visit character stations (explore)
- ``stack-builder`` — kid push/pop call-stack challenge (learn-by-doing)
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GameMode = Literal["toon-gallery", "stack-builder"]
GameCharacter = Literal["soldier", "hazmat", "enemy"]
GameVisitClip = Literal["Idle", "Wave", "Yes", "Punch", "No"]

KIT_PREFIX = "/game-kits/toon/"
CHARACTER_FILES: dict[GameCharacter, str] = {
    "soldier": "Character_Soldier.gltf",
    "hazmat": "Character_Hazmat.gltf",
    "enemy": "Character_Enemy.gltf",
}
_CHAR_CYCLE: tuple[GameCharacter, ...] = ("soldier", "hazmat", "enemy")
_CLIP_CYCLE: tuple[GameVisitClip, ...] = ("Wave", "Yes", "Punch")
_ID_RE = re.compile(r"[^a-z0-9]+")
_TAGS_RE = re.compile(r"<[^>]+>")
_STACK_TOPIC_RE = re.compile(
    r"\b(call\s*stack|stack\s*frame|push\s+and\s+pop|stack-?builder|kitchen\s+stack)\b",
    re.I,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GameStation(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=100)
    plaque: str = Field(min_length=1, max_length=500)
    character: GameCharacter = "soldier"
    visit_clip: GameVisitClip = "Wave"
    src: str = Field(min_length=1, max_length=200)

    @field_validator("src")
    @classmethod
    def validate_src(cls, value: str) -> str:
        if not value.startswith(KIT_PREFIX) or ".." in value or "\\" in value:
            raise ValueError("station src must be a first-party /game-kits/toon/ path")
        name = value[len(KIT_PREFIX) :]
        if name not in CHARACTER_FILES.values():
            raise ValueError(f"unknown kit asset: {name}")
        return value

    @model_validator(mode="after")
    def src_matches_character(self) -> GameStation:
        expected = KIT_PREFIX + CHARACTER_FILES[self.character]
        if self.src != expected:
            raise ValueError("station src must match character kit file")
        return self


class StackFrame(StrictModel):
    """One function frame a kid can push onto the call stack."""

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str = Field(min_length=1, max_length=40)
    hint: str = Field(min_length=1, max_length=240)
    character: GameCharacter = "soldier"
    src: str = Field(min_length=1, max_length=200)

    @field_validator("src")
    @classmethod
    def validate_src(cls, value: str) -> str:
        if not value.startswith(KIT_PREFIX) or ".." in value or "\\" in value:
            raise ValueError("frame src must be a first-party /game-kits/toon/ path")
        name = value[len(KIT_PREFIX) :]
        if name not in CHARACTER_FILES.values():
            raise ValueError(f"unknown kit asset: {name}")
        return value

    @model_validator(mode="after")
    def src_matches_character(self) -> StackFrame:
        expected = KIT_PREFIX + CHARACTER_FILES[self.character]
        if self.src != expected:
            raise ValueError("frame src must match character kit file")
        return self


class StackChallenge(StrictModel):
    story: str = Field(min_length=1, max_length=400)
    program_lines: list[str] = Field(min_length=2, max_length=6)
    push_order: list[str] = Field(min_length=2, max_length=4)
    pop_order: list[str] = Field(min_length=2, max_length=4)


class GameManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: GameMode = "toon-gallery"
    title: str = Field(min_length=1, max_length=180)
    goal: str = Field(min_length=1, max_length=280)
    win_copy: str = Field(
        default="You visited every station. Nice work.",
        min_length=1,
        max_length=280,
    )
    stations: list[GameStation] = Field(default_factory=list, max_length=3)
    frames: list[StackFrame] = Field(default_factory=list, max_length=4)
    challenge: StackChallenge | None = None

    @model_validator(mode="after")
    def mode_shape(self) -> GameManifest:
        if self.mode == "toon-gallery":
            if len(self.stations) < 2:
                raise ValueError("toon-gallery needs at least 2 stations")
            return self
        if len(self.frames) < 2 or self.challenge is None:
            raise ValueError("stack-builder needs frames and a challenge")
        ids = {frame.id for frame in self.frames}
        for frame_id in self.challenge.push_order + self.challenge.pop_order:
            if frame_id not in ids:
                raise ValueError(f"challenge references unknown frame id: {frame_id}")
        if self.challenge.pop_order != list(reversed(self.challenge.push_order)):
            raise ValueError("pop_order must be the reverse of push_order")
        return self


def prepare_game_plan(plan: dict[str, Any], knobs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stamp game routing metadata before generate (no mesh pipeline needed)."""
    knobs = knobs or {}
    result = dict(plan)
    result["presentation"] = "game"
    result["archetype"] = "game"
    result["game_mode"] = resolve_game_mode(result, knobs)
    return result


def resolve_game_mode(plan: dict[str, Any], knobs: dict[str, Any] | None = None) -> GameMode:
    knobs = knobs or {}
    raw = str(plan.get("game_mode") or knobs.get("game_mode") or "").strip().lower()
    if raw in ("toon-gallery", "stack-builder"):
        return raw  # type: ignore[return-value]
    hay = " ".join(
        str(x)
        for x in (
            plan.get("title"),
            plan.get("subtitle"),
            plan.get("objective"),
            plan.get("topic"),
            knobs.get("topic"),
            knobs.get("subject"),
        )
        if x
    )
    if _STACK_TOPIC_RE.search(hay):
        return "stack-builder"
    return "toon-gallery"


def build_game_manifest(
    plan: dict[str, Any], knobs: dict[str, Any] | None = None
) -> GameManifest:
    """Project a lesson plan into a GameManifest (gallery or stack-builder)."""
    knobs = knobs or {}
    mode = resolve_game_mode(plan, knobs)
    if mode == "stack-builder":
        return _build_stack_builder(plan, knobs)
    return _build_toon_gallery(plan, knobs)


def _build_toon_gallery(plan: dict[str, Any], knobs: dict[str, Any]) -> GameManifest:
    title = _text(plan.get("title") or knobs.get("topic"), "Learning Gallery", 180)
    goal = _text(
        knobs.get("goal") or plan.get("game_goal") or plan.get("subtitle"),
        f"Orbit the gallery, visit every station, and read each plaque about {title}.",
        280,
    )
    win_copy = _text(
        plan.get("win_copy") or knobs.get("win_copy"),
        "You visited every station. Nice work.",
        280,
    )
    return GameManifest(
        mode="toon-gallery",
        title=title,
        goal=goal,
        win_copy=win_copy,
        stations=_stations_from_plan(plan, title),
    )


def _build_stack_builder(plan: dict[str, Any], knobs: dict[str, Any]) -> GameManifest:
    title = _text(plan.get("title") or knobs.get("topic"), "Call Stack Kitchen", 180)
    goal = _text(
        knobs.get("goal") or plan.get("game_goal"),
        "Push frames when a function is called. Pop when it finishes. Build the stack like a real program.",
        280,
    )
    win_copy = _text(
        plan.get("win_copy") or knobs.get("win_copy"),
        "You built the stack and unwound it. That's how a call stack works!",
        280,
    )
    frames, challenge = _default_kitchen_challenge()
    # Optional: map first 3 section titles onto frame labels (keep kitchen defaults if thin).
    sections = [s for s in (plan.get("sections") or []) if isinstance(s, dict)]
    if len(sections) >= 3:
        labels = [
            _text(sections[0].get("title"), "main", 40),
            _text(sections[1].get("title"), "cook", 40),
            _text(sections[2].get("title"), "mix", 40),
        ]
        hints = [
            _text(sections[0].get("objective"), "The program starts here.", 240),
            _text(sections[1].get("objective"), "Called next.", 240),
            _text(sections[2].get("objective"), "Called last — sits on top.", 240),
        ]
        frames = [
            _make_frame("main", labels[0], hints[0], "soldier"),
            _make_frame("cook", labels[1], hints[1], "hazmat"),
            _make_frame("mix", labels[2], hints[2], "enemy"),
        ]
        challenge = StackChallenge(
            story=_text(
                plan.get("subtitle") or plan.get("objective"),
                f"A tiny program for {title}: start at the bottom, then call deeper functions.",
                400,
            ),
            program_lines=[
                f"{labels[0]}()",
                f"  {labels[1]}()",
                f"    {labels[2]}()",
            ],
            push_order=["main", "cook", "mix"],
            pop_order=["mix", "cook", "main"],
        )
    return GameManifest(
        mode="stack-builder",
        title=title,
        goal=goal,
        win_copy=win_copy,
        frames=frames,
        challenge=challenge,
    )


def _default_kitchen_challenge() -> tuple[list[StackFrame], StackChallenge]:
    frames = [
        _make_frame("main", "main", "The program starts here.", "soldier"),
        _make_frame("cook", "cook", "main calls cook to make dinner.", "hazmat"),
        _make_frame("mix", "mix", "cook calls mix — this sits on top.", "enemy"),
    ]
    challenge = StackChallenge(
        story="A tiny kitchen program: main calls cook, and cook calls mix.",
        program_lines=["main()", "  cook()", "    mix()"],
        push_order=["main", "cook", "mix"],
        pop_order=["mix", "cook", "main"],
    )
    return frames, challenge


def _make_frame(
    frame_id: str, label: str, hint: str, character: GameCharacter
) -> StackFrame:
    return StackFrame(
        id=frame_id,
        label=label,
        hint=hint,
        character=character,
        src=KIT_PREFIX + CHARACTER_FILES[character],
    )


def _stations_from_plan(plan: dict[str, Any], title: str) -> list[GameStation]:
    stations: list[GameStation] = []
    seen: set[str] = set()
    for i, raw in enumerate(plan.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        if len(stations) >= 3:
            break
        label = _text(raw.get("title"), f"Station {len(stations) + 1}", 100)
        plaque = _text(
            raw.get("objective") or raw.get("body") or raw.get("summary"),
            f"Notice how this relates to {title}.",
            500,
        )
        stations.append(_make_station(label, plaque, len(stations), seen))

    facts = plan.get("facts") or []
    fi = 0
    while len(stations) < 2 and fi < len(facts):
        fact = facts[fi]
        fi += 1
        text = _text(
            fact if not isinstance(fact, dict) else fact.get("text") or fact.get("claim"),
            "",
            500,
        )
        if not text:
            continue
        label = _text(text.split(".")[0], f"Insight {len(stations) + 1}", 100)
        stations.append(_make_station(label, text, len(stations), seen))

    defaults = (
        ("Base case", f"What stops the recursion for {title}?"),
        ("Recursive step", f"What smaller problem does {title} reduce to?"),
        ("Call stack", f"What piles up before {title} unwinds?"),
    )
    di = 0
    while len(stations) < 2:
        label, plaque = defaults[di % len(defaults)]
        di += 1
        stations.append(_make_station(label, plaque, len(stations), seen))

    return stations[:3]


def _make_station(
    title: str, plaque: str, index: int, seen: set[str]
) -> GameStation:
    character = _CHAR_CYCLE[index % len(_CHAR_CYCLE)]
    clip = _CLIP_CYCLE[index % len(_CLIP_CYCLE)]
    sid = _slug(title) or f"station-{index + 1}"
    if sid in seen:
        sid = f"{sid}-{index + 1}"
    seen.add(sid)
    return GameStation(
        id=sid,
        title=title,
        plaque=plaque,
        character=character,
        visit_clip=clip,
        src=KIT_PREFIX + CHARACTER_FILES[character],
    )


def _slug(value: Any) -> str:
    result = _ID_RE.sub("-", str(value or "").lower()).strip("-")
    return result[:64]


def _text(value: Any, fallback: str, limit: int) -> str:
    text = _TAGS_RE.sub("", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        text = fallback
    return text[:limit]
