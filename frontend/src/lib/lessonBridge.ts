/**
 * Parent-side client for the lesson bridge injected into every artifact by
 * backend/app/capsule/postprocess.py (marker: hituto-lesson-bridge).
 *
 * The lesson iframe is sandbox="allow-scripts" (opaque origin), so identity checks use
 * `event.source === iframe.contentWindow` — the one signal an unrelated window can't spoof —
 * rather than origin strings. Commands go to the iframe with targetOrigin "*" for the same
 * opaque-origin reason; payloads are lesson content the app itself served, never secrets.
 */

const BRIDGE_SOURCE = "hituto-lesson-bridge";

// NOTE: page control (snapshot/actions/agent cursor) moved to the GuideBridge SDK
// (@guidebridge/react useAgentFrame + the server-injected guidebridge iframe runtime).
// This bridge now carries only Hi-Tuto features: edit mode, learning events,
// HTML export, and iframe auto-sizing.

export type SelectedElement = {
  id: string;
  tag: string;
  dataLessonSection: string | null;
  dataLessonControl: string | null;
  textSummary: string;
  outerHTML: string;
  rect: { top: number; left: number; width: number; height: number };
};

let seq = 0;

type BridgeRequestType = "HT_PING" | "HT_SET_EDIT_MODE" | "HT_GET_HTML";

function request<T>(
  iframe: HTMLIFrameElement | null,
  type: BridgeRequestType,
  payload?: unknown,
  timeoutMs = 4000
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const target = iframe?.contentWindow;
    if (!target) {
      reject(new Error("lesson iframe not available"));
      return;
    }
    const requestId = `req_${Date.now().toString(36)}_${++seq}`;
    const timer = window.setTimeout(() => {
      window.removeEventListener("message", onMessage);
      reject(new Error("lesson page did not respond"));
    }, timeoutMs);

    function onMessage(e: MessageEvent) {
      if (e.source !== target) return; // only OUR iframe (opaque origin ⇒ source check, not origin)
      const d = e.data;
      if (!d || d.source !== BRIDGE_SOURCE || d.requestId !== requestId) return;
      window.clearTimeout(timer);
      window.removeEventListener("message", onMessage);
      if (d.type === "HT_ERROR") reject(new Error(d.payload?.error ?? "bridge error"));
      else resolve(d.payload as T);
    }

    window.addEventListener("message", onMessage);
    target.postMessage({ source: BRIDGE_SOURCE, type, requestId, payload }, "*");
  });
}

export function setEditMode(
  iframe: HTMLIFrameElement | null,
  enabled: boolean
): Promise<{ enabled: boolean }> {
  return request<{ enabled: boolean }>(iframe, "HT_SET_EDIT_MODE", { enabled });
}

export function getDocumentHtml(iframe: HTMLIFrameElement | null): Promise<{ html: string }> {
  return request<{ html: string }>(iframe, "HT_GET_HTML", undefined, 8000);
}

/**
 * Subscribe to in-iframe element picks while Edit mode is on.
 */
export function subscribeElementSelected(
  iframe: HTMLIFrameElement | null,
  onSelect: (el: SelectedElement) => void
): () => void {
  function onMessage(e: MessageEvent) {
    if (!iframe || e.source !== iframe.contentWindow) return;
    const d = e.data;
    if (!d || d.source !== BRIDGE_SOURCE || d.type !== "HT_ELEMENT_SELECTED") return;
    const p = d.payload;
    if (!p || typeof p.id !== "string") return;
    onSelect({
      id: p.id,
      tag: String(p.tag || ""),
      dataLessonSection: p.dataLessonSection ?? null,
      dataLessonControl: p.dataLessonControl ?? null,
      textSummary: String(p.textSummary || ""),
      outerHTML: String(p.outerHTML || ""),
      rect: p.rect || { top: 0, left: 0, width: 0, height: 0 },
    });
  }
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}

export type CapsuleLearningEvent = {
  eventType:
    | "capsule_control_used"
    | "capsule_section_viewed"
    | "studio_mode_opened"
    | "studio_part_selected"
    | "studio_control_changed"
    | "studio_playback_completed"
    | "studio_reset"
    | "studio_degraded";
  data: Record<string, string>;
};

/** Receive content-minimized learner interactions from this specific sandboxed lesson. */
export function subscribeCapsuleLearningEvents(
  iframeRef: { current: HTMLIFrameElement | null },
  onEvent: (event: CapsuleLearningEvent) => void,
): () => void {
  function onMessage(event: MessageEvent) {
    const iframe = iframeRef.current;
    if (!iframe || event.source !== iframe.contentWindow) return;
    const message = event.data;
    if (!message || message.source !== BRIDGE_SOURCE || message.type !== "HT_LEARNING_EVENT") return;
    const eventType = message.payload?.eventType;
    const allowed = new Set<CapsuleLearningEvent["eventType"]>([
      "capsule_control_used",
      "capsule_section_viewed",
      "studio_mode_opened",
      "studio_part_selected",
      "studio_control_changed",
      "studio_playback_completed",
      "studio_reset",
      "studio_degraded",
    ]);
    if (!allowed.has(eventType)) return;
    onEvent({ eventType, data: message.payload?.data ?? {} });
  }
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}

/**
 * Subscribe to `HT_UI_HEIGHT` content-height reports from a capsule iframe (auto-sizing a
 * generate_ui / Path B surface). Uses the same `event.source === iframe.contentWindow` identity
 * check as the request bridge — the one signal an opaque-origin iframe can't spoof. Returns an
 * unsubscribe function.
 */
export function subscribeUiHeight(
  iframe: HTMLIFrameElement | null,
  onHeight: (height: number) => void
): () => void {
  function onMessage(e: MessageEvent) {
    if (!iframe || e.source !== iframe.contentWindow) return;
    const d = e.data;
    if (!d || d.source !== BRIDGE_SOURCE || d.type !== "HT_UI_HEIGHT") return;
    const h = Number(d.payload?.height);
    if (Number.isFinite(h) && h > 0) onHeight(h);
  }
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}
