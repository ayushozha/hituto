---
name: ui-game-style
description: >-
  Server-owned GameManifest templates and toon-gallery runtime. Authors do not write
  Three.js for archetype=game when GAME_DESIGN_ENABLED — fill the manifest; this skill
  owns the stage.
---

# Game gallery (server template)

When `GAME_DESIGN_ENABLED` routes a lesson to the game design agent:

1. Build a validated `GameManifest` (`coursegen.game_manifest.build_game_manifest`).
2. Render through `game-gallery.html` + `game-runtime.js` (`coursegen.game_renderer`).
3. Capsule `postprocess` remains the security gate.

Characters load only from `/game-kits/toon/`. Classic Three.js r147 + GLTFLoader pins only.
