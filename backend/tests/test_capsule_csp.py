from app.capsule.csp import artifact_csp
from app.capsule.postprocess import ensure_artifact_runtime, postprocess
from app.core.config import get_settings


def test_frame_ancestors_converts_cors_allowlist_to_csp_sources(monkeypatch) -> None:
    monkeypatch.setenv(
        "FRONTEND_ORIGIN",
        "http://localhost:5173,https://8xdj824y.insforge.site",
    )
    get_settings.cache_clear()

    try:
        csp = artifact_csp()
    finally:
        get_settings.cache_clear()

    assert (
        "frame-ancestors 'self' http://localhost:5173 https://8xdj824y.insforge.site"
        in csp
    )


def test_capsule_bridge_reports_content_minimized_learning_events() -> None:
    html, _checks = postprocess(
        "<html><body><section data-lesson-section='intro'><button id='try'>Try</button></section></body></html>"
    )

    assert "HT_LEARNING_EVENT" in html
    assert "capsule_control_used" in html
    assert "capsule_section_viewed" in html
    assert "hituto:studio-event" in html
    assert "studio_control_changed" in html


def test_capsule_gets_guidebridge_runtime_and_no_legacy_page_control() -> None:
    """Page control moved to the GuideBridge iframe runtime; the slim Hi-Tuto
    bridge must no longer carry snapshot/execute/agent-cursor code."""
    html, checks = postprocess(
        "<html><body><section data-lesson-section='intro'><button id='try'>Try</button>"
        "<canvas></canvas><img src='x.png'/></section></body></html>"
    )

    from guidebridge.iframe import IFRAME_RUNTIME_MARKER

    assert IFRAME_RUNTIME_MARKER in html
    assert "HT_GET_SNAPSHOT" not in html
    assert "HT_EXECUTE_ACTION" not in html
    assert "HT_AGENT_CURSOR" not in html
    # Edit mode + HTML export survive in the slim bridge.
    assert "HT_SET_EDIT_MODE" in html
    assert "HT_GET_HTML" in html
    # The parent-access gate judged only MODEL code, not our injected scripts.
    assert "unsafe parent/top window access" not in checks["failed"]


def test_reprocessing_injected_artifact_passes_parent_access_check() -> None:
    """SECURITY-CRITICAL ordering: both first-party scripts use window.parent and are
    stripped before the parent-access lint, then re-injected. Re-processing stored
    (already-injected) HTML must never fail its own scripts."""
    seed = (
        "<html><body><section data-lesson-section='intro'><button id='try'>Try</button>"
        "<canvas></canvas><img src='x.png'/></section></body></html>"
    )
    first, first_checks = postprocess(seed)
    assert "unsafe parent/top window access" not in first_checks["failed"]

    second, second_checks = postprocess(first)
    assert "unsafe parent/top window access" not in second_checks["failed"]

    from guidebridge.iframe import IFRAME_RUNTIME_MARKER

    # Idempotent: exactly one copy of each injected script family.
    assert second.count(IFRAME_RUNTIME_MARKER) == 1
    assert second.count("hituto-lesson-bridge v") == 1


def test_serve_time_upgrade_swaps_old_fat_bridge_for_slim_plus_runtime() -> None:
    """Stored artifacts carrying the old v6/v7 bridge (with page control) get the
    slim v8 bridge + guidebridge runtime at serve time, no regeneration."""
    old_style = (
        "<html><body><h1>Old lesson</h1>"
        "<script>\n// hituto-lesson-bridge v6\n(function(){ /* old fat bridge with "
        "HT_GET_SNAPSHOT and HT_EXECUTE_ACTION handlers */ })();\n</script>"
        "</body></html>"
    )

    upgraded = ensure_artifact_runtime(old_style)

    from guidebridge.iframe import IFRAME_RUNTIME_MARKER

    assert "hituto-lesson-bridge v8" in upgraded
    assert "hituto-lesson-bridge v6" not in upgraded
    assert IFRAME_RUNTIME_MARKER in upgraded
    assert "HT_GET_SNAPSHOT" not in upgraded


def test_legacy_generated_lesson_receives_spacious_transparent_page_layout() -> None:
    legacy = """<!doctype html>
    <html><head><style>
    body { background:#F5F2EA; color:#1B1A16; font-family:"Plus Jakarta Sans"; }
    h1 { font-family:"Bricolage Grotesque", ui-sans-serif; color:#2C50EE; }
    </style></head><body><div class="flex"><nav class="fixed"></nav><main></main></div></body></html>
    """

    migrated = ensure_artifact_runtime(legacy)

    assert "hituto-generated-lesson-theme-v2" in migrated
    assert "#FDF1E7" in migrated
    assert "#4B2450" in migrated
    assert "background:transparent !important" in migrated
    assert "nav.fixed {\n    display:none !important;" in migrated
    assert "main > header { display:none !important; }" in migrated
    assert "position:sticky !important" not in migrated
    assert "#F5F2EA" not in migrated


def test_studio_template_does_not_receive_legacy_page_layout_patch() -> None:
    studio = """<!doctype html>
    <html data-studio-mode="specimen"><head><style>body { background:#f7f1e8; }</style></head>
    <body><main>Studio</main></body></html>
    """

    migrated = ensure_artifact_runtime(studio)

    assert "hituto-generated-lesson-theme-v2" not in migrated
