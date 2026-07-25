---
name: capsule-authoring
description: >-
  Author Hi Tuto HTML lesson capsules. Use when emitting final lesson HTML,
  choosing scroll vs Canvas Studio vs slide shell, wiring tutor hooks, or applying
  postprocess/CSP constraints.
---

# capsule-authoring

Emit one complete, self-contained HTML capsule that passes `capsule/postprocess.py`.

## Choose a shell (from `knobs.presentation` / plan.presentation)

| Presentation | Shell | Skill |
|---|---|---|
| `studio` | Validated stage-first lab (specimen / simulation / process cutaway) | `ui-studio-style` |
| `page` | Scroll mini-app | `lesson_system.md` paper theme |
| `slide` | Stepped deck | `ui-slide-deck` |
| `auto` | Resolved by `coursegen/presentation.py` (spatial/3D → studio, else page) | — |

When presentation is `auto`, `needs_3d: true` or a Hunyuan mesh selects **studio**. An explicit
`page` or `slide` presentation remains authoritative.

## Hard constraints (every capsule)

- Tailwind CDN + only pinned Chart.js / Three.js / GLTFLoader URLs from postprocess
- Images: `go-data-src="/gen?..."` or `go-data-src="/image?query=..."` only
- Tutor hooks: `data-lesson-section`, `data-lesson-title`, `data-lesson-control` on controls
- At least one working canvas, one lazy image, one control that changes the view
- End with `</body></html>`; keep under ~45 KB

## Studio mode extras

- Initial Studio lessons are rendered from `StudioManifest`; do not invent another shell.
- Use the selected mode reference plus the shared `studio-tokens.css` / `studio-runtime.js`.
- Short copy only; no Chapter Map, quiz, self-assessment, game, score, or tutor panel inside the capsule
- When `data-mesh-src` present: do not start a second Three.js loop
- Hunyuan mesh generation is **specimen Studio only**; simulation and cutaway use suitable adapters.

## Page / slide mode

Follow `coursegen/prompts/lesson_system.md` paper theme (Bricolage / Jakarta / cobalt / grass).

## Archetype skills (game / simulation)

When the lesson `archetype` is `game` or `simulation`, also follow the injected skill:

| Archetype | Skill | Intent |
|---|---|---|
| `game` | `skills/game` | Default: dominant Three.js explore gallery (goal → explore stations → progress → reset) |
| `simulation` | `skills/simulation` | Parameterize → play/step → readout (no required win) |

Game lessons are stage-first (Recursion Galleries–style), not scroll textbooks. Classic pinned
Three.js only — never Phaser, ES modules, or third-party jam art packs.
