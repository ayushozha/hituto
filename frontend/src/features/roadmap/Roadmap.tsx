import { Fragment, useEffect, useMemo, useState } from "react";

import {
  CourseCard,
  CourseDetail,
  Lesson,
  Progress,
  generateLesson,
  getCourse,
  subscribeProgress,
} from "../../api";
import { AddChapterModal } from "./AddChapterModal";
import { AddVideoModal } from "./AddVideoModal";
import { OutlineReview } from "./OutlineReview";

type RoadmapProps = {
  course: CourseCard;
  onBack: () => void;
  onLaunchLesson: (lesson: Lesson) => void;
};

export function Roadmap({ course, onBack, onLaunchLesson }: RoadmapProps) {
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [progressLog, setProgressLog] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addChapterOpen, setAddChapterOpen] = useState(false);

  async function fetchDetails() {
    try {
      const d = await getCourse(course.id);
      setDetail(d);
      setError(null);
    } catch {
      setError("Failed to load syllabus details.");
    }
  }

  useEffect(() => {
    fetchDetails();
  }, [course.id]);

  useEffect(() => {
    if (!detail) return;
    const generatingLesson = detail.lessons.find((l) => l.status === "generating");
    if (!generatingLesson) return;

    const unsub = subscribeProgress(course.id, (p) => {
      setProgressLog(p);
      if (p.pct >= 100) {
        fetchDetails();
        setProgressLog(null);
      }
    });
    return () => unsub();
  }, [detail?.lessons.map((l) => l.id + l.status).join(",")]);

  async function triggerGenerate(lessonId: string) {
    try {
      await generateLesson(course.id, lessonId);
      fetchDetails();
    } catch {
      setError("Failed to launch generator.");
    }
  }

  const lessonsWithLocks = useMemo(() => {
    if (!detail) return [];
    let unlockedPrevious = true;
    return detail.lessons.map((l) => {
      const isLocked = !unlockedPrevious;
      unlockedPrevious = l.completed;
      return { ...l, isLocked };
    });
  }, [detail]);

  // Chapter tabs (course-authoring-flow §4): group by the 3-level roadmap module fields.
  const modules = useMemo(() => {
    const seen = new Map<number, string>();
    for (const l of lessonsWithLocks) {
      if (l.module_ordinal !== null && l.module_title && !seen.has(l.module_ordinal)) {
        seen.set(l.module_ordinal, l.module_title);
      }
    }
    return [...seen.entries()].sort((a, b) => a[0] - b[0]).map(([ordinal, title]) => ({ ordinal, title }));
  }, [lessonsWithLocks]);
  const courseStatus = detail?.status ?? course.status;
  const isVideoCourse =
    detail?.source?.source_type === "video" || course.source?.source_type === "video";
  const designMode = detail?.design_mode ?? course.design_mode ?? "auto";
  const showTabs = modules.length >= 2 && !isVideoCourse;
  const [activeModule, setActiveModule] = useState<number | null>(null);
  const defaultModule = useMemo(() => {
    const next = lessonsWithLocks.find((l) => !l.completed && !l.isLocked);
    return next?.module_ordinal ?? modules[0]?.ordinal ?? null;
  }, [lessonsWithLocks, modules]);
  const currentModule = activeModule ?? defaultModule;
  const visibleLessons = showTabs
    ? lessonsWithLocks.filter((l) => l.module_ordinal === currentModule)
    : lessonsWithLocks;

  const completedCount = lessonsWithLocks.filter((l) => l.completed).length;
  const total = lessonsWithLocks.length;
  const overallPct = total > 0 ? Math.round((completedCount / total) * 100) : 0;

  return (
    <div className="min-h-full bg-bone pb-24 font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <header className="sticky top-0 z-30 border-b border-ink/5 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={onBack}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-ink/5 bg-white text-ink shadow-chip transition hover:bg-sand"
            aria-label="Back to shelf"
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">arrow_back</span>
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-archivo text-lg font-semibold leading-tight tracking-[-0.01em]">
              {course.title ?? course.topic}
            </h1>
            <p className="mt-0.5 text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
              {course.archetype ? `${course.archetype} path` : "Your learning path"}
            </p>
          </div>
          {course.source && !isVideoCourse && (
            <span
              className="hidden shrink-0 items-center gap-1.5 rounded-full border border-ink/5 bg-white px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-soft shadow-chip sm:inline-flex"
              title={course.source.title ?? course.source.filename}
            >
              <span className="material-symbols-outlined text-[14px]">description</span>
              {course.source.source_type ?? "source"}
            </span>
          )}
        </div>
      </header>

      {courseStatus === "outline_review" ? (
        <OutlineReview course={course} onApproved={fetchDetails} />
      ) : (
        <main className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
          {error && (
            <div className="mb-6 rounded-2xl bg-coral-soft p-4 text-sm font-semibold text-coral-dark">
              {error}
            </div>
          )}

          {!detail ? (
            <div className="space-y-6">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-28 animate-pulse rounded-2xl border border-ink/5 bg-sand/70" />
              ))}
            </div>
          ) : (
            <>
              <section className="animate-fade-up mb-10 rounded-3xl bg-ink p-6 text-white shadow-panel sm:p-7">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-semibold text-white/70">
                      <span className="h-1.5 w-1.5 rounded-full bg-lime" aria-hidden="true" />
                      Your progress
                    </span>
                    <p className="font-archivo text-[clamp(2rem,5vw,2.75rem)] font-semibold leading-none tracking-[-0.03em]">
                      {completedCount}
                      <span className="text-lime"> / {total}</span>
                    </p>
                    <p className="mt-2 text-sm font-medium text-white/60">
                      {completedCount === 1 ? "chapter done" : "chapters done"}
                      {overallPct === 100 ? " — nice work!" : ""}
                    </p>
                  </div>
                  <div className="grid h-16 w-16 place-items-center rounded-2xl bg-lime font-archivo text-xl font-semibold text-lime-dark">
                    {overallPct}%
                  </div>
                </div>
                <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/15">
                  <div
                    className="h-full rounded-full bg-lime transition-all duration-700"
                    style={{ width: `${overallPct}%` }}
                  />
                </div>
              </section>

              {showTabs && (
                <div className="mb-8 flex flex-wrap gap-2" role="tablist" aria-label="Chapters">
                  {modules.map((m) => {
                    const active = m.ordinal === currentModule;
                    const chapterLessons = lessonsWithLocks.filter((l) => l.module_ordinal === m.ordinal);
                    const done = chapterLessons.every((l) => l.completed) && chapterLessons.length > 0;
                    return (
                      <button
                        key={m.ordinal}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        onClick={() => setActiveModule(m.ordinal)}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-xs font-semibold transition ${
                          active
                            ? "border-ink bg-ink text-white"
                            : "border-ink/5 bg-white text-ink-soft shadow-chip hover:text-ink"
                        }`}
                      >
                        {done && (
                          <span
                            className="material-symbols-outlined text-[14px] text-lime"
                            style={{ fontVariationSettings: '"FILL" 1' }}
                          >
                            check_circle
                          </span>
                        )}
                        {m.title}
                      </button>
                    );
                  })}
                </div>
              )}

              <div className="relative">
                <div className="relative z-10 space-y-8">
                  {visibleLessons.map((l, index) => {
                    const isGenerating =
                      l.status === "generating" || l.status === "awaiting_review";
                    const isReady = l.status === "ready";
                    const isFailed = l.status === "failed";
                    const isPending = l.status === "pending";
                    const videoCanLaunch = isVideoCourse;

                    const prevL = index > 0 ? visibleLessons[index - 1] : null;
                    const showChapter =
                      !showTabs && !!l.module_title && (!prevL || prevL.module_title !== l.module_title);

                    let nodeCls = "border border-ink/10 bg-white text-ink";
                    if (l.completed) nodeCls = "bg-mint text-lime";
                    else if (isReady) nodeCls = "cursor-pointer bg-brand text-white hover:brightness-110";
                    else if (isGenerating && isVideoCourse) nodeCls = "cursor-pointer bg-brand text-white hover:brightness-110";
                    else if (isGenerating) nodeCls = "cursor-pointer bg-sky-100 text-sky-700 hover:brightness-95";
                    else if (isFailed) nodeCls = "bg-coral-soft text-coral-dark";
                    else if (isPending && !l.isLocked) nodeCls = "cursor-pointer border border-ink/10 bg-white text-ink hover:border-ink/40";
                    else if (l.isLocked) nodeCls = "bg-sand text-ink-faint";

                    return (
                      <Fragment key={l.id}>
                        {showChapter && (
                          <div className="relative z-10 -mb-2 pl-[4.25rem]">
                            <span className="inline-block rounded-full bg-ink px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white">
                              {l.module_title}
                            </span>
                          </div>
                        )}
                        <div
                          className={`group relative flex items-start gap-5 ${l.isLocked ? "opacity-55" : ""}`}
                          style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
                        >
                          <div className="relative flex flex-col items-center">
                            <button
                              type="button"
                              disabled={l.isLocked || (isFailed && !isVideoCourse)}
                              className={`grid h-14 w-14 place-items-center rounded-[18px] font-archivo text-lg font-semibold transition duration-200 select-none ${nodeCls}`}
                              onClick={() => {
                                if (l.isLocked) return;
                                if (videoCanLaunch) {
                                  if (isPending) void triggerGenerate(l.id);
                                  onLaunchLesson(l);
                                  return;
                                }
                                if (isReady) onLaunchLesson(l);
                                // fast_gen §4: a generating lesson opens into the live
                                // theater; a pending one starts generating and opens too.
                                if (isGenerating) onLaunchLesson(l);
                                if (isPending) {
                                  triggerGenerate(l.id);
                                  onLaunchLesson(l);
                                }
                              }}
                              aria-label={
                                l.completed
                                  ? `Chapter ${l.ordinal + 1} complete`
                                  : l.isLocked
                                    ? `Chapter ${l.ordinal + 1} locked`
                                    : `Chapter ${l.ordinal + 1}`
                              }
                            >
                              {l.completed ? (
                                <span
                                  className="material-symbols-outlined text-[26px]"
                                  style={{ fontVariationSettings: '"FILL" 1' }}
                                >
                                  check
                                </span>
                              ) : l.isLocked ? (
                                <span className="material-symbols-outlined text-[20px]">lock</span>
                              ) : isGenerating ? (
                                <div className="h-5 w-5 animate-spin-slow rounded-full border-[3px] border-ink border-t-transparent" />
                              ) : isFailed ? (
                                <span className="material-symbols-outlined text-[22px]">priority_high</span>
                              ) : (
                                <span>{l.ordinal + 1}</span>
                              )}
                            </button>

                            {index < visibleLessons.length - 1 && (
                              <div
                                className={`absolute -bottom-8 top-14 left-1/2 -z-10 w-[3px] -translate-x-1/2 rounded-full ${
                                  l.completed ? "bg-lime" : "bg-sand"
                                }`}
                              />
                            )}
                          </div>

                          <div
                            className={`flex-1 rounded-2xl border p-5 transition duration-200 ${
                              l.isLocked
                                ? "border-ink/5 bg-sand/50"
                                : "border-ink/5 bg-white shadow-chip"
                            } ${!l.isLocked && isReady ? "group-hover:-translate-y-0.5" : ""}`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <h2 className="font-archivo text-lg font-semibold leading-snug tracking-[-0.01em]">
                                  {l.title}
                                </h2>
                                <p className="mt-1.5 line-clamp-3 text-[13px] leading-relaxed text-ink-soft">
                                  {l.objective}
                                </p>
                                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                                  <span className="inline-flex items-center gap-1 rounded-full bg-sand px-2.5 py-1">
                                    <span className="material-symbols-outlined text-[14px]">schedule</span>
                                    {l.estimated_duration}
                                  </span>
                                  <span className="inline-flex items-center gap-1 rounded-full bg-sand px-2.5 py-1">
                                    <span className="material-symbols-outlined text-[14px]">category</span>
                                    {l.archetype}
                                  </span>
                                </div>
                              </div>

                              <div className="shrink-0 pt-0.5">
                                {videoCanLaunch && !l.isLocked ? (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (isPending) void triggerGenerate(l.id);
                                      onLaunchLesson(l);
                                    }}
                                    className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white transition hover:bg-ink/80"
                                  >
                                    {isReady ? (l.completed ? "Review" : "Start") : "Watch now"}
                                  </button>
                                ) : isPending && !l.isLocked ? (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      triggerGenerate(l.id);
                                      onLaunchLesson(l);
                                    }}
                                    className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white transition hover:bg-ink/80"
                                  >
                                    Generate
                                  </button>
                                ) : isGenerating && !l.isLocked ? (
                                  <button
                                    type="button"
                                    onClick={() => onLaunchLesson(l)}
                                    className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white transition hover:bg-ink/80"
                                  >
                                    Watch live
                                  </button>
                                ) : isReady ? (
                                  <button
                                    type="button"
                                    onClick={() => onLaunchLesson(l)}
                                    className={`rounded-full px-4 py-2 text-xs font-semibold transition ${
                                      l.completed
                                        ? "bg-sand text-ink-soft hover:bg-ink/10 hover:text-ink"
                                        : "bg-ink text-white hover:bg-ink/80"
                                    }`}
                                  >
                                    {l.completed ? "Review" : "Start"}
                                  </button>
                                ) : isGenerating ? (
                                  <div className="rounded-full bg-sky-100 px-3 py-1.5 text-[11px] font-semibold uppercase text-sky-700">
                                    {progressLog?.pct ? `${progressLog.pct}%` : "Building"}
                                  </div>
                                ) : isFailed ? (
                                  <button
                                    type="button"
                                    onClick={() => triggerGenerate(l.id)}
                                    className="rounded-full bg-coral px-4 py-2 text-xs font-semibold text-white transition hover:brightness-110"
                                  >
                                    Retry
                                  </button>
                                ) : null}
                              </div>
                            </div>

                            {isFailed && l.error && (
                              <div className="mt-3 rounded-xl bg-coral-soft p-2.5 font-mono text-[11px] text-coral-dark">
                                {l.error}
                              </div>
                            )}
                          </div>
                        </div>
                      </Fragment>
                    );
                  })}
                  {detail && (
                    <div className="group relative flex items-center gap-5 pt-1">
                      <div className="relative flex shrink-0 flex-col items-center">
                        <div
                          className="absolute -top-8 left-1/2 h-8 w-[3px] -translate-x-1/2 rounded-full bg-sand"
                          aria-hidden="true"
                        />
                        <button
                          type="button"
                          onClick={() => setAddChapterOpen(true)}
                          className="grid h-14 w-14 place-items-center rounded-[18px] border border-dashed border-ink/20 bg-white text-ink-soft transition hover:border-ink/40 hover:text-ink"
                          aria-label="Add another chapter"
                        >
                          <span className="material-symbols-outlined text-[26px]" aria-hidden="true">add</span>
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => setAddChapterOpen(true)}
                        className="min-h-20 flex-1 rounded-2xl border border-dashed border-ink/15 bg-white/60 px-5 py-4 text-left transition group-hover:border-ink/30 group-hover:bg-white"
                      >
                        <span className="block font-archivo text-base font-semibold tracking-[-0.01em] text-ink">
                          Add another chapter
                        </span>
                        <span className="mt-1 block text-xs leading-snug text-ink-soft">
                          {isVideoCourse
                            ? "Continue with a video link and learning description."
                            : `Create another ${designMode === "slide" ? "Slides" : designMode === "auto" ? "Hi Tuto" : designMode[0].toUpperCase() + designMode.slice(1)} lesson from a focused learning brief.`}
                        </span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      )}
      {addChapterOpen &&
        (isVideoCourse ? (
          <AddVideoModal
            courseId={course.id}
            courseTitle={course.title ?? course.topic}
            onClose={() => setAddChapterOpen(false)}
            onAdded={(updated) => {
              setDetail(updated);
              setActiveModule(null);
              setAddChapterOpen(false);
            }}
          />
        ) : (
          <AddChapterModal
            courseId={course.id}
            courseTitle={course.title ?? course.topic}
            designMode={designMode}
            onClose={() => setAddChapterOpen(false)}
            onAdded={(updated) => {
              setDetail(updated);
              setActiveModule(null);
              setAddChapterOpen(false);
            }}
          />
        ))}
    </div>
  );
}
