import { useCallback, useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";
import { createPortal } from "react-dom";
import WidgetCard from "./WidgetCard";
import type { CodingLabFile, CodingLabRunPayload } from "../lib/codingLabAgUi";
import {
  buildHtmlPreviewDocument,
  checkExpectedStdout,
  normalizeLang,
  pickEntrypoint,
  runJavaScript,
  runPython,
} from "../lib/codingLabRunners";
import type { ToolResult } from "./renderToolWidget";

export type CodingLabComponentProps = {
  title: string;
  language: string;
  instructions: string;
  files?: CodingLabFile[];
  entrypoint?: string | null;
  expectedStdout?: string | null;
  hint?: string | null;
  coding_lab_session_id?: string;
  onFilesChange?: (files: CodingLabFile[], sessionId?: string) => void;
  onLabEvent?: (event: CodingLabRunPayload) => void;
  onResult?: (result: ToolResult) => void;
};

type Tab = "code" | "console" | "preview";

function normalizeFiles(files?: CodingLabFile[], language?: string): CodingLabFile[] {
  if (Array.isArray(files) && files.length > 0) {
    return files.map((f) => ({
      path: String(f.path || "main.txt"),
      content: String(f.content ?? ""),
    }));
  }
  const rawLanguage = (language || "").trim().toLowerCase();
  if (["typescript", "ts"].includes(rawLanguage)) {
    return [{ path: "main.ts", content: "// Write your solution\n\n" }];
  }
  const kind = normalizeLang(language || "javascript");
  if (kind === "python") return [{ path: "main.py", content: "# Write your solution\n\n" }];
  if (kind === "html") {
    return [
      {
        path: "index.html",
        content: "<!DOCTYPE html>\n<html>\n<body>\n  <h1>Hello</h1>\n</body>\n</html>\n",
      },
    ];
  }
  return [{ path: "main.js", content: "// Write your solution\nconsole.log('hello');\n" }];
}

export default function CodingLabComponent({
  title,
  language,
  instructions,
  files: initialFiles,
  entrypoint,
  expectedStdout,
  hint,
  coding_lab_session_id,
  onFilesChange,
  onLabEvent,
  onResult,
}: CodingLabComponentProps) {
  const [files, setFiles] = useState<CodingLabFile[]>(() => normalizeFiles(initialFiles, language));
  const [activePath, setActivePath] = useState(() => files[0]?.path || "main.js");
  const [tab, setTab] = useState<Tab>("code");
  const [stdout, setStdout] = useState("");
  const [stderr, setStderr] = useState("");
  const [running, setRunning] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [passed, setPassed] = useState<boolean | null>(null);
  const [previewHtml, setPreviewHtml] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const syncTimer = useRef<number | null>(null);
  const workspaceSeedRef = useRef("");
  const kind = normalizeLang(language);
  const canRun = kind === "javascript" || kind === "python" || kind === "html";
  const showPreviewTab = kind === "html";
  const visibleTabs = useMemo<Tab[]>(
    () => (showPreviewTab ? ["code", "console", "preview"] : ["code", "console"]),
    [showPreviewTab],
  );
  const runLabel = canRun ? (running ? "Running…" : "Run") : "Submit for review";
  const editorId = `lab-editor-${coding_lab_session_id || "x"}`;

  // Only reset the workspace when the tutor actually changes the exercise — not on
  // every parent re-render (new `files` array identity would wipe the Console tab).
  useEffect(() => {
    const next = normalizeFiles(initialFiles, language);
    const seed = JSON.stringify({
      session: coding_lab_session_id || "",
      language: language || "",
      instructions: instructions || "",
      files: next,
    });
    if (seed === workspaceSeedRef.current) return;
    workspaceSeedRef.current = seed;
    setFiles(next);
    setActivePath(next[0]?.path || "main.js");
    setPassed(null);
    setStdout("");
    setStderr("");
    setPreviewHtml("");
    setTab("code");
  }, [initialFiles, language, coding_lab_session_id, instructions]);

  useEffect(() => {
    if (!showPreviewTab && tab === "preview") setTab("code");
  }, [showPreviewTab, tab]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [fullscreen]);

  const activeFile = useMemo(
    () => files.find((f) => f.path === activePath) || files[0],
    [files, activePath],
  );

  const lineCount = Math.max((activeFile?.content || "").split("\n").length, 1);

  const queueSync = useCallback(
    (next: CodingLabFile[]) => {
      if (!onFilesChange) return;
      if (syncTimer.current) window.clearTimeout(syncTimer.current);
      syncTimer.current = window.setTimeout(() => {
        onFilesChange(next, coding_lab_session_id);
      }, 400);
    },
    [onFilesChange, coding_lab_session_id],
  );

  const updateActiveContent = (content: string) => {
    setFiles((prev) => {
      const next = prev.map((f) => (f.path === activePath ? { ...f, content } : f));
      queueSync(next);
      return next;
    });
  };

  /** Tab key must indent in the editor (critical for Python) — not move focus. */
  const handleEditorKeyDown = (e: SyntheticEvent<HTMLTextAreaElement> & { key: string; shiftKey: boolean }) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    e.stopPropagation();
    const el = e.currentTarget;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const value = el.value;
    const indent = "    ";
    if (e.shiftKey) {
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const removable = value.slice(lineStart).match(/^( {1,4}|\t)/)?.[0] ?? "";
      if (!removable) return;
      const next =
        value.slice(0, lineStart) + value.slice(lineStart + removable.length);
      updateActiveContent(next);
      requestAnimationFrame(() => {
        const pos = Math.max(lineStart, start - removable.length);
        el.selectionStart = el.selectionEnd = pos;
      });
      return;
    }
    const next = value.slice(0, start) + indent + value.slice(end);
    updateActiveContent(next);
    requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = start + indent.length;
    });
  };

  const emitEvent = (event: CodingLabRunPayload) => {
    onLabEvent?.(event);
    onResult?.({
      toolName: "show_coding_lab",
      agUiType: event.type,
      ...event,
    });
  };

  const run = async () => {
    setRunning(true);
    setPassed(null);
    setStderr("");
    try {
      if (!canRun) {
        const entry = pickEntrypoint(files, entrypoint, language);
        const code = entry?.content || "";
        const msg = `Submitted ${language} solution for tutor review.\n\n--- ${entry?.path || "main"} ---\n${code}`;
        setStdout(msg);
        setTab("console");
        emitEvent({
          type: "CODING_LAB_CHECK_RESULT",
          sessionId: coding_lab_session_id,
          ok: true,
          passed: null,
          stdout: msg,
          stderr: "",
          language,
          files,
        });
        return;
      }
      if (kind === "html") {
        const html = buildHtmlPreviewDocument(files);
        setPreviewHtml(html);
        setStdout("Preview updated.");
        setTab("preview");
        emitEvent({
          type: "CODING_LAB_RUN_RESULT",
          sessionId: coding_lab_session_id,
          ok: true,
          passed: null,
          stdout: "Preview updated.",
          stderr: "",
          language,
          files,
        });
        return;
      }
      const entry = pickEntrypoint(files, entrypoint, language);
      if (!entry) {
        setStderr("No entry file to run.");
        return;
      }
      if (kind === "python") {
        setTab("console");
        setStdout("Loading Python packages (first run may take a minute)…");
      }
      const result =
        kind === "python"
          ? await runPython(entry.content, { files })
          : await runJavaScript(entry.content);
      setStdout(result.stdout);
      setStderr(result.stderr);
      const match = checkExpectedStdout(result.stdout, expectedStdout);
      setPassed(match);
      setTab("console");
      emitEvent({
        type: match != null ? "CODING_LAB_CHECK_RESULT" : "CODING_LAB_RUN_RESULT",
        sessionId: coding_lab_session_id,
        ok: result.ok,
        passed: match,
        stdout: result.stdout,
        stderr: result.stderr,
        language,
        files,
      });
    } finally {
      setRunning(false);
    }
  };

  const openFullscreen = (e?: SyntheticEvent) => {
    e?.stopPropagation();
    e?.preventDefault();
    setFullscreen(true);
  };

  const closeFullscreen = (e?: SyntheticEvent) => {
    e?.stopPropagation();
    e?.preventDefault();
    setFullscreen(false);
  };

  const renderGoal = (className = "") => (
    <div
      className={`rounded-lg border border-zinc-800/80 bg-zinc-900/60 px-3 py-2 text-[11px] leading-relaxed text-zinc-300 ${className}`}
    >
      <strong className="font-semibold text-zinc-100">Goal:</strong> {instructions}
    </div>
  );

  const renderWorkspace = (mode: "card" | "fullscreen") => {
    const tall = mode === "fullscreen";
    const paneH = tall ? "min-h-0 flex-1" : "h-[260px]";
    // Row layout: file tree | editor (same as card; fullscreen just grows taller).
    const shellH = tall ? "flex min-h-0 flex-1" : "flex min-h-[260px]";

    return (
      <div
        className={`overflow-hidden rounded-xl border border-[#243049] bg-[#0b0f1a] text-[#e8eefc] shadow-inner ${
          tall ? "flex min-h-0 flex-1 flex-col" : ""
        }`}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-[#243049] bg-[#121826] px-2 py-1.5">
          {visibleTabs.map((t) => (
            <button
              key={t}
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setTab(t);
              }}
              className={
                tab === t
                  ? "rounded-md bg-[#0b0f1a] px-2.5 py-1 text-[11px] font-semibold capitalize text-white ring-1 ring-[#243049]"
                  : "rounded-md px-2.5 py-1 text-[11px] font-medium capitalize text-[#8b9bb8] hover:text-white"
              }
            >
              {t === "console" && kind === "python" ? "Console (Python)" : t}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            {hint ? (
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  setShowHint((v) => !v);
                }}
                className="rounded-md px-2 py-1 text-[11px] font-semibold text-[#8b9bb8] hover:text-white"
              >
                {showHint ? "Hide hint" : "Hint"}
              </button>
            ) : null}
            <button
              type="button"
              disabled={running}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                void run();
              }}
              className="rounded-md bg-[#3d8bfd] px-3 py-1 text-[11px] font-semibold text-white disabled:opacity-40"
              title={
                canRun
                  ? "Run"
                  : `${language}: no in-browser runner — submit for tutor review`
              }
            >
              {runLabel}
            </button>
          </div>
        </div>

        <div className={shellH}>
          <aside
            className={`w-[140px] shrink-0 border-r border-[#243049] bg-[#121826] ${
              tall ? "overflow-y-auto" : ""
            }`}
          >
            <div className="px-2.5 pb-1 pt-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[#8b9bb8]">
              Files
            </div>
            <div className="space-y-0.5 px-1.5 pb-2">
              {files.map((f) => (
                <button
                  key={f.path}
                  type="button"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    setActivePath(f.path);
                    setTab("code");
                  }}
                  className={
                    f.path === activePath
                      ? "block w-full truncate rounded-md bg-[#3d8bfd]/20 px-2 py-1.5 text-left font-mono text-[11px] text-[#dbeafe]"
                      : "block w-full truncate rounded-md px-2 py-1.5 text-left font-mono text-[11px] text-[#8b9bb8] hover:bg-[#1a2236] hover:text-white"
                  }
                >
                  {f.path}
                </button>
              ))}
            </div>
            <div className="border-t border-[#243049] px-2.5 py-2 text-[10px] text-[#8b9bb8]">
              {kind === "python" ? "Pyodide packages" : "Dependencies"}
            </div>
          </aside>

          <div className={`relative flex min-w-0 flex-1 flex-col ${tall ? "min-h-0" : ""}`}>
            {/* Keep panes mounted so Console output survives tab switches. */}
            <div className={`${paneH} ${tab === "code" ? "flex" : "hidden"}`}>
              <div
                aria-hidden
                className="w-9 shrink-0 select-none overflow-hidden border-r border-[#243049] bg-[#0e1422] py-3 pr-2 text-right font-mono text-[11px] leading-[1.55] text-[#5b6b88]"
              >
                {Array.from({ length: lineCount }, (_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <label className="sr-only" htmlFor={`${editorId}-${mode}`}>
                Code editor
              </label>
              <textarea
                id={`${editorId}-${mode}`}
                value={activeFile?.content ?? ""}
                onChange={(e) => updateActiveContent(e.target.value)}
                onKeyDown={handleEditorKeyDown}
                spellCheck={false}
                className="h-full w-full resize-none bg-transparent p-3 font-mono text-[12.5px] leading-[1.55] text-[#e8eefc] outline-none"
              />
            </div>

            <div
              className={`${paneH} space-y-2 overflow-auto p-3 font-mono text-[11px] ${
                tab === "console" ? "block" : "hidden"
              }`}
              role="tabpanel"
              aria-label="Console"
            >
              {passed === true ? (
                <div className="rounded-md bg-emerald-900/40 px-2 py-1 text-emerald-300">
                  Check passed
                </div>
              ) : null}
              {passed === false ? (
                <div className="rounded-md bg-rose-900/40 px-2 py-1 text-rose-300">
                  Output does not match expected
                </div>
              ) : null}
              {stdout ? (
                <pre className="whitespace-pre-wrap text-zinc-200">{stdout}</pre>
              ) : (
                <p className="text-[#8b9bb8]">
                  {kind === "python"
                    ? "No console output yet. Press Run — Python print() shows here."
                    : "No console output yet. Press Run."}
                </p>
              )}
              {stderr ? <pre className="whitespace-pre-wrap text-rose-300">{stderr}</pre> : null}
              {expectedStdout != null && expectedStdout !== "" ? (
                <div className="border-t border-[#243049] pt-2 text-[#8b9bb8]">
                  Expected: <span className="text-zinc-300">{expectedStdout}</span>
                </div>
              ) : null}
            </div>

            {showPreviewTab ? (
              <div className={`${paneH} bg-white ${tab === "preview" ? "block" : "hidden"}`}>
                {previewHtml ? (
                  <iframe
                    title="HTML preview"
                    sandbox="allow-scripts"
                    srcDoc={previewHtml}
                    className="h-full w-full border-0"
                  />
                ) : (
                  <p className="p-3 text-xs text-[#8b9bb8]">Press Run to refresh the preview.</p>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  };

  const renderExtras = () => (
    <>
      {!canRun ? (
        <p className="mt-2 text-[11px] text-ink-soft">
          {language}: no in-browser runner yet (Java, Go, C++, …). Write your solution and press{" "}
          <strong>Submit for review</strong> — the tutor will check it.
        </p>
      ) : null}

      {showHint && hint ? (
        <div className="mt-2 rounded-xl border border-ink/5 bg-white p-3 text-xs text-ink">
          <strong className="font-semibold">Hint:</strong> {hint}
        </div>
      ) : null}
    </>
  );

  return (
    <>
      <WidgetCard
        title={title}
        eyebrow={`${language} lab`}
        tone="code"
        className="!p-3"
        footer={
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={openFullscreen}
            className="w-full rounded-full bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-chip btn-press hover:brightness-105"
            aria-label="Open coding lab fullscreen"
          >
            Fullscreen
          </button>
        }
      >
        {renderGoal("mb-2")}
        {renderWorkspace("card")}
        {renderExtras()}
      </WidgetCard>

      {fullscreen &&
        createPortal(
          <div
            className="fixed inset-0 z-[9999] flex flex-col bg-[#0b0f1a]"
            role="dialog"
            aria-modal="true"
            aria-label={title || "Coding lab fullscreen"}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#243049] bg-[#121826] px-4 py-3 text-[#e8eefc] shadow-sm">
              <div className="min-w-0">
                <h3 className="truncate font-display text-base font-semibold text-white">
                  {title || "Coding Lab"}
                </h3>
                <p className="truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8b9bb8]">
                  {language} lab
                </p>
              </div>
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={closeFullscreen}
                className="shrink-0 rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white shadow-chip btn-press hover:brightness-105"
              >
                Close
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
              {renderGoal("shrink-0")}
              {renderWorkspace("fullscreen")}
              <div className="shrink-0">{renderExtras()}</div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
