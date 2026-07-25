---
name: ui-slide-deck
description: >-
  Slide-deck lesson shell — one idea per slide with prev/next navigation.
  Use when knobs.presentation is slide or the learner asked for slides/deck/presentation mode.
---

# UI Skill: Slide Deck

Build a **stepped slide deck**, not a long scroll article and not the Canvas Studio shell.

## Layout

- Full-viewport slides stacked or translated horizontally
- One primary idea per slide (headline + short body + optional viz)
- Bottom or side: Prev / Next + progress dots
- Shared palette and typography from `hituto-generated-lesson-design`; use one bold color field per
  slide and keep controls visually identical to page lessons.

## Required

- Add `<meta name="hituto-presentation" content="slide">` inside `<head>` so the capsule gate
  preserves the deck's full-viewport section geometry.
- `data-lesson-control="slide-prev"` / `slide-next` / `slide-goto-N`
- Each slide: `data-lesson-section="slide-N"` + `data-lesson-title`
- At least one canvas viz, one `go-data-src` image, one interactive control across the deck
- Keep under ~45 KB

## Do not

- Do not use the studio sidebar chrome (`ui-studio-style`)
- Do not dump all content on one scrollable page
