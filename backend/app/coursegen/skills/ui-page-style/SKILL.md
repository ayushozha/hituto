---
name: ui-page-style
description: >-
  Default scroll-page lesson shell — a scrollable interactive mini-app with a clear
  section rhythm. Use when knobs.presentation is page (or resolves to the default).
---

# UI Skill: Page

Build a **scrollable interactive mini-app**, not a slide deck and not the Canvas Studio shell.

## Layout

- Start with the shared `hituto-generated-lesson-design` canvas and token contract (zinc-neutral).
- Outer shell: `mx-auto max-w-7xl px-4 py-5 md:px-6 md:py-7` (e.g. `<main class="ht-shell …">`).
- **Reading column (required):** put every major section inside one centered column —
  `mx-auto w-full max-w-3xl` (768px). Same width for every section so side gutters stay even and
  more of a section fits on screen. Do not use `max-w-4xl` / `max-w-5xl` / `max-w-6xl` or
  full-bleed sections that stretch to the shell.
- Use one spacious centered content column on a transparent canvas. Do not add a sidebar.
- Start directly with the first content section. Do not generate a lesson title, intro header,
  module label, table of contents, or section-navigation buttons.
- Keep prose near 65–72 characters per line (`max-w-2xl` on text-only blocks is fine);
  keep cards, grids, and interactive regions inside the `max-w-3xl` column.
- Section rhythm: hook → concept → interactive exploration → check → recap
- Each concept section pairs a short explanation with a hands-on element beside/below it
- Alternate restrained mint soft fills with white panels; one lime accent action per section.

## Required

- Each major section: `data-lesson-section="..."` + `data-lesson-title`
- Interactive controls carry `data-lesson-control` (sliders, buttons, toggles)
- At least one **drawn** visualization (canvas or inline SVG) wired to a control
  (change input → graphic updates). Prefer Chart.js only for standard charts.
- Optional real-world `<img go-data-src="/image?query=...">` only when a photograph teaches
  better than a diagram — never use `/gen` art as the teaching graphic.
- A short knowledge check (2–3 questions) near the end — inline, no score dashboard
- Primary actions are lime pills; supporting cards are flat with a light `border-line`.
- Keep under ~45 KB; max-width 100% — no horizontal overflow.

## Do not

- Do not use the studio sidebar chrome (`ui-studio-style`) unless the plan sets `needs_3d`
- Do not paginate content behind prev/next controls (`ui-slide-deck` owns that)
- Do not duplicate trusted host title/progress/tutor/share controls inside the capsule
- Do not imitate a generic documentation site with a white page, blue active link, and fixed rail
- Do not tint the full lesson canvas or place the content inside nested background containers
- Do not front-load a wall of text — interleave explanation and interaction
- Do not require decorative hero images
- Do not stretch sections to the full `max-w-7xl` shell or mix `max-w-4xl`/`max-w-3xl`/full-bleed —
  one `max-w-3xl` reading column for the whole lesson (`capsule/postprocess.py` coerces this)
- Never touch `window.parent`, `window.top`, or `localStorage`
