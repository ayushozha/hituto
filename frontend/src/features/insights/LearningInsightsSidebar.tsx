import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";

import {
  deleteInsights,
  getInsightPreferences,
  getInsightSummary,
  refreshInsights,
  type InsightPreferences,
  type InsightSummary,
  type InsightWindow,
  updateInsightPreferences,
} from "../../api";
import {
  LearningInsightsDetails,
  type InsightDetailTab,
} from "./LearningInsightsDetails";

type LearningInsightsSidebarProps = {
  className?: string;
};

const insightWindows: Array<{ value: InsightWindow; label: string }> = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
];

export function LearningInsightsSidebar({ className = "" }: LearningInsightsSidebarProps) {
  const [insightWindow, setInsightWindow] = useState<InsightWindow>("7d");
  const [summary, setSummary] = useState<InsightSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const [detailTab, setDetailTab] = useState<InsightDetailTab>("overview");
  const [reloadVersion, setReloadVersion] = useState(0);
  const [agentRefreshPending, setAgentRefreshPending] = useState(false);
  const refreshRequested = useRef(new Set<InsightWindow>());
  const summaryCache = useRef(new Map<InsightWindow, InsightSummary>());
  const settingsReturnFocus = useRef<HTMLElement | null>(null);
  const detailsReturnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let pollTimer: number | null = null;
    let cancelled = false;
    const pollDelays = [3_000, 5_000, 7_000, 10_000];

    const cached = summaryCache.current.get(insightWindow);
    if (cached) setSummary(cached);
    setLoading(!cached);
    setError(false);
    setAgentRefreshPending(false);

    const load = async () => {
      try {
        const initial = await getInsightSummary(insightWindow, { signal: controller.signal });
        if (cancelled) return;
        summaryCache.current.set(insightWindow, initial);
        setSummary(initial);
        setLoading(false);

        const shouldRefresh =
          initial.status === "ready" &&
          initial.generated_by !== "agent" &&
          !refreshRequested.current.has(insightWindow);
        if (!shouldRefresh) return;

        refreshRequested.current.add(insightWindow);
        setAgentRefreshPending(true);
        try {
          await refreshInsights(insightWindow, { signal: controller.signal });
          if (cancelled) return;
          let pollIndex = 0;
          const pollForAgent = async () => {
            try {
              const refreshed = await getInsightSummary(insightWindow, {
                signal: controller.signal,
              });
              if (cancelled) return;
              summaryCache.current.set(insightWindow, refreshed);
              setSummary(refreshed);
              if (refreshed.generated_by === "agent") {
                setAgentRefreshPending(false);
                return;
              }
              pollIndex += 1;
              if (pollIndex < pollDelays.length) {
                pollTimer = window.setTimeout(pollForAgent, pollDelays[pollIndex]);
                return;
              }
              refreshRequested.current.delete(insightWindow);
            } catch (refreshError) {
              if (!(refreshError instanceof DOMException && refreshError.name === "AbortError")) {
                // The deterministic summary remains useful if the optional agent refresh fails.
                refreshRequested.current.delete(insightWindow);
              }
            } finally {
              if (!cancelled && pollIndex >= pollDelays.length) {
                setAgentRefreshPending(false);
              }
            }
          };
          pollTimer = window.setTimeout(pollForAgent, pollDelays[0]);
        } catch (refreshError) {
          refreshRequested.current.delete(insightWindow);
          if (!cancelled) setAgentRefreshPending(false);
          if (refreshError instanceof DOMException && refreshError.name === "AbortError") return;
        }
      } catch (loadError) {
        if (loadError instanceof DOMException && loadError.name === "AbortError") return;
        if (!cancelled) {
          const fallback = summaryCache.current.get(insightWindow);
          setSummary(fallback ?? null);
          setError(!fallback);
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
      controller.abort();
      if (pollTimer !== null) window.clearTimeout(pollTimer);
      refreshRequested.current.delete(insightWindow);
    };
  }, [insightWindow, reloadVersion]);

  const reload = useCallback(() => {
    summaryCache.current.delete(insightWindow);
    setSummary(null);
    setLoading(true);
    setReloadVersion((version) => version + 1);
  }, [insightWindow]);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);
  const closeDetails = useCallback(() => setDetailsOpen(false), []);
  const openSettings = useCallback((event: MouseEvent<HTMLButtonElement>) => {
    settingsReturnFocus.current = event.currentTarget;
    setSettingsOpen(true);
  }, []);
  const openDetails = useCallback(
    (event: MouseEvent<HTMLButtonElement>, tab: InsightDetailTab) => {
      detailsReturnFocus.current = event.currentTarget;
      setDetailTab(tab);
      setDetailsOpen(true);
    },
    [],
  );
  const selectWindow = (nextWindow: InsightWindow) => {
    if (nextWindow === insightWindow) return;
    const cached = summaryCache.current.get(nextWindow);
    setLoading(!cached);
    setSummary(cached ?? null);
    setError(false);
    setInsightWindow(nextWindow);
  };

  if (loading && !summary) {
    return (
      <aside
        className={`min-h-[112px] animate-pulse rounded-3xl border border-ink/5 bg-white/70 lg:min-h-[560px] ${className}`}
        aria-label="Loading your learning insights"
        aria-busy="true"
      >
        <span className="sr-only">Loading learning insights…</span>
      </aside>
    );
  }

  if (error || !summary) {
    return (
      <aside
        className={`animate-fade-up rounded-3xl border border-ink/5 bg-white p-6 shadow-chip lg:!bottom-auto ${className}`}
        aria-labelledby="learning-insights-error-title"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
          Learning insights
        </p>
        <h2 id="learning-insights-error-title" className="mt-3 font-archivo text-2xl font-semibold tracking-[-0.03em]">
          Learning insights are unavailable
        </h2>
        <p className="mt-3 text-sm font-medium leading-relaxed text-ink-soft">
          You can keep learning or create a course while we reconnect this private view.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={reload}
            className="inline-flex min-h-12 items-center justify-center rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={openSettings}
            className="inline-flex min-h-12 items-center justify-center rounded-full border border-ink/10 bg-white px-5 text-sm font-semibold text-ink transition hover:border-ink/25"
          >
            Privacy
          </button>
        </div>
        {settingsOpen ? (
          <InsightSettings
            onClose={closeSettings}
            onChanged={reload}
            returnFocus={settingsReturnFocus.current}
          />
        ) : null}
      </aside>
    );
  }

  const metrics = summary.metrics;
  const answerAccuracy =
    metrics.quiz_accuracy === null ? "—" : `${Math.round(metrics.quiz_accuracy * 100)}%`;
  const topStruggle = summary.struggles[0];
  const topInterest = summary.interests[0];

  return (
    <>
      <aside
        className={`animate-fade-up rounded-3xl border border-ink/5 bg-white p-4 text-ink shadow-chip sm:p-5 ${className}`}
        aria-labelledby="learning-insights-title"
        aria-busy={loading || agentRefreshPending}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
                Your learning snapshot
              </p>
              <span className="rounded-full border border-ink/5 bg-bone px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-soft">
                Private
              </span>
            </div>
            <h2 id="learning-insights-title" className="mt-1.5 font-archivo text-2xl font-semibold tracking-[-0.03em]">
              Learning insights
            </h2>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={openSettings}
              className="grid h-12 w-12 place-items-center rounded-full bg-ink/5 text-ink transition hover:bg-ink/10"
              aria-label="Open learning insight privacy settings"
              title="Privacy and settings"
            >
              <span className="material-symbols-outlined text-[20px]">tune</span>
            </button>
            <button
              type="button"
              onClick={() => setMobileExpanded((expanded) => !expanded)}
              className="grid h-12 w-12 place-items-center rounded-full bg-ink text-white transition hover:bg-ink/80 lg:hidden"
              aria-expanded={mobileExpanded}
              aria-controls="learning-insights-summary"
              aria-label={mobileExpanded ? "Collapse learning insights" : "Expand learning insights"}
            >
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
                {mobileExpanded ? "expand_less" : "expand_more"}
              </span>
            </button>
          </div>
        </div>
        <div id="learning-insights-summary" className={mobileExpanded ? "block" : "hidden lg:block"}>
          <div className="mt-3 grid grid-cols-2 gap-1 rounded-full border border-ink/5 bg-bone p-1" aria-label="Insight time range">
            {insightWindows.map((range) => (
              <button
                key={range.value}
                type="button"
                aria-pressed={insightWindow === range.value}
                onClick={() => selectWindow(range.value)}
                className={`min-h-11 rounded-full px-3 py-2 text-xs font-semibold transition ${
                  insightWindow === range.value
                    ? "bg-ink text-white"
                    : "text-ink-soft hover:bg-white hover:text-ink"
                }`}
              >
                {range.label}
              </button>
            ))}
          </div>

          {summary.status === "disabled" ? (
            <section className="mt-3 rounded-2xl border border-ink/5 bg-bone p-5 text-ink">
              <span className="material-symbols-outlined text-[28px] text-ink-soft" aria-hidden="true">visibility_off</span>
              <h3 className="mt-2 font-archivo text-xl font-semibold tracking-[-0.01em]">Learning activity is paused</h3>
              <p className="mt-2 text-sm font-medium leading-relaxed text-ink-soft">
                No new lesson time, answers, or tutor activity is being added to this view.
              </p>
              <button
                type="button"
                onClick={openSettings}
                className="mt-5 inline-flex min-h-12 items-center justify-center rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
              >
                Review privacy settings
              </button>
            </section>
          ) : (
            <>
            <section className="mt-3 grid grid-cols-2 gap-2" aria-label="Key learning metrics">
              <CompactMetric
                label="Active time"
                value={formatMinutes(metrics.active_minutes)}
                detail={`${metrics.active_days} active ${metrics.active_days === 1 ? "day" : "days"}`}
                icon="timer"
                tone="border border-ink/5 bg-bone"
              />
              <CompactMetric
                label="Answer quality"
                value={answerAccuracy}
                detail={metrics.answers_total > 0 ? `${metrics.answers_correct}/${metrics.answers_total} correct` : "No answers yet"}
                icon="task_alt"
                tone="border border-ink/5 bg-bone"
              />
              <CompactMetric
                label="Lessons"
                value={`${metrics.lessons_completed}/${metrics.lessons_viewed}`}
                detail="Completed / viewed"
                icon="menu_book"
                tone="border border-ink/5 bg-bone"
              />
              <CompactMetric
                label="Tutor use"
                value={String(metrics.tutor_questions)}
                detail={`${metrics.tutor_responses} finished ${metrics.tutor_responses === 1 ? "reply" : "replies"}`}
                icon="forum"
                tone="border border-ink/5 bg-bone"
              />
            </section>

            <button
              type="button"
              onClick={(event) => openDetails(event, "patterns")}
              className="mt-2.5 block min-h-12 w-full rounded-2xl border border-ink/5 bg-bone p-4 text-left text-ink transition hover:border-ink/15"
              aria-haspopup="dialog"
            >
              <span className="flex items-center justify-between gap-3">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
                  Tuto’s take
                </span>
                <span className="rounded-full bg-white px-2 py-1 text-[9px] font-semibold text-ink-soft shadow-chip">
                  {agentRefreshPending
                    ? "Checking…"
                    : summary.generated_by === "agent"
                      ? "Agent reviewed"
                      : "Evidence summary"}
                </span>
              </span>
              <span className="mt-2 block line-clamp-2 font-archivo text-base font-semibold leading-snug tracking-[-0.01em]">
                {summary.report?.headline ?? "Your patterns will become clearer as you learn"}
              </span>
              <span className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-brand">
                Open feedback
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">arrow_forward</span>
              </span>
            </button>

            <button
              type="button"
              onClick={(event) => openDetails(event, "patterns")}
              className="mt-2.5 block min-h-12 w-full rounded-2xl border border-ink/5 bg-bone p-3.5 text-left transition hover:border-ink/15"
              aria-haspopup="dialog"
            >
              <SignalPeek
                icon="troubleshoot"
                label="Getting stuck"
                value={topStruggle?.title ?? "No supported pattern yet"}
                tone="bg-white text-ink-soft"
              />
              <SignalPeek
                icon="interests"
                label="Exploring"
                value={topInterest?.title ?? "Your recent focus will appear here"}
                tone="bg-cream text-brand-dark"
              />
            </button>

            {summary.recommended_action ? (
              <button
                type="button"
                onClick={() => navigateTo(summary.recommended_action?.href ?? "#dashboard")}
                className="mt-2.5 flex min-h-12 w-full items-center gap-3 rounded-2xl border border-ink/5 bg-bone p-3.5 text-left text-ink transition hover:border-ink/15"
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand text-white">
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">play_arrow</span>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[9px] font-semibold uppercase tracking-[0.13em] text-ink-faint">Next up</span>
                  <span className="mt-0.5 block line-clamp-2 font-archivo text-sm font-semibold leading-snug tracking-[-0.01em]">
                    {summary.recommended_action.label}
                  </span>
                </span>
              </button>
            ) : null}

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={(event) => openDetails(event, "patterns")}
                className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 rounded-full bg-ink px-4 text-sm font-semibold text-white transition hover:bg-ink/80"
                aria-haspopup="dialog"
              >
                View full report
                <span className="material-symbols-outlined text-[17px]" aria-hidden="true">open_in_new</span>
              </button>
              <button
                type="button"
                onClick={(event) => openDetails(event, "activity")}
                className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-ink/5 text-ink transition hover:bg-ink/10"
                aria-label="Open recent learning activity"
                aria-haspopup="dialog"
              >
                <span className="material-symbols-outlined text-[19px]" aria-hidden="true">history</span>
              </button>
            </div>
            </>
          )}
        </div>

        <span className="sr-only" aria-live="polite">
          {agentRefreshPending ? "Checking your latest learning patterns" : "Learning insights are up to date"}
        </span>
      </aside>

      <LearningInsightsDetails
        open={detailsOpen}
        summary={summary}
        insightWindow={insightWindow}
        agentRefreshPending={agentRefreshPending}
        initialTab={detailTab}
        returnFocus={detailsReturnFocus.current}
        onClose={closeDetails}
      />

      {settingsOpen ? (
        <InsightSettings
          onClose={closeSettings}
          onChanged={reload}
          returnFocus={settingsReturnFocus.current}
        />
      ) : null}
    </>
  );
}

function CompactMetric({
  label,
  value,
  detail,
  icon,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  icon: string;
  tone: string;
}) {
  return (
    <div className={`min-h-[94px] rounded-2xl p-3 text-ink ${tone}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-[9px] font-semibold uppercase tracking-[0.09em] opacity-70">{label}</p>
        <span className="material-symbols-outlined text-[16px] opacity-70" aria-hidden="true">{icon}</span>
      </div>
      <p className="mt-1.5 font-archivo text-2xl font-semibold leading-none tracking-[-0.01em] text-brand-dark">{value}</p>
      <p className="mt-1.5 line-clamp-1 text-[9px] font-semibold leading-snug opacity-70">{detail}</p>
    </div>
  );
}

function SignalPeek({
  icon,
  label,
  value,
  tone,
}: {
  icon: string;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <span className="flex items-center gap-2.5 py-1.5 first:pt-0 last:pb-0">
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${tone}`}>
        <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[9px] font-semibold uppercase tracking-[0.11em] text-ink-faint">{label}</span>
        <span className="mt-0.5 block truncate text-[11px] font-semibold text-ink">{value}</span>
      </span>
      <span className="material-symbols-outlined text-[16px] text-ink-faint" aria-hidden="true">chevron_right</span>
    </span>
  );
}

function navigateTo(href: string): void {
  window.location.hash = href.startsWith("#") ? href : "#dashboard";
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function InsightSettings({
  onClose,
  onChanged,
  returnFocus,
}: {
  onClose: () => void;
  onChanged: () => void;
  returnFocus: HTMLElement | null;
}) {
  const [preferences, setPreferences] = useState<InsightPreferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getInsightPreferences().then(setPreferences).catch(() => setError("Couldn’t load settings."));
  }, []);

  useEffect(() => {
    const previousFocus = returnFocus ?? (document.activeElement as HTMLElement | null);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = dialogRef.current;
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
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
      previousFocus?.focus();
    };
  }, [onClose, returnFocus]);

  const update = async (patch: Partial<InsightPreferences>) => {
    setSaving(true);
    setError(null);
    try {
      const next = await updateInsightPreferences(patch);
      setPreferences(next);
      onChanged();
    } catch {
      setError("That change didn’t save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete all of your learning activity and generated insights?")) return;
    setSaving(true);
    setError(null);
    try {
      await deleteInsights();
      onChanged();
      onClose();
    } catch {
      setError("Your insight data couldn’t be deleted. Please try again.");
      setSaving(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[100] grid place-items-center overflow-y-auto bg-ink/75 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="insight-settings-title"
      ref={dialogRef}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="my-auto w-full max-w-lg rounded-3xl border border-ink/5 bg-white p-6 text-ink shadow-panel sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">You’re in control</p>
            <h2 id="insight-settings-title" className="mt-2 font-archivo text-2xl font-semibold tracking-[-0.03em]">
              Learning insight privacy
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-ink/5 text-ink-soft transition hover:bg-ink/10 hover:text-ink"
            aria-label="Close settings"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="mt-6 space-y-3">
          <PreferenceRow
            title="Learning activity"
            description="Use active lesson time, completions, quiz results, and tutor activity for your private insight view."
            checked={preferences?.analytics_enabled ?? true}
            disabled={!preferences || saving}
            onChange={(checked) => void update({ analytics_enabled: checked })}
          />
          <PreferenceRow
            title="Question content"
            description="Optional storage for future topic-aware feedback. Current insights use counts and course activity, so this stays off by default."
            checked={preferences?.question_content_enabled ?? false}
            disabled={!preferences || saving || !preferences.analytics_enabled}
            onChange={(checked) => void update({ question_content_enabled: checked })}
          />
        </div>

        <div className="mt-5 rounded-2xl bg-cream p-4 text-sm font-medium leading-relaxed text-brand-dark">
          These insights are personal, aren’t shared with teachers or parents, and never compare you with other learners.
        </div>
        <div className="mt-3 rounded-2xl bg-sand p-4 text-ink">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-faint">
            What this view records
          </p>
          <ul className="mt-2 space-y-1 text-xs font-medium leading-relaxed text-ink-soft">
            <li>Active lesson time and lesson progress</li>
            <li>Quiz totals, correctness, pacing, hints, and retries</li>
            <li>Tutor question counts, finished replies, and reply time</li>
          </ul>
          <p className="mt-2 text-[11px] font-medium leading-relaxed text-ink-soft">
            It doesn’t record raw answers, tutor replies, keystrokes, mouse trails, or background-tab time.
          </p>
        </div>
        {error ? <p className="mt-3 text-sm font-semibold text-coral-dark" role="alert">{error}</p> : null}

        <button
          type="button"
          onClick={() => void remove()}
          disabled={saving}
          className="mt-6 inline-flex min-h-12 items-center justify-center rounded-full bg-coral-soft px-5 text-sm font-semibold text-coral-dark transition hover:bg-coral/10 disabled:cursor-wait disabled:opacity-50"
        >
          Delete my insight data
        </button>
      </div>
    </div>,
    document.body,
  );
}

function PreferenceRow({
  title,
  description,
  checked,
  disabled,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-24 cursor-pointer items-center justify-between gap-4 rounded-2xl bg-sand p-4">
      <span>
        <span className="block text-sm font-semibold text-ink">{title}</span>
        <span className="mt-1 block text-xs font-medium leading-relaxed text-ink-soft">{description}</span>
      </span>
      <input
        type="checkbox"
        className="h-6 w-6 shrink-0 accent-brand"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}
