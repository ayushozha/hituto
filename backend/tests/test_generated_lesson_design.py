from pathlib import Path

from app.capsule.postprocess import postprocess
from app.coursegen.agents.lesson_agent import _brief
from app.coursegen.agents.roles.capsule_author import _fallback_tree, capsule_author_subagent
from app.coursegen.prompt import SYSTEM, build_user_prompt

_SKILLS = Path(__file__).resolve().parents[1] / "app" / "coursegen" / "skills"


def _plan(**overrides: object) -> dict:
    base = {
        "title": "Loop Engineering",
        "archetype": "explainer",
        "difficulty": "intermediate",
        "sections": [{"title": "The loop", "objective": "Trace one iteration."}],
        "interactions": [{"type": "slider", "purpose": "Change iteration count"}],
        "facts": [],
        "knobs": {"presentation": "page"},
    }
    base.update(overrides)
    return base


def test_graph_prompt_contains_current_hituto_design_contract() -> None:
    assert "hituto-generated-lesson-design" in SYSTEM
    assert "paper:'#FAFAFA'" in SYSTEM
    assert "fixed full-height documentation sidebar" in SYSTEM
    assert "Bricolage Grotesque:opsz" not in SYSTEM


def test_deep_capsule_author_receives_brand_skill_before_page_shell() -> None:
    prompt = capsule_author_subagent(design="page")["system_prompt"]

    brand_index = prompt.index("Shared Hi Tuto lesson design")
    shell_index = prompt.index("Page shell — REQUIRED")
    assert brand_index < shell_index
    assert "#FAFAFA" in prompt
    assert "Never build a fixed full-height documentation sidebar" in prompt


def test_page_brief_starts_with_first_section_without_heading_or_navigation() -> None:
    prompt = build_user_prompt(_plan())

    assert "Start directly with the first learning section" in prompt
    assert "Do not generate a page title" in prompt
    assert "section navigation" in prompt
    assert "Include a fixed left-rail" not in prompt


def test_deep_page_brief_and_a2ui_fallback_do_not_repeat_host_title() -> None:
    brief = _brief("course-1", _plan(), "Loop Engineering", "page")
    assert "Start /build/capsule.html directly with the first content section" in brief
    assert "no title/intro header" in brief

    tree = _fallback_tree(_plan())
    children = tree["root"]["children"]
    assert children[0]["props"]["text"] == "The loop"
    assert all(node.get("props", {}).get("text") != "Loop Engineering" for node in children)


def test_game_skill_contract_forbids_phaser_and_requires_3d_explore() -> None:
    body = (_SKILLS / "game" / "SKILL.md").read_text(encoding="utf-8")
    assert "Phaser" in body
    assert "goal" in body.lower() and "reset" in body.lower()
    assert "Three.js" in body or "three.js" in body.lower()
    assert "explore" in body.lower()
    assert "data-lesson-control" in body
    assert "ES modules" in body or "No ES modules" in body
    assert "/game-kits/toon/" in body
    assert "Character_Soldier.gltf" in body
    assert "GLTFLoader" in body or "GLTF_LOADER" in body
    assert "stock" in body.lower() or "photograph" in body.lower() or "photo" in body.lower()
    assert "#stage3d" in body or "stage3d" in body


def test_simulation_skill_distinguishes_from_game() -> None:
    body = (_SKILLS / "simulation" / "SKILL.md").read_text(encoding="utf-8")
    assert "Parameterize" in body or "parameterize" in body
    assert "Placeholder" not in body
    assert "game skill" in body.lower() or "`game`" in body
    assert "Phaser" in body


def test_user_prompt_injects_game_skill_for_game_archetype() -> None:
    prompt = build_user_prompt(
        _plan(
            archetype="game",
            title="Chaos Game",
            sections=[{"title": "Play", "objective": "Build the Sierpinski pattern."}],
            interactions=[{"kind": "game", "id": "chaos-game"}],
        )
    )
    assert "Archetype skill — REQUIRED for this game lesson" in prompt
    assert "Immersive mini-game capsules" in prompt
    assert "Three.js" in prompt or "explore" in prompt.lower()
    assert "Phaser" in prompt


def test_user_prompt_injects_simulation_skill_not_game() -> None:
    prompt = build_user_prompt(
        _plan(
            archetype="simulation",
            title="Orbit Lab",
            sections=[{"title": "Parameters", "objective": "Vary eccentricity."}],
        )
    )
    assert "Archetype skill — REQUIRED for this simulation lesson" in prompt
    assert "Simulation capsules" in prompt
    assert "Immersive mini-game capsules" not in prompt


def test_user_prompt_skips_archetype_skill_for_explainer() -> None:
    prompt = build_user_prompt(_plan())
    assert "Archetype skill — REQUIRED" not in prompt
    assert "Immersive mini-game capsules" not in prompt


def test_deep_capsule_author_injects_game_skill_after_shell() -> None:
    prompt = capsule_author_subagent(design="page", archetype="game")["system_prompt"]
    shell_index = prompt.index("Page shell — REQUIRED")
    game_index = prompt.index("Game archetype — REQUIRED")
    assert shell_index < game_index
    assert "Immersive mini-game capsules" in prompt
    assert "Phaser" in prompt


def test_deep_capsule_author_injects_simulation_skill() -> None:
    prompt = capsule_author_subagent(design="page", archetype="simulation")["system_prompt"]
    assert "Simulation archetype — REQUIRED" in prompt
    assert "Simulation capsules" in prompt


def test_minimal_game_capsule_passes_postprocess() -> None:
    raw = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Game</title>
<script src="https://cdn.tailwindcss.com"></script>
</head><body>
<section id="arena" data-lesson-section="arena" data-lesson-title="Practice Arena">
  <p>Score: <span id="score" aria-live="polite">0</span></p>
  <canvas id="board" width="320" height="180"></canvas>
  <button type="button" data-lesson-control="score-point" aria-label="Score a point">Play</button>
  <button type="button" data-lesson-control="reset-game" aria-label="Reset">Reset</button>
</section>
<script>
(function () {
  var score = 0;
  var canvas = document.getElementById("board");
  var ctx = canvas.getContext("2d");
  var scoreEl = document.getElementById("score");
  function draw() {
    ctx.fillStyle = "#FAFAFA";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#16A34A";
    ctx.fillRect(20, 20, 40 + score * 8, 40);
  }
  function setScore(n) {
    score = n;
    scoreEl.textContent = String(score);
    draw();
  }
  document.querySelector("[data-lesson-control=score-point]").addEventListener("click", function () {
    setScore(score + 1);
  });
  document.querySelector("[data-lesson-control=reset-game]").addEventListener("click", function () {
    setScore(0);
  });
  draw();
})();
</script>
</body></html>"""
    cleaned, checks = postprocess(raw)
    assert "unsafe parent/top window access" not in checks["failed"]
    assert "data-lesson-control" in cleaned
    assert "Reset" in cleaned
    assert "<canvas" in cleaned
