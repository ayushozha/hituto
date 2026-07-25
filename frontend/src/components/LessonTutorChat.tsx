import React, { useCallback, useState, useEffect, useRef } from "react";
import {
  sendTutorChatMessage,
  streamTutorChat,
  ChatMessage,
  Lesson,
  syncTutorWhiteboard,
  syncTutorCodingLab,
  recordTutorCodingLabRun,
} from "../api";
import { parsePartialJson } from "../lib/partialJson";
import { renderToolWidget } from "./renderToolWidget";
import A2UIRenderer, { UiNode } from "./A2UIRenderer";
import WidgetCard from "./WidgetCard";
import { compactWhiteboardElements } from "../lib/whiteboardContext";
import { codingLabStateFromRun, type CodingLabFile, type CodingLabRunPayload, type CodingLabState } from "../lib/codingLabAgUi";
import { recordQuizResult } from "../lib/learningEvents";
import type { ToolResult } from "./renderToolWidget";

interface LessonTutorChatProps {
  courseId: string;
  lesson: Lesson;
  onClose?: () => void;
}

/** Chat message plus transient streaming state (underscore fields never leave the client). */
type StreamMsg = ChatMessage & {
  _streaming?: boolean;
  _pendingTool?: string; // tool name while its args stream / capsule builds
  _partialRoot?: UiNode; // best-effort A2UI tree for node-by-node render_ui mounting
};

const SUGGESTIONS = ["quiz", "flashcards", "coding lab", "game", "simulator", "diagram", "formula calculator"];
const LAB_TOOL_NAMES = new Set(["show_coding_lab", "update_coding_lab"]);

export default function LessonTutorChat({ courseId, lesson, onClose }: LessonTutorChatProps) {
  const [messages, setMessages] = useState<StreamMsg[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const whiteboardElementsRef = useRef<Record<string, unknown>[]>([]);
  const activeWhiteboardSessionRef = useRef("");
  const lastQueuedSignaturesRef = useRef(new Map<string, string>());
  const whiteboardSyncQueueRef = useRef<Promise<void>>(Promise.resolve());
  const whiteboardRetryTimersRef = useRef(new Set<number>());
  const whiteboardSyncEpochRef = useRef(0);
  const whiteboardChangeHandlerRef = useRef<(elements: unknown[], sessionId?: string) => void>(
    () => undefined,
  );
  const codingLabFilesRef = useRef<CodingLabFile[]>([]);
  const codingLabStateRef = useRef<CodingLabState | null>(null);
  const activeCodingLabSessionRef = useRef("");
  const handleToolResult = useCallback(
    (result: ToolResult) => recordQuizResult({ courseId, lessonId: lesson.id }, result),
    [courseId, lesson.id],
  );

  let activeWhiteboardIndex = -1;
  let activeCodingLabIndex = -1;
  for (let idx = 0; idx < messages.length; idx += 1) {
    const name = messages[idx].tool_call?.name;
    if (name === "show_whiteboard") activeWhiteboardIndex = idx;
    if (name && LAB_TOOL_NAMES.has(name)) activeCodingLabIndex = idx;
  }
  const activeWhiteboard =
    activeWhiteboardIndex >= 0 ? messages[activeWhiteboardIndex].tool_call : undefined;
  const activeWhiteboardSessionId = String(
    activeWhiteboard?.arguments.whiteboard_session_id ?? "",
  );
  const activeCodingLab =
    activeCodingLabIndex >= 0 ? messages[activeCodingLabIndex].tool_call : undefined;
  const activeCodingLabSessionId = String(
    activeCodingLab?.arguments.coding_lab_session_id ?? "",
  );

  const handleWhiteboardChange = useCallback(
    (elements: unknown[], sessionId?: string) => {
      const compact = compactWhiteboardElements(elements);
      const normalizedSessionId = sessionId ?? "";
      if (
        normalizedSessionId &&
        activeWhiteboardSessionRef.current &&
        normalizedSessionId !== activeWhiteboardSessionRef.current
      ) {
        return;
      }
      whiteboardElementsRef.current = compact;
      if (!normalizedSessionId) return;

      const signature = JSON.stringify(compact);
      if (lastQueuedSignaturesRef.current.get(normalizedSessionId) === signature) return;
      lastQueuedSignaturesRef.current.set(normalizedSessionId, signature);
      const epoch = whiteboardSyncEpochRef.current;

      // Serialize writes so an older request can never commit after a newer scene. Jobs that have
      // not started yet collapse to the latest signature for this session.
      whiteboardSyncQueueRef.current = whiteboardSyncQueueRef.current
        .catch(() => undefined)
        .then(async () => {
          if (epoch !== whiteboardSyncEpochRef.current) return;
          if (lastQueuedSignaturesRef.current.get(normalizedSessionId) !== signature) return;
          try {
            await syncTutorWhiteboard(courseId, lesson.id, normalizedSessionId, compact);
          } catch {
            if (
              epoch !== whiteboardSyncEpochRef.current ||
              lastQueuedSignaturesRef.current.get(normalizedSessionId) !== signature
            ) {
              return;
            }
            // Clear the dedupe marker before retrying; otherwise the unchanged scene is dropped.
            lastQueuedSignaturesRef.current.delete(normalizedSessionId);
            const timer = window.setTimeout(() => {
              whiteboardRetryTimersRef.current.delete(timer);
              if (
                epoch === whiteboardSyncEpochRef.current &&
                activeWhiteboardSessionRef.current === normalizedSessionId
              ) {
                whiteboardChangeHandlerRef.current(compact, normalizedSessionId);
              }
            }, 1000);
            whiteboardRetryTimersRef.current.add(timer);
          }
        });
    },
    [courseId, lesson.id],
  );
  whiteboardChangeHandlerRef.current = handleWhiteboardChange;

  const handleCodingLabFilesChange = useCallback(
    (files: CodingLabFile[], sessionId?: string) => {
      const normalizedSessionId = sessionId ?? "";
      if (
        normalizedSessionId &&
        activeCodingLabSessionRef.current &&
        normalizedSessionId !== activeCodingLabSessionRef.current
      ) {
        return;
      }
      codingLabFilesRef.current = files;
      codingLabStateRef.current = {
        ...(codingLabStateRef.current || {}),
        session_id: normalizedSessionId || codingLabStateRef.current?.session_id,
        coding_lab_session_id: normalizedSessionId || codingLabStateRef.current?.coding_lab_session_id,
        files,
      };
      if (!normalizedSessionId) return;
      void syncTutorCodingLab(courseId, lesson.id, normalizedSessionId, files).catch(() => undefined);
    },
    [courseId, lesson.id],
  );

  const handleCodingLabEvent = useCallback(
    (event: CodingLabRunPayload) => {
      const sessionId = event.sessionId || activeCodingLabSessionRef.current;
      const files = event.files || codingLabFilesRef.current;
      codingLabStateRef.current = codingLabStateFromRun(sessionId, event, files);
      if (sessionId) {
        void recordTutorCodingLabRun(courseId, lesson.id, sessionId, {
          ok: event.ok,
          passed: event.passed,
          stdout: event.stdout,
          stderr: event.stderr,
          language: event.language,
          event: event.type,
          files,
        }).catch(() => undefined);
      }
    },
    [courseId, lesson.id],
  );

  useEffect(() => {
    whiteboardSyncEpochRef.current += 1;
    for (const timer of whiteboardRetryTimersRef.current) window.clearTimeout(timer);
    whiteboardRetryTimersRef.current.clear();
    lastQueuedSignaturesRef.current.clear();
    activeWhiteboardSessionRef.current = "";
    whiteboardElementsRef.current = [];
    activeCodingLabSessionRef.current = "";
    codingLabFilesRef.current = [];
    codingLabStateRef.current = null;
    setMessages([
      {
        role: "assistant",
        content: `Hi! I'm your AI tutor for "${lesson.title}".\n\nAsk me to clarify a concept, or tap a chip below to spin up an interactive widget.`,
      },
    ]);
    return () => {
      whiteboardSyncEpochRef.current += 1;
      for (const timer of whiteboardRetryTimersRef.current) window.clearTimeout(timer);
      whiteboardRetryTimersRef.current.clear();
    };
  }, [lesson.id, lesson.title]);

  useEffect(() => {
    activeWhiteboardSessionRef.current = activeWhiteboardSessionId;
    whiteboardElementsRef.current = compactWhiteboardElements(
      Array.isArray(activeWhiteboard?.arguments.elements)
        ? activeWhiteboard.arguments.elements
        : [],
    );
  }, [activeWhiteboard, activeWhiteboardSessionId]);

  useEffect(() => {
    activeCodingLabSessionRef.current = activeCodingLabSessionId;
    const files = Array.isArray(activeCodingLab?.arguments.files)
      ? (activeCodingLab.arguments.files as CodingLabFile[])
      : [];
    codingLabFilesRef.current = files;
    if (activeCodingLabSessionId) {
      codingLabStateRef.current = {
        session_id: activeCodingLabSessionId,
        coding_lab_session_id: activeCodingLabSessionId,
        title: typeof activeCodingLab?.arguments.title === "string" ? activeCodingLab.arguments.title : undefined,
        language:
          typeof activeCodingLab?.arguments.language === "string"
            ? activeCodingLab.arguments.language
            : undefined,
        instructions:
          typeof activeCodingLab?.arguments.instructions === "string"
            ? activeCodingLab.arguments.instructions
            : undefined,
        files,
      };
    }
  }, [activeCodingLab, activeCodingLabSessionId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMessage: StreamMsg = { role: "user", content: text.trim() };
    const base: ChatMessage[] = messages.map(({ role, content, tool_call }) => ({
      role,
      content,
      tool_call: tool_call ?? null,
    }));
    base.push({
      role: "user",
      content: userMessage.content,
      tool_call: null,
      whiteboard_state:
        whiteboardElementsRef.current.length > 0
          ? { elements: whiteboardElementsRef.current }
          : null,
      coding_lab_state: codingLabStateRef.current,
    });
    const assistantIdx = base.length;

    setMessages((prev) => [...prev, userMessage, { role: "assistant", content: "", _streaming: true }]);
    setInputValue("");
    setLoading(true);
    setError(null);

    // Mutate only the in-flight assistant message (last entry) as frames arrive.
    const patch = (fn: (m: StreamMsg) => StreamMsg) =>
      setMessages((prev) => {
        const copy = prev.slice();
        if (copy[assistantIdx]) copy[assistantIdx] = fn(copy[assistantIdx]);
        return copy;
      });

    let argsBuf = "";

    try {
      await streamTutorChat(courseId, lesson.id, base, (frame) => {
        switch (frame.type) {
          case "TEXT_MESSAGE_CONTENT":
            patch((m) => ({ ...m, content: (m.content || "") + frame.delta }));
            break;
          case "TOOL_CALL_START":
            argsBuf = "";
            patch((m) => ({ ...m, _pendingTool: frame.toolCallName, _partialRoot: undefined }));
            break;
          case "TOOL_CALL_ARGS": {
            // render_ui only (safe JSON) — accumulate + best-effort parse for progressive mount.
            argsBuf += frame.delta;
            const parsed = parsePartialJson<{ root?: UiNode }>(argsBuf);
            if (parsed && parsed.root) patch((m) => ({ ...m, _partialRoot: parsed.root }));
            break;
          }
          case "TOOL_CALL_END":
            patch((m) => {
              const next: StreamMsg = { ...m, _pendingTool: undefined, _partialRoot: undefined };
              if (frame.arguments) next.tool_call = { name: frame.toolCallName, arguments: frame.arguments };
              return next;
            });
            break;
          case "RUN_ERROR":
            setError(frame.detail || "The tutor stream was interrupted.");
            break;
          default:
            break;
        }
      });
    } catch {
      // Streaming failed (network/endpoint) — fall back to the non-streaming POST.
      try {
        const reply = await sendTutorChatMessage(courseId, lesson.id, base);
        patch(() => ({ ...reply }));
      } catch {
        setError("Failed to get tutor reply. Try again.");
      }
    } finally {
      patch((m) => ({ ...m, _streaming: false, _pendingTool: undefined, _partialRoot: undefined }));
      setLoading(false);
    }
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    send(inputValue);
  };

  const last = messages[messages.length - 1];
  const showThinking =
    loading &&
    last?.role === "assistant" &&
    !last.content &&
    !last._pendingTool &&
    !last.tool_call;

  return (
    <div className="flex h-full flex-col bg-bone text-ink">
      {/* Header */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-ink/5 bg-white px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-mint text-lime">
            <span className="material-symbols-outlined text-[20px]">psychology</span>
          </span>
          <div className="min-w-0">
            <h3 className="font-archivo text-sm font-semibold leading-tight tracking-[-0.01em] text-ink">
              AI Tutor
            </h3>
            <p className="max-w-[170px] truncate text-[11px] text-ink-faint">{lesson.title}</p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-full text-ink-faint transition hover:bg-sand hover:text-ink"
            title="Close tutor panel"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((msg, idx) => (
          <div key={idx} className="flex flex-col gap-3">
            <MessageBubble
              message={msg}
              courseId={courseId}
              lessonId={lesson.id}
              onWhiteboardChange={handleWhiteboardChange}
              onCodingLabFilesChange={handleCodingLabFilesChange}
              onCodingLabEvent={handleCodingLabEvent}
              onResult={handleToolResult}
              renderWhiteboard={idx === activeWhiteboardIndex}
              renderCodingLab={idx === activeCodingLabIndex}
            />
          </div>
        ))}
        {showThinking && (
          <div className="flex w-fit items-center gap-2 rounded-2xl border border-ink/5 bg-white px-3.5 py-2.5 text-ink-faint shadow-chip">
            <span className="h-2 w-2 animate-bounce rounded-full bg-lime" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-lime [animation-delay:0.12s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-lime [animation-delay:0.24s]" />
            <span className="ml-1 text-[11px] font-semibold uppercase tracking-wider text-ink-soft">Thinking…</span>
          </div>
        )}
        {error && (
          <div className="w-[85%] self-start rounded-2xl border border-coral/20 bg-coral-soft p-3 text-xs font-medium text-coral-dark">
            ⚠️ {error}
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Suggestion chips */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => send(`Give me a ${s}`)}
              disabled={loading}
              className="rounded-full border border-ink/5 bg-white px-3 py-1.5 text-[11px] font-semibold capitalize text-ink-soft shadow-chip transition hover:text-ink disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSend} className="flex gap-2 border-t border-ink/5 bg-white p-3">
        <input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Ask a question or request a quiz…"
          disabled={loading}
          className="h-10 flex-1 rounded-full border border-ink/10 bg-white px-4 text-sm text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !inputValue.trim()}
          className="grid h-10 w-10 place-items-center rounded-full bg-ink text-white transition hover:bg-ink/80 disabled:opacity-40"
        >
          <span className="material-symbols-outlined text-[18px]">send</span>
        </button>
      </form>
    </div>
  );
}

/** A shimmering placeholder shown while a widget's args stream / a capsule builds. */
function WidgetSkeleton({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-ink/5 bg-white px-3.5 py-3 text-ink-faint shadow-chip">
      <span className="material-symbols-outlined animate-spin-slow text-[18px] text-lime">progress_activity</span>
      <span className="text-xs font-medium text-ink-soft">{label}</span>
    </div>
  );
}

function MessageBubble({
  message,
  courseId,
  lessonId,
  onWhiteboardChange,
  onCodingLabFilesChange,
  onCodingLabEvent,
  onResult,
  renderWhiteboard,
  renderCodingLab,
}: {
  message: StreamMsg;
  courseId: string;
  lessonId: string;
  onWhiteboardChange: (elements: unknown[], sessionId?: string) => void;
  onCodingLabFilesChange: (files: CodingLabFile[], sessionId?: string) => void;
  onCodingLabEvent: (event: CodingLabRunPayload) => void;
  onResult: (result: ToolResult) => void;
  renderWhiteboard: boolean;
  renderCodingLab: boolean;
}) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="ml-auto max-w-[85%] self-end rounded-2xl bg-ink px-3.5 py-2.5 text-[13px] font-medium leading-relaxed text-white">
        <p className="whitespace-pre-line">{message.content}</p>
      </div>
    );
  }

  // Assistant: text (if any), then the final widget OR a streaming placeholder.
  const textBubble = message.content ? (
    <div className="mr-auto max-w-[85%] self-start rounded-2xl border border-ink/5 bg-white px-3.5 py-2.5 text-[13px] font-medium leading-relaxed text-ink shadow-chip">
      <p className="whitespace-pre-line">
        {message.content}
        {message._streaming && <span className="ml-0.5 inline-block animate-pulse text-lime">▌</span>}
      </p>
    </div>
  ) : null;

  let widget: React.ReactNode = null;
  if (message.tool_call) {
    const name = message.tool_call.name;
    const hideWhiteboard = name === "show_whiteboard" && !renderWhiteboard;
    const hideLab = LAB_TOOL_NAMES.has(name) && !renderCodingLab;
    if (!hideWhiteboard && !hideLab) {
      widget = renderToolWidget(message.tool_call, {
        courseId,
        lessonId,
        onWhiteboardChange,
        onCodingLabFilesChange,
        onCodingLabEvent,
        onResult,
      });
    }
  } else if (message._pendingTool === "render_ui" && message._partialRoot) {
    // Progressive Path A: mount the nodes that have arrived; the renderer drops incomplete ones.
    widget = (
      <WidgetCard title="Building…" eyebrow="Interactive surface" tone="interactive">
        <A2UIRenderer root={message._partialRoot} />
        <div className="mt-2 h-3 w-2/3 animate-pulse rounded bg-sand" />
      </WidgetCard>
    );
  } else if (message._pendingTool === "generate_ui") {
    widget = <WidgetSkeleton label="Building an interactive visual…" />;
  } else if (message._pendingTool) {
    widget = <WidgetSkeleton label="Preparing…" />;
  }

  if (!textBubble && !widget) return null;
  return (
    <>
      {textBubble}
      {widget}
    </>
  );
}
