# Dimensional mascot system

## Source order

Use these sources in order:

1. `../../../frontend/src/components/Mascot.tsx` — live source of truth.
2. `../assets/Mascot.tsx` — skill-bundled reusable snapshot; synchronize it after every live mascot change.
3. `../../ui-ux-design.md` — placement and broader composition guidance.

Do not use the generated raster concept in the app. It has a baked background. The SVG must remain transparent on mint, sky, cream, forest, and purple surfaces.

## Invariants

- Keep `viewBox="0 0 220 220"` and the squared body silhouette.
- Keep the body free of a heavy outer stroke.
- Preserve upper-left satin sheen, lower-right body shadow, soft grounding depth, glossy tall eyes, and a small calm mouth.
- Keep colors mood-driven through the palette: `body`, `highlight`, `shadow`, `stroke`, and `detail`.
- Use `useId()`-scoped gradient and filter IDs. Static IDs collide when several mascots render on one page.
- Keep props integrated into the body. Avoid detached clip-art, realistic limbs, ghost/blob shapes, or complex backgrounds.
- Keep all raster backgrounds, text, logos, and watermarks out of the mascot.

## Existing moods

| Mood | Expression and prop | Intended use |
|---|---|---|
| `mark` | Calm glossy eyes, tiny smile, gold sparkle | Brand chips and compact identity moments |
| `study` | Calm glossy eyes, tiny smile, integrated arms holding a layered cream book | Landing, dashboard, active learning |
| `tutor` | Calm glossy eyes, dimensional pale-blue body, headset and mic | Tutor, voice, hints |
| `celebrate` | Closed happy eyes, tiny smile, lavender body, confetti and sparkles | Completion, streaks, achievements |

## Adding an emotion

1. Add the emotion to `MascotMood`.
2. Add a palette entry. Prefer an existing brand colorway unless the new state has a strong semantic reason.
3. Reuse the base body, sheen, depth filter, and eye treatment.
4. Add one conditional layer for facial changes and one prop/accent group at most.
5. Keep features inside the safe face area: eyes around `y=96–127`, mouth around `y=136–148`, props primarily below `y=150`.
6. Use closed-eye arcs for joy/rest, eye scale or vertical position for focus/surprise, and small mouth changes for tone. Do not add eyebrows by default.
7. Use soft prop strokes (`2–4px`) and colored shadows. Avoid restoring the old thick body contour.
8. Test on both light and dark brand panels at approximately `220px`, `128px`, `44px`, and `32px`.
9. Copy the final live component to `../assets/Mascot.tsx`.

## UI placement

- Use one hero mascot per screen. Tiny chat chips are the only routine exception.
- Use `study` on mint, `tutor` on sky, and `celebrate` on forest or deep purple.
- Keep the mascot away from destructive actions and error messaging.
- Animate a wrapper when positioning depends on transforms; `animate-mascot-bob` owns the mascot transform.
- Respect reduced-motion preferences and preserve accessible titles only when the mascot is meaningful.
