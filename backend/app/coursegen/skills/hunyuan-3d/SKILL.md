---
name: hunyuan-3d
description: >-
  Generate PBR meshes (Hunyuan 3D Pro) for specimen-mode Studio lessons only.
  Use when presentation is studio, studio_mode is specimen, and a subject needs realistic 3D.
  Studio chrome lives in ui-studio-style — this skill owns mesh generation only.
---

# hunyuan-3d

Produce a GLB (or batch of GLBs) for the **studio stage**. Soft-fail to procedural geometry.

**UI chrome:** follow `skills/ui-studio-style/` (editorial specimen-explorer shell). Do not invent a separate layout.

## When

- `presentation: studio` and `studio_mode: specimen` only — **never** call `generate_mesh` for
  page/slide, simulation, or process-cutaway lessons (cost gate)
- `viz-engineer` / mesh role during `asset_plan`
- `capsule-author` embeds mesh(es) inside the clipped studio stage canvas

## Steps

1. **Prompt** — educational, single centered object, PBR, no text overlays
2. **Optional image-to-3D** — `get_media().generate_image`, then `generate_mesh(image_url=...)` for complex detail
3. **Mesh tool** — `generate_mesh(prompt=..., enable_pbr=true, face_count=1000000)` via `providers.registry.get_mesh()`; the configured provider applies its own safe limit
4. **Embed** in studio shell:
   ```html
   <canvas id="studio-canvas" width="640" height="420"></canvas>
   <div data-mesh-src="/build/mesh/model.glb" data-mesh-canvas="studio-canvas" hidden></div>
   ```
5. **Manifest handoff** — return managed mesh paths to `StudioManifest`; the server-owned Studio
   runtime handles loading and keeps a procedural fallback available.

## Do not

- Start a second Three.js loop when `data-mesh-src` is present (mesh runtime owns the canvas)
- Invent OrbitControls CDN / ES modules
- Mix studio tokens with cobalt paper theme
- Generate Hunyuan meshes outside specimen Studio presentation

## Soft-fail

Missing mesh credentials (`TENCENTCLOUD_SECRET_ID/KEY` preferred; GMI/Atlas are optional fallbacks), API errors, or timeouts must not fail the lesson — procedural abstract fallback inside the clipped stage.
