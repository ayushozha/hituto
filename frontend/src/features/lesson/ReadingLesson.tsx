import { useState } from "react";

import type { ReadingDoc } from "../../api";

/**
 * Trusted renderer for the `reading` design (specs/design_agents step 4).
 *
 * The doc's `body_md` is the SOURCE's own prose (verbatim, chosen server-side); the
 * annotation layer (objectives, margin notes, checks, glossary) came from a validated
 * Pydantic tree. Everything renders as escaped React text — no HTML from any model
 * ever reaches the DOM, so this surface never touches the capsule gate.
 */

/** Minimal markdown-ish block renderer: headings, bullet lists, paragraphs — text only. */
function ProseBlocks({ text }: { text: string }) {
  const blocks = text.split(/\n\s*\n/).filter((b) => b.trim());
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
        const heading = /^(#{1,4})\s+(.*)$/.exec(lines[0] ?? "");
        if (heading && lines.length === 1) {
          return (
            <h3
              key={i}
              className="mt-6 font-archivo text-lg font-semibold tracking-[-0.01em] text-ink"
            >
              {heading[2]}
            </h3>
          );
        }
        if (lines.every((l) => /^[-*•]\s+/.test(l))) {
          return (
            <ul key={i} className="my-3 list-disc space-y-1.5 pl-5 text-[15px] leading-7 text-ink">
              {lines.map((l, j) => (
                <li key={j}>{l.replace(/^[-*•]\s+/, "")}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="my-3 text-[15px] leading-7 text-ink">
            {lines.join(" ")}
          </p>
        );
      })}
    </>
  );
}

function CheckCard({ question, answer }: { question: string; answer: string }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div className="mt-5 rounded-2xl bg-lime-soft p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-lime">
        Check yourself
      </p>
      <p className="mt-1.5 text-sm font-semibold text-ink">{question}</p>
      {revealed ? (
        <p className="mt-2 text-sm leading-6 text-ink-soft">{answer}</p>
      ) : (
        <button
          type="button"
          onClick={() => setRevealed(true)}
          className="mt-2.5 rounded-full bg-ink px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-ink/80"
        >
          Reveal answer
        </button>
      )}
    </div>
  );
}

export function ReadingLesson({ doc }: { doc: ReadingDoc }) {
  return (
    <article className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
        Reading companion
      </p>
      <h1 className="mt-2 font-archivo text-3xl font-semibold tracking-[-0.02em] text-ink">
        {doc.title}
      </h1>
      {doc.intent && <p className="mt-2 text-[15px] leading-7 text-ink-soft">{doc.intent}</p>}

      {doc.sections.map((section, i) => (
        <section key={section.id || i} className="mt-10" data-lesson-section={section.id}>
          <div className="flex items-baseline gap-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-lime-soft text-xs font-bold text-lime">
              {i + 1}
            </span>
            <h2 className="font-archivo text-xl font-semibold tracking-[-0.01em] text-ink">
              {section.title}
            </h2>
          </div>
          {section.objective && (
            <p className="mt-1.5 pl-10 text-[13px] font-medium text-ink-faint">
              {section.objective}
            </p>
          )}

          <div className="mt-4 rounded-3xl border border-line bg-white p-6 sm:p-8">
            <ProseBlocks text={section.body_md} />
          </div>

          {section.notes.length > 0 && (
            <div className="mt-4 space-y-2.5">
              {section.notes.map((note, j) => (
                <aside
                  key={j}
                  className="flex gap-3 rounded-2xl bg-sand px-4 py-3 text-sm leading-6 text-ink-soft"
                >
                  <span className="material-symbols-outlined mt-0.5 text-[18px] text-lime" aria-hidden>
                    lightbulb
                  </span>
                  <span>{note.text}</span>
                </aside>
              ))}
            </div>
          )}

          {section.check && (
            <CheckCard question={section.check.question} answer={section.check.answer} />
          )}
        </section>
      ))}

      {doc.glossary.length > 0 && (
        <section className="mt-12">
          <h2 className="font-archivo text-lg font-semibold text-ink">Glossary</h2>
          <dl className="mt-4 grid gap-3 sm:grid-cols-2">
            {doc.glossary.map((term, i) => (
              <div key={i} className="rounded-2xl border border-line bg-white p-4">
                <dt className="text-sm font-semibold text-ink">{term.term}</dt>
                <dd className="mt-1 text-[13px] leading-6 text-ink-soft">{term.definition}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </article>
  );
}
