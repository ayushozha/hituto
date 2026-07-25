---
name: ui-studio-style
description: >-
  Build stage-first Hi Tuto Studio lessons using the validated specimen, simulation, or
  process-cutaway mode. Use for presentation=studio lessons, spatial inspection, controllable
  systems, and staged internal processes; select image-to-3D only for suitable static specimens.
---

# UI Skill: Studio v2

Build one interactive learning lab around a dominant live stage. Keep selection/input on the left,
the learning object in the center, explanation/evidence on the right, and time or playback controls
at the bottom. Treat these as information roles, not a requirement to create many cards.

The graph pipeline owns initial Studio rendering:

1. Resolve `studio_mode` with `coursegen.studio_manifest.resolve_studio_mode`.
2. Plan only mode-compatible assets.
3. Build and validate `StudioManifest`.
4. Render `assets/templates/studio-v2.html` with `scripts/studio-tokens.css` and
   `scripts/studio-runtime.js`.
5. Pass the complete document through the capsule postprocessor and runtime validator.

Do not replace this flow with arbitrary generated HTML for initial Studio lessons.

## Select one shipped mode

| Mode | Select when | Read |
|---|---|---|
| `specimen` | Orbiting and annotating a mostly static object teaches the objective | [references/specimen.md](references/specimen.md) |
| `simulation` | A bounded input changes a time-based system or verified trace | [references/simulation.md](references/simulation.md) |
| `process-cutaway` | A learner must trace stages, flow, or internal transformation | [references/process-cutaway.md](references/process-cutaway.md) |

Do not route systems maps, telemetry maps, or configurators until their runtime adapters and
validated mode references ship.

## Shared invariants

- Make the stage at least 55% of usable desktop width and the first content on mobile.
- Wire every visible control to state, a visible response, and an accessible current value.
- Use domain labels such as `Components`, `Forces`, or `Stages`; avoid generic repeated headings.
- Keep the lesson title/progress and tutor/voice surfaces in the trusted host shell.
- Use short explanations and link factual claims to supplied evidence IDs when available.
- Declare an asset fallback; never let a mesh timeout block a usable lesson.
- Emit only normalized, content-minimized Studio learning events through the lesson bridge.
- Keep one scene owner and one animation loop. Never start a second WebGL renderer when the mesh
  runtime owns the canvas.
- Add `data-lesson-section` and `data-lesson-control` hooks to primary surfaces and controls.
- Preserve `h-screen` behavior, keyboard operation, reduced motion, and mobile bottom sheets.

## Asset choice

- Use image-to-3D for a single static specimen whose silhouette or surface matters.
- Use procedural geometry for exact mathematical, orbital, molecular, field, and dynamic models.
- Use reviewed multi-part assets or procedural assemblies for joints, internals, cutaways, and
  isolation.
- Never infer scientific claims, semantic parts, rigging, or physical behavior from a generated
  fused mesh.
- Enable isolate/hide/animate only when the manifest declares the required mesh-node capability.

## Reject the artifact when

- a control changes only its own styling;
- a required capability is absent from the selected asset;
- the stage is obscured or smaller than the supporting panels;
- placeholder copy or nonfunctional actions remain;
- a fallback cannot teach the objective;
- the capsule gate, browser validation, keyboard path, or reduced-motion path fails; or
- console errors or competing scene loops appear.
