# Specimen mode

Use `specimen` when inspecting an object's shape, surface, spatial relationships, or labelled
regions is the teaching action.

## Required learner loop

Select a subject → orbit or zoom → select an anchor → connect the visible region with a concise
explanation and supplied evidence.

## Required manifest behavior

- Provide at least one subject and one focus part.
- Declare `orbit`, `zoom`, `focus_anchor`, and `reset` capabilities.
- Use normalized anchors for fused generated meshes.
- Use `mesh_node` only when a reviewed multi-part asset exposes that node.
- Keep comparison optional; include it only when it changes the stage or adds direct contrast.

## Asset routing

Prefer image-to-3D or a supplied GLB for a single biological specimen, artifact, product, or static
machine. Prefer procedural geometry for planets, atoms, molecules, fields, and exact mathematical
objects. Fall back to the procedural specimen scene without blocking lesson generation.

## Interaction checks

- Drag changes the object/camera orientation.
- Wheel or keyboard zoom changes framing within safe bounds.
- Reset restores the declared camera preset.
- Focus selection updates the stage annotation and evidence rail.
- Fused meshes expose focus markers, not fake isolate or animation controls.
