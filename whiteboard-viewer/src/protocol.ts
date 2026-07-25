/** Shared postMessage contract between Hi Tuto host and this viewer. */

export const MSG_SET = "hituto:whiteboard:set";
export const MSG_READY = "hituto:whiteboard:ready";
export const MSG_CHANGE = "hituto:whiteboard:change";
export const MSG_GET = "hituto:whiteboard:get";
export const MSG_SCENE = "hituto:whiteboard:scene";

export type WhiteboardSetMessage = {
  type: typeof MSG_SET;
  elements?: unknown[];
  appState?: Record<string, unknown>;
};

export type WhiteboardReadyMessage = {
  type: typeof MSG_READY;
};

export type WhiteboardChangeMessage = {
  type: typeof MSG_CHANGE;
  elements: unknown[];
};

export type WhiteboardGetMessage = {
  type: typeof MSG_GET;
};

export type WhiteboardSceneMessage = {
  type: typeof MSG_SCENE;
  elements: unknown[];
};

/** Comma-separated parent origins allowed to drive the canvas (build-time). */
export function allowedParentOrigins(): string[] {
  const raw = import.meta.env.VITE_ALLOWED_PARENT_ORIGINS as string | undefined;
  const defaults = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://8xdj824y.insforge.site",
  ];
  if (!raw?.trim()) return defaults;
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function isAllowedOrigin(origin: string): boolean {
  const allowed = allowedParentOrigins();
  if (allowed.includes("*")) return true;
  return allowed.includes(origin);
}
