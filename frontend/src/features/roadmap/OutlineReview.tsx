import { useEffect, useMemo, useRef, useState } from "react";

import {
  CourseCard,
  OutlineDoc,
  OutlineOut,
  getOutline,
  reviewOutline,
  subscribeProgress,
} from "../../api";

type OutlineReviewProps = {
  course: CourseCard;
  /** Called after approve succeeds — parent refetches the course (lessons now exist). */
  onApproved: () => void;
};

/**
 * Chapter-outline HITL editor (course-authoring-flow §3).
 *
 * Three teacher moves, mirrored 1:1 on the review API:
 *  - inline-edit chapter titles/descriptions → Save edits (verbatim, no LLM)
 *  - feedback → Request revision (bounded LLM loop, SSE refresh)
 *  - Approve → lessons are created and generation starts
 */
export function OutlineReview({ course, onApproved }: OutlineReviewProps) {
  const [data, setData] = useState<OutlineOut | null>(null);
  const [doc, setDoc] = useState<OutlineDoc | null>(null); // local editable copy
  const [dirty, setDirty] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState<"save" | "revise" | "approve" | null>(null);
  const [revising, setRevising] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revisingRef = useRef(false);

  async function load() {
    try {
      const out = await getOutline(course.id);
      setData(out);
      setDoc(out.outline ? structuredClone(out.outline) : null);
      setDirty(false);
      setError(null);
    } catch {
      setError("Failed to load the outline.");
    }
  }

  useEffect(() => {
    load();
  }, [course.id]);

  // A requested revision lands over SSE; refetch when it completes (or fails).
  useEffect(() => {
    const unsub = subscribeProgress(course.id, (p) => {
      if (p.stage === "outline_revised") {
        revisingRef.current = false;
        setRevising(false);
        load();
      } else if (p.stage === "outline" && revisingRef.current && p.detail.startsWith("Revision failed")) {
        revisingRef.current = false;
        setRevising(false);
        setError(p.detail);
      }
    });
    return () => unsub();
  }, [course.id]);

  const revisionsLeft = useMemo(() => {
    if (!data || !doc) return 0;
    return Math.max(0, data.max_revisions - doc.feedback_log.length);
  }, [data, doc]);

  function editChapter(idx: number, patch: { title?: string; description?: string }) {
    if (!doc) return;
    const next = structuredClone(doc);
    Object.assign(next.chapters[idx], patch);
    setDoc(next);
    setDirty(true);
  }

  async function act(kind: "save" | "revise" | "approve") {
    if (!doc) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "save") {
        const out = await reviewOutline(course.id, { action: "edit", outline: doc });
        setData(out);
        setDoc(out.outline ? structuredClone(out.outline) : null);
        setDirty(false);
      } else if (kind === "revise") {
        revisingRef.current = true;
        setRevising(true);
        await reviewOutline(course.id, { action: "revise", feedback: feedback.trim() });
        setFeedback("");
      } else {
        await reviewOutline(course.id, { action: "approve" });
        onApproved();
      }
    } catch (e) {
      revisingRef.current = false;
      setRevising(false);
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  }

  if (!doc) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
        {error ? (
          <div className="rounded-2xl bg-coral-soft p-4 text-sm font-semibold text-coral-dark">
            {error}
          </div>
        ) : (
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-2xl border border-ink/5 bg-sand/70" />
            ))}
          </div>
        )}
      </div>
    );
  }

  const inputCls =
    "w-full rounded-xl border-0 bg-transparent px-2 py-1 font-archivo text-lg font-semibold tracking-[-0.01em] outline-none transition focus:bg-sand focus:ring-4 focus:ring-ink/5";
  const textareaCls =
    "mt-1 w-full resize-none rounded-xl border-0 bg-transparent px-2 py-1 text-[13px] leading-relaxed text-ink-soft outline-none transition focus:bg-sand focus:ring-4 focus:ring-ink/5";

  return (
    <main className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
      <div className="animate-fade-up mb-8 rounded-3xl border border-ink/5 bg-white p-6 shadow-chip sm:p-7">
        <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
          <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
          Review the outline
        </span>
        <h2 className="mt-5 text-balance font-archivo text-[clamp(1.75rem,4vw,2.35rem)] font-semibold leading-[1.04] tracking-[-0.03em]">
          Shape the chapters before we <span className="text-brand">build</span>
        </h2>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink-soft">
          Rename chapters and rewrite descriptions directly, or describe what to change and let the
          planner revise. Lessons are only generated after you approve.
        </p>
        <p className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
          Revision {doc.revision} · {revisionsLeft} AI {revisionsLeft === 1 ? "revision" : "revisions"} left
        </p>
      </div>

      {error && (
        <div className="mb-6 rounded-2xl bg-coral-soft p-4 text-sm font-semibold text-coral-dark">
          {error}
        </div>
      )}

      <div className={`space-y-4 ${revising ? "pointer-events-none opacity-50" : ""}`}>
        {doc.chapters.map((ch, i) => (
          <div key={ch.id} className="rounded-2xl border border-ink/5 bg-white p-5 shadow-chip">
            <div className="flex items-start gap-3">
              <span className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink font-archivo text-sm font-semibold text-white">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <input
                  value={ch.title}
                  onChange={(e) => editChapter(i, { title: e.target.value })}
                  className={inputCls}
                  aria-label={`Chapter ${i + 1} title`}
                />
                <textarea
                  value={ch.description}
                  onChange={(e) => editChapter(i, { description: e.target.value })}
                  rows={2}
                  placeholder="What this chapter covers…"
                  className={textareaCls}
                  aria-label={`Chapter ${i + 1} description`}
                />
                {ch.lessons.length > 1 && (
                  <ul className="mt-2 space-y-1">
                    {ch.lessons.map((les, j) => (
                      <li key={j} className="flex items-center gap-2 text-xs font-medium text-ink-soft">
                        <span className="material-symbols-outlined text-[14px]">subdirectory_arrow_right</span>
                        <span className="truncate">{les.title}</span>
                        <span className="rounded-full bg-sand px-2 py-0.5 text-[10px] font-semibold uppercase">
                          {les.archetype}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 rounded-3xl bg-ink p-5 text-white shadow-panel sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/50">
          Ask the planner to revise
        </p>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          rows={2}
          disabled={revising || revisionsLeft === 0}
          placeholder={
            revisionsLeft === 0
              ? "Revision limit reached — edit the chapters directly, then approve."
              : "e.g. Split chapter 2 into basics and applications; make the last chapter a project."
          }
          className="mt-3 w-full resize-none rounded-2xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm font-medium text-white outline-none transition placeholder:text-white/40 focus:border-white/25 focus:ring-4 focus:ring-white/10"
        />
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => act("revise")}
            disabled={!feedback.trim() || revising || busy !== null || revisionsLeft === 0}
            className="inline-flex min-h-11 items-center rounded-full bg-white/10 px-4 text-xs font-semibold text-white transition hover:bg-white/20 disabled:opacity-40"
          >
            {revising ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-brand border-t-transparent" />
                Revising…
              </span>
            ) : (
              "Request revision"
            )}
          </button>
          <div className="flex items-center gap-3">
            {dirty && (
              <button
                type="button"
                onClick={() => act("save")}
                disabled={busy !== null || revising}
                className="inline-flex min-h-11 items-center rounded-full bg-white/10 px-4 text-xs font-semibold text-white transition hover:bg-white/20 disabled:opacity-40"
              >
                {busy === "save" ? "Saving…" : "Save edits"}
              </button>
            )}
            <button
              type="button"
              onClick={() => act("approve")}
              disabled={busy !== null || revising || dirty}
              title={dirty ? "Save your edits first" : undefined}
              className="inline-flex min-h-11 items-center rounded-full bg-white px-5 text-xs font-semibold text-ink transition hover:bg-white/90 disabled:opacity-40"
            >
              {busy === "approve" ? "Approving…" : "Approve & build course"}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
