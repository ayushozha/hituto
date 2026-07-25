---
name: hituto-design
description: Hi-Tuto design system for all frontend/UI work in this repo. Use whenever creating or modifying React components, pages, styles, Tailwind classes, or the dimensional SVG mascot and its emotions in frontend/ — ensures the Thinkby-inspired look stays consistent.
---

# Hi-Tuto Design System Skill

Full source of truth: `../ui-ux-design.md` (read it for anything not covered here).
Live implementations: `../../frontend/tailwind.config.js` (tokens), `../../frontend/src/components/Mascot.tsx` + `BrandMark.tsx` (canonical mascot SVGs), `../../frontend/src/index.css` (`.font-display`, `.font-logo`, `.hard-card`, `.sticker`, `.btn-press`), `../../frontend/src/features/landing/Landing.tsx` (reference-quality composition examples).

Bundled mascot resources:

- `assets/Mascot.tsx` — reusable snapshot of the canonical transparent dimensional SVG component.
- `references/mascot-system.md` — anatomy, emotion-extension workflow, placement rules, and sync requirements. Read it before changing mascot geometry, moods, facial expressions, props, or colorways.

## The look in one paragraph

Warm cream canvas (`bg-paper` #FDF1E7) with **flat, borderless** cards in vivid fills — deep forest `lime-dark` #14380E and deep purples `plum`/`cobalt` alternate with light mint, pink-lavender `lilac`, peach, and one punchy blue `sky` tile. Vivid green `lime`/`grass` #2BC15D is the action color. Depth comes from **one-sided bottom shadows** (`shadow-press` = `0 4px 0 #14380E`) on buttons and sticker pills only. A soft square mascot with tall calm eyes appears at one emotional moment per screen. Four-point sparkles ✦ decorate dark panels.

## Hard rules

1. **Never** put black borders or diagonal offset shadows (`4px 4px 0 #000`) on components — that's the rejected "Gumroad" look. Cards are flat: `hard-card` = `rounded-4xl border-0 shadow-card`.
2. Outlines exist only on sticker chat pills, headline highlight pills, and small mascot details that need separation. Never add a heavy contour around the mascot body; its depth comes from gradients, highlights, and soft colored shadows.
3. Buttons: `rounded-full bg-lime text-lime-dark font-extrabold shadow-press btn-press hover:brightness-105`, no border. On dark panels use `shadow-[0_4px_0_rgba(0,0,0,0.35)]`.
4. Always use Tailwind tokens (`bg-lime`, `text-plum`, `shadow-press`…). Raw hex only inside Mascot/BrandMark SVGs.
5. Headings: `font-display` (Plus Jakarta Sans 800, tracking -0.025em). The Fraunces soft serif (`font-logo`) is ONLY for the "Hi Tuto" wordmark.
6. Mascot: use the existing `<Mascot mood="..."/>` component. Preserve its transparent canvas, squared silhouette, satin body gradient, upper-left sheen, glossy eyes, and soft depth shadow. Never replace it with a white-backed raster or redraw it as a blob. Colorways: `study`/`mark` vivid green, `tutor` pale blue, `celebrate` lavender. Max one hero mascot per screen plus tiny 32px chips in chat pills.
7. Text pairings: `text-lime-dark` on mint, `text-plum` on lilac, `text-paper`/`text-mint` on deep panels, `ink` on cream/peach/sky. Never white text on vivid `lime`.

## Chat/sticker pills (tutor UI)

- Student/green: `rounded-xl border-2 border-lime-dark bg-lime text-lime-dark font-extrabold shadow-[0_4px_0_#14380E] rotate-[-1.5deg]`
- Tutor/lavender: `rounded-xl border-2 border-cobalt bg-lilac text-plum shadow-[0_4px_0_#35193B] rotate-[1.5deg]`
- Width content-driven (`w-max max-w-full`), tiny `<Mascot mood="mark" className="h-8 w-8"/>` chip inside.

## Mascot workflow

Before adding or changing an emotion, read `references/mascot-system.md` and inspect `../../frontend/src/components/Mascot.tsx`.

1. Keep the base body, lighting definitions, viewBox, and `useId()`-scoped SVG IDs unchanged unless redesigning the whole mascot system.
2. Express emotion through eyes, mouth, pose, prop, sparkle/confetti accents, and palette—not through a new silhouette.
3. Add a typed `MascotMood`, its palette entry, and one conditional SVG layer. Reuse the existing gradients and filters.
4. Verify the mood at hero size and at 32–44px. Preserve `title`, `aria-label`, and decorative `aria-hidden` behavior.
5. After updating the live component, synchronize it to `assets/Mascot.tsx` so the bundled skill asset never drifts.

## Gotchas (will bite you)

- **Restart the Vite dev server after editing `tailwind.config.js`** — the config watcher is broken on this machine; stale classes keep serving and changes silently don't render. `lsof -ti :5173 | xargs kill` then `cd frontend && npm run dev`.
- Keyframes that set `transform` (`animate-mascot-bob`) override Tailwind translate utilities — wrap the mascot in a positioned div and animate the inner SVG.
- `font-display` is both a CSS component class and a Tailwind utility; both must stay mapped to Plus Jakarta Sans.

## Composition recipe per screen

One bold statement · one mascot moment · one dominant flat color field (make some of them DEEP forest/purple, not all light) · one sticker/achievement element · generous cream negative space. Verify against the checklist in `../ui-ux-design.md` §13.
