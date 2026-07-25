# Hi-Tuto UI/UX Design System

> Visual source of truth: [Thinkby — AI Study Companion by Musemind](https://dribbble.com/shots/27511034-AI-Study-Companion-Edtech-Brand-Design-Mascot-Design-Thinkby).
> This document describes the system **as implemented** in `frontend/` (Tailwind tokens in `frontend/tailwind.config.js`, mascot in `frontend/src/components/Mascot.tsx`). When code and this doc disagree, fix the code.

## 1. Creative direction

Hi-Tuto feels like a **warm study friend**, not a productivity dashboard or a futuristic AI tool: flat saturated color fields on warm cream, a soft square mascot, sticker pills, tiny four-point sparkles ✦, and playful editorial compositions.

**Brand promise:** a friend who studies with you and celebrates every win.

**Design keywords:** warm, youthful, cheeky, optimistic, flat, editorial, companion-led.

### Non-negotiable visual rules

1. Warm cream canvas (`#FDF1E7`), never pure white or cool gray page backgrounds.
2. **Cards and panels are flat and borderless.** Color does the separation work — no black outlines around cards, no diagonal offset shadows. (This is what distinguishes us from the "Gumroad" neobrutalist look. We tried it; it was wrong.)
3. Play with **deep** colors: deep forest green (`#14380E`) and deep purple (`#3F2447` / `#4B2450`) as full section/panel fills, alternating with cream and the light tints (mint `#D9F2DC`, pink-lavender `#E3C8F5`, peach `#F8C5A8`).
4. Vivid green (`#2BC15D`) is the dominant action/brand color; purple is the tutor/focus color.
5. Outlines belong to sticker pills and small mascot details that need separation. The mascot body has no heavy contour; satin gradients, highlights, and soft colored shadows create its depth.
6. Depth = **one-sided bottom shadow** (`0 4px 0 <deep tone>`) on buttons and sticker pills only. Cards get either nothing or a barely-there ambient (`shadow-card`).
7. Headings are a chunky rounded sans; the soft serif (Fraunces) is reserved for the "Hi Tuto" wordmark only.
8. Keep the square mascot visible at key emotional moments — and *only* there. One or two per screen, never one per card.
9. Copy is friendly and direct. No technical AI language in student-facing UI.

### Avoid

- Black borders + diagonal hard shadows on every component (Gumroad/neobrutalism)
- Generic white SaaS dashboards
- Purple-on-white AI gradients, glassmorphism, neon glows
- Thin gray borders and diffused corporate shadows
- Muted/sage desaturated tints where the reference uses vivid color
- Stock robot, brain, circuit, or chatbot imagery
- Mascot overuse or fat/blobby mascot redraws

---

## 2. Color system

Tokens live in `frontend/tailwind.config.js`. **The Tailwind class names are the API** — always use tokens, never raw hex in components (the mascot SVG is the one exception).

### Core brand colors

| Tailwind token | Hex | Role |
|---|---:|---|
| `ink` | `#0B1F10` | Primary text and icon color (dark forest-black) |
| `ink-soft` | `#3E5244` | Secondary text on light surfaces |
| `ink-faint` | `#7C8B84` | Tertiary/muted text |
| `paper` | `#FDF1E7` | App canvas, warm cream |
| `surface` | `#FFFFFF` | Cards that must lift from cream (e.g., app-card on purple panel) |
| `lime` / `grass` | `#2BC15D` | Vivid brand green: buttons, mascot, active states, green pills |
| `lime-dark` | `#14380E` | Deep forest: dark panels, green outlines, one-sided button shadows, text on mint |
| `lime-soft` / `mint` | `#D9F2DC` | Pale mint: light canvases, onboarding, gentle cards |
| `cobalt` | `#4B2450` | Deep purple panel (streaks, photo frames) |
| `cobalt-dark` | `#35193B` | One-sided shadow under lavender pills |
| `cobalt-soft` / `lilac` | `#E3C8F5` | Pink-lavender: tutor pills, highlights, celebrate mascot body |
| `plum` | `#3F2447` | Deepest purple: celebration canvas, tutor panels, text on lilac |
| `sky` | `#41A0FB` | Vivid blue tile for the headphone mascot; info accents |
| `peach` | `#F8C5A8` | Friendly announcement panels |
| `coral` | `#FE936D` | Energy accent, confetti ticks |
| `sunshine` | `#FFCF3F` | Stars, trophies, sparkle fills |
| `sand` / `line` | `#F2E0CE` / `#EBDACA` | Rails, hairline dividers (header/footer only) |

Special: the celebrate mascot's facial details and accessory accents use vivid purple `#7C2FA8` (hardcoded in the mascot SVG only).

### Usage ratio

- ~45% cream/white
- ~25% vivid green + mint
- ~20% deep purple + lavender + deep forest
- ~10% peach, sky, sunshine, coral accents

One dominant color field per section. Text: `ink` on cream/mint/lilac/peach/sky; `paper`/`mint` on deep forest and deep purple; `lime-dark` for headings on mint; `plum` for headings on lilac.

---

## 3. Typography

- **Headings/display:** Plus Jakarta Sans, weight 800, tracking `-0.025em` — exposed as the `.font-display` class *and* the `font-display` Tailwind utility (both map to PJS).
- **Wordmark only ("Hi Tuto"):** Fraunces variable, `SOFT 100, WONK 0` — the `.font-logo` class / `font-logo` utility. Never use Fraunces for general headings.
- **Body/UI:** Plus Jakarta Sans 400–700. **Mono:** JetBrains Mono.
- Fonts load in `frontend/index.html` via Google Fonts (`Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,300..900,100,0` + Plus Jakarta Sans + JetBrains Mono + Material Symbols Rounded).

| Style | Desktop | Line height | Weight |
|---|---:|---:|---:|
| Display hero | clamp 3.2–6.1rem | 0.99 | 800 |
| Section title | clamp 2.5–4.4rem | 1.02 | 800 |
| Card title | 1.875–2.25rem | 1.02–1.05 | 800 |
| Body large | 18–20px | 1.6 | 500 |
| Label/eyebrow | 12px caps | 1.2 | 800, tracking 0.17em |

Emphasize one or two headline words with a **highlight pill**: lavender fill, `border-[3px] border-ink`, slight rotation (`rotate-[-1.5deg]`), radius `0.3em` — like the reference's "Online" pill. This is the *only* place a near-black outline is allowed outside the sticker/mascot system.

---

## 4. Shape, border, and depth

### Radius scale

- `rounded-xl` (12px): sticker chat pills, compact controls
- `rounded-2xl` (16px): inputs
- `rounded-4xl` (28px, custom): standard cards (`hard-card` class)
- `30–34px`: hero collage tiles
- `rounded-full`: buttons, "Swipe up" pills, avatars

### Borders

- **Containers/cards/inputs: no border.** Flat fill only.
- Sticker pills: `border-2` in a deep *colored* tone — `border-lime-dark` on green pills, `border-cobalt` on lavender pills.
- Highlight pills in headlines: `border-[3px] border-ink`.
- Hairline `border-line` only for header/footer dividers.

### Shadows (Tailwind tokens)

```
soft         0 3px 0 rgba(11,31,16,0.14)      subtle one-sided (small pills, swipe chip)
press        0 4px 0 0 #14380E                green buttons (pressable-key look)
press-cobalt 0 4px 0 0 #35193B                lavender elements
card         0 8px 20px rgba(11,31,16,0.06)   barely-there ambient for white cards on cream
lift         0 12px 28px rgba(11,31,16,0.12)  hover lift only
```

Never diagonal offsets (`4px 4px 0 #000`-style), never blurred gray drops as default. On dark panels use `shadow-[0_4px_0_rgba(0,0,0,0.35)]` so the one-sided shadow stays visible.

### Buttons

**Primary:** `rounded-full bg-lime text-lime-dark font-extrabold shadow-press hover:brightness-105 btn-press` (no border). On dark panels swap shadow to the rgba variant above.
**Secondary:** white/`surface` pill, `shadow-card`.
**Tertiary:** underlined text link with icon.

---

## 5. Mascot system

A dimensional, transparent **square** character with tall glossy eyes, a calm mouth, satin lighting, and a soft colored depth shadow. Its silhouette is intentionally squarer than a blob and has no heavy body outline. Never use a white-backed raster or per-card mascot decoration.

Live source: `frontend/src/components/Mascot.tsx`. Skill snapshot: `.agents/skills/hituto-design/assets/Mascot.tsx`. Emotion anatomy and extension rules: `.agents/skills/hituto-design/references/mascot-system.md`.

### Colorways

| Mood | Body gradient | Detail tone | Use |
|---|---|---|---|
| `mark` / `study` | vivid green `#71E891 → #2BC15D → #159744` | forest `#14380E` | brand chips, reading/active study |
| `tutor` (headphones + mic) | pale blue `#F3F9FF → #CFE6FC → #93BFE9` | forest `#14380E` | chat, voice tutoring, hints — sits on the `sky` blue tile |
| `celebrate` | lavender `#F4E8FC → #E3C8F5 → #BD91DB` | vivid purple `#7C2FA8` | completion, streaks, achievements — sits on deep purple/forest |

### Canonical SVG component

Do not duplicate the component in this document. Read the live implementation or the synchronized skill asset above. The component uses instance-scoped gradients and filters, so copying only the visible paths will break multi-mascot pages and flatten the intended rendering.

### BrandMark (app icon)

Vivid green rounded tile with a cream outlined face — `frontend/src/components/BrandMark.tsx`:

```tsx
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <div className={`relative grid h-12 w-12 shrink-0 place-items-center rounded-[15px] bg-grass ${className}`}
      aria-label="Hi Tuto mascot logo">
      <svg viewBox="0 0 48 48" className="h-9 w-9" fill="none" aria-hidden="true">
        <rect x="8" y="9" width="32" height="30" rx="10" stroke="#FDF1E7" strokeWidth="4" />
        <rect x="19" y="19" width="3.6" height="10" rx="1.8" fill="#FDF1E7" />
        <rect x="26" y="19" width="3.6" height="10" rx="1.8" fill="#FDF1E7" />
      </svg>
    </div>
  );
}
```

### Placement and motion

- One hero-moment mascot per screen (e.g., mint onboarding card), plus at most tiny 32px chips inside sticker pills.
- Gotcha: `animate-mascot-bob` sets `transform`, which **overrides** Tailwind translate utilities (`-translate-x-1/2`). Wrap the mascot in a positioned container div and animate the inner SVG.
- Respect `prefers-reduced-motion`. Never place the mascot beside destructive actions or errors.

---

## 6. Layout and composition

- Max content width `1280px` (`max-w-7xl`), 12-col grid, `24px` gutters.
- **Bento/collage hero**: pale-mint phone card (mascot + "Swipe up"), vivid blue tile (headphone mascot), peach tile with highlight-pill word, deep-forest wordmark panel with twinkling sparkles, deep-purple streak tile.
- Alternate section canvases: cream → deep forest band → cream → white → deep forest CTA. Deep panels are what make the page feel like the reference — don't stay light everywhere.
- Sticker chat pills (on deep panels): green pill + lavender pill + cream pill, rotated ±1.5°, tiny mascot chips, one-sided shadows.
- Spacing scale `4, 8, 12, 16, 24, 32, 48, 64, 96`; card padding 20–28px; section gaps 48–96px.

Each major screen: one bold statement, one mascot moment, one dominant flat color field, one sticker/achievement element, generous cream negative space.

---

## 7. Core components (as implemented)

- **`hard-card`** (index.css): `rounded-4xl border-0 shadow-card` — the standard flat card. Give it a `bg-*` fill and matching text color (`bg-mint text-lime-dark`, `bg-lilac text-plum`, `bg-plum text-paper`, `bg-cobalt text-paper`, `bg-peach`, `bg-surface`).
- **`sticker`** (index.css): outlined white pill with one-sided shadow — hero badges only.
- **`btn-press`**: 2px translate on `:active`.
- **Inputs:** `bg-surface` (or `bg-paper` on dark), `rounded-full`/`rounded-2xl`, no border, `shadow-card`; focus ring 3px `sky` (global `:focus-visible`).
- **Chat bubbles:** student = `bg-lime border-2 border-lime-dark text-lime-dark shadow-[0_4px_0_#14380E]`; tutor = `bg-lilac border-2 border-cobalt text-plum shadow-[0_4px_0_#35193B]`; width content-driven, ≤80% of column, rotation ±2°.
- **Progress/achievements:** deep purple cards, `sunshine` trophies/stars used sparingly; completion triggers the celebrate mascot once.
- **Sparkle ✦:** the four-point star (see `Star`/`Sparkle` components) in `lime`, `lilac`, `sunshine`, `coral`, or `paper`; `animate-twinkle` for gentle pulsing on dark panels. Max ~3 per card, ~6 per hero.

---

## 8. Screen direction

- **Onboarding rhythm (from reference):** 1) mint canvas + green study mascot "Unlock your potential" → 2) lavender canvas + headphone mascot → 3) deep purple canvas + celebrate mascot.
- **Dashboard:** mint welcome panel + study mascot, lavender readout panel, flat course cards, purple streak card.
- **Roadmap:** vertical journey; active = vivid green, complete = deep forest + check, locked = cream at reduced opacity.
- **Lesson viewer:** cream reading canvas (680–760px measure); tutor panel lilac/purple with headphone mascot; widgets are bold flat-color cards.
- **Voice tutor:** deep purple focus canvas, plain-language status ("Listening…"), outlined organic waveform.
- **Completion:** celebrate mascot on deep purple, one big line, "Next lesson" primary.

---

## 9. Motion

- Page entrance 180–260ms, staggered 40–60ms (`animate-fade-up` with `animationDelay`).
- Button press: `btn-press` translate, 100–140ms.
- Mascot idle: `animate-mascot-bob` (4s), sparkles `animate-twinkle` (2.6s).
- Celebration: single 500–700ms bounce + 3–5 sparkles; never looping confetti.
- Ease: `cubic-bezier(.2,.8,.2,1)`. Honor `prefers-reduced-motion`.

---

## 10. Content voice

Encouraging peer: "Ready for a quick win?" / "Let's pick up where you left off." / "Want me to explain it another way?"
Never: "The AI has generated a response." / "Processing request…" / robotic or babyish copy.

---

## 11. Accessibility

- WCAG 2.2 AA contrast (note: `text-lime-dark` on `mint`, `paper` on `lime-dark`/`plum`/`cobalt` all pass; vivid `lime` is a fill color — pair it with `lime-dark` text, not white).
- 3px visible focus ring (`sky`) on all keyboard-operable controls; 48px touch targets.
- Mascot gets `title` (alt) only when meaningful; decorative sparkles are `aria-hidden`.
- Reduced-motion fallbacks; 200% zoom without horizontal scroll; test at 360–1440px.

---

## 12. Engineering notes (read before styling)

1. **Always use Tailwind tokens** (`bg-lime`, `text-plum`, `shadow-press`…). Raw hex belongs only in `Mascot.tsx`/`BrandMark.tsx`.
2. **Restart the Vite dev server after editing `tailwind.config.js`.** On this machine the Tailwind config watcher is broken; the server keeps serving classes generated from a stale config and changes silently don't appear. (`kill` port 5173, then `cd frontend && npm run dev`.)
3. `font-display` is both a component class and the Tailwind `fontFamily.display` utility — keep both mapped to Plus Jakarta Sans so they can't fight.
4. Keyframe animations that set `transform` (e.g., `mascot-bob`) override Tailwind translate/rotate utilities — wrap and animate the inner element.

---

## 13. Acceptance checklist

A screen matches this system only when:

- [ ] Canvas is warm cream; at least one deep forest or deep purple flat panel anchors the page.
- [ ] Cards are flat and borderless; **no black outlines, no diagonal offset shadows anywhere**.
- [ ] Buttons are vivid-green pills with a one-sided `0 4px 0` deep-forest shadow.
- [ ] Sticker pills use deep *colored* outlines + one-sided shadows and slight rotation.
- [ ] Headings are Plus Jakarta Sans 800; Fraunces appears only in the "Hi Tuto" wordmark.
- [ ] The correct mascot colorway appears at one emotional moment (green study / pale-blue tutor / lavender celebrate) — and mascots are not sprinkled on every card.
- [ ] Sparkles ✦ are sparse and on-palette.
- [ ] Keyboard, contrast, touch, and reduced-motion requirements are met.
- [ ] No Gumroad-style neobrutalism, AI gradients, glass, or gray SaaS patterns.

This document is the visual and interaction source of truth for Hi-Tuto. When an existing component conflicts with it, preserve behavior and accessibility while updating presentation to this system.
