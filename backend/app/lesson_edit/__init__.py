"""Lesson-edit agent — surgical in-place updates (not coursegen authoring).

Owns HTML section rewrites, A2UI section rewrites, and catalogue node inserts.
Never regenerates a whole lesson document. Inputs are **one unit** only
(section outerHTML or A2UI section/node JSON), never the full capsule.
"""
from __future__ import annotations

from .agent import (
    author_catalogue_insert,
    rewrite_a2ui_section,
    rewrite_html_section,
    style_fingerprint,
)

__all__ = [
    "author_catalogue_insert",
    "rewrite_a2ui_section",
    "rewrite_html_section",
    "style_fingerprint",
]
