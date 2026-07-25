# Process-cutaway mode

Use `process-cutaway` when the learner must follow material, energy, information, or force through
ordered stages or internal components.

## Required learner loop

Choose a stage → see the active region and flow direction → read its transformation → play or step
through the complete sequence.

## Required manifest behavior

- Declare `timeline`, `playback`, `focus_anchor`, and `reset` capabilities.
- Provide at least two ordered stages.
- Synchronize timeline position, active stage, annotation, explanation, and flow highlight.
- Explain input, transformation, and output with supplied evidence where available.
- Enable isolate/explode only for declared multi-part nodes.

## Asset routing

Prefer a reviewed multi-part GLB or a procedural assembly. Do not use a single fused image-to-3D
mesh as if it contains trustworthy internal parts. Fall back to a simplified procedural flow that
still teaches the complete sequence.

## Interaction checks

- Timeline movement changes the active stage visibly.
- Playback advances stages and announces completion.
- Previous/next or direct stage selection remains available when motion is reduced.
- Flow direction is visible without relying on color alone.
- The final output is explicitly connected to the starting input.
