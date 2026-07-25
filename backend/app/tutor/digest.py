"""Back-compat shim — the digesters moved to the surface protocol (specs/design_agents §6).

Import from ``app.surface`` going forward; this module survives only so existing
imports (tests, older callers) keep working during the transition.
"""
from __future__ import annotations

from ..surface.digest import ARTIFACT_DIGEST_CHARS, html_to_text

__all__ = ["ARTIFACT_DIGEST_CHARS", "html_to_text"]
