import { useId, useState } from "react";
import WidgetCard from "./WidgetCard";

export interface CodeInputComponentProps {
  title: string;
  language: string;
  initialCode: string;
  instructions: string;
  expectedOutput?: string | null;
  hint?: string | null;
}

// A practice editor for code exercises. We deliberately do NOT execute the
// learner's code: there is no in-browser sandbox for arbitrary languages and
// faking execution would be misleading. Instead the learner writes their
// solution and can reveal the expected output to self-check.
export default function CodeInputComponent({
  title,
  language,
  initialCode,
  instructions,
  expectedOutput,
  hint,
}: CodeInputComponentProps) {
  const editorId = useId();
  const [code, setCode] = useState(initialCode);
  const [showHint, setShowHint] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);

  return (
    <WidgetCard title={title} eyebrow={`${language} practice`} tone="code">
      <div className="mb-4 rounded-2xl border border-ink/5 bg-white p-3 text-xs font-medium leading-relaxed text-ink-soft">
        <strong className="font-semibold text-ink">Goal:</strong> {instructions}
      </div>

      <div className="relative mb-3 font-mono text-xs">
        <label className="sr-only" htmlFor={editorId}>
          {title} code editor
        </label>
        <textarea
          id={editorId}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          spellCheck={false}
          className="h-36 w-full resize-none rounded-2xl border border-ink/10 bg-ink p-4 font-mono leading-relaxed text-white outline-none transition focus:ring-2 focus:ring-brand/30"
        />
        <div className="absolute right-3 top-2 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-white/80">
          {language}
        </div>
      </div>

      <div className="mb-3 flex items-center gap-2">
        {hint && (
          <button
            type="button"
            onClick={() => setShowHint((prev) => !prev)}
            className="rounded-full border border-ink/10 bg-white px-4 py-2.5 text-xs font-semibold text-ink-soft transition hover:border-brand/30 hover:text-ink"
          >
            {showHint ? "Hide hint" : "Hint"}
          </button>
        )}
        {expectedOutput != null && expectedOutput !== "" && (
          <button
            type="button"
            onClick={() => setShowAnswer((prev) => !prev)}
            className="btn-press flex-1 rounded-full bg-brand py-2.5 text-sm font-semibold text-white shadow-chip hover:brightness-105"
          >
            {showAnswer ? "Hide expected output" : "Check against expected output"}
          </button>
        )}
      </div>

      {showHint && hint && (
        <div className="mb-3 rounded-2xl border border-ink/5 bg-white p-3 text-xs font-medium leading-relaxed text-ink">
          <strong className="font-semibold">Hint:</strong> {hint}
        </div>
      )}

      {showAnswer && expectedOutput != null && (
        <div className="rounded-2xl bg-mint p-3 font-mono text-[11px] font-medium leading-relaxed text-lime-dark">
          <div className="mb-1 font-sans text-[10px] font-semibold uppercase tracking-wider">
            Expected output
          </div>
          <pre className="whitespace-pre-wrap">{expectedOutput}</pre>
        </div>
      )}
    </WidgetCard>
  );
}
