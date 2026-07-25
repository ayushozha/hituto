import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { InsightSummary, InsightWindow } from "../../api";

export type InsightDetailTab = "overview" | "patterns" | "activity";

type LearningInsightsDetailsProps = {
  open: boolean;
  summary: InsightSummary;
  insightWindow: InsightWindow;
  agentRefreshPending: boolean;
  initialTab: InsightDetailTab;
  returnFocus: HTMLElement | null;
  onClose: () => void;
};

const tabs: Array<{ value: InsightDetailTab; label: string; icon: string }> = [
  { value: "overview", label: "Overview", icon: "space_dashboard" },
  { value: "patterns", label: "Patterns", icon: "auto_awesome" },
  { value: "activity", label: "Activity", icon: "history" },
];

export function LearningInsightsDetails({
  open,
  summary,
  insightWindow,
  agentRefreshPending,
  initialTab,
  returnFocus,
  onClose,
}: LearningInsightsDetailsProps) {
  const [activeTab, setActiveTab] = useState<InsightDetailTab>(initialTab);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) setActiveTab(initialTab);
  }, [initialTab, open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = dialogRef.current;
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
    focusable()[0]?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      if (!elements.length) return;
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocus?.focus();
    };
  }, [onClose, open, returnFocus]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[90] flex justify-end bg-ink/70"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="learning-details-title"
        className="flex h-full w-full animate-panel-in flex-col overflow-hidden bg-bone text-ink shadow-panel sm:max-w-[30rem] sm:rounded-l-3xl sm:border-l sm:border-ink/10"
      >
        <header className="shrink-0 border-b border-ink/5 px-5 pb-4 pt-5 sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
                  Your private report
                </span>
                <span className="rounded-full border border-ink/5 bg-white px-2 py-1 text-[9px] font-semibold uppercase text-ink-soft shadow-chip">
                  {insightWindow === "7d" ? "7 days" : "30 days"}
                </span>
              </div>
              <h2 id="learning-details-title" className="mt-2 font-archivo text-2xl font-semibold tracking-[-0.03em]">
                Learning insights
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-ink/5 text-ink-soft transition hover:bg-ink/10 hover:text-ink"
              aria-label="Close learning insights"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-1 rounded-full border border-ink/5 bg-white p-1 shadow-chip" role="tablist" aria-label="Insight details">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.value}
                onClick={() => setActiveTab(tab.value)}
                className={`inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full px-2 text-[11px] font-semibold transition ${
                  activeTab === tab.value
                    ? "bg-ink text-white"
                    : "text-ink-soft hover:text-ink"
                }`}
              >
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
                  {tab.icon}
                </span>
                {tab.label}
              </button>
            ))}
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
          {activeTab === "overview" ? (
            <OverviewPanel summary={summary} />
          ) : activeTab === "patterns" ? (
            <PatternsPanel
              summary={summary}
              agentRefreshPending={agentRefreshPending}
              onNavigate={(href) => {
                onClose();
                navigateTo(href);
              }}
            />
          ) : (
            <ActivityPanel
              summary={summary}
              onNavigate={(href) => {
                onClose();
                navigateTo(href);
              }}
            />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function OverviewPanel({ summary }: { summary: InsightSummary }) {
  const metrics = summary.metrics;
  const accuracy =
    metrics.quiz_accuracy === null ? "—" : `${Math.round(metrics.quiz_accuracy * 100)}%`;
  const metricItems = [
    {
      label: "Active time",
      value: formatMinutes(metrics.active_minutes),
      detail: `${metrics.active_days} active ${metrics.active_days === 1 ? "day" : "days"}`,
      icon: "timer",
    },
    {
      label: "Answer quality",
      value: accuracy,
      detail:
        metrics.answers_total > 0
          ? `${metrics.answers_correct}/${metrics.answers_total} quiz answers correct`
          : "No graded answers yet",
      icon: "task_alt",
    },
    {
      label: "Answer time",
      value: formatSeconds(metrics.average_answer_seconds),
      detail: `${metrics.quiz_attempts} quiz ${metrics.quiz_attempts === 1 ? "attempt" : "attempts"}`,
      icon: "speed",
    },
    {
      label: "Tutor use",
      value: String(metrics.tutor_questions),
      detail: `${metrics.tutor_responses} ${metrics.tutor_responses === 1 ? "reply" : "replies"} finished`,
      icon: "forum",
    },
    {
      label: "Tutor reply time",
      value: formatSeconds(metrics.average_tutor_response_seconds),
      detail: "Question to finished reply",
      icon: "acute",
    },
    {
      label: "Lessons",
      value: `${metrics.lessons_completed}/${metrics.lessons_viewed}`,
      detail: "Completed / viewed",
      icon: "menu_book",
    },
  ];

  return (
    <div id="insight-panel-overview" role="tabpanel" aria-label="Overview">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
          Measured activity
        </p>
        <h3 className="mt-1 font-archivo text-xl font-semibold tracking-[-0.01em]">
          The full ledger for this window
        </h3>
      </div>

      <div className="mt-4 overflow-hidden rounded-3xl border border-ink/5 bg-white shadow-chip">
        <dl className="divide-y divide-ink/5">
          {metricItems.map((item) => (
            <div key={item.label} className="flex items-center gap-3.5 px-4 py-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sand text-ink-soft">
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                  {item.icon}
                </span>
              </span>
              <div className="min-w-0 flex-1">
                <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-soft">
                  {item.label}
                </dt>
                <dd className="mt-0.5 text-xs font-medium leading-snug text-ink-faint">
                  {item.detail}
                </dd>
              </div>
              <span className="shrink-0 font-archivo text-xl font-semibold tracking-[-0.01em]">
                {item.value}
              </span>
            </div>
          ))}
        </dl>
      </div>

      <section
        className="mt-3 rounded-3xl border border-ink/5 bg-white p-4 shadow-chip"
        aria-labelledby="support-signal-title"
      >
        <div className="flex items-center justify-between gap-3">
          <h3
            id="support-signal-title"
            className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft"
          >
            Support signals
          </h3>
          <span className="text-[9px] font-medium text-ink-faint">Context, never a score</span>
        </div>
        <dl className="mt-3 grid grid-cols-3 divide-x divide-ink/10 text-center">
          <SupportSignal label="Hints" value={metrics.hints_requested} />
          <SupportSignal label="Explanations" value={metrics.explanations_requested} />
          <SupportSignal label="Retries" value={metrics.practice_retries} />
        </dl>
      </section>

      <p className="mt-4 rounded-2xl bg-sand px-4 py-3 text-[11px] font-medium leading-relaxed text-ink-soft">
        Answer quality means quiz correctness. Answer time is pacing, and tutor reply time is service latency—not a judgment of ability or response quality.
      </p>
    </div>
  );
}

function PatternsPanel({
  summary,
  agentRefreshPending,
  onNavigate,
}: {
  summary: InsightSummary;
  agentRefreshPending: boolean;
  onNavigate: (href: string) => void;
}) {
  return (
    <div id="insight-panel-patterns" role="tabpanel" aria-label="Patterns" className="space-y-3">
      <section className="rounded-3xl bg-ink p-5 text-white shadow-panel" aria-labelledby="full-agent-feedback-title">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="full-agent-feedback-title" className="text-xs font-semibold uppercase tracking-[0.14em] text-white/50">
            Tuto’s evidence note
          </h3>
          <span className="rounded-full bg-white/10 px-2.5 py-1 text-[9px] font-semibold text-white/70">
            {agentRefreshPending
              ? "Checking patterns…"
              : summary.generated_by === "agent"
                ? "Agent reviewed"
                : "Evidence summary"}
          </span>
        </div>
        <p className="mt-3 font-archivo text-xl font-semibold leading-snug tracking-[-0.01em]">
          {summary.report?.headline ?? "Your patterns will become clearer as you learn"}
        </p>
        <p className="mt-2 text-sm font-medium leading-relaxed text-white/65">
          {summary.report?.summary ??
            "Open a lesson, answer a quiz, or ask the tutor. This view only makes claims supported by that activity."}
        </p>
        {summary.report?.insights.map((insight, index) => (
          <div key={`${insight.kind}-${index}`} className="mt-3 rounded-2xl border border-white/10 bg-white/5 p-3.5">
            <p className="text-sm font-semibold">{insight.title}</p>
            <p className="mt-1 text-xs font-medium leading-relaxed text-white/65">{insight.body}</p>
          </div>
        ))}
        <p className="mt-3 text-[10px] font-semibold text-white/45">
          Updated {formatUpdatedAt(summary.updated_at)} · never compared with other learners
        </p>
      </section>

      <section className="rounded-3xl border border-ink/5 bg-white p-5 shadow-chip" aria-labelledby="detail-struggle-title">
        <SectionHeading id="detail-struggle-title" icon="troubleshoot" title="Where you may be stuck" />
        {summary.struggles.length > 0 ? (
          <div className="mt-3 space-y-2.5">
            {summary.struggles.map((struggle) => (
              <button
                key={`${struggle.course_id}-${struggle.lesson_id}`}
                type="button"
                onClick={() => onNavigate(struggle.href)}
                className="block min-h-12 w-full rounded-2xl border border-ink/5 bg-sand p-3.5 text-left transition hover:border-ink/15 hover:bg-white"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="font-archivo text-sm font-semibold leading-snug tracking-[-0.01em]">{struggle.title}</span>
                  <span className="shrink-0 rounded-full bg-coral-soft px-2 py-1 text-[9px] font-semibold uppercase text-coral-dark">
                    {struggle.confidence}
                  </span>
                </span>
                <span className="mt-1.5 block text-xs font-medium leading-relaxed text-ink-soft">
                  {struggle.evidence}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs font-medium leading-relaxed text-ink-soft">
            No supported struggle pattern yet. A low score alone isn’t enough—we wait for repeated answers plus a help or retry signal.
          </p>
        )}
      </section>

      <section className="rounded-3xl border border-ink/5 bg-white p-5 text-ink shadow-chip" aria-labelledby="detail-interest-title">
        <SectionHeading id="detail-interest-title" icon="interests" title="Topics you’re exploring" />
        {summary.interests.length > 0 ? (
          <div className="mt-3 space-y-2.5">
            {summary.interests.map((interest) => (
              <div key={interest.course_id} className="rounded-2xl bg-sand p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-archivo text-sm font-semibold leading-snug tracking-[-0.01em]">{interest.title}</p>
                  <span className="shrink-0 rounded-full bg-ink px-2 py-1 text-[9px] font-semibold uppercase text-white">
                    {interest.basis === "activity" ? "Active" : "On shelf"}
                  </span>
                </div>
                <p className="mt-1.5 text-xs font-medium leading-relaxed text-ink-soft">
                  {interest.evidence}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs font-medium leading-relaxed text-ink-soft">
            Add a course or spend time in a lesson to see your recent focus here.
          </p>
        )}
      </section>

      {summary.recommended_action ? (
        <button
          type="button"
          onClick={() => onNavigate(summary.recommended_action?.href ?? "#dashboard")}
          className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">play_arrow</span>
          {summary.recommended_action.label}
        </button>
      ) : null}
    </div>
  );
}

function ActivityPanel({
  summary,
  onNavigate,
}: {
  summary: InsightSummary;
  onNavigate: (href: string) => void;
}) {
  return (
    <div id="insight-panel-activity" role="tabpanel" aria-label="Activity">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">Recent signals</p>
        <h3 className="mt-1 font-archivo text-xl font-semibold tracking-[-0.01em]">Your latest learning moments</h3>
      </div>
      {summary.recent_activity.length > 0 ? (
        <ol className="mt-5 space-y-3">
          {summary.recent_activity.map((activity, index) => (
            <li
              key={`${activity.occurred_at}-${activity.kind}-${activity.lesson_id ?? activity.course_id ?? index}`}
              className={`flex gap-3 rounded-2xl border border-ink/5 p-4 ${index % 2 === 0 ? "bg-white" : "bg-sand"}`}
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cream text-brand">
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                  {activityIcon(activity.kind)}
                </span>
              </span>
              <div className="min-w-0 flex-1">
                {activity.href ? (
                  <button
                    type="button"
                    onClick={() => onNavigate(activity.href ?? "#dashboard")}
                    className="min-h-11 text-left font-archivo text-sm font-semibold leading-snug tracking-[-0.01em] hover:underline"
                  >
                    {activity.title}
                  </button>
                ) : (
                  <p className="font-archivo text-sm font-semibold leading-snug tracking-[-0.01em]">{activity.title}</p>
                )}
                <p className="mt-1 text-xs font-medium leading-relaxed text-ink-soft">{activity.detail}</p>
                <p className="mt-1 text-[10px] font-medium text-ink-faint">
                  {formatRelativeTime(activity.occurred_at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="mt-5 rounded-2xl bg-cream p-5 text-brand-dark">
          <span className="material-symbols-outlined text-[28px]" aria-hidden="true">auto_stories</span>
          <p className="mt-2 font-archivo text-lg font-semibold tracking-[-0.01em]">Your timeline starts here</p>
          <p className="mt-1 text-xs font-medium leading-relaxed text-ink-soft">
            Significant lesson, practice, and tutor activity will appear after you learn.
          </p>
        </div>
      )}
    </div>
  );
}

function SupportSignal({ label, value }: { label: string; value: number }) {
  return (
    <div className="px-1.5">
      <dt className="text-[10px] font-medium text-ink-faint">{label}</dt>
      <dd className="mt-0.5 font-archivo text-lg font-semibold text-ink">{value}</dd>
    </div>
  );
}

function SectionHeading({ id, icon, title }: { id: string; icon: string; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="material-symbols-outlined text-[20px]" aria-hidden="true">{icon}</span>
      <h3 id={id} className="font-archivo text-base font-semibold tracking-[-0.01em]">{title}</h3>
    </div>
  );
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  const elapsedMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60_000));
  if (elapsedMinutes < 1) return "just now";
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`;
  const elapsedHours = Math.round(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours}h ago`;
  return `${Math.round(elapsedHours / 24)}d ago`;
}

function activityIcon(kind: "lesson" | "completion" | "practice" | "tutor"): string {
  if (kind === "completion") return "task_alt";
  if (kind === "practice") return "quiz";
  if (kind === "tutor") return "forum";
  return "menu_book";
}

function navigateTo(href: string): void {
  window.location.hash = href.startsWith("#") ? href : "#dashboard";
}
