"""fast_gen Phase 5: per-section parallel authoring — eligibility, assembly, fallback."""
from app.coursegen import sections as sec


def _plan(n: int = 3, archetype: str = "explainer") -> dict:
    return {
        "title": "Gears",
        "archetype": archetype,
        "difficulty": "intermediate",
        "facts": [],
        "interactions": [{"kind": "sliders", "id": "ratio", "label": "Gear ratio"}],
        "sections": [
            {
                "id": f"part-{i}",
                "icon": "school",
                "title": f"Part {i}",
                "objective": f"Learn part {i}",
                "body": f"<p>Draft body {i}</p>",
            }
            for i in range(n)
        ],
    }


class _SectionLLM:
    """Returns a valid fragment for every section, echoing the slug it was asked for."""

    def __init__(self, bad_slugs: set[str] | None = None, *, text_only: bool = False):
        self.bad = bad_slugs or set()
        self.text_only = text_only
        self.calls: list[str] = []

    async def generate_html(self, system: str, user: str, on_delta=None) -> str:
        slug = system.split('data-lesson-section="')[1].split('"')[0]
        self.calls.append(slug)
        if slug in self.bad:
            return "sorry, here is a paragraph instead"  # invalid fragment → fallback
        body = f"<h2>{slug}</h2>" + ("x" * 300)
        if not self.text_only:
            body += (
                f'<canvas id="{slug}-c" width="200" height="80"></canvas>'
                f'<input type="range" id="{slug}-r" min="0" max="10" value="5">'
            )
        html = (
            f'<section id="section-{slug}" data-lesson-section="{slug}" '
            f'data-lesson-title="{slug}">{body}</section>'
        )
        if on_delta is not None:
            res = on_delta(html)
            if hasattr(res, "__await__"):
                await res
        return f"```html\n{html}\n```"  # fences must be stripped


def test_eligibility_gates() -> None:
    assert sec.sections_eligible(_plan(), {}) is True
    assert sec.sections_eligible(_plan(archetype="simulation"), {}) is False
    assert sec.sections_eligible(_plan(archetype="game"), {}) is False
    assert sec.sections_eligible(_plan(n=1), {}) is False
    assert sec.sections_eligible(_plan(), {"previous_html": "<html>"}) is False
    assert sec.sections_eligible(_plan(), {"target_html": "<div>"}) is False


async def test_author_sections_assembles_in_plan_order() -> None:
    plan = _plan(3)
    llm = _SectionLLM()
    html = await sec.author_sections(plan=plan, llm=llm)
    assert html is not None
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    # All three sections present, in plan order, inside the server shell.
    positions = [html.index(f'data-lesson-section="part-{i}"') for i in range(3)]
    assert positions == sorted(positions)
    assert "cdn.tailwindcss.com" in html  # server-owned head, not model-authored


async def test_bad_section_degrades_to_plan_body_fallback() -> None:
    plan = _plan(3)
    llm = _SectionLLM(bad_slugs={"part-1"})
    html = await sec.author_sections(plan=plan, llm=llm)
    assert html is not None
    # The failed section shipped its deterministic draft-body fallback (with SVG stub).
    assert "<p>Draft body 1</p>" in html
    assert "<svg" in html
    # Invalid output was retried once before falling back.
    assert llm.calls.count("part-1") == 2


async def test_all_sections_failing_returns_none_for_whole_doc_fallback() -> None:
    plan = _plan(2)
    llm = _SectionLLM(bad_slugs={"part-0", "part-1"})
    assert await sec.author_sections(plan=plan, llm=llm) is None


async def test_text_only_section_rejected_then_fallback() -> None:
    plan = _plan(2)
    llm = _SectionLLM(text_only=True)
    html = await sec.author_sections(plan=plan, llm=llm)
    # Both sections fail the visual gate → systemic failure → None (whole-doc fallback).
    assert html is None
    assert llm.calls.count("part-0") == 2


def test_fragment_cleaning_extracts_and_rejects() -> None:
    ok = (
        f'<section data-lesson-section="a">{"x" * 200}'
        f"<canvas width='10' height='10'></canvas></section>"
    )
    # Noise (and even a page wrapper) around the section is stripped to the fragment.
    assert sec._clean_fragment(f"noise before {ok} noise after") == ok
    assert sec._clean_fragment(f"<html><body>{ok}</body></html>") == ok
    # Page-level markup *inside* the fragment is rejected outright.
    assert sec._clean_fragment("<section>" + "x" * 300 + "<body>oops</body></section>") is None
    assert sec._clean_fragment("no section here") is None
    # Text-only sections rejected even when long enough.
    text_only = f'<section data-lesson-section="a">{"x" * 300}</section>'
    assert sec._clean_fragment(text_only) is None
