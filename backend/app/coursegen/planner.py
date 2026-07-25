"""interpret/plan logic: topic + knobs -> archetype + rich syllabus/lesson plans."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_ARCHETYPE_HINTS = {
    "game": ("game", "play", "quiz", "puzzle", "memory", "arcade"),
    "simulation": ("simulate", "simulation", "model", "physics", "ising", "orbit", "evolution"),
    "tool": ("calculator", "converter", "planner", "budget", "tracker", "estimator"),
    "narrative": ("story", "adventure", "novel", "scenario", "role-play", "roleplay"),
}


def pick_archetype(topic: str) -> str:
    low = topic.lower()
    for arch, hints in _ARCHETYPE_HINTS.items():
        if any(h in low for h in hints):
            return arch
    return "explainer"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "section"


def _learner_summary(context: dict | None) -> str:
    """One-line learner-profile rendering for planner prompts (specs/learner_profile)."""
    if not isinstance(context, dict) or not context:
        return ""
    from ..services.profile_service import summary_line

    return summary_line(context)


async def build_syllabus(topic: str, knobs: dict) -> dict:
    from .studio_catalog import is_studio_knobs, shape_studio_syllabus

    requested = knobs.get("archetype") or "auto"
    difficulty = knobs.get("difficulty", "intermediate")
    base_topic = re.split(r"\n\nchange request:", topic, maxsplit=1, flags=re.I)[0]
    title = base_topic.strip().rstrip(".?!").title()
    studio = is_studio_knobs(knobs)

    from ..providers.registry import get_coursegen_planner_llm
    llm = get_coursegen_planner_llm()

    if studio:
        plan = {
            "title": title,
            "subtitle": f"A single-page studio for exploring {title}.",
            "lessons": [
                {
                    "title": f"{title} Studio",
                    "objective": f"Explore {title} via subjects in the studio sidebar.",
                    "archetype": requested if requested != "auto" else "explainer",
                    "estimated_duration": "10m",
                }
            ],
        }
        return shape_studio_syllabus(plan, topic, knobs)

    if "fractal" in topic.lower():
        # Curated demo syllabus: "fractals" is the showcase topic, so its plan is
        # hand-tuned rather than LLM-generated (see _fractal_lesson_blueprint).
        title = "Fractals"
        subtitle = "The geometry of nature, infinity, and iteration."
        lessons = [
            {"title": "What exactly is a Fractal?", "objective": "Build intuition for self-similarity and recursive structure.", "archetype": "explainer", "estimated_duration": "5m"},
            {"title": "The Mathematics: Fractal Dimension", "objective": "Explain why fractals can have non-integer dimension.", "archetype": "tool", "estimated_duration": "8m"},
            {"title": "The Mandelbrot & Julia Sets", "objective": "Let learners explore linked complex-plane dynamics.", "archetype": "simulation", "estimated_duration": "10m"},
            {"title": "Constructing Infinity", "objective": "Show recursive construction with iteration sliders.", "archetype": "simulation", "estimated_duration": "7m"},
            {"title": "Fractals in Nature: The Chaos Game", "objective": "Turn randomness into a stable fractal pattern.", "archetype": "game", "estimated_duration": "8m"}
        ]
    else:
        from ..services.billing_plans import MAX_LESSONS_PER_COURSE_CREDIT

        try:
            max_lessons = int(knobs.get("max_lessons") or MAX_LESSONS_PER_COURSE_CREDIT)
        except (TypeError, ValueError):
            max_lessons = MAX_LESSONS_PER_COURSE_CREDIT
        max_lessons = max(1, min(MAX_LESSONS_PER_COURSE_CREDIT, max_lessons))

        system_prompt = f"""You are an expert learning designer. Create a multi-chapter course syllabus outline for a given topic.
Output MUST be a valid JSON object matching this schema:
{{
  "title": "Course Title",
  "subtitle": "Short, engaging course subtitle",
  "lessons": [
    {{
      "title": "Lesson Title (e.g. Chapter 1: Introduction to X)",
      "objective": "Brief learning objective for this lesson",
      "archetype": "explainer|game|simulation|tool|narrative",
      "estimated_duration": "5m"
    }}
  ]
}}
Design between 3 to {max_lessons} chapters/lessons that progress logically.
Return ONLY the raw JSON object. No markdown formatting, no comments."""

        user_prompt = f"Topic: {title}\nDifficulty: {difficulty}\nArchetype Preference: {requested}"
        learner_line = _learner_summary(knobs.get("learner_profile"))
        if learner_line:
            user_prompt += f"\n{learner_line} Shape lesson ordering and sizing accordingly."
        # Bind defaults up front so the except-fallback (below) can't hit UnboundLocalError.
        subtitle = f"An interactive {difficulty}-level guide to {title}."
        try:
            resp = await llm.generate_html(system_prompt, user_prompt)
            clean_resp = re.sub(r"^```json\s*", "", resp.strip())
            clean_resp = re.sub(r"\s*```$", "", clean_resp)
            data = json.loads(clean_resp)
            title = data.get("title") or title
            subtitle = data.get("subtitle") or f"An interactive {difficulty}-level guide to {title}."
            lessons = data.get("lessons", [])
        except Exception as exc:
            logger.warning("Syllabus generation failed for %r; using generic fallback lessons: %s", title, exc)
            lessons = [
                {"title": f"Introduction to {title}", "objective": f"Explain the core concept of {title}.", "archetype": "explainer", "estimated_duration": "5m"},
                {"title": f"{title} Core Mechanics", "objective": f"Explore how {title} behaves with parameters.", "archetype": "simulation", "estimated_duration": "8m"},
                {"title": f"Interactive {title} Playground", "objective": f"Practice with a live {title} challenge.", "archetype": "game", "estimated_duration": "10m"},
                {"title": f"Advanced Applications of {title}", "objective": f"Apply {title} to real-world scenarios.", "archetype": "tool", "estimated_duration": "7m"}
            ]

    from ..services.billing_plans import MAX_LESSONS_PER_COURSE_CREDIT

    try:
        max_lessons = int(knobs.get("max_lessons") or MAX_LESSONS_PER_COURSE_CREDIT)
    except (TypeError, ValueError):
        max_lessons = MAX_LESSONS_PER_COURSE_CREDIT
    max_lessons = max(1, min(MAX_LESSONS_PER_COURSE_CREDIT, max_lessons))
    lessons = list(lessons)[:max_lessons]

    return {
        "title": title,
        "subtitle": subtitle,
        "lessons": lessons,
    }


async def build_lesson_plan(
    course_title: str,
    lesson_title: str,
    objective: str,
    archetype: str,
    difficulty: str,
    style_theme: str | None = None,
    presentation: str | None = None,
    learner_profile: dict | None = None,
) -> dict:
    from ..providers.registry import get_coursegen_planner_llm
    llm = get_coursegen_planner_llm()
    
    if "fractal" in course_title.lower():
        sections, interactions = _fractal_lesson_blueprint(lesson_title)
    else:
        system_prompt = f"""You are an expert learning designer. Create a detailed outline for a single interactive educational lesson/page.
The lesson is a chapter within a larger course on "{course_title}".
Output MUST be a valid JSON object matching this schema:
{{
  "sections": [
    {{
      "id": "slug-name",
      "icon": "material-symbol-name",
      "title": "Section Title",
      "objective": "Brief learning objective",
      "body": "<p>Detailed lesson text with HTML formatting. Keep it engaging.</p>",
      "image": "optional search query for an image"
    }}
  ],
  "interactions": [
    {{
      "kind": "canvas|game|calculator|tool|sliders",
      "id": "widget-id",
      "label": "Brief description of the widget"
    }}
  ]
}}
Return ONLY the raw JSON object. No markdown formatting, no comments."""

        user_prompt = f"Lesson Title: {lesson_title}\nObjective: {objective}\nArchetype: {archetype}\nDifficulty: {difficulty}"
        learner_line = _learner_summary(learner_profile)
        if learner_line:
            user_prompt += f"\n{learner_line} Reflect it in section ordering and interactions."
        try:
            resp = await llm.generate_html(system_prompt, user_prompt)
            clean_resp = re.sub(r"^```json\s*", "", resp.strip())
            clean_resp = re.sub(r"\s*```$", "", clean_resp)
            data = json.loads(clean_resp)
            sections = data.get("sections", [])
            interactions = data.get("interactions", [])
        except Exception as exc:
            logger.warning("Lesson plan generation failed for %r; using generic blueprint: %s", lesson_title, exc)
            sections, interactions = _generic_blueprint(lesson_title, archetype)

    return {
        "title": lesson_title,
        "subtitle": objective,
        "archetype": archetype,
        "difficulty": difficulty,
        "style_theme": style_theme,
        "presentation": presentation or "auto",
        "cover_prompt": f"hyperreal abstract illustration representing {lesson_title}, dark cinematic background",
        "sections": sections,
        "interactions": interactions,
        "facts": [],
    }


def _section(title: str, icon: str, objective: str, body: str, image: str | None = None) -> dict:
    return {
        "id": _slug(title),
        "icon": icon,
        "title": title,
        "objective": objective,
        "body": body,
        "image": image,
    }


def _fractal_lesson_blueprint(title: str) -> tuple[list[dict], list[dict]]:
    low = title.lower()
    if "what exactly" in low:
        sections = [
            _section(
                "What exactly is a Fractal?",
                "blur_on",
                "Build intuition for self-similarity, detail at every scale, and recursive structure.",
                "<p><strong>Fractals</strong> are shapes whose parts echo the whole. Zoom in and new detail keeps appearing, often through a simple rule repeated many times.</p><ul><li>Self-similarity: smaller regions resemble the larger form.</li><li>Fine detail: structure persists across scales.</li><li>Simple rules: complexity emerges from iteration.</li></ul>",
                "macro photograph of Romanesco broccoli spiral fractal geometry",
            ),
            _section(
                "A Brief History of Infinity",
                "timeline",
                "Place Mandelbrot and fractal geometry in a historical arc.",
                "<p>The modern word <strong>fractal</strong> was popularized by Benoit Mandelbrot, but mathematicians had studied strange recursive curves long before computers made them visible.</p>",
            ),
        ]
        interactions = []
    elif "mathematics" in low or "dimension" in low:
        sections = [
            _section(
                "The Mathematics: Fractal Dimension",
                "functions",
                "Explain why fractals can have non-integer dimension.",
                "<p>Fractal dimension measures how detail changes as scale changes. A curve can fill more than a line but less than a plane, so its dimension can sit between 1 and 2.</p>",
            ),
        ]
        interactions = [{"kind": "calculator", "id": "dimension-calc", "label": "Fractal dimension calculator"}]
    elif "mandelbrot" in low or "julia" in low:
        sections = [
            _section(
                "The Mandelbrot & Julia Sets",
                "auto_awesome",
                "Let learners explore linked complex-plane dynamics.",
                "<p>The Mandelbrot set maps which complex numbers remain bounded under repeated squaring. Julia sets reveal the behavior for a fixed parameter.</p>",
            ),
        ]
        interactions = [{"kind": "canvas", "id": "mandelbrot-julia", "label": "Linked Mandelbrot and Julia explorer"}]
    elif "constructing" in low or "infinity" in low:
        sections = [
            _section(
                "Constructing Infinity",
                "construction",
                "Show recursive construction with iteration sliders.",
                "<p>Koch snowflakes and Sierpinski triangles are built by repeating a small construction step. Drag the sliders to watch complexity grow.</p>",
            ),
        ]
        interactions = [{"kind": "sliders", "id": "recursive-builders", "label": "Koch and Sierpinski iteration sliders"}]
    else:  # Chaos Game / Nature
        sections = [
            _section(
                "Fractals in Nature: The Chaos Game",
                "forest",
                "Turn randomness into a stable fractal pattern.",
                "<p>The chaos game repeatedly jumps toward randomly selected triangle corners. Random moves converge into the Sierpinski triangle.</p>",
            ),
            _section(
                "Real-World Applications",
                "travel_explore",
                "Connect fractals to antennas, lungs, terrain, art, and simulation.",
                "<p>Fractal geometry appears in branching lungs, coastlines, terrain generation, antennas, compression, and procedural art.</p>",
            ),
        ]
        interactions = [{"kind": "game", "id": "chaos-game", "label": "Chaos game point generator"}]
    return sections, interactions


def _generic_blueprint(title: str, archetype: str) -> tuple[list[dict], list[dict]]:
    if archetype == "game":
        sections = [
            _section("Mission Brief", "flag", f"Explain the objective of learning {title}.", f"<p>Learn <strong>{title}</strong> through short challenges, feedback, and repeatable practice.</p>"),
            _section("Rules of Play", "rule", "Turn concepts into simple game rules.", f"<p>Each round asks you to match a concept, prediction, or pattern related to {title}.</p>"),
            _section("Practice Arena", "sports_esports", "Provide a playable widget.", "<p>Use the game board to test recall and build intuition.</p>"),
            _section("Debrief", "workspace_premium", "Summarize what mastery looks like.", "<p>Review the score and replay until the main ideas feel automatic.</p>"),
        ]
        return sections, [{"kind": "game", "id": "practice-arena", "label": "Playable practice board"}]
    if archetype == "simulation":
        sections = [
            _section("System Overview", "hub", f"Introduce the moving parts of {title}.", f"<p><strong>{title}</strong> is easiest to understand as a system of variables that influence one another.</p>"),
            _section("Parameter Lab", "tune", "Expose the controllable parameters.", "<p>Adjust the model and watch the output change immediately.</p>"),
            _section("Live Simulation", "analytics", "Render dynamic behavior.", "<p>The canvas translates abstract rules into motion and visible patterns.</p>"),
            _section("What to Notice", "visibility", "Guide interpretation.", "<p>Look for thresholds, feedback loops, and surprising stable states.</p>"),
        ]
        return sections, [{"kind": "canvas", "id": "simulation-lab", "label": "Parameter-driven simulation"}]
    if archetype == "tool":
        sections = [
            _section("Goal", "target", f"Define the practical outcome for {title}.", f"<p>This mini-tool helps you reason through <strong>{title}</strong> with inputs, outputs, and tradeoffs.</p>"),
            _section("Inputs", "input", "Collect meaningful learner choices.", "<p>Change the sliders and fields to see how the recommendation shifts.</p>"),
            _section("Result", "fact_check", "Explain the output.", "<p>The result updates live so every assumption is inspectable.</p>"),
            _section("Next Step", "arrow_forward", "Provide actionable follow-through.", "<p>Use the summary as a checklist for the real-world task.</p>"),
        ]
        return sections, [{"kind": "tool", "id": "decision-tool", "label": "Interactive decision helper"}]
    if archetype == "narrative":
        sections = [
            _section("Scene", "theater_comedy", f"Set up the world of {title}.", f"<p>Enter a guided scenario where each choice reveals a key idea about <strong>{title}</strong>.</p>"),
            _section("Characters", "groups", "Make the concept memorable through roles.", "<p>Each character represents a force, constraint, or decision point.</p>"),
            _section("Choice Point", "alt_route", "Let the learner branch the story.", "<p>Click through choices and compare outcomes.</p>"),
            _section("Reflection", "psychology", "Tie story events back to learning.", "<p>The ending explains why the best choice works.</p>"),
        ]
        return sections, [{"kind": "narrative", "id": "choice-story", "label": "Branching scene"}]
    sections = [
        _section("Why It Matters", "lightbulb", f"Set the stakes for {title}.", f"<p><strong>{title}</strong> becomes clear when you can see the big idea, manipulate it, and connect it to real examples.</p>", f"{title} concept visual"),
        _section("Core Model", "schema", f"Break {title} into parts.", "<p>Start with the smallest useful model, then layer complexity only when the learner can interact with it.</p>"),
        _section("Interactive Lab", "play_circle", f"Experiment with {title}.", "<p>Drag controls, observe the visualization, and compare outcomes.</p>"),
        _section("Applications", "apps", f"Connect {title} to the world.", "<p>Use the final cards to remember where this idea shows up outside the lesson.</p>"),
    ]
    return sections, [{"kind": "canvas", "id": "interactive-lab", "label": "Topic-specific interactive lab"}]
