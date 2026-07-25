---
name: hituto-generated-lesson-design
description: >-
  Shared Hi Tuto UI/UX contract for LLM-authored HTML lesson capsules. Use whenever the
  capsule-author creates or refines page, slide, or free-form studio HTML so generated learning
  content matches the trusted Hi Tuto app instead of looking like a generic docs site or dashboard.
---

# Hi Tuto Generated Lesson Design

Build a focused learning mini-app that feels native inside Hi Tuto. The shell-specific skill owns
the information architecture; this skill owns the shared brand, spacing, typography, and component
behavior.

## Respect the product boundary

- Let the trusted host own Roadmap, lesson title, version, Edit, Complete, Share, tutor, and progress.
- Start immediately with the first learning section. Never generate a capsule title/intro header,
  module label, section navigation, app chrome, second tutor, account controls, or dashboard.
- Make the capsule teach one mechanism through a dominant **drawn** visual and a small number of
  real controls — SVG/canvas first; photographs only when the concept needs a real-world reference.

## Use the exact brand system (zinc-neutral)

- Canvas: `paper` (`#FAFAFA`); text: zinc ink (`#18181B`).
- Soft fills: `mint` (`#EAF7EE`), `sand` (`#F4F4F5`), white `surface`.
- Action green: `lime` (`#16A34A`); deep text/panels: `lime-dark` / `plum` (`#18181B`).
- Functional only: `coral` (danger), `sky` (info). Legacy names `lilac`/`cobalt` map to neutrals.
- Use Plus Jakarta Sans 800 for headings and 400–700 for body. Use JetBrains Mono only for code.
- Avoid purple gradients, warm-cream nostalgia palettes, glass blur, and black borders.

Configure Tailwind with the same tokens as `frontend/tailwind.config.js`:

```js
tailwind.config = { theme: { extend: {
  colors: {
    paper:'#FAFAFA', sand:'#F4F4F5', surface:'#FFFFFF', line:'#E4E4E7',
    ink:{DEFAULT:'#18181B',soft:'#52525B',faint:'#A1A1AA'},
    cobalt:{DEFAULT:'#27272A',dark:'#18181B',soft:'#F4F4F5'},
    lime:{DEFAULT:'#16A34A',dark:'#14532D',soft:'#EAF7EE'},
    coral:{DEFAULT:'#EF4444',dark:'#991B1B',soft:'#FEF2F2'},
    grass:{DEFAULT:'#16A34A',soft:'#EAF7EE'},
    mint:'#EAF7EE', lilac:'#F4F4F5', peach:'#FEF2F2', sky:'#2563EB', plum:'#18181B'
  },
  fontFamily:{
    display:['"Plus Jakarta Sans"','ui-sans-serif','system-ui','sans-serif'],
    sans:['"Plus Jakarta Sans"','ui-sans-serif','system-ui','sans-serif'],
    mono:['"JetBrains Mono"','ui-monospace','monospace']
  },
  borderRadius:{'4xl':'1.75rem'},
  boxShadow:{card:'0 1px 3px rgba(0,0,0,.06)',press:'0 1px 2px rgba(0,0,0,.08)'}
} } };
```

## Compose, do not decorate

- Start with `mx-auto max-w-7xl px-4 py-5 md:px-6 md:py-7` for the outer shell, then put all
  major regions in one reading column: `mx-auto w-full max-w-3xl` (768px). Do not mix
  `max-w-4xl` / full-bleed / `max-w-3xl` across sections — gutters must stay even while scrolling.
  Prose-only blocks may use `max-w-2xl`. Postprocess coerces wider section columns to `max-w-3xl`.
- Use an 8px spacing rhythm, 24–32px outer gutters, and 20–28px card radii.
- For page lessons, let the transparent iframe canvas reveal the host paper and use one subtle
  `line` border around purposeful interactive regions. Do not tint the entire reading surface.
- Use colored fields only where they communicate a state or define one dominant interaction.
- Avoid nested cards. Use `shadow-card` sparingly.
- Keep prose near 65–72 characters per line and paragraphs to roughly three sentences.
- `img, canvas, svg { max-width: 100% }` — never overflow the capsule horizontally.

## Page-shell alignment

- Never build a fixed full-height documentation sidebar.
- Use one centered reading column with generous negative space and no navigation chrome.
- The first rendered heading must be the first section heading, never the lesson title.
- Keep visualizations full-width inside the content column; do not squeeze them beside a rail.

## Controls and states

- Make controls at least 44px high, rounded-full or rounded-xl, visibly labeled, and keyboard usable.
- Use lime for the primary action, sand/zinc for secondary actions, and coral for warnings.
- Every control must update visible state immediately. Show the current value beside sliders/toggles.
- Give controls `data-lesson-control`; give sections `data-lesson-section` and `data-lesson-title`.
