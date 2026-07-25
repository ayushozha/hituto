import { ReactNode } from "react";
import { ACTIVITY_TONES, type ActivityTone } from "./activityWidgetPalette";

/**
 * Activity tones identify the widget family. State colors inside the widget keep
 * their own meaning (green = correct/success, coral = error).
 */
export type WidgetTone = ActivityTone;

export interface WidgetCardProps {
  /** Card title — truncated, font-display. */
  title: string;
  /** Small uppercase eyebrow label under the title (e.g. "Flashcard deck"). */
  eyebrow?: string;
  /** Right-aligned status pill (e.g. "1 of 5", "Interactive visual"). */
  pill?: ReactNode;
  /** Semantic activity identity; correctness and status colors override it locally. */
  tone?: WidgetTone;
  /**
   * Optional footer, rendered inside the shared frame.
   * The card body (`children`) supplies its own trailing gap when needed.
   */
  footer?: ReactNode;
  /** Extra classes on the outer container (e.g. `select-none`, `animate-pop-in`). */
  className?: string;
  children: ReactNode;
}

/**
 * Shared tutor-widget frame for quiz, flashcards, games, and generative UI cards.
 */
export default function WidgetCard({
  title,
  eyebrow,
  pill,
  tone = "neutral",
  footer,
  className = "",
  children,
}: WidgetCardProps) {
  const activityTone = ACTIVITY_TONES[tone];

  return (
    <div
      className={`w-full rounded-2xl border border-ink/10 p-5 shadow-chip ${activityTone.shell} ${className}`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate font-display text-base font-semibold leading-snug text-ink">{title}</h4>
          {eyebrow && (
            <p
              className={`mt-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] ${activityTone.eyebrow}`}
            >
              {eyebrow}
            </p>
          )}
        </div>
        {pill != null && (
          <div className="shrink-0 rounded-full border border-ink/5 bg-surface px-2.5 py-1 text-xs font-semibold text-ink-soft">
            {pill}
          </div>
        )}
      </div>

      {children}

      {footer != null && <div className="mt-4 pt-1">{footer}</div>}
    </div>
  );
}
