import { useEffect, useState } from "react";

import { CourseDetail, Knobs, appendChapterToCourse } from "../../api";

type DesignMode = NonNullable<Knobs["design_mode"]>;

type AddChapterModalProps = {
  courseId: string;
  courseTitle: string;
  designMode: DesignMode;
  onClose: () => void;
  onAdded: (course: CourseDetail) => void;
};

const MODE_DETAILS: Record<
  DesignMode,
  { label: string; icon: string; blurb: string; iconPanel: string }
> = {
  auto: {
    label: "Auto",
    icon: "auto_awesome",
    blurb: "Hi Tuto will choose the clearest interactive format.",
    iconPanel: "bg-cream text-brand",
  },
  studio: {
    label: "Studio",
    icon: "view_in_ar",
    blurb: "An immersive lab with a focused stage and hands-on controls.",
    iconPanel: "bg-sky/10 text-sky",
  },
  page: {
    label: "Page",
    icon: "article",
    blurb: "A scrollable interactive lesson that starts directly with the content.",
    iconPanel: "bg-cream text-brand",
  },
  slide: {
    label: "Slides",
    icon: "view_carousel",
    blurb: "A focused sequence that moves through one learning idea at a time.",
    iconPanel: "bg-ink/5 text-ink-soft",
  },
  reading: {
    label: "Reading",
    icon: "menu_book",
    blurb: "The source's own prose with objectives, margin notes, and quick checks.",
    iconPanel: "bg-sand text-ink-soft",
  },
};

export function AddChapterModal({
  courseId,
  courseTitle,
  designMode,
  onClose,
  onAdded,
}: AddChapterModalProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mode = MODE_DETAILS[designMode];
  const canSubmit = title.trim().length > 0 && description.trim().length > 0;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      onAdded(
        await appendChapterToCourse(courseId, {
          title: title.trim(),
          description: description.trim(),
          archetype: "auto",
        }),
      );
    } catch (cause) {
      setError(String((cause as Error).message));
      setBusy(false);
    }
  }

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
        aria-labelledby="add-generated-chapter-title"
      >
        <header className="px-6 pt-6 sm:px-7 sm:pt-7">
          <div className="flex items-start justify-between gap-5">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Next chapter
              </span>
              <h2
                id="add-generated-chapter-title"
                className="mt-4 font-archivo text-[clamp(1.7rem,5vw,2.2rem)] font-semibold leading-none tracking-[-0.03em]"
              >
                What comes next?
              </h2>
              <p className="mt-2 max-w-md text-sm leading-snug text-ink-soft">
                Add another stop to “{courseTitle}.” It will inherit this course’s {mode.label} design.
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
          <div className="flex items-start gap-4 rounded-2xl border border-ink/5 bg-sand/50 p-4">
            <div className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${mode.iconPanel}`}>
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">
                {mode.icon}
              </span>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-faint">
                Inherited design
              </p>
              <p className="mt-0.5 font-archivo text-lg font-semibold tracking-[-0.01em]">{mode.label}</p>
              <p className="mt-1 text-xs leading-snug text-ink-soft">{mode.blurb}</p>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            <label className="block text-sm font-semibold text-ink">
              Chapter title
              <input
                autoFocus
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="e.g. Put the idea into practice"
                className="mt-1.5 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-medium shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
              />
            </label>

            <label className="block text-sm font-semibold text-ink">
              Learning description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe what the learner should understand, explore, or practice in this chapter."
                className="mt-1.5 h-32 w-full resize-none rounded-2xl border border-ink/10 bg-white p-4 text-sm font-medium leading-relaxed shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5"
              />
              <span className="mt-1.5 block text-xs leading-snug text-ink-soft">
                A clear learning goal gives the generation agent a stronger chapter brief.
              </span>
            </label>
          </div>

          {error && (
            <p className="mt-4 rounded-2xl bg-coral-soft p-3 text-sm font-semibold text-coral-dark" role="alert">
              {error}
            </p>
          )}

          <footer className="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="inline-flex min-h-12 items-center rounded-full px-5 text-sm font-medium text-ink-soft transition hover:text-ink disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy || !canSubmit}
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-40"
            >
              <span className="material-symbols-outlined text-[19px]">add</span>
              {busy ? "Building chapter…" : "Create chapter"}
            </button>
          </footer>
        </div>
      </section>
    </div>
  );
}
