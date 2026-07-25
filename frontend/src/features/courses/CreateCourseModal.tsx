import { useEffect, useState } from "react";

import {
  BillingUsage,
  CourseCard,
  CourseDetail,
  Knobs,
  SourceOut,
  SourceOutline,
  createCourse,
  createCourseFromSource,
  createVideoLinkSource,
  fetchBillingUsage,
  getProfile,
  getSource,
  getSourceOutline,
  uploadSource,
} from "../../api";

type CreateCourseModalProps = {
  onClose: () => void;
  onCreated: (course: CourseCard) => void;
  onCreatedFromSource: (course: CourseDetail) => void;
};

const DESIGN_MODE_OPTS = [
  { id: "auto" as const, label: "Auto", blurb: "Agent chooses" },
  { id: "studio" as const, label: "Studio", blurb: "1 chapter · live lab" },
  { id: "page" as const, label: "Page", blurb: "Scroll mini-app" },
  { id: "slide" as const, label: "Slides", blurb: "One idea each" },
] as const;

/** Tiny layout glyphs — clearer than Material icons (esp. Slides). */
function DesignModeGlyph({
  id,
  active,
}: {
  id: NonNullable<Knobs["design_mode"]>;
  active: boolean;
}) {
  const ink = active ? "#18181B" : "#A1A1AA";
  const fill = "#FFFFFF";
  const accent = active ? "#16A34A" : "#E4E4E7";

  if (id === "auto") {
    return (
      <svg viewBox="0 0 48 32" className="h-8 w-12" aria-hidden>
        <rect x="1" y="1" width="46" height="30" rx="6" fill={fill} stroke={ink} strokeWidth="1.5" />
        <circle cx="16" cy="16" r="5" fill="none" stroke={ink} strokeWidth="1.5" />
        <path d="M16 9v2.5M16 20.5V23M9 16h2.5M20.5 16H23" stroke={ink} strokeWidth="1.4" strokeLinecap="round" />
        <path d="M28 11h12M28 16h9M28 21h11" stroke={ink} strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
      </svg>
    );
  }

  if (id === "studio") {
    return (
      <svg viewBox="0 0 48 32" className="h-8 w-12" aria-hidden>
        <rect x="1" y="1" width="46" height="30" rx="5" fill={fill} stroke={ink} strokeWidth="1.5" />
        <rect x="4" y="5" width="8" height="22" rx="2" fill={accent} stroke={ink} strokeWidth="1" />
        <rect x="14" y="5" width="20" height="16" rx="2" fill="#fff" stroke={ink} strokeWidth="1.2" />
        <circle cx="24" cy="13" r="4" fill="none" stroke={ink} strokeWidth="1.2" />
        <rect x="14" y="23" width="9" height="4" rx="1" fill={accent} />
        <rect x="25" y="23" width="9" height="4" rx="1" fill={accent} />
        <rect x="36" y="5" width="8" height="22" rx="2" fill="#fff" stroke={ink} strokeWidth="1" />
        <path d="M38 10h4M38 14h3" stroke={ink} strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    );
  }

  if (id === "page") {
    return (
      <svg viewBox="0 0 48 32" className="h-8 w-12" aria-hidden>
        <rect x="8" y="1" width="32" height="30" rx="4" fill={fill} stroke={ink} strokeWidth="1.5" />
        <rect x="12" y="5" width="24" height="8" rx="2" fill="#fff" stroke={ink} strokeWidth="1" />
        <path d="M12 17h24M12 21h18M12 25h20" stroke={ink} strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    );
  }

  // slide — stacked deck, not the broken Material "slides" glyph
  return (
    <svg viewBox="0 0 48 32" className="h-8 w-12" aria-hidden>
      <rect x="10" y="3" width="28" height="18" rx="3" fill={accent} stroke={ink} strokeWidth="1" opacity="0.85" />
      <rect x="7" y="6" width="28" height="18" rx="3" fill={fill} stroke={ink} strokeWidth="1.2" />
      <rect x="4" y="9" width="28" height="18" rx="3" fill="#fff" stroke={ink} strokeWidth="1.5" />
      <path d="M10 15h16M10 19h11" stroke={ink} strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="16" cy="24" r="1.4" fill={ink} />
      <circle cx="20" cy="24" r="1.4" fill={ink} opacity="0.35" />
      <circle cx="24" cy="24" r="1.4" fill={ink} opacity="0.35" />
    </svg>
  );
}

function DesignModePicker({
  value,
  onChange,
}: {
  value: NonNullable<Knobs["design_mode"]>;
  onChange: (v: NonNullable<Knobs["design_mode"]>) => void;
}) {
  return (
    <div className="mt-5">
      <p className="text-sm font-semibold text-ink">Design mode</p>
      <p className="mt-0.5 text-[12px] font-medium leading-snug text-ink-soft">
        How the lesson is built — separate from lesson style. Studio is one immersive interactive lab.
        Auto picks it when the topic benefits from a live stage.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {DESIGN_MODE_OPTS.map((opt) => {
          const active = value === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => onChange(opt.id)}
              aria-pressed={active}
              className={`relative rounded-2xl border px-3 pb-3 pt-2.5 text-left transition ${
                active
                  ? "border-ink bg-sand text-ink"
                  : "border-ink/10 bg-white text-ink-soft hover:border-ink/30"
              }`}
            >
              <div
                className={`mb-2 flex h-11 items-center justify-center rounded-xl transition ${
                  active ? "bg-cream" : "bg-sand"
                }`}
              >
                <DesignModeGlyph id={opt.id} active={active} />
              </div>
              <div className={`text-sm font-semibold tracking-tight ${active ? "text-ink" : "text-ink-soft"}`}>
                {opt.label}
              </div>
              <div className="mt-0.5 text-[10px] font-medium leading-snug text-ink-faint">{opt.blurb}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function CreateCourseModal({ onClose, onCreated, onCreatedFromSource }: CreateCourseModalProps) {
  const [mode, setMode] = useState<"topic" | "document" | "video">("topic");
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState<Knobs["difficulty"]>("intermediate");
  const [archetype, setArchetype] = useState<NonNullable<Knobs["archetype"]>>("auto");
  const [designMode, setDesignMode] = useState<NonNullable<Knobs["design_mode"]>>("auto");
  const [reviewOutline, setReviewOutline] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [profileDefaults, setProfileDefaults] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Credit balance shown at the spend point; fail-silent — a billing outage
  // must never block the create flow (backend enforces when configured).
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
  const outOfCredits = usage !== null && usage.enforced && usage.course_credits.remaining <= 0;

  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [videoTitle, setVideoTitle] = useState("");
  const [videoTranscript, setVideoTranscript] = useState("");
  const [source, setSource] = useState<SourceOut | null>(null);
  const [outline, setOutline] = useState<SourceOutline | null>(null);
  const [lessonCount, setLessonCount] = useState(5);
  const [docMode, setDocMode] = useState("paper_walkthrough");

  const isVideo = mode === "video";
  const isYouTubeLink = /(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/i.test(
    videoUrl,
  );
  const canSubmitVideoLink =
    /^https?:\/\//i.test(videoUrl.trim()) &&
    (!isYouTubeLink || videoTranscript.trim().length > 0);

  function selectMode(nextMode: "topic" | "document" | "video") {
    if (nextMode === mode) return;
    setMode(nextMode);
    setFile(null);
    setVideoUrl("");
    setVideoTitle("");
    setVideoTranscript("");
    setSource(null);
    setOutline(null);
    setErr(null);
    setDocMode(nextMode === "video" ? "video_companion" : "paper_walkthrough");
    if (nextMode !== "topic") {
      setDesignMode("auto");
    }
  }

  useEffect(() => {
    if (!source || source.status === "ready" || source.status === "failed") return;
    const t = window.setInterval(async () => {
      try {
        const s = await getSource(source.id);
        setSource(s);
        if (s.status === "ready") setOutline(await getSourceOutline(s.id));
      } catch {
        /* keep polling */
      }
    }, 1200);
    return () => window.clearInterval(t);
  }, [source?.id, source?.status]);

  // Prefill defaults from the learner profile (specs/learner_profile). Best-effort; any
  // explicit choice the user makes afterwards always wins.
  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (cancelled || !p.onboarded_at) return;
        let applied = false;
        if (difficulty === "intermediate" && p.hints.difficulty !== "intermediate") {
          setDifficulty(p.hints.difficulty);
          applied = true;
        }
        if (designMode === "auto" && p.hints.design_mode) {
          setDesignMode(p.hints.design_mode);
          applied = true;
        }
        if (archetype === "auto" && p.hints.archetype) {
          setArchetype(p.hints.archetype);
          applied = true;
        }
        if (applied) setProfileDefaults(true);
      })
      .catch(() => {
        /* modal works unchanged without a profile */
      });
    return () => {
      cancelled = true;
    };
    // Mount-only prefill — the knobs are intentionally not reactive deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  async function submitTopic() {
    if (!topic.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      onCreated(
        await createCourse(topic.trim(), {
          difficulty,
          depth: designMode === "studio" ? "single-page" : "multi-lesson",
          archetype,
          design_mode: designMode,
          review_outline: reviewOutline,
        }),
      );
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
    }
  }

  async function uploadDoc() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      setSource(await uploadSource(file));
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function linkVideo() {
    if (!canSubmitVideoLink) return;
    setBusy(true);
    setErr(null);
    try {
      setSource(
        await createVideoLinkSource({
          url: videoUrl.trim(),
          ...(videoTitle.trim() ? { title: videoTitle.trim() } : {}),
          ...(videoTranscript.trim() ? { transcript: videoTranscript.trim() } : {}),
        }),
      );
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function createFromSource() {
    if (!source) return;
    setBusy(true);
    setErr(null);
    try {
      const course = await createCourseFromSource(source.id, {
        difficulty,
        lesson_count: isVideo ? 1 : lessonCount,
        mode: docMode,
        design_mode: "auto",
        review_outline: reviewOutline,
      });
      onCreatedFromSource(course);
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
    }
  }

  const selectCls =
    "mt-1.5 w-full rounded-2xl border border-ink/10 bg-white px-3 py-2.5 text-sm font-medium text-ink shadow-chip outline-none transition focus:border-ink/30 focus:ring-4 focus:ring-ink/5 disabled:opacity-50";

  const primaryBtn =
    "inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:cursor-not-allowed disabled:bg-sand disabled:text-ink-soft";

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-end justify-center bg-ink/45 p-0 backdrop-blur-sm sm:grid sm:place-items-center sm:p-4"
      onClick={onClose}
    >
      <div
        className="animate-pop-in flex h-[100dvh] w-full max-w-2xl flex-col overflow-hidden border border-ink/5 bg-white shadow-panel sm:h-auto sm:max-h-[calc(100vh-2rem)] sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-course-title"
      >
        <div className="flex shrink-0 items-start justify-between border-b border-ink/5 px-5 pb-4 pt-5 sm:px-7 sm:pb-6 sm:pt-7">
          <div className="pr-10">
            <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
              <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
              New course
            </span>
            <h2 id="create-course-title" className="mt-3 font-archivo text-[clamp(1.75rem,4vw,2.35rem)] font-semibold leading-[1.02] tracking-[-0.03em] text-ink sm:mt-4">
              What do you want to <span className="text-brand">master?</span>
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-ink/5 bg-white text-ink-soft shadow-chip transition hover:text-ink"
            aria-label="Close"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">
          <div className="mb-5 grid w-full grid-cols-3 rounded-full border border-ink/5 bg-white p-1 text-sm font-semibold shadow-chip sm:w-max">
            {(["topic", "document", "video"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => selectMode(m)}
                className={`min-h-11 rounded-full px-3 py-2 transition sm:px-4 ${
                  mode === m ? "bg-ink text-white" : "text-ink-soft hover:text-ink"
                }`}
              >
                {m === "topic" ? "From a topic" : m === "document" ? "From a document" : "From a video"}
              </button>
            ))}
          </div>

          {mode === "topic" ? (
            <>
              <textarea
                autoFocus
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. History of the solar system, quantum physics for beginners, how compilers work…"
                className="h-32 w-full resize-none rounded-2xl border border-ink/10 bg-white p-4 text-[15px] font-medium text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
              />
              {profileDefaults && (
                <p className="mt-2 flex items-center gap-1.5 text-[12px] font-medium text-ink-faint">
                  <span className="material-symbols-outlined text-[16px]" aria-hidden="true">tune</span>
                  Difficulty and layout prefilled from your learning style.
                </p>
              )}
            </>
          ) : (
            <div className="space-y-4">
              {!source ? (
                isVideo ? (
                  <div className="space-y-3 rounded-2xl border border-ink/5 bg-white p-4 shadow-chip">
                    <div className="flex items-start gap-3">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky/10 text-sky">
                        <span className="material-symbols-outlined text-[22px]">link</span>
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-ink">Link the video, store only the learning data</p>
                        <p className="mt-0.5 text-[11px] font-medium leading-snug text-ink-soft">
                          YouTube stays embedded. Direct MP4 or audio links are transcribed without an upload.
                        </p>
                      </div>
                    </div>
                    <label className="block text-[12px] font-semibold text-ink">
                      Video URL
                      <input
                        type="url"
                        value={videoUrl}
                        onChange={(e) => setVideoUrl(e.target.value)}
                        placeholder="https://youtube.com/watch?v=… or https://cdn.example.com/training.mp4"
                        className="mt-1.5 w-full rounded-2xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-medium text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
                      />
                    </label>
                    <label className="block text-[12px] font-semibold text-ink">
                      Training title <span className="font-medium text-ink-faint">(optional)</span>
                      <input
                        type="text"
                        value={videoTitle}
                        onChange={(e) => setVideoTitle(e.target.value)}
                        placeholder="e.g. Linear regression fundamentals"
                        className="mt-1.5 w-full rounded-2xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-medium text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
                      />
                    </label>
                    <label className="block text-[12px] font-semibold text-ink">
                      Timed captions{" "}
                      <span className="font-medium text-ink-faint">
                        {isYouTubeLink ? "(required for YouTube)" : "(optional)"}
                      </span>
                      <textarea
                        value={videoTranscript}
                        onChange={(e) => setVideoTranscript(e.target.value)}
                        placeholder={"00:00 Welcome to the lesson\n00:18 Linear regression fits a line…"}
                        className="mt-1.5 h-24 w-full resize-none rounded-2xl border border-ink/10 bg-white p-3 font-mono text-[11px] font-medium leading-relaxed text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
                      />
                      <span className="mt-1 block text-[10px] font-medium leading-snug text-ink-soft">
                        Paste copied YouTube timestamps, SRT, or WebVTT. For direct media, leave this empty to use speech-to-text.
                      </span>
                    </label>
                  </div>
                ) : (
                  <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-ink/10 bg-white p-8 text-ink shadow-chip transition hover:border-ink/30">
                    <span className="grid h-12 w-12 place-items-center rounded-2xl bg-cream text-brand">
                      <span className="material-symbols-outlined text-[26px]">upload_file</span>
                    </span>
                    <span className="text-center text-sm font-semibold">
                      {file ? file.name : "Choose a PDF, .txt, or .md file"}
                    </span>
                    <span className="text-center text-[11px] font-medium text-ink-soft">
                      Max 25 MB · the course stays grounded in this source
                    </span>
                    <input
                      type="file"
                      accept=".pdf,.txt,.md,.markdown"
                      className="hidden"
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                )
              ) : source.status === "failed" ? (
                <div className="rounded-2xl border border-coral/15 bg-coral-soft p-4 text-sm font-medium text-coral-dark">
                  Ingestion failed: {source.error ?? "unknown error"}
                </div>
              ) : source.status !== "ready" ? (
                <div className="rounded-2xl border border-ink/5 bg-white p-6 text-center shadow-chip">
                  <div className="mx-auto mb-3 h-6 w-6 animate-spin-slow rounded-full border-2 border-ink/10 border-t-brand" />
                  <p className="text-sm font-semibold text-ink">
                    {isVideo ? `Preparing “${source.filename}”…` : `Reading “${source.filename}”…`}
                  </p>
                  <p className="mt-2 inline-flex rounded-full bg-sky-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-sky-700">{source.status}</p>
                  {isVideo && source.status === "transcribing" && (
                    <p className="mx-auto mt-2 max-w-sm text-[11px] font-medium leading-snug text-ink-soft">
                      Building the timestamped transcript before the checkpoint agent reviews it.
                    </p>
                  )}
                  {isVideo && source.status === "checkpointing" && (
                    <p className="mx-auto mt-2 max-w-sm text-[11px] font-medium leading-snug text-ink-soft">
                      The transcript is safe. The agent is placing quizzes, visuals, and readings on its timeline.
                    </p>
                  )}
                </div>
              ) : outline ? (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-ink/5 bg-white p-4 shadow-chip">
                    <p className="text-sm font-semibold text-ink">{outline.title ?? source.filename}</p>
                    <p className="mt-0.5 text-[11px] font-medium text-ink-soft">
                      {isVideo
                        ? `${formatDuration(outline.duration_seconds)} · ${outline.checkpoint_count} timed checkpoints · ${outline.sections.length} transcript sections`
                        : `${outline.source_type ?? "document"} · ${outline.page_count ?? "?"} pages · ${outline.sections.length} sections`}
                    </p>
                    {outline.warnings.length > 0 && (
                      <ul className="mt-2 list-disc pl-4 text-[11px] text-coral-dark">
                        {outline.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    )}
                    {outline.sections.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {outline.sections.slice(0, 12).map((s, i) => (
                          <span key={i} className="rounded-full bg-ink/5 px-2.5 py-0.5 text-[10px] font-semibold text-ink-soft">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {isVideo && (
                    <div className="flex items-start gap-3 rounded-2xl border border-ink/5 bg-white p-4 shadow-chip">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky/10 text-sky">
                        <span className="material-symbols-outlined text-[22px]" aria-hidden="true">
                          timeline
                        </span>
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-ink">Playback-synced training</p>
                        <p className="mt-0.5 text-[11px] font-medium leading-snug text-ink-soft">
                          Quizzes, visual recaps, and readings unlock only after the matching explanation plays.
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}

          <button
            type="button"
            onClick={() => setAdvancedOpen((open) => !open)}
            className="mt-5 flex min-h-16 w-full items-center gap-3 rounded-2xl border border-ink/5 bg-sand px-4 py-3 text-left transition hover:border-ink/15"
            aria-expanded={advancedOpen}
            aria-controls="course-options"
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-brand shadow-chip">
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">tune</span>
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-ink">Course options</span>
              <span className="mt-0.5 block truncate text-[11px] font-medium capitalize text-ink-soft">
                {difficulty} · {mode === "topic" ? `${designMode} layout` : `${isVideo ? 1 : lessonCount} lesson${!isVideo && lessonCount !== 1 ? "s" : ""}`}
              </span>
            </span>
            <span className="material-symbols-outlined text-[20px] text-ink-faint" aria-hidden="true">
              {advancedOpen ? "expand_less" : "expand_more"}
            </span>
          </button>

          {advancedOpen ? (
            <div id="course-options" className="mt-3 rounded-3xl border border-ink/5 bg-bone p-4 sm:p-5">
              {mode === "topic" ? (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="text-sm font-semibold text-ink">
                      Difficulty
                      <select
                        value={difficulty}
                        onChange={(e) => setDifficulty(e.target.value as Knobs["difficulty"])}
                        className={selectCls}
                      >
                        <option value="beginner">Beginner</option>
                        <option value="intermediate">Intermediate</option>
                        <option value="advanced">Advanced</option>
                      </select>
                    </label>
                    <label className="text-sm font-semibold text-ink">
                      Lesson style
                      <select
                        value={archetype}
                        onChange={(e) => setArchetype(e.target.value as NonNullable<Knobs["archetype"]>)}
                        className={selectCls}
                      >
                        <option value="auto">Auto-select (recommended)</option>
                        <option value="explainer">Explainer · concept deep dive</option>
                        <option value="simulation">Simulation · parameter playground</option>
                        <option value="game">Game · interactive practice</option>
                        <option value="tool">Tool · calculator / helper</option>
                        <option value="narrative">Narrative · branching roleplay</option>
                      </select>
                    </label>
                  </div>
                  <DesignModePicker value={designMode} onChange={setDesignMode} />
                </>
              ) : (
                <div className="grid gap-4 sm:grid-cols-3">
                  <label className="text-sm font-semibold text-ink">
                    Difficulty
                    <select
                      value={difficulty}
                      onChange={(e) => setDifficulty(e.target.value as Knobs["difficulty"])}
                      className={selectCls}
                    >
                      <option value="beginner">Beginner</option>
                      <option value="intermediate">Intermediate</option>
                      <option value="advanced">Advanced</option>
                    </select>
                  </label>
                  <label className="text-sm font-semibold text-ink">
                    Lessons
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={isVideo ? 1 : lessonCount}
                      disabled={isVideo}
                      onChange={(e) => setLessonCount(Math.max(1, Math.min(5, Number(e.target.value) || 5)))}
                      className={selectCls}
                      title={
                        isVideo
                          ? "Synchronized video training is one continuous lesson"
                          : "One course credit covers up to five interactive lessons"
                      }
                    />
                  </label>
                  <label className="text-sm font-semibold text-ink">
                    Mode
                    <select value={docMode} onChange={(e) => setDocMode(e.target.value)} className={selectCls}>
                      {isVideo ? (
                        <>
                          <option value="video_companion">Video companion</option>
                          <option value="exam_prep">Certification review</option>
                          <option value="skills_lab">Skills lab</option>
                        </>
                      ) : (
                        <>
                          <option value="paper_walkthrough">Paper walkthrough</option>
                          <option value="textbook_chapter">Textbook chapter</option>
                          <option value="exam_prep">Exam prep</option>
                          <option value="code_lab">Code lab</option>
                          <option value="math_lab">Math lab</option>
                        </>
                      )}
                    </select>
                  </label>
                </div>
              )}

              <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-2xl bg-cream p-4">
                <input
                  type="checkbox"
                  checked={reviewOutline}
                  onChange={(e) => setReviewOutline(e.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-brand"
                />
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-ink">Review the outline first</span>
                  <span className="mt-0.5 block text-[12px] font-medium leading-snug text-ink-soft">
                    See the chapter plan before anything is built, then revise and approve it.
                  </span>
                </span>
              </label>
            </div>
          ) : null}

          {err && <p className="mt-3 text-sm font-medium text-coral-dark">{err}</p>}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-ink/5 bg-white/95 px-5 py-4 backdrop-blur sm:px-7">
            {usage !== null ? (
              <span
                className={`mr-auto min-w-0 text-[12px] font-medium leading-snug ${
                  usage.course_credits.remaining <= 0
                    ? "text-brand-dark"
                    : "text-ink-soft"
                }`}
              >
                {usage.course_credits.remaining > 0 ? (
                  <>
                    Uses 1 course credit · {usage.course_credits.remaining} of{" "}
                    {usage.course_credits.total} left · up to{" "}
                    {usage.max_lessons_per_course} lessons
                  </>
                ) : (
                  <>
                    No course credits left this month ·{" "}
                    <a href="#billing" className="font-semibold underline underline-offset-2">
                      See usage
                    </a>
                    {" · "}
                    <a href="#pricing" className="font-semibold underline underline-offset-2">
                      Upgrade
                    </a>
                  </>
                )}
              </span>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="hidden min-h-12 items-center rounded-full px-5 text-sm font-medium text-ink-soft transition hover:text-ink sm:inline-flex"
            >
              Cancel
            </button>
            {mode === "topic" ? (
              <button
                type="button"
                onClick={submitTopic}
                disabled={busy || !topic.trim() || outOfCredits}
                className={`${primaryBtn} flex-1 sm:flex-none`}
              >
                {busy ? "Designing outline…" : "Design syllabus"}
              </button>
            ) : !source ? (
              <button
                type="button"
                onClick={isVideo ? linkVideo : uploadDoc}
                disabled={busy || (isVideo ? !canSubmitVideoLink : !file)}
                className={`${primaryBtn} flex-1 sm:flex-none`}
              >
                {busy
                  ? isVideo
                    ? "Analyzing…"
                    : "Uploading…"
                  : isVideo
                    ? "Analyze link"
                    : "Upload & parse"}
              </button>
            ) : (
              <button
                type="button"
                onClick={createFromSource}
                disabled={busy || source.status !== "ready" || outOfCredits}
                className={`${primaryBtn} flex-1 sm:flex-none`}
              >
                {busy ? "Building course…" : source.status === "ready" ? "Create course" : "Parsing…"}
              </button>
            )}
        </div>
      </div>
    </div>
  );
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 1) return "Video";
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${minutes}:${String(secs).padStart(2, "0")}`;
}
