"""image_artist subagent — plans lesson imagery (course-authoring-flow §5).

Planning only, no generation calls: capsule images resolve lazily through the
same-origin `/gen` proxy at view time (`<img go-data-src=...>`), so authoring
costs nothing. The artist writes a compact manifest the capsule author reads.
"""
from __future__ import annotations


def image_artist_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: writes an image-prompt manifest to /build/media.json."""
    from ..prompt_loader import load_agent_prompt

    return {
        "name": "image_artist",
        "description": (
            "Plan the lesson's illustrative imagery: 1-3 image prompts with placements, "
            "written to /build/media.json for the capsule author."
        ),
        "system_prompt": load_agent_prompt(
            "image_artist",
            "You are the image artist. Plan 1-3 illustrative images for the lesson: one hero "
            "image plus optional section illustrations. Write /build/media.json via write_file "
            'as {"images": [{"prompt": str, "aspect": "16:9|1:1|4:3", "placement": str}]}. '
            "Prompts must be concrete and subject-accurate (no text-in-image, no charts — "
            "charts are canvas work). Images load lazily via <img go-data-src=\"<prompt>\"> in "
            "the capsule; NEVER inline base64 image data and never fetch images yourself.",
        ),
    }
