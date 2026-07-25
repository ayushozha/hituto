export type ActivityTone =
  | "neutral"
  | "quiz"
  | "flashcards"
  | "game"
  | "code"
  | "diagram"
  | "calculator"
  | "whiteboard"
  | "interactive";

type ActivityToneClasses = {
  /** Opaque outer card surface and its essential foreground. */
  shell: string;
  /** Small identity label inside the card header. */
  eyebrow: string;
  /** Exposed tab on a floating/dealt card. */
  tab: string;
};

/**
 * One semantic activity palette shared by tutor and voice widgets.
 *
 * These tones identify the kind of learning activity; they never communicate
 * correctness or status. Components keep success, error, and pending feedback
 * on the existing green, coral, and labeled system-state colors.
 */
export const ACTIVITY_TONES: Record<ActivityTone, ActivityToneClasses> = {
  neutral: {
    shell: "bg-surface text-ink",
    eyebrow: "text-ink-soft",
    tab: "bg-surface text-ink",
  },
  quiz: {
    shell: "bg-pink-soft text-ink",
    eyebrow: "text-pink-dark",
    tab: "bg-pink-soft text-pink-dark",
  },
  flashcards: {
    shell: "bg-sky-soft text-ink",
    eyebrow: "text-sky-dark",
    tab: "bg-sky-soft text-sky-dark",
  },
  game: {
    shell: "bg-mint text-ink",
    eyebrow: "text-lime-dark",
    tab: "bg-mint text-lime-dark",
  },
  code: {
    shell: "bg-sand text-ink",
    eyebrow: "text-ink-soft",
    tab: "bg-sand text-ink",
  },
  diagram: {
    shell: "bg-sky-soft text-ink",
    eyebrow: "text-sky-dark",
    tab: "bg-sky-soft text-sky-dark",
  },
  calculator: {
    shell: "bg-cream text-ink",
    eyebrow: "text-brand-dark",
    tab: "bg-cream text-brand-dark",
  },
  whiteboard: {
    shell: "bg-surface text-ink",
    eyebrow: "text-lime-dark",
    tab: "bg-mint text-lime-dark",
  },
  interactive: {
    shell: "bg-surface text-ink",
    eyebrow: "text-sky-dark",
    tab: "bg-sky-soft text-sky-dark",
  },
};

export type ActivityWidgetMeta = {
  label: string;
  icon: string;
  tone: ActivityTone;
};

const DEFAULT_WIDGET_META: ActivityWidgetMeta = {
  label: "Card",
  icon: "widgets",
  tone: "neutral",
};

const TOOL_WIDGET_META: Record<string, ActivityWidgetMeta> = {
  create_quiz: { label: "Quiz", icon: "quiz", tone: "quiz" },
  show_flashcards: { label: "Flashcards", icon: "style", tone: "flashcards" },
  create_game: { label: "Game", icon: "joystick", tone: "game" },
  show_code_exercise: { label: "Code", icon: "code", tone: "code" },
  show_coding_lab: { label: "Coding lab", icon: "code_blocks", tone: "code" },
  update_coding_lab: { label: "Coding lab", icon: "code_blocks", tone: "code" },
  show_diagram: { label: "Diagram", icon: "account_tree", tone: "diagram" },
  show_formula_calculator: { label: "Calculator", icon: "calculate", tone: "calculator" },
  show_whiteboard: { label: "Whiteboard", icon: "draw", tone: "whiteboard" },
  update_whiteboard: { label: "Whiteboard", icon: "draw", tone: "whiteboard" },
  render_ui: { label: "Surface", icon: "dashboard_customize", tone: "interactive" },
  generate_ui: { label: "Visual", icon: "view_in_ar", tone: "interactive" },
};

export function getActivityWidgetMeta(toolName: string): ActivityWidgetMeta {
  return TOOL_WIDGET_META[toolName] ?? DEFAULT_WIDGET_META;
}
