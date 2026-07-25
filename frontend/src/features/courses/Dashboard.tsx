import { BillingUsage, CourseCard, Progress, fetchBillingUsage } from "../../api";
import { BrandMark } from "../../components/BrandMark";
import { Mascot } from "../../components/Mascot";
import { hashFor } from "../../routing";
import { UserButton } from "@clerk/react";
import { useEffect, useRef, useState } from "react";
import { LearningInsightsSidebar } from "../insights/LearningInsightsSidebar";
import { OnboardingPage } from "../onboarding/OnboardingPage";

export type StatusFilter = "all" | CourseCard["status"];

type DashboardProps = {
  courses: CourseCard[];
  loading: boolean;
  loadError?: string | null;
  progress: Record<string, Progress>;
  query: string;
  status: StatusFilter;
  onQueryChange: (query: string) => void;
  onStatusChange: (status: StatusFilter) => void;
  onRetry: () => void;
  onCreate: () => void;
  onOpenRoadmap: (course: CourseCard) => void;
  onRename: (id: string, title: string) => Promise<void>;
  onDelete: (id: string) => void;
};

export function Dashboard({
  courses,
  loading,
  loadError,
  progress,
  query,
  status,
  onQueryChange,
  onStatusChange,
  onRetry,
  onCreate,
  onOpenRoadmap,
  onRename,
  onDelete,
}: DashboardProps) {
  const liveCount = courses.filter((c) => c.status === "generating").length;
  const [editingStyle, setEditingStyle] = useState(false);
  // Course-credit balance chip; fail-silent so a billing outage never marks up the header.
  const [usage, setUsage] = useState<BillingUsage | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchBillingUsage()
      .then((u) => {
        if (!cancelled) setUsage(u);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  const resumeCourse =
    courses.find(
      (course) =>
        course.status === "ready" &&
        course.completed_count > 0 &&
        course.completed_count < course.lesson_count,
    ) ??
    courses.find(
      (course) => course.status === "ready" && course.completed_count < course.lesson_count,
    ) ??
    courses.find((course) => course.status === "outline_review");
  const resumePercent =
    resumeCourse && resumeCourse.lesson_count > 0
      ? Math.round((resumeCourse.completed_count / resumeCourse.lesson_count) * 100)
      : 0;

  return (
    <div className="min-h-full bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <header className="sticky top-0 z-40 border-b border-ink/5 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => { window.location.hash = hashFor({ kind: "dashboard" }); }}
            aria-label="Go to dashboard home"
            className="flex min-h-12 shrink-0 items-center gap-2.5 text-left"
          >
            <BrandMark className="!h-9 !w-9 rounded-xl" />
            <span className="text-lg font-semibold tracking-[-0.01em]">Hi Tuto</span>
          </button>
          <div className="flex shrink-0 items-center gap-2.5">
            {usage !== null &&
            usage.course_credits.remaining <=
              Math.max(1, Math.ceil(usage.course_credits.total * 0.15)) ? (
              <a
                href="#billing"
                title={`${usage.plan} — course credits reset ${new Date(usage.renews_at).toLocaleDateString()}`}
                className="hidden min-h-11 items-center gap-1.5 rounded-full border border-brand/25 bg-cream px-4 text-xs font-semibold text-brand-dark transition hover:border-brand/50 md:inline-flex"
              >
                <span className="material-symbols-outlined text-[15px]" aria-hidden="true">bolt</span>
                {usage.course_credits.remaining <= 0
                  ? "No credits left"
                  : `${usage.course_credits.remaining} credit${
                      usage.course_credits.remaining === 1 ? "" : "s"
                    } left`}
              </a>
            ) : null}
            <button
              type="button"
              onClick={onCreate}
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
            >
              <span className="material-symbols-outlined text-[18px]" aria-hidden="true">add</span>
              <span className="hidden sm:inline">New course</span>
              <span className="sm:hidden">New</span>
            </button>
            <UserButton
              appearance={{
                elements: {
                  avatarBox: "h-9 w-9 rounded-full",
                  userButtonPopoverCard: "rounded-2xl shadow-panel",
                  userButtonPopoverActionButton: "rounded-xl",
                },
              }}
            >
              <UserButton.MenuItems>
                <UserButton.Action
                  label="Plan & usage"
                  labelIcon={<BillingIcon />}
                  onClick={() => {
                    window.location.hash = "#billing";
                  }}
                />
                <UserButton.Action
                  label="Learning style"
                  labelIcon={<LearningStyleIcon />}
                  onClick={() => setEditingStyle(true)}
                />
              </UserButton.MenuItems>
            </UserButton>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 pb-24 pt-6 sm:px-8 sm:pt-8">
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="animate-fade-up min-w-0 lg:col-start-1 lg:row-start-1">
          <div className="relative overflow-hidden rounded-3xl border border-ink/5 bg-white p-4 shadow-chip sm:p-5">
            <div
              className="pointer-events-none absolute -right-8 -top-10 h-56 w-56 rounded-full bg-lime/25 blur-3xl"
              aria-hidden="true"
            />
            <div
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_90%_at_100%_-10%,rgba(43,193,93,0.22),transparent_58%)]"
              aria-hidden="true"
            />
            <div className="relative flex flex-col gap-3 md:flex-row md:items-stretch md:gap-3">
              <div className="relative min-w-0 flex-1 md:pr-24">
                <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white/80 px-3 py-1 text-xs font-semibold text-ink-soft shadow-chip">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                  {liveCount > 0
                    ? `${liveCount} course${liveCount > 1 ? "s" : ""} building`
                    : "Ready for a quick win"}
                </span>
                <h2 className="mt-3 max-w-md text-balance font-archivo text-[clamp(1.75rem,3vw,2.55rem)] font-semibold leading-[1.04] tracking-[-0.035em]">
                  What do you want to learn <span className="text-brand">next?</span>
                </h2>
                <p className="mt-2 max-w-sm text-sm leading-6 text-ink-soft">
                  Open a course below, or use New course to turn any topic or PDF into a guided path.
                </p>
              </div>

              {resumeCourse ? (
                <button
                  type="button"
                  onClick={() => onOpenRoadmap(resumeCourse)}
                  className="group relative z-10 flex min-h-[9.75rem] w-full shrink-0 flex-col rounded-2xl bg-ink p-4 text-left text-white transition hover:bg-ink/90 md:w-[15.75rem]"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/50">
                      {resumeCourse.status === "outline_review" ? "Needs review" : "Continue course"}
                    </span>
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white/10 text-white transition group-hover:bg-white/20">
                      <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
                        {resumeCourse.status === "outline_review" ? "checklist" : "arrow_forward"}
                      </span>
                    </span>
                  </span>
                  <span className="mt-2 line-clamp-2 font-archivo text-[15px] font-semibold leading-snug tracking-[-0.01em]">
                    {resumeCourse.title || resumeCourse.topic}
                  </span>
                  <span className="mt-auto pt-2.5 text-[11px] font-medium text-white/55">
                    {resumeCourse.status === "outline_review"
                      ? "Roadmap ready to review"
                      : `${resumeCourse.completed_count} of ${resumeCourse.lesson_count} lessons done`}
                  </span>
                  {resumeCourse.status !== "outline_review" ? (
                    <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-white/15" aria-hidden="true">
                      <span
                        className="block h-full rounded-full bg-brand"
                        style={{ width: `${resumePercent}%` }}
                      />
                    </span>
                  ) : null}
                </button>
              ) : (
                <div className="relative z-10 flex min-h-[9.75rem] w-full shrink-0 flex-col rounded-2xl bg-ink p-4 text-white md:w-[15.75rem]">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/50">
                    {liveCount > 0 ? "Taking shape" : "Start anywhere"}
                  </p>
                  <h3 className="mt-2 font-archivo text-[15px] font-semibold leading-snug tracking-[-0.01em]">
                    {liveCount > 0 ? "Your new course is being built." : "Turn one idea into a learning path."}
                  </h3>
                  <button
                    type="button"
                    onClick={onCreate}
                    className="mt-auto inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-full bg-white px-4 text-sm font-semibold text-ink transition hover:bg-white/90"
                  >
                    <span className="material-symbols-outlined text-[17px]" aria-hidden="true">add</span>
                    New course
                  </button>
                </div>
              )}

              <Mascot
                mood="study"
                className="pointer-events-none absolute bottom-0 right-[16.5rem] z-[1] hidden h-24 w-24 animate-mascot-bob md:block"
                title="Hi Tuto ready to study"
              />
            </div>
          </div>
        </section>

          <LearningInsightsSidebar className="min-w-0 lg:fixed lg:bottom-6 lg:right-[max(2rem,calc((100vw-80rem)/2+2rem))] lg:top-[6.8125rem] lg:z-30 lg:w-[22rem] lg:overflow-y-auto" />

          <div className="min-w-0 lg:col-start-1 lg:row-start-2">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <span className="material-symbols-outlined pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[20px] text-ink-faint">
                  search
                </span>
                <input
                  value={query}
                  onChange={(e) => onQueryChange(e.target.value)}
                  placeholder="Search your courses…"
                  className="h-12 w-full rounded-full border border-ink/10 bg-white pl-11 pr-4 text-sm font-medium text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
                />
              </div>
              <div className="flex overflow-x-auto rounded-full border border-ink/5 bg-white p-1 shadow-chip">
                {(["all", "generating", "ready", "failed"] as StatusFilter[]).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => onStatusChange(s)}
                    className={`rounded-full px-3.5 py-2 text-[13px] font-semibold capitalize transition ${
                      status === s ? "bg-ink text-white" : "text-ink-soft hover:text-ink"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-80 animate-pulse rounded-3xl border border-ink/5 bg-sand/70" />
                ))}
              </div>
            ) : loadError ? (
              <LoadError message={loadError} onRetry={onRetry} />
            ) : courses.length === 0 ? (
              <Empty onCreate={onCreate} />
            ) : (
              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                {courses.map((c, i) => (
                  <Card
                    key={c.id}
                    c={c}
                    index={i}
                    progress={progress[c.id]}
                    onOpen={() => {
                      if (c.status === "ready" || c.status === "outline_review") onOpenRoadmap(c);
                    }}
                    onRename={(title) => onRename(c.id, title)}
                    onDelete={() => onDelete(c.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {editingStyle && (
        <OnboardingPage
          mode="edit"
          onDone={() => setEditingStyle(false)}
          onClose={() => setEditingStyle(false)}
        />
      )}
    </div>
  );
}

/** Compact icon for Clerk's UserButton menu — sized to match their default glyphs. */
function BillingIcon() {
  return (
    <span
      className="material-symbols-outlined block leading-none"
      style={{ fontSize: 16 }}
      aria-hidden="true"
    >
      account_balance_wallet
    </span>
  );
}

function LearningStyleIcon() {
  return (
    <span
      className="material-symbols-outlined block leading-none"
      style={{ fontSize: 16 }}
      aria-hidden="true"
    >
      tune
    </span>
  );
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="animate-fade-up rounded-3xl border border-ink/5 bg-white p-6 shadow-chip sm:p-8">
      <div className="flex max-w-2xl flex-col gap-5 sm:flex-row sm:items-center">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-coral-soft text-coral-dark">
          <span className="material-symbols-outlined text-[25px]" aria-hidden="true">sync_problem</span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-coral-dark">Courses unavailable</p>
          <h2 className="mt-1 font-archivo text-xl font-semibold tracking-[-0.02em] text-ink">We couldn’t load your shelf.</h2>
          <p className="mt-1 line-clamp-2 text-sm leading-6 text-ink-soft">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80"
        >
          <span className="material-symbols-outlined text-[19px]" aria-hidden="true">refresh</span>
          Try again
        </button>
      </div>
    </div>
  );
}

function Empty({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="animate-fade-up grid min-h-[400px] place-items-center rounded-3xl bg-ink p-10 text-center text-white shadow-panel">
      <div className="max-w-lg">
        <div className="mb-6 inline-flex items-center gap-2.5 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white/80">
          <Mascot mood="mark" className="h-8 w-8 shrink-0" />
          Start here
        </div>
        <h2 className="mb-3 font-archivo text-4xl font-semibold tracking-[-0.03em]">
          Your shelf is empty
        </h2>
        <p className="mx-auto mb-8 max-w-md text-[15px] leading-relaxed text-white/65">
          Ask for anything — “Quantum computing”, “The solar system”, “Baking sourdough”.
          We’ll design the path and build the interactive lessons with you.
        </p>
        <button
          type="button"
          onClick={onCreate}
          className="inline-flex min-h-12 items-center gap-2 rounded-full bg-white px-7 text-sm font-semibold text-ink transition hover:bg-white/90"
        >
          <span className="material-symbols-outlined text-[20px]">auto_awesome</span>
          Generate your first course
        </button>
      </div>
    </div>
  );
}

/** Icon-chip tints — one per course, stable via toneIndex. Cards themselves stay white;
 *  the tint gives each shelf card its own identity without loud full-bleed color. */
const TONES = [
  { chip: "bg-mint text-lime", pill: "bg-ink/5 text-ink-soft" },
  { chip: "bg-stone-200 text-stone-600", pill: "bg-ink/5 text-ink-soft" },
  { chip: "bg-sky/10 text-sky", pill: "bg-ink/5 text-ink-soft" },
  { chip: "bg-ink text-white", pill: "bg-ink/5 text-ink-soft" },
  { chip: "bg-ink/5 text-ink-soft", pill: "bg-ink/5 text-ink-soft" },
] as const;
type Tone = (typeof TONES)[number];

/** Stable per-course tone: hash the id (not the grid index) so a card keeps its color on reorder.
 *  FNV-1a + avalanche spreads UUID hex evenly across the tones (plain char-sum clusters). */
function toneIndex(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  h ^= h >>> 15;
  h = Math.imul(h, 2246822519) >>> 0;
  h ^= h >>> 13;
  return (h >>> 0) % TONES.length;
}

/** Topic → Material Symbol. First keyword hit wins; no match falls back to a monogram.
 *  Keywords are \b-anchored so substrings don't false-match ("Generated"≠gene,
 *  "Revolution"≠evolution, "Fundamentals"≠mental, "biological"≠logic). */
const ICON_RULES: [RegExp, string][] = [
  [/\bchemist|\bmolecul|\breaction|\borganic|\batom/i, "science"],
  [/\bphysics|\bquantum|\brelativ|\bthermodynam|\bmechanic|\bgravity/i, "experiment"],
  [/\bbiolog|\bcell|\bgenetic|\bgenome|\bdna\b|\banatomy|\becolog|\bbotan|\bzoolog|\borganism|\bevolution/i, "biotech"],
  [/\bmath|\balgebra|\bcalculus|\bgeometry|\bstatistic|\bprobabilit|\btrigonometr|\bequation/i, "functions"],
  [/\bhistor|\bancient|\bempire|\brenaissance|\brevolution|\bmedieval|\bciviliz|\bdynasty/i, "history_edu"],
  [/\bgeograph|\bclimate|\bplanet|\bsolar|\bastronom|\bspace|\bcosmos|\buniverse|\bgalaxy/i, "public"],
  [/\bspanish|\bfrench|\bgerman|\bitalian|\bjapanese|\bmandarin|\blanguage|\bgrammar|\bvocabulary|\blinguist/i, "translate"],
  [/\bprogram|\bcoding|\bjavascript|\bpython|\breact|\bsoftware|\bdevelop|\balgorithm|\bfrontend|\bbackend/i, "code"],
  [/\bcomput|\bmachine learning|\bneural|\bdatabase|\bnetwork|\bai\b|\bdata scien/i, "memory"],
  [/\bmusic|\bpiano|\bguitar|\bchord|\bmelody|\brhythm/i, "music_note"],
  [/\bpaint|\bdraw|\bsketch|\bdesign|\billustrat|\bart\b/i, "palette"],
  [/\becon|\bfinance|\bmoney|\binvest|\bmarket|\bbusiness|\baccount|\btrading|\bstock/i, "payments"],
  [/\bcook|\bbak|\brecipe|\bcuisine|\bculinary|\bsourdough|\bpastry/i, "restaurant"],
  [/\blaw\b|\blegal|\bjustice|\bconstitution|\bcourt|\bjurisprud/i, "gavel"],
  [/\bmedic|\bhealth|\bdisease|\bnursing|\bclinical|\bpharmac/i, "medical_services"],
  [/\bpsycholog|\bcognit|\bbehavior|\bmind|\bmental/i, "psychology"],
  [/\bphilosoph|\bethic|\blogic|\bexistential|\bmetaphys|\bstoic/i, "menu_book"],
  [/\bwrit|\bessay|\bliterature|\bpoetry|\bnovel|\bstorytell|\bfiction/i, "auto_stories"],
  [/\bfitness|\bexercise|\byoga|\bworkout|\bsport|\bathletic|\btraining/i, "fitness_center"],
];

function iconFor(title: string): string | null {
  for (const [re, icon] of ICON_RULES) if (re.test(title)) return icon;
  return null;
}

/** Sum of lesson estimates → a short "~4h" / "~40m" label; null when unknown. */
function formatMinutes(min: number): string | null {
  if (!min || min <= 0) return null;
  if (min < 60) return `~${min}m`;
  return `~${Math.round(min / 60)}h`;
}

/** Top-right status/archetype chip — one pill, status-aware. */
function HeadPill({ c, tone }: { c: CourseCard; tone: Tone }) {
  const base = "rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider";
  if (c.status === "generating")
    return <span className={`${base} bg-sky-100 text-sky-700`}>Generating</span>;
  if (c.status === "failed")
    return <span className={`${base} bg-coral-soft text-coral-dark`}>Failed</span>;
  if (c.status === "outline_review")
    return <span className={`${base} bg-ink text-white`}>Review</span>;
  if (c.archetype) return <span className={`${base} ${tone.pill}`}>{c.archetype}</span>;
  return null;
}

function Card({
  c,
  index,
  progress,
  onOpen,
  onRename,
  onDelete,
}: {
  c: CourseCard;
  index: number;
  progress?: Progress;
  onOpen: () => void;
  onRename: (title: string) => Promise<void>;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.title ?? c.topic);
  const [saving, setSaving] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const generating = c.status === "generating";
  const pct = progress?.pct ?? (generating ? 8 : c.status === "ready" ? 100 : 0);
  const done = c.completed_count === c.lesson_count && c.lesson_count > 0;
  const readyPct = c.lesson_count ? Math.round((c.completed_count / c.lesson_count) * 100) : 0;
  const displayTitle = c.title ?? c.topic;
  const tone = TONES[toneIndex(c.id)];
  const icon = iconFor(displayTitle);
  const monogram = displayTitle.trim().charAt(0).toUpperCase() || "?";
  const duration = formatMinutes(c.estimated_minutes);
  const metaLabel = `${c.lesson_count} chapter${c.lesson_count === 1 ? "" : "s"}${
    duration ? ` · ${duration}` : ""
  }`;

  useEffect(() => {
    setDraft(c.title ?? c.topic);
  }, [c.title, c.topic]);

  useEffect(() => {
    if (!menuOpen) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  async function commitRename() {
    const next = draft.trim();
    if (!next || next === (c.title ?? c.topic)) {
      setEditing(false);
      setDraft(c.title ?? c.topic);
      return;
    }
    setSaving(true);
    try {
      await onRename(next);
      setEditing(false);
    } catch {
      setDraft(c.title ?? c.topic);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article
      className="group animate-fade-up relative flex flex-col overflow-hidden rounded-3xl border border-ink/5 bg-white shadow-chip transition-transform duration-300 hover:-translate-y-1"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={
          generating ||
          editing ||
          (c.status !== "ready" && c.status !== "failed" && c.status !== "outline_review")
        }
        className="flex flex-1 flex-col p-5 text-left disabled:cursor-default"
      >
        <div className="mb-3 flex items-center gap-2">
          <span
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${tone.chip}`}
            aria-hidden="true"
          >
            {icon ? (
              <span className="material-symbols-outlined text-[22px]">{icon}</span>
            ) : (
              <span className="font-archivo text-lg font-semibold leading-none">{monogram}</span>
            )}
          </span>
          <HeadPill c={c} tone={tone} />
        </div>

        {editing ? (
          <input
            ref={inputRef}
            value={draft}
            disabled={saving}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void commitRename()}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") {
                e.preventDefault();
                void commitRename();
              }
              if (e.key === "Escape") {
                setDraft(c.title ?? c.topic);
                setEditing(false);
              }
            }}
            className="mt-1 w-full rounded-xl border border-ink/20 bg-white px-3 py-2 font-archivo text-base font-semibold leading-snug text-ink outline-none focus:ring-4 focus:ring-ink/5"
            aria-label="Course title"
          />
        ) : (
          <h3 className="mt-1 line-clamp-2 font-archivo text-[17px] font-semibold leading-snug tracking-[-0.01em]">
            {displayTitle}
          </h3>
        )}

        {!editing && c.tagline && !generating && (
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-ink-soft">
            {c.tagline}
          </p>
        )}

        <div className="mt-auto pt-3.5">
          {generating ? (
            <div>
              <div className="h-[7px] overflow-hidden rounded-full bg-ink/10">
                <div
                  className="h-full rounded-full bg-lime transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="mt-2 flex items-center gap-1.5 truncate text-xs font-medium text-ink-soft">
                <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-lime" />
                {progress?.detail ?? "Mapping your chapters…"}
              </p>
            </div>
          ) : c.status === "ready" ? (
            done ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-faint">{metaLabel}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-mint px-3 py-1.5 text-[11px] font-semibold text-lime-dark">
                  <span className="material-symbols-outlined text-[14px]">check_circle</span>
                  Done
                </span>
              </div>
            ) : (
              <div>
                <div className="mb-1.5 flex items-baseline justify-between gap-2">
                  <span className="text-xs font-medium text-ink-faint">{metaLabel}</span>
                  <span className="text-xs font-medium tabular-nums text-ink-soft">
                    {c.completed_count} / {c.lesson_count}
                  </span>
                </div>
                <div className="h-[7px] overflow-hidden rounded-full bg-ink/10">
                  <div className="h-full rounded-full bg-lime" style={{ width: `${readyPct}%` }} />
                </div>
              </div>
            )
          ) : c.status === "outline_review" ? (
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink">
              <span className="material-symbols-outlined text-[16px]">rate_review</span>
              Outline ready — review the chapters
            </p>
          ) : (
            <p className="flex items-start gap-1.5 text-xs font-medium text-ink-soft">
              <span className="material-symbols-outlined shrink-0 text-[15px] text-coral">error</span>
              <span className="line-clamp-2">{c.error ?? "Couldn’t design this roadmap."}</span>
            </p>
          )}
        </div>
      </button>

      <div ref={menuRef} className="absolute right-3 top-3 z-10">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((o) => !o);
          }}
          className={`grid h-11 w-11 place-items-center rounded-full border border-ink/5 bg-white text-ink-soft shadow-chip transition duration-200 hover:text-ink ${
            menuOpen ? "opacity-100" : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
          }`}
          title="Course settings"
          aria-label={`Course settings for ${c.title || c.topic}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
        >
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">settings</span>
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="absolute right-0 top-10 min-w-[160px] overflow-hidden rounded-2xl border border-ink/5 bg-white py-1 shadow-panel"
          >
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-ink transition hover:bg-sand"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                setDraft(c.title ?? c.topic);
                setEditing(true);
              }}
            >
              <span className="material-symbols-outlined text-[18px] text-ink-soft">edit</span>
              Rename
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-coral-dark transition hover:bg-coral-soft"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                onDelete();
              }}
            >
              <span className="material-symbols-outlined text-[18px]">delete</span>
              Delete
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
