---
name: simulation
description: >-
  Author parameter-driven educational simulations inside HTML lesson capsules. Use when the
  lesson archetype is simulation (or the plan centers on observing a dynamic system). Canvas or
  allowlisted Three.js — never Phaser. Distinct from the game skill (no required win condition).
---

# Simulation capsules

Build a **working parameter-driven simulation** that teaches cause and effect — not a static
diagram, not a scored mini-game. Align with Studio simulation intent when presentation is studio;
for page/slide shells, keep the same learner loop inside a scroll section.

## Learner loop (required)

1. **Parameterize** — at least one bounded control (slider, select, or toggle) with units and a
   safe default; show the current value beside the control.
2. **Play / step** — Play/Pause and/or Step that advances the model; Reset returns to the
   deterministic initial state.
3. **Observe** — stage (canvas / SVG / Three.js) and numeric readout update together so the
   learner can explain the relationship.

Every control must produce an immediate visible change. Dead scrubbers and fake play buttons fail.

## Simulation vs game

| | Simulation | Game (`skills/game`) |
|---|---|---|
| Goal | Observe how a system responds | Achieve a challenge (score / target / count) |
| Win condition | Optional / none | Required |
| Primary loop | Parameterize → play/step → readout | Goal → play → feedback → reset |

If the plan archetype is `game`, follow the game skill instead.

## Stack and data

- Prefer procedural **canvas / SVG**; use pinned Three.js / GLTFLoader URLs only when spatial 3D
  is essential. **No Phaser or other engines.** No ES modules / importmaps.
- When a **PRECOMPUTED SIMULATION TRACE** (or compute artifact) is in the brief, render and
  step/replay **only those values** — do not recompute competing physics client-side.
- Procedural equations are fine when no verified trace is supplied; keep them deterministic and
  seeded. Do not claim physical accuracy from decorative mesh motion.
- Same capsule rules: zinc brand tokens, tutor hooks, no parent/storage access, ~45 KB budget.

## UI and accessibility

- Lime for Play / primary actions; sand/zinc for secondary; Reset always available.
- Stage + current-value readout stay synchronized; use `aria-live="polite"` on the readout.
- `data-lesson-section` on the sim block; `data-lesson-control` on every control.
- Keyboard-operable controls; if `prefers-reduced-motion: reduce`, prefer Step / static frames
  over continuous animation.

## Studio presentation note

When `PRESENTATION = studio` and studio mode is simulation, preserve the Studio v2 stage-first
layout and capabilities (`parameterize`, `playback`, `reset`). Do not invent a second shell or
duplicate host title/progress/tutor chrome.
