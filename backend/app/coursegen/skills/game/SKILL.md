---
name: game
description: >-
  Author immersive educational mini-games inside HTML lesson capsules. Default to a
  Code Artists Recursion Galleries–style Three.js explore stage using the first-party
  Quaternius toon kit when characters are needed. Classic allowlisted Three.js only —
  never Phaser, ES modules, or third-party asset CDNs.
---

# Immersive mini-game capsules (3D explore first)

> **Production path:** when `GAME_DESIGN_ENABLED` is on, coursegen routes `archetype=game`
> through a validated **GameManifest** + server-owned `ui-game-style` runtime (no LLM
> Three.js). This skill still applies for deep-agent / page fallback authoring.

Ship a **walkable / explorable 3D learning space** — Code Artists Recursion Galleries energy
plus real characters from the **first-party toon kit** — **not** a scroll textbook with cubes
or a stock photo.

If the first screen is prose + a photograph, you failed.

## REQUIRED first paint (non-negotiable)

The **first** content in `<body>` must be ONE stage section:

1. One-line **Goal**
2. Full-width `#stage3d` canvas (~50vh+) with a **dark** background (`#0B1220`)
3. **Next / Reset** + `Visited N / M` (`aria-live`)
4. One plaque readout

**Forbidden before the stage:** stock `/image` photos, essay sections, calculators, secondary
canvases.

**Forbidden as the “3D”:** white-on-white wireframes or empty paper canvases. Prefer loaded
toon characters + colored pedestals on a dark floor.

## First-party toon kit (REQUIRED for character games)

Load characters **only** from these same-origin URLs (Quaternius CC0, served by Hi Tuto):

| Role | URL |
|---|---|
| Guide / hero | `/game-kits/toon/Character_Soldier.gltf` |
| Alternate | `/game-kits/toon/Character_Hazmat.gltf` |
| Challenge | `/game-kits/toon/Character_Enemy.gltf` |

Include **both** pinned scripts from the system prompt:

- `{{THREE_JS_CDN}}`
- `{{GLTF_LOADER_CDN}}`

Use classic `THREE.GLTFLoader` (global). Play `Idle` by default; on visit switch to `Wave` or
`Yes`. Scale ~1.0–1.4; feet on y=0. Do **not** invent `/mesh?key=` hashes or hotlink Quaternius
/ Drive / vibejam CDNs.

If a model fails to load, keep the pedestal + show an error on the plaque — still stage-first.

## 3D gallery loop

1. **Explore** — drag orbit + click station (raycast) + Next button.
2. **Learn-on-contact** — plaque updates with the concept fragment; character reacts.
3. **Progress** — `Visited N / M`; success when all stations visited.
4. **Reset** — camera + visits + Idle restore.

2–3 stations is enough. Prefer ~45 KB of **your** HTML/JS (models load separately).

## Stack constraints

- Classic script tags only — **no ES modules / importmaps / Phaser / OrbitControls CDN**.
- Orbit via pointer listeners on the `THREE` global (r147 UMD).
- Hemisphere + Directional lights so textured characters read clearly.
- Tutor hooks: `data-lesson-section` / `data-lesson-control`; lime primary buttons.
- No vibejam art packs or third-party GLB URLs.

## Fallback (rare)

Procedural high-contrast meshes only if the lesson is non-character spatial. Still stage-first.

## Distinction from simulation

- **Game** — explore/challenge with progress to a clear success.
- **Simulation** — parameterize → play/step → readout; use `simulation` skill.
