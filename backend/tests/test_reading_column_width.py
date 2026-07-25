"""Page capsules share one reading-column width (max-w-3xl / 768px)."""

from app.capsule.postprocess import (
    _normalize_reading_column_width,
    ensure_artifact_runtime,
    postprocess,
)


def test_coerces_section_max_w_4xl_to_3xl() -> None:
    html = _normalize_reading_column_width(
        '<main class="ht-shell mx-auto max-w-7xl px-4">'
        '<section data-lesson-section="intro" '
        'class="max-w-4xl mx-auto px-4 sm:px-6 py-8">'
        "<p>Hi</p></section></main>"
    )

    assert 'class="ht-shell mx-auto max-w-7xl px-4"' in html
    assert "max-w-4xl" not in html
    assert "max-w-3xl" in html
    assert 'class="max-w-3xl mx-auto px-4 sm:px-6 py-8"' in html


def test_adds_reading_column_to_bare_full_bleed_section() -> None:
    html = _normalize_reading_column_width(
        '<main class="mx-auto max-w-7xl">'
        '<section data-lesson-section="spectrum" id="section-spectrum">'
        "<p>Wide</p></section></main>"
    )

    assert 'class="mx-auto w-full max-w-3xl"' in html
    assert "max-w-7xl" in html


def test_preserves_existing_max_w_3xl_and_prose() -> None:
    html = _normalize_reading_column_width(
        '<main class="ht-shell mx-auto max-w-7xl">'
        '<div class="mx-auto w-full max-w-3xl space-y-10">'
        '<section data-lesson-section="a" class="bg-paper">'
        '<p class="max-w-2xl text-ink-soft">Prose</p>'
        "</section></div></main>"
    )

    assert html.count("max-w-3xl") >= 2  # wrapper + forced on section without max-w
    assert "max-w-2xl" in html
    assert "max-w-7xl" in html


def test_skips_studio_capsules() -> None:
    raw = (
        '<html data-studio-mode="specimen"><body>'
        '<section class="max-w-4xl mx-auto">Studio</section>'
        "</body></html>"
    )
    assert _normalize_reading_column_width(raw) == raw


def test_skips_slide_capsules() -> None:
    with_meta = (
        '<html><head><meta name="hituto-presentation" content="slide"></head><body>'
        '<section data-lesson-section="slide-1" class="h-screen w-full">Slide</section>'
        "</body></html>"
    )
    legacy = (
        '<section data-lesson-section="slide-1" class="h-screen w-full">'
        "Legacy slide</section>"
    )

    assert _normalize_reading_column_width(with_meta) == with_meta
    assert _normalize_reading_column_width(legacy) == legacy


def test_postprocess_and_serve_time_apply_reading_column() -> None:
    raw = (
        "<!DOCTYPE html><html><head>"
        '<script src="https://cdn.tailwindcss.com"></script></head><body>'
        '<main class="ht-shell mx-auto max-w-7xl">'
        '<section data-lesson-section="a" class="max-w-4xl mx-auto">'
        "<svg></svg><button type='button'>Go</button></section>"
        '<section data-lesson-section="b"><canvas></canvas><p>Full</p></section>'
        "</main></body></html>"
    )
    cleaned, checks = postprocess(raw)
    assert "max-w-4xl" not in cleaned
    assert cleaned.count("max-w-3xl") >= 2
    assert "max-w-7xl" in cleaned
    assert checks["passed"]

    served = ensure_artifact_runtime(raw)
    assert "max-w-4xl" not in served
    assert "max-w-3xl" in served


def test_normalize_is_idempotent() -> None:
    raw = (
        '<section class="max-w-4xl mx-auto" data-lesson-section="x">'
        "<div>y</div></section>"
        '<section data-lesson-section="z">z</section>'
    )
    once = _normalize_reading_column_width(raw)
    twice = _normalize_reading_column_width(once)
    assert once == twice
    assert "max-w-4xl" not in twice
    assert twice.count("max-w-3xl") >= 2
