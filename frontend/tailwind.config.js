/** @type {import('tailwindcss').Config} */
/*
 * Hi Tuto palette roles (modern minimalist system):
 *   paper/sand/line  — neutral white/zinc ground + hairlines
 *   ink              — zinc-900 text (never pure black)
 *   brand            — amber brand accent: app chrome (landing, dashboard, dialogs,
 *                      insights) emphasis, selection, links, logo
 *   cream            — barely-there warm tint: brand-soft fills, calculator activity cards
 *   lime             — learning green: progress, success, correct states, lesson widgets
 *   mint             — barely-there green tint: success, game and whiteboard activity cues
 *   grass            — accent alias (A2UI success), mirrors lime
 *   lilac/plum/cobalt — legacy names kept for compatibility; now neutral
 *                      zinc fills/inks (active pills, dark panels)
 *   coral/peach      — functional error/danger feedback only
 *   pink             — quiz / voice quiz cards (soft lilac-pink + deep purple ink)
 *   sky              — flashcards, diagrams, generated-info tabs, and tutor/media chrome
 *                      (mic, suggestions); sunshine legacy
 *
 * Landing page clean layer (features/landing/Landing.tsx only):
 *   bone             — warm ivory ground + warm hairline
 *   shadow chip/panel — soft diffuse elevation for floating UI cards
 *   font archivo     — Archivo grotesque for tight-tracked headlines
 *   animate drift    — gentle bob for floating chips (composes with rotate)
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FAFAFA",
        sand: "#F4F4F5",
        surface: "#FFFFFF",
        ink: {
          DEFAULT: "#18181B",
          soft: "#52525B",
          faint: "#A1A1AA",
        },
        line: "#E4E4E7",
        cobalt: {
          DEFAULT: "#27272A",
          dark: "#18181B",
          soft: "#F4F4F5",
        },
        lime: {
          DEFAULT: "#16A34A",
          dark: "#14532D",
          soft: "#EAF7EE",
        },
        brand: {
          DEFAULT: "#D97706",
          dark: "#92400E",
          soft: "#FAF3E3",
        },
        cream: "#FAF3E3",
        coral: {
          DEFAULT: "#EF4444",
          dark: "#991B1B",
          soft: "#FEF2F2",
        },
        grass: {
          DEFAULT: "#16A34A",
          soft: "#EAF7EE",
        },
        mint: "#EAF7EE",
        lilac: "#F4F4F5",
        peach: "#FEF2F2",
        orange: "#FF5A1F",
        // Complementary to brand amber — tutor/media chrome (mic, suggestions, generating)
        sky: {
          DEFAULT: "#2563EB",
          soft: "#E8F0FE",
          dark: "#1E40AF",
        },
        violet: "#9B5CF6",
        // Quiz / voice-widget pink (matches VoiceInstructor create_quiz tab)
        pink: {
          DEFAULT: "#E3C8F5",
          dark: "#3F2447",
          soft: "#F6ECFB",
        },
        sunshine: "#FFD91A",
        plum: "#18181B",
        bone: {
          DEFAULT: "#F7F5F1",
          line: "#EAE6DF",
        },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        logo: ['"Fraunces"', "Georgia", "serif"],
        serif: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        archivo: ['"Archivo"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(0,0,0,0.05)",
        lift: "0 8px 24px rgba(0,0,0,0.08)",
        card: "0 1px 3px rgba(0,0,0,0.06)",
        press: "0 1px 2px rgba(0,0,0,0.08)",
        "press-cobalt": "0 1px 2px rgba(0,0,0,0.08)",
        chip: "0 12px 32px -12px rgba(24, 24, 27, 0.16)",
        panel: "0 32px 90px -32px rgba(24, 24, 27, 0.18)",
      },
      borderRadius: {
        "4xl": "1rem",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.94)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "panel-in": {
          "0%": { opacity: "0", transform: "translateX(18px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        "mascot-bob": {
          "0%,100%": { transform: "translateY(0) rotate(-1deg)" },
          "50%": { transform: "translateY(-7px) rotate(1deg)" },
        },
        "spin-slow": {
          to: { transform: "rotate(360deg)" },
        },
        confetti: {
          "0%": { transform: "translateY(-10%) rotate(0deg)", opacity: "0" },
          "10%": { opacity: "1" },
          "100%": { transform: "translateY(420%) rotate(360deg)", opacity: "0" },
        },
        "sparkle-twinkle": {
          "0%,100%": { transform: "scale(1) rotate(0deg)", opacity: "1" },
          "50%": { transform: "scale(0.72) rotate(12deg)", opacity: "0.75" },
        },
        drift: {
          "0%, 100%": { transform: "translateY(0) rotate(var(--tw-rotate, 0deg))" },
          "50%": { transform: "translateY(-10px) rotate(var(--tw-rotate, 0deg))" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.55s cubic-bezier(0.2,0.7,0.2,1) both",
        "fade-in": "fade-in 0.5s ease both",
        "pop-in": "pop-in 0.35s cubic-bezier(0.2,0.8,0.2,1) both",
        "panel-in": "panel-in 0.4s cubic-bezier(0.2,0.8,0.2,1) both",
        float: "float 6s ease-in-out infinite",
        "mascot-bob": "mascot-bob 4s ease-in-out infinite",
        "spin-slow": "spin-slow 1s linear infinite",
        confetti: "confetti 2.4s ease-in forwards",
        twinkle: "sparkle-twinkle 2.6s ease-in-out infinite",
        drift: "drift 7s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
