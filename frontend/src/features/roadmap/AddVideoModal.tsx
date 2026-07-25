import { useEffect, useState } from "react";

import {
  CourseDetail,
  SourceOut,
  appendVideoToCourse,
  createVideoLinkSource,
  getSource,
} from "../../api";

type AddVideoModalProps = {
  courseId: string;
  courseTitle: string;
  onClose: () => void;
  onAdded: (course: CourseDetail) => void;
};

export function AddVideoModal({
  courseId,
  courseTitle,
  onClose,
  onAdded,
}: AddVideoModalProps) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [transcript, setTranscript] = useState("");
  const [source, setSource] = useState<SourceOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isYouTube = /(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/i.test(url);
  const canAnalyze =
    /^https?:\/\//i.test(url.trim()) && (!isYouTube || transcript.trim().length > 0);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  useEffect(() => {
    if (!source || source.status === "ready" || source.status === "failed") return;
    const timer = window.setInterval(async () => {
      try {
        setSource(await getSource(source.id));
      } catch {
        // Ingestion may briefly be between stages; keep the current status visible.
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [source?.id, source?.status]);

  async function analyze() {
    if (!canAnalyze) return;
    setBusy(true);
    setError(null);
    try {
      setSource(
        await createVideoLinkSource({
          url: url.trim(),
          ...(title.trim() ? { title: title.trim() } : {}),
          ...(transcript.trim() ? { transcript: transcript.trim() } : {}),
        }),
      );
    } catch (cause) {
      setError(String((cause as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function addToCourse() {
    if (!source || source.status !== "ready") return;
    setBusy(true);
    setError(null);
    try {
      onAdded(await appendVideoToCourse(courseId, source.id, description));
    } catch (cause) {
      setError(String((cause as Error).message));
      setBusy(false);
    }
  }

  function startOver() {
    setSource(null);
    setError(null);
  }

  const inputCls =
    "mt-1.5 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-medium shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5";

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 grid place-items-center bg-ink/60 p-4 backdrop-blur-sm"
      onClick={() => !busy && onClose()}
      role="presentation"
    >
      <section
        className="animate-pop-in max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-3xl border border-ink/5 bg-white shadow-panel"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-video-title"
      >
        <header className="px-6 pt-6 sm:px-7 sm:pt-7">
          <div className="flex items-start justify-between gap-5">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Next chapter
              </span>
              <h2
                id="add-video-title"
                className="mt-4 font-archivo text-[clamp(1.7rem,5vw,2.2rem)] font-semibold leading-none tracking-[-0.03em]"
              >
                Add a video chapter.
              </h2>
              <p className="mt-2 max-w-md text-sm leading-snug text-ink-soft">
                Extend “{courseTitle}” with another stop on the learning trail.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink/5 text-ink-soft transition hover:bg-ink/10 hover:text-ink disabled:opacity-50"
              aria-label="Close"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          </div>
        </header>

        <div className="p-6 sm:p-7 sm:pt-5">
          {!source ? (
            <div className="space-y-4">
              <div className="flex items-start gap-3 rounded-2xl border border-ink/5 bg-sand/50 p-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cream text-brand" aria-hidden="true">
                  <span className="material-symbols-outlined text-[20px]">link</span>
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">Link a public learning video</p>
                  <p className="mt-0.5 text-xs leading-snug text-ink-soft">
                    YouTube remains embedded. Direct media links can be transcribed automatically.
                  </p>
                </div>
              </div>

              <label className="block text-sm font-semibold text-ink">
                Video URL
                <input
                  autoFocus
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://youtube.com/watch?v=…"
                  className={inputCls}
                />
              </label>

              <label className="block text-sm font-semibold text-ink">
                Chapter title <span className="font-medium text-ink-faint">(optional)</span>
                <input
                  type="text"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="e.g. Gradient descent fundamentals"
                  className={inputCls}
                />
              </label>

              <label className="block text-sm font-semibold text-ink">
                Learning description <span className="font-medium text-ink-faint">(optional)</span>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="What should this chapter help the learner understand or practice?"
                  className={`${inputCls} h-20 resize-none leading-relaxed`}
                />
              </label>

              <label className="block text-sm font-semibold text-ink">
                Timed captions{" "}
                <span className="font-medium text-ink-faint">
                  {isYouTube ? "(required for YouTube)" : "(optional)"}
                </span>
                <textarea
                  value={transcript}
                  onChange={(event) => setTranscript(event.target.value)}
                  placeholder={"00:00 Welcome to the lesson\n00:18 The first idea begins…"}
                  className={`${inputCls} h-28 resize-none font-mono text-[11px] leading-relaxed`}
                />
                <span className="mt-1.5 block text-xs leading-snug text-ink-soft">
                  Paste copied timestamps, SRT, or WebVTT so checkpoints stay aligned with playback.
                </span>
              </label>
            </div>
          ) : source.status === "failed" ? (
            <div className="rounded-2xl bg-coral-soft p-5 text-coral-dark">
              <p className="font-archivo text-lg font-semibold tracking-[-0.01em]">This video could not be analyzed.</p>
              <p className="mt-1 text-sm font-medium">{source.error ?? "Try another public video link."}</p>
            </div>
          ) : source.status === "ready" ? (
            <div className="rounded-2xl border border-ink/5 bg-cream p-5">
              <div className="flex items-start gap-4">
                <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-brand text-white">
                  <span
                    className="material-symbols-outlined text-[24px]"
                    style={{ fontVariationSettings: '"FILL" 1' }}
                  >
                    check_circle
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-brand-dark/70">
                    Ready to add
                  </p>
                  <p className="mt-1 font-archivo text-xl font-semibold leading-tight tracking-[-0.01em] text-ink">
                    {source.title ?? source.filename}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold uppercase tracking-wider text-ink-soft">
                    <span className="rounded-full bg-white px-3 py-1.5 shadow-chip">
                      {formatDuration(source.duration_seconds)}
                    </span>
                    <span className="rounded-full bg-white px-3 py-1.5 shadow-chip">
                      {source.checkpoint_count} checkpoints
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl bg-ink p-6 text-center text-white shadow-panel">
              <div className="mx-auto mb-3 h-7 w-7 animate-spin-slow rounded-full border-[3px] border-brand border-t-transparent" />
              <p className="font-archivo text-lg font-semibold tracking-[-0.01em]">Shaping the next chapter…</p>
              <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">
                {source.status}
              </p>
              <p className="mx-auto mt-2 max-w-sm text-xs leading-snug text-white/60">
                We’re building the transcript, timeline, and learning checkpoints before adding it.
              </p>
            </div>
          )}

          {error && (
            <p className="mt-4 rounded-2xl bg-coral-soft p-3 text-sm font-semibold text-coral-dark" role="alert">
              {error}
            </p>
          )}

          <footer className="sticky bottom-0 z-10 -mx-6 -mb-7 mt-6 flex flex-wrap items-center justify-end gap-3 border-t border-ink/5 bg-white/95 px-6 pb-7 pt-3 backdrop-blur sm:-mx-7 sm:px-7">
            {source && (source.status === "ready" || source.status === "failed") && (
              <button
                type="button"
                onClick={startOver}
                disabled={busy}
                className="inline-flex min-h-12 items-center rounded-full px-5 text-sm font-medium text-ink-soft transition hover:text-ink disabled:opacity-50"
              >
                Use another video
              </button>
            )}
            {!source ? (
              <button
                type="button"
                onClick={analyze}
                disabled={busy || !canAnalyze}
                className="inline-flex min-h-12 items-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-40"
              >
                <span className="material-symbols-outlined text-[19px]">auto_awesome</span>
                {busy ? "Starting…" : "Prepare chapter"}
              </button>
            ) : source.status === "ready" ? (
              <button
                type="button"
                onClick={addToCourse}
                disabled={busy}
                className="inline-flex min-h-12 items-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[19px]">add</span>
                {busy ? "Adding chapter…" : "Add chapter"}
              </button>
            ) : null}
          </footer>
        </div>
      </section>
    </div>
  );
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds < 1) return "Video";
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${minutes}:${String(secs).padStart(2, "0")}`;
}
