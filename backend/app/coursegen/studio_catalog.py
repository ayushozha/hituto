"""Studio chapter catalog — subjects for the 8-card shell (one chapter, many subjects)."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field


class StudioSubject(BaseModel):
    id: str
    name: str
    subtitle: str = ""
    mesh_strategy: Literal["hunyuan", "procedural"] = "procedural"
    prompt: str | None = None
    default_part: str = "part-0"
    compare_a: str = ""
    compare_b: str = ""
    procedural_kind: Literal[
        "plant-cell",
        "animal-cell",
        "bacteria",
        "neuron",
        "muscle-fiber",
    ] | None = None
    stage_image_query: str | None = None
    initial_yaw: float | None = None
    initial_pitch: float | None = None
    tags: list[str] = Field(default_factory=list)
    field_notes: list[dict[str, str]] = Field(default_factory=list)
    flower_query: str | None = None
    # Filled after generation:
    path: str | None = None
    cache_key: str | None = None


_SOLAR = [
    ("mercury", "Mercury", "Rocky inner planet"),
    ("venus", "Venus", "Thick atmosphere"),
    ("earth", "Earth", "Our home world"),
    ("mars", "Mars", "The red planet"),
    ("jupiter", "Jupiter", "Gas giant"),
    ("saturn", "Saturn", "Ringed giant"),
    ("uranus", "Uranus", "Ice giant"),
    ("neptune", "Neptune", "Distant ice giant"),
]

_CELL_TYPES = [
    ("plant", "Plant Cell", "Eukaryotic"),
    ("animal", "Animal Cell", "Eukaryotic"),
    ("bacteria", "Bacteria Cell", "Prokaryotic"),
    ("neuron", "Neuron", "Nerve cell"),
    ("muscle", "Muscle Cell", "Contractile fiber"),
]

_CELL_MESH_DETAILS = {
    "plant": (
        "a thick cell wall, membrane, nucleus, central vacuole, chloroplasts, and mitochondria, "
        "all contained inside one cohesive cell body"
    ),
}

_CELL_PROCEDURAL_KIND = {
    "plant": "plant-cell",
    "animal": "animal-cell",
    "bacteria": "bacteria",
    "neuron": "neuron",
    "muscle": "muscle-fiber",
}

_POLLINATORS = [
    {
        "id": "orchid-bee",
        "name": "Orchid Bee",
        "subtitle": "Euglossa dilemma · Apidae",
        "tags": ["Neotropical", "Diurnal", "Solitary", "Fragrance collector"],
        "field_notes": [
            {
                "label": "Species details",
                "value": (
                    "An iridescent metallic bee; males carry orchid fragrances in enlarged "
                    "hind-leg pockets."
                ),
            },
            {
                "label": "Pollination traits",
                "value": (
                    "Fast, agile flight and a long tongue help it reach complex tropical blossoms."
                ),
            },
            {
                "label": "Favorite flowers",
                "value": (
                    "Orchids, Costus, Stanhopea, vanilla, passionflower, and fragrant forest "
                    "blooms."
                ),
            },
            {
                "label": "Range",
                "value": "Tropical Central America into northern South America.",
            },
            {
                "label": "Ecological role",
                "value": (
                    "A specialist orchid pollinator and fragrance transporter in tropical forests."
                ),
            },
        ],
        "flower_query": "single purple tropical orchid botanical plate on warm ivory background",
    },
    {
        "id": "garden-tiger",
        "name": "Garden Tiger Moth",
        "subtitle": "Arctia caja · Erebidae",
        "tags": ["Nocturnal", "Nectarivore", "Silk moth relative"],
        "field_notes": [
            {
                "label": "Species details",
                "value": (
                    "A large moth with chocolate-and-cream forewings and vivid orange hindwings."
                ),
            },
            {
                "label": "Pollination traits",
                "value": "Transfers pollen while feeding from fragrant flowers after dusk.",
            },
            {
                "label": "Favorite flowers",
                "value": "Evening primrose, jasmine, and other night-blooming flowers.",
            },
            {
                "label": "Range",
                "value": "Temperate habitats across Europe, Asia, and North America.",
            },
            {
                "label": "Ecological role",
                "value": (
                    "Connects nocturnal flower communities while also supporting birds and bats "
                    "as prey."
                ),
            },
        ],
        "flower_query": "single white moonflower botanical plate on warm ivory background",
    },
    {
        "id": "jewel-beetle",
        "name": "Jewel Beetle",
        "subtitle": "Buprestidae · Coleoptera",
        "tags": ["Metallic", "Diurnal", "Ancient pollinator"],
        "field_notes": [
            {
                "label": "Species details",
                "value": (
                    "A heavily armored beetle with brilliant structural color across its wing "
                    "cases."
                ),
            },
            {
                "label": "Pollination traits",
                "value": (
                    "Carries pollen across its textured body while feeding on pollen and floral "
                    "tissue."
                ),
            },
            {
                "label": "Favorite flowers",
                "value": "Magnolia, water lilies, cycads, and open bowl-shaped flowers.",
            },
            {
                "label": "Range",
                "value": "Worldwide, with greatest diversity in warm forest habitats.",
            },
            {
                "label": "Ecological role",
                "value": "An important early-diverging pollinator; larvae also recycle dead wood.",
            },
        ],
        "flower_query": "single white magnolia botanical plate on warm ivory background",
    },
    {
        "id": "ruby-hummingbird",
        "name": "Ruby-throated Hummingbird",
        "subtitle": "Archilochus colubris · Trochilidae",
        "tags": ["Diurnal", "Hover-feeder", "Long-distance migrant"],
        "field_notes": [
            {
                "label": "Species details",
                "value": (
                    "A tiny emerald hummingbird; adult males carry a luminous ruby throat patch."
                ),
            },
            {
                "label": "Pollination traits",
                "value": (
                    "Hovering flight and a long bill transfer pollen among deep tubular flowers."
                ),
            },
            {
                "label": "Favorite flowers",
                "value": "Trumpet vine, cardinal flower, bee balm, and red columbine.",
            },
            {
                "label": "Range",
                "value": "Eastern North America, wintering in Mexico and Central America.",
            },
            {
                "label": "Ecological role",
                "value": (
                    "A mobile pollen courier connecting distant flowering patches across "
                    "migration routes."
                ),
            },
        ],
        "flower_query": "single red cardinal flower botanical plate on warm ivory background",
    },
    {
        "id": "lesser-long-nosed-bat",
        "name": "Lesser Long-nosed Bat",
        "subtitle": "Leptonycteris yerbabuenae · Phyllostomidae",
        "tags": ["Mammal", "Nocturnal", "Keystone pollinator"],
        "field_notes": [
            {
                "label": "Species details",
                "value": "A small nectar bat with an elongated muzzle and brush-tipped tongue.",
            },
            {
                "label": "Pollination traits",
                "value": (
                    "Its face and fur collect heavy pollen while it hovers at large night flowers."
                ),
            },
            {
                "label": "Favorite flowers",
                "value": "Agave, saguaro, organ-pipe cactus, and columnar cacti.",
            },
            {"label": "Range", "value": "Mexico and the desert southwest of the United States."},
            {
                "label": "Ecological role",
                "value": (
                    "Essential for wild agave and cactus reproduction across desert ecosystems."
                ),
            },
        ],
        "flower_query": "single agave blossom botanical plate on warm ivory background",
    },
]

_POLLINATOR_MESH_PROMPTS = {
    "orchid-bee": (
        "Scientifically accurate adult male orchid bee (Euglossa dilemma), complete full body, "
        "iridescent emerald exoskeleton, two transparent wing pairs held slightly open, two "
        "antennae, six separated legs, and enlarged fragrance-carrying hind tibiae"
    ),
    "garden-tiger": (
        "Scientifically accurate garden tiger moth (Arctia caja), complete full body, stout "
        "thorax, paired antennae, six visible legs, and all four patterned wings opened in a "
        "shallow natural V so the cream, brown, orange, and blue markings remain distinct"
    ),
    "jewel-beetle": (
        "Scientifically accurate jewel beetle (Buprestidae), complete full body, elongated "
        "armored form, metallic green and blue elytra, visible head and antennae, and six clearly "
        "separated connected legs"
    ),
    "ruby-hummingbird": (
        "Scientifically accurate adult male ruby-throated hummingbird (Archilochus colubris), "
        "complete full body, emerald back, ruby gorget, long connected bill, two wings partially "
        "spread, and a compact fanned tail"
    ),
    "lesser-long-nosed-bat": (
        "Scientifically accurate lesser long-nosed bat (Leptonycteris yerbabuenae), complete full "
        "body, elongated muzzle, upright ears, visible hind feet, and both wings partially spread "
        "with each continuous membrane clearly connected to the body and fingers"
    ),
}

# Pixal3D preserves the source-view geometry, but imported GLBs do not share one
# canonical forward axis. Keep a reviewed presentation angle with each specimen so
# the learner sees recognizable anatomy immediately while retaining free orbit.
_POLLINATOR_INITIAL_VIEW = {
    "garden-tiger": (0.0, 0.0),
    "jewel-beetle": (3.14159, 0.0),
    "lesser-long-nosed-bat": (-1.5708, 0.0),
}


def _pollinator_stage_query(name: str) -> str:
    return (
        f"Ultra-detailed macro field-guide photograph of one {name}, complete full body, "
        "single three-quarter side view, accurate natural anatomy, every wing and limb visible, "
        "isolated on a uniform warm ivory background, soft contact shadow directly underneath, "
        "museum specimen lighting, crisp focus, photorealistic, centered and filling 82 percent "
        "of the frame, no flower, no foliage, no habitat, no props, no text, no labels, no border"
    )


def _primary_subject_name(topic: str, concept: str | None = None) -> str:
    """Extract the object to model without leaking lesson instructions into its image."""
    name = (concept or topic or "Subject").strip()
    name = re.sub(r"^chapter\s+\d+\s*[:\-–—]?\s*", "", name, flags=re.I) or name
    # Course prompts commonly use an em-dash to introduce learning goals. Those goals
    # are useful to the lesson author but become unwanted props in an image-to-3D input.
    name = re.split(r"\s+[—–]\s+", name, maxsplit=1)[0].strip() or name
    # "Pollinator Lab: Orchid Bee" describes one object: the text after the lab label.
    if ":" in name:
        prefix, candidate = name.split(":", 1)
        if re.search(r"\b(lab|studio|explorer|lesson|guide)\b", prefix, re.I):
            name = candidate.strip() or name
    name = re.sub(r"\s+(studio|lesson)$", "", name, flags=re.I).strip()
    return (name or "Subject")[:80]


def is_studio_knobs(knobs: dict[str, Any] | None) -> bool:
    """True when create-course explicitly requested studio design mode."""
    from .presentation import knobs_design_mode

    return knobs_design_mode(knobs) == "studio"


def shape_studio_syllabus(
    plan: dict[str, Any], topic: str, knobs: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Force a single studio chapter — subjects live inside the capsule, not as lessons."""
    from .studio_manifest import resolve_studio_mode

    lessons = list(plan.get("lessons") or [])
    title = (plan.get("title") or topic or "Studio").strip()
    studio_mode = resolve_studio_mode({"title": title, "topic": topic}, knobs)
    studio_archetype = "simulation" if studio_mode == "simulation" else "explainer"
    if lessons:
        first = dict(lessons[0])
        first["title"] = first.get("title") or f"{title} Studio"
        first["objective"] = (
            first.get("objective")
            or f"Explore {title} through a focused interactive Studio lab."
        )
        first["archetype"] = studio_archetype
        first["estimated_duration"] = first.get("estimated_duration") or "10m"
        plan["lessons"] = [first]
    else:
        plan["lessons"] = [
            {
                "title": f"{title} Studio",
                "objective": f"Explore {title} in an interactive studio.",
                "archetype": studio_archetype,
                "estimated_duration": "10m",
            }
        ]
    plan["studio_chapter"] = True
    plan["studio_mode"] = studio_mode
    plan.setdefault("subtitle", plan.get("subtitle") or f"A single-page studio for {title}.")
    return plan


def propose_studio_subjects(topic: str, concept: str | None = None) -> list[StudioSubject]:
    """Heuristic subject catalog for the studio sidebar (no LLM required)."""
    hay = f"{topic} {concept or ''}".lower()

    if re.search(r"\b(pollinat(?:or|ion|ors)?|orchid\s+bee)\b", hay):
        return [
            StudioSubject(
                id=entry["id"],
                name=entry["name"],
                subtitle=entry["subtitle"],
                # Pixal3D is image-to-mesh: the provider turns this reconstruction prompt into
                # one isolated square reference image, uploads that image, and caches the GLB.
                # stage_image_query remains a truthful visual fallback when a subject fails.
                mesh_strategy="hunyuan",
                prompt=_POLLINATOR_MESH_PROMPTS[entry["id"]],
                stage_image_query=_pollinator_stage_query(entry["name"]),
                initial_yaw=_POLLINATOR_INITIAL_VIEW.get(entry["id"], (None, None))[0],
                initial_pitch=_POLLINATOR_INITIAL_VIEW.get(entry["id"], (None, None))[1],
                tags=entry["tags"],
                field_notes=entry["field_notes"],
                flower_query=entry["flower_query"],
                compare_a=entry["name"],
                compare_b="Orchid Bee" if entry["id"] != "orchid-bee" else "Garden Tiger Moth",
            )
            for entry in _POLLINATORS
        ]

    if re.search(r"\b(solar\s*system|planets?)\b", hay):
        subjects = [
            StudioSubject(
                id=sid,
                name=name,
                subtitle=sub,
                mesh_strategy="procedural",  # spheres are cheap
                prompt=f"Educational 3D model of planet {name}, single centered sphere, PBR, clean background",
                compare_a=name,
                compare_b="Earth" if sid != "earth" else "Mars",
            )
            for sid, name, sub in _SOLAR
        ]
        # Mark a couple for Hunyuan if budget allows (complex detail)
        for s in subjects:
            if s.id in ("saturn", "jupiter"):
                s.mesh_strategy = "hunyuan"
        return subjects

    if re.search(r"\b(cells?|organelles?|biology|eukaryot|prokaryot)\b", hay):
        subjects = [
            StudioSubject(
                id=sid,
                name=name,
                subtitle=sub,
                # A generated plant-cell cutaway is visually strong; fragile branching
                # and hidden anatomy are deterministic so they cannot disappear during
                # single-view reconstruction. Every cell also has a procedural fallback.
                mesh_strategy="hunyuan" if sid == "plant" else "procedural",
                prompt=(
                    f"One cohesive plant cell educational sculpture with {_CELL_MESH_DETAILS[sid]}. "
                    "One connected subject, distinct educational colors, realistic 3D materials"
                    if sid == "plant"
                    else None
                ),
                procedural_kind=_CELL_PROCEDURAL_KIND[sid],
                compare_a=name,
                compare_b="Plant Cell" if sid != "plant" else "Animal Cell",
            )
            for sid, name, sub in _CELL_TYPES
        ]
        return subjects

    # Generic: one primary subject = the concept/topic
    name = _primary_subject_name(topic, concept)
    return [
        StudioSubject(
            id="primary",
            name=name,
            subtitle="Primary subject",
            mesh_strategy="hunyuan",
            prompt=(
                f"{name}. Accurate educational 3D object with realistic geometry and materials"
            ),
            compare_a=name[:40],
            compare_b="Related form",
        )
    ]


def studio_subjects_for_prompt(subjects: list[StudioSubject]) -> list[dict[str, Any]]:
    """Serialize catalog for LLM prompt + capsule wiring (public URLs filled at persist)."""
    out: list[dict[str, Any]] = []
    for s in subjects:
        entry: dict[str, Any] = {
            "id": s.id,
            "name": s.name,
            "subtitle": s.subtitle,
            "mesh_strategy": s.mesh_strategy,
            "default_part": s.default_part,
            "compare_a": s.compare_a,
            "compare_b": s.compare_b,
        }
        if s.path:
            entry["meshSrc"] = s.path
        if s.cache_key:
            entry["cache_key"] = s.cache_key
        if s.prompt:
            entry["prompt"] = s.prompt
        if s.procedural_kind:
            entry["procedural_kind"] = s.procedural_kind
        if s.stage_image_query:
            entry["stage_image_query"] = s.stage_image_query
        if s.initial_yaw is not None:
            entry["initial_yaw"] = s.initial_yaw
        if s.initial_pitch is not None:
            entry["initial_pitch"] = s.initial_pitch
        if s.tags:
            entry["tags"] = s.tags
        if s.field_notes:
            entry["field_notes"] = s.field_notes
        if s.flower_query:
            entry["flower_query"] = s.flower_query
        out.append(entry)
    return out
