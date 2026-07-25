import { useEffect, useRef, useState } from "react";

import {
  DEFAULT_LEARNING_PREFERENCES,
  LearningModality,
  LearningPreferences,
  getProfile,
  putProfile,
} from "../../api";
import { Mascot } from "../../components/Mascot";

/**
 * Learner-profile onboarding (specs/learner_profile).
 * Always a fixed overlay dialog: "firstRun" pops over the app right after signup
 * (dismissible only via Skip/Finish); "edit" opens from the dashboard settings
 * button (dismissible via X, Escape, or the backdrop).
 */
type OnboardingPageProps = {
  mode?: "firstRun" | "edit";
  /** Called after a successful save (or a first-run skip, even if its save failed). */
  onDone: () => void;
  /** Edit mode only: closed without saving. */
  onClose?: () => void;
};

type Option = {
  id: string;
  title: string;
  blurb: string;
  icon?: string;
};

const GOAL_OPTS: Option[] = [
  { id: "curiosity", title: "Just curious", blurb: "Explore topics for the fun of it", icon: "travel_explore" },
  { id: "exam", title: "Ace an exam", blurb: "Structured coverage and practice", icon: "quiz" },
  { id: "career", title: "Grow my career", blurb: "Applied skills, project-style", icon: "work" },
  { id: "school", title: "School & assignments", blurb: "Keep up with class material", icon: "school" },
];

const MODALITY_OPTS: (Option & { id: LearningModality })[] = [
  { id: "visual", title: "Visuals & diagrams", blurb: "Charts, canvases, spatial layouts", icon: "monitoring" },
  { id: "auditory", title: "Listening & discussion", blurb: "Conversational explanations", icon: "headphones" },
  { id: "reading", title: "Reading & writing", blurb: "Deep text, definitions, notes", icon: "menu_book" },
  { id: "hands_on", title: "Doing & interacting", blurb: "Sliders, simulations, trying things", icon: "touch_app" },
];

const STRUCTURE_OPTS: Option[] = [
  { id: "examples_first", title: "Examples first", blurb: "A worked example, then the rule", icon: "play_circle" },
  { id: "theory_first", title: "Theory first", blurb: "The concept, then applications", icon: "account_tree" },
  { id: "balanced", title: "No preference", blurb: "Mix both, depending on the topic", icon: "balance" },
];

const PRIOR_OPTS: Option[] = [
  { id: "beginner", title: "Usually new", blurb: "Most topics are new to me", icon: "flag" },
  { id: "intermediate", title: "Some background", blurb: "I know the basics of many topics", icon: "trending_up" },
  { id: "advanced", title: "Strong background", blurb: "Skip the basics where possible", icon: "emoji_events" },
];

const STEP_TITLES = [
  "What are you here to achieve?",
  "How do you like to learn?",
  "Examples first or theory first?",
  "How much do you know going in?",
];

const STEP_SUBS = [
  "This shapes the tone and rigor of your courses.",
  "Pick up to two — your first pick matters most. This only shapes how lessons are presented.",
  "How each new concept should be introduced.",
  "Sets the starting difficulty — you can always change it per course.",
];

const LAST_STEP = STEP_TITLES.length - 1;

function OptionCard({
  option,
  selected,
  onClick,
  badge,
}: {
  option: Option;
  selected: boolean;
  onClick: () => void;
  badge?: string | null;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`flex min-h-[64px] w-full min-w-0 items-start gap-3 rounded-2xl border p-4 text-left transition active:scale-[0.99] ${
        selected
          ? "border-brand bg-cream shadow-soft"
          : "border-ink/10 bg-white hover:border-ink/30 hover:shadow-soft"
      }`}
    >
      {option.icon && (
        <span
          className={`material-symbols-outlined mt-0.5 shrink-0 text-[22px] ${selected ? "text-brand" : "text-ink-faint"}`}
          aria-hidden="true"
        >
          {option.icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block break-words text-sm font-semibold tracking-tight text-ink">
          {option.title}
        </span>
        <span className="mt-0.5 block break-words text-[12px] font-medium leading-snug text-ink-soft">
          {option.blurb}
        </span>
      </span>
      {badge ? (
        <span className="ml-auto shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold text-brand-dark">
          {badge}
        </span>
      ) : selected ? (
        <span
          className="material-symbols-outlined ml-auto shrink-0 text-[20px] text-brand"
          aria-hidden="true"
        >
          check_circle
        </span>
      ) : null}
    </button>
  );
}

function OptionGrid({
  options,
  value,
  onChange,
  columns = 2,
}: {
  options: Option[];
  value: string;
  onChange: (id: string) => void;
  columns?: 1 | 2;
}) {
  // Multi-column grids respond to the *dialog* width (~30rem), not the viewport —
  // longer-text options stay 1-wide so words never break mid-token.
  const cols = columns === 1 ? "" : "sm:grid-cols-2";
  return (
    <div className={`grid grid-cols-1 gap-2.5 ${cols}`}>
      {options.map((opt) => (
        <OptionCard
          key={opt.id}
          option={opt}
          selected={value === opt.id}
          onClick={() => onChange(opt.id)}
        />
      ))}
    </div>
  );
}

export function OnboardingPage({ mode = "edit", onDone, onClose }: OnboardingPageProps) {
  const firstRun = mode === "firstRun";
  const [step, setStep] = useState(0);
  const [prefs, setPrefs] = useState<LearningPreferences>(DEFAULT_LEARNING_PREFERENCES);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const advanceTimer = useRef<number | null>(null);
  const finishRef = useRef<() => void>(() => {});

  // Edit mode: prefill from the saved profile.
  useEffect(() => {
    if (firstRun) return;
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (!cancelled) setPrefs(p.preferences);
      })
      .catch(() => {
        /* defaults are fine — the editor still works */
      });
    return () => {
      cancelled = true;
    };
  }, [firstRun]);

  // Edit mode: Escape closes. First-run is a deliberate choice (Skip or Finish).
  useEffect(() => {
    if (firstRun || !onClose) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [firstRun, onClose]);

  useEffect(
    () => () => {
      if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
    },
    [],
  );

  function patch<K extends keyof LearningPreferences>(key: K, value: LearningPreferences[K]) {
    setPrefs((p) => ({ ...p, [key]: value }));
  }

  /** Single-select: record the pick, then (first run only) glide to the next step. */
  function pick<K extends keyof LearningPreferences>(
    key: K,
    value: LearningPreferences[K],
    advance: "next" | "finish",
  ) {
    patch(key, value);
    if (!firstRun) return;
    if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
    advanceTimer.current = window.setTimeout(() => {
      if (advance === "finish") finishRef.current();
      else setStep((s) => Math.min(s + 1, LAST_STEP));
    }, 220);
  }

  function toggleModality(id: LearningModality) {
    setPrefs((p) => {
      if (p.modalities.includes(id)) {
        return { ...p, modalities: p.modalities.filter((m) => m !== id) };
      }
      if (p.modalities.length >= 2) return p; // cap reached — first two picks stand
      return { ...p, modalities: [...p.modalities, id] };
    });
  }

  async function finish() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await putProfile(prefs, true);
      onDone();
    } catch {
      setError("Couldn't save your preferences. Check the backend connection and try again.");
      setSaving(false);
    }
  }
  finishRef.current = finish;

  async function skip() {
    setSaving(true);
    try {
      await putProfile(DEFAULT_LEARNING_PREFERENCES, false);
    } catch {
      /* skipping must never trap the user — defaults apply server-side */
    }
    onDone();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 backdrop-blur-sm sm:items-center sm:p-6"
      role="presentation"
      onClick={firstRun ? undefined : onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={firstRun ? "Welcome — set up your learning preferences" : "Your learning style"}
        onClick={(e) => e.stopPropagation()}
        className="motion-safe:animate-pop-in flex max-h-[94dvh] w-full min-w-0 flex-col overflow-hidden rounded-t-3xl bg-paper shadow-panel sm:max-h-[88dvh] sm:max-w-xl sm:rounded-3xl"
      >
        {/* Header — fixed */}
        <div className="shrink-0 px-5 pt-4 sm:px-7">
          <div className="flex items-center justify-between gap-4">
            <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
              {firstRun ? `Step ${step + 1} of ${STEP_TITLES.length}` : "Your learning style"}
            </p>
            {firstRun ? (
              <button
                type="button"
                onClick={skip}
                disabled={saving}
                className="min-h-11 rounded-full px-3 text-sm font-semibold text-ink-soft transition hover:text-ink disabled:opacity-50"
              >
                Skip for now
              </button>
            ) : (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close learning style editor"
                className="flex h-10 w-10 items-center justify-center rounded-full text-ink-soft transition hover:bg-sand hover:text-ink"
              >
                <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
                  close
                </span>
              </button>
            )}
          </div>
          <div
            className="mt-3 h-1 overflow-hidden rounded-full bg-sand"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={STEP_TITLES.length}
            aria-valuenow={step + 1}
            aria-label="Onboarding progress"
          >
            <div
              className="h-full rounded-full bg-brand transition-[width] duration-500"
              style={{ width: `${((step + 1) / STEP_TITLES.length) * 100}%` }}
            />
          </div>
        </div>

        {/* Content — the only scrolling region */}
        <main key={step} className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
          <div className="motion-safe:animate-fade-up">
            <div className="flex items-start gap-4">
              {firstRun && step === 0 && (
                <Mascot mood="study" className="mt-1 h-11 w-11 shrink-0" title="Hi Tuto mascot" />
              )}
              <div className="min-w-0">
                <h1 className="break-words font-archivo text-2xl font-semibold leading-tight tracking-[-0.02em] text-ink">
                  {STEP_TITLES[step]}
                </h1>
                <p className="mt-1.5 break-words text-sm font-medium leading-relaxed text-ink-soft">
                  {STEP_SUBS[step]}
                </p>
              </div>
            </div>

            <div className="mt-6">
              {step === 0 && (
                <OptionGrid
                  options={GOAL_OPTS}
                  value={prefs.goal}
                  onChange={(id) => pick("goal", id as LearningPreferences["goal"], "next")}
                />
              )}

              {step === 1 && (
                <>
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    {MODALITY_OPTS.map((opt) => {
                      const rank = prefs.modalities.indexOf(opt.id);
                      return (
                        <OptionCard
                          key={opt.id}
                          option={opt}
                          selected={rank >= 0}
                          badge={rank === 0 ? "1st pick" : rank === 1 ? "2nd pick" : null}
                          onClick={() => toggleModality(opt.id)}
                        />
                      );
                    })}
                  </div>
                  <p className="mt-3 text-[12px] font-medium text-ink-faint">
                    Optional — tap again to remove. Two picks maximum.
                  </p>
                </>
              )}

              {step === 2 && (
                <OptionGrid
                  options={STRUCTURE_OPTS}
                  value={prefs.structure}
                  onChange={(id) => pick("structure", id as LearningPreferences["structure"], "next")}
                  columns={1}
                />
              )}

              {step === 3 && (
                <OptionGrid
                  options={PRIOR_OPTS}
                  value={prefs.prior_knowledge}
                  onChange={(id) =>
                    pick("prior_knowledge", id as LearningPreferences["prior_knowledge"], "finish")
                  }
                  columns={1}
                />
              )}
            </div>
          </div>
        </main>

        {/* Footer — fixed, solid background, error on its own row */}
        <footer className="shrink-0 border-t border-ink/5 bg-paper px-5 py-4 sm:px-7">
          {error && (
            <p role="alert" className="mb-2 break-words text-[12px] font-semibold text-coral">
              {error}
            </p>
          )}
          <div className="flex items-center justify-between gap-3">
            {step > 0 ? (
              <button
                type="button"
                onClick={() => setStep((s) => s - 1)}
                disabled={saving}
                className="min-h-11 shrink-0 rounded-full px-4 text-sm font-semibold text-ink-soft transition hover:text-ink disabled:opacity-50"
              >
                Back
              </button>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-2">
              {!firstRun && step < LAST_STEP && (
                <button
                  type="button"
                  onClick={() => setStep((s) => s + 1)}
                  disabled={saving}
                  className="min-h-11 rounded-full px-4 text-sm font-semibold text-ink-soft transition hover:text-ink disabled:opacity-50"
                >
                  Continue
                </button>
              )}
              {firstRun && step < LAST_STEP ? (
                <button
                  type="button"
                  onClick={() => setStep((s) => s + 1)}
                  className="inline-flex min-h-11 items-center rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80"
                >
                  Continue
                </button>
              ) : (
                <button
                  type="button"
                  onClick={finish}
                  disabled={saving}
                  className="inline-flex min-h-11 items-center rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-60"
                >
                  {saving ? "Saving…" : firstRun ? "Finish" : "Save preferences"}
                </button>
              )}
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
