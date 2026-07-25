import { useEffect } from "react";

import {
  type LearningEventInput,
  type LearningEventType,
  postLearningEvents,
} from "../api";

type LearningContext = { courseId?: string; lessonId?: string; sessionId?: string };

const queue: LearningEventInput[] = [];
let flushing: Promise<void> | null = null;
let flushTimer: number | null = null;

function eventId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `evt_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`;
}

export function recordLearningEvent(
  eventType: LearningEventType,
  context: LearningContext = {},
  payload: Record<string, unknown> = {},
  options: { immediate?: boolean; source?: LearningEventInput["source"] } = {},
): void {
  if (queue.length >= 200) queue.splice(0, queue.length - 199);
  queue.push({
    event_id: eventId(),
    event_type: eventType,
    occurred_at: new Date().toISOString(),
    course_id: context.courseId,
    lesson_id: context.lessonId,
    session_id: context.sessionId,
    source: options.source ?? "web",
    schema_version: 1,
    payload,
  });
  if (options.immediate) {
    void flushLearningEvents();
  } else if (flushTimer === null) {
    flushTimer = window.setTimeout(() => {
      flushTimer = null;
      void flushLearningEvents();
    }, 10_000);
  }
}

export async function flushLearningEvents(keepalive = false): Promise<void> {
  if (flushing) return flushing;
  if (flushTimer !== null) {
    window.clearTimeout(flushTimer);
    flushTimer = null;
  }
  const batch = queue.splice(0, 50);
  if (!batch.length) return;
  flushing = postLearningEvents(batch, { keepalive })
    .then(() => undefined)
    .catch(() => {
      queue.unshift(...batch);
    })
    .finally(() => {
      flushing = null;
      if (queue.length) void flushLearningEvents(keepalive);
    });
  return flushing;
}

export function recordQuizResult(
  context: LearningContext,
  result: Record<string, unknown>,
): void {
  const toolName = String(result.toolName ?? "");
  if (toolName === "create_quiz") {
    recordLearningEvent(
      "quiz_submitted",
      context,
      {
        score: Number(result.score ?? 0),
        total: Number(result.total ?? 0),
        attempt: Number(result.attempt ?? 1),
        duration_ms: Number(result.durationMs ?? 0),
      },
      { immediate: true },
    );
    if (result.hintUsed) {
      recordLearningEvent("hint_requested", context, {}, { immediate: true });
    }
  } else if (toolName === "practice_retried") {
    recordLearningEvent(
      "practice_retried",
      context,
      { attempt: Number(result.attempt ?? 2) },
      { immediate: true },
    );
  }
}

/** Track only visible, focused, recently interacted-with lesson time. */
export function useLessonLearningSession(courseId: string, lessonId: string): void {
  useEffect(() => {
    const sessionId = eventId();
    const context = { courseId, lessonId, sessionId };
    let lastInteraction = Date.now();
    let lastHeartbeat = Date.now();

    const markInteraction = () => {
      lastInteraction = Date.now();
    };
    const heartbeat = () => {
      const now = Date.now();
      const active =
        document.visibilityState === "visible" &&
        document.hasFocus() &&
        now - lastInteraction <= 120_000;
      if (active) {
        const activeMs = Math.min(60_000, Math.max(1, now - lastHeartbeat));
        recordLearningEvent("active_time_increment", context, { active_ms: activeMs });
      }
      lastHeartbeat = now;
    };

    recordLearningEvent("lesson_view_started", context, {}, { immediate: true });
    const interval = window.setInterval(heartbeat, 30_000);
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown", "touchstart"];
    events.forEach((name) => window.addEventListener(name, markInteraction, { passive: true }));
    const onVisibilityChange = () => {
      heartbeat();
      void flushLearningEvents(true);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", markInteraction);

    return () => {
      heartbeat();
      recordLearningEvent("lesson_view_ended", context, {}, { immediate: true });
      void flushLearningEvents(true);
      window.clearInterval(interval);
      events.forEach((name) => window.removeEventListener(name, markInteraction));
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", markInteraction);
    };
  }, [courseId, lessonId]);
}
