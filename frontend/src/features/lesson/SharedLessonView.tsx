import { useEffect, useState } from "react";

import { SharedLesson, getSharedLesson, sharedLessonArtifactUrl } from "../../api";

type SharedLessonViewProps = {
  token: string;
};

/**
 * Read-only public view of a single shared lesson. No auth required — reachable
 * at #s/{token}. Renders just the artifact iframe with a light header and a CTA;
 * no tutor, refine, complete, roadmap, or version controls.
 */
export function SharedLessonView({ token }: SharedLessonViewProps) {
  const [lesson, setLesson] = useState<SharedLesson | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getSharedLesson(token)
      .then((l) => active && setLesson(l))
      .catch(() => active && setErr("This lesson isn't available — the link may have been revoked."));
    return () => {
      active = false;
    };
  }, [token]);

  if (err) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-bone p-6 text-center font-sans text-ink">
        <span className="material-symbols-outlined text-[48px] text-ink-faint">link_off</span>
        <p className="max-w-sm text-sm font-medium text-ink-soft">{err}</p>
        <a
          href="#"
          className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
        >
          Explore Hi Tuto
        </a>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-bone font-sans text-ink">
      <div className="flex flex-wrap items-center gap-3 border-b border-ink/5 bg-bone/85 px-4 py-3 backdrop-blur">
        <div className="min-w-0">
          <h2 className="truncate font-archivo text-lg font-semibold tracking-[-0.01em] text-ink">
            {lesson?.title ?? "Loading lesson…"}
          </h2>
          {lesson && (
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
              {lesson.archetype} chapter
              {lesson.course_title ? ` · ${lesson.course_title}` : ""}
            </p>
          )}
        </div>
        <a
          href="#"
          className="ml-auto inline-flex min-h-11 items-center gap-1.5 rounded-full bg-ink px-4 text-xs font-semibold text-white transition hover:bg-ink/80"
        >
          <span className="material-symbols-outlined text-[16px]">auto_awesome</span>
          Made with Hi Tuto — start your own
        </a>
      </div>
      <div className="relative min-h-0 flex-1 p-3">
        <div className="h-full overflow-hidden rounded-3xl border border-ink/5 bg-white shadow-chip">
          <iframe
            title={lesson?.title ?? "Shared lesson"}
            src={sharedLessonArtifactUrl(token)}
            sandbox="allow-scripts"
            className="h-full w-full bg-white"
          />
        </div>
      </div>
    </div>
  );
}
