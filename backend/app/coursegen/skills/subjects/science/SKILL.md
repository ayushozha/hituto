---
name: science
description: >-
  Science lesson guidance for coursegen. Use for biology, physics, earth science,
  and when lessons need structural 3D, labs, or Canvas Studio inspectable UIs.
---

# science

## Spatial / structural topics

When the lesson is about cells, organelles, membranes, anatomy, molecules, or other
inspectable structure:

1. Set / honor `needs_3d: true` when a mesh helps more than a flat diagram
2. **UI:** `ui-studio-style` (interactive specimen explorer — short copy, clipped stage, no quizzes)
3. **Mesh:** `hunyuan-3d` only when `presentation: studio` (`generate_mesh`); soft-fail to procedural

## Non-spatial science

Use the default scroll capsule from `lesson_system.md` (experiments, equations, charts).
