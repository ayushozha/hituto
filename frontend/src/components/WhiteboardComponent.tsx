import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from "react";
import { createPortal } from "react-dom";
import WidgetCard from "./WidgetCard";

const MSG_SET = "hituto:whiteboard:set";
const MSG_READY = "hituto:whiteboard:ready";
const MSG_CHANGE = "hituto:whiteboard:change";
const MSG_GET = "hituto:whiteboard:get";
const MSG_SCENE = "hituto:whiteboard:scene";

export type WhiteboardArgs = {
  title?: string;
  intent?: string;
  elements?: unknown[];
  caption?: string;
  whiteboard_session_id?: string;
  onSceneChange?: (elements: unknown[], sessionId?: string) => void;
};

function viewerUrl(): string {
  const configured = (import.meta.env.VITE_WHITEBOARD_VIEWER_URL as string | undefined)?.replace(
    /\/$/,
    "",
  );
  if (configured) return configured;
  // Bundled under frontend/public/whiteboard for InsForge same-origin hosting.
  // Address the static entrypoint explicitly. Vite's SPA fallback otherwise serves the main app
  // for `/whiteboard` and `/whiteboard/` during local development.
  return `${window.location.origin}/whiteboard/index.html`;
}

function viewerOrigin(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/**
 * Tutor whiteboard card: embeds the Excalidraw viewer SPA
 * via iframe + postMessage, with an optional fullscreen portal.
 */
export default function WhiteboardComponent({
  title,
  intent,
  elements,
  caption,
  whiteboard_session_id: sessionId,
  onSceneChange,
}: WhiteboardArgs) {
  const url = viewerUrl();
  const origin = viewerOrigin(url);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const fullscreenIframeRef = useRef<HTMLIFrameElement>(null);
  const latestElementsRef = useRef<unknown[]>(Array.isArray(elements) ? elements : []);
  const closeTimerRef = useRef<number | null>(null);
  const closingFullscreenRef = useRef(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [viewerReady, setViewerReady] = useState(false);
  const [fsReady, setFsReady] = useState(false);

  const scenePayload = useCallback(
    (sceneElements: unknown[]) => ({
      type: MSG_SET,
      elements: sceneElements,
      appState: { viewBackgroundColor: "#FDF1E7" },
    }),
    [],
  );

  const postScene = useCallback(
    (iframe: HTMLIFrameElement | null, ready: boolean, sceneElements = latestElementsRef.current) => {
      if (!iframe?.contentWindow || !origin || !ready) return;
      iframe.contentWindow.postMessage(scenePayload(sceneElements), origin);
    },
    [origin, scenePayload],
  );

  const finishClosingFullscreen = useCallback(() => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    closingFullscreenRef.current = false;
    setFullscreen(false);
  }, []);

  useEffect(() => {
    if (!origin) return;
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin) return;
      const data = event.data as { type?: string; elements?: unknown } | null;
      const fromViewer = iframeRef.current?.contentWindow === event.source;
      const fromFullscreen = fullscreenIframeRef.current?.contentWindow === event.source;
      if (!fromViewer && !fromFullscreen) return;
      if ((data?.type === MSG_CHANGE || data?.type === MSG_SCENE) && Array.isArray(data.elements)) {
        // While fullscreen is open, its iframe owns the scene. The inline iframe remains mounted
        // behind the portal, so accepting both sources would make their independent scenes race.
        if (fullscreen && fromViewer) return;
        const sourceIframe = fromViewer ? iframeRef.current : fullscreenIframeRef.current;
        const rect = sourceIframe?.getBoundingClientRect();
        // VoiceInstructor mounts desktop + mobile card layouts simultaneously and hides one
        // with CSS. Ignore the hidden iframe so its stale initial scene cannot overwrite edits
        // made in the visible whiteboard.
        if (!rect || rect.width <= 0 || rect.height <= 0) return;
        latestElementsRef.current = data.elements;
        onSceneChange?.(data.elements, sessionId);
        if (fromFullscreen && data.type === MSG_SCENE && closingFullscreenRef.current) {
          finishClosingFullscreen();
        }
        return;
      }
      if (data?.type !== MSG_READY) return;
      // Mark whichever iframe signaled ready.
      if (fromViewer) setViewerReady(true);
      if (fromFullscreen) setFsReady(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [finishClosingFullscreen, fullscreen, onSceneChange, origin, sessionId]);

  const requestScene = useCallback(
    (iframe: HTMLIFrameElement | null) => {
      if (!iframe?.contentWindow || !origin) return;
      const rect = iframe.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      iframe.contentWindow.postMessage({ type: MSG_GET }, origin);
    },
    [origin],
  );

  const requestFullscreenClose = useCallback(() => {
    if (!fsReady) {
      finishClosingFullscreen();
      return;
    }
    // Pull the exact live scene before unmounting the fullscreen iframe. Its debounced change
    // event may not have fired yet for the learner's final stroke.
    closingFullscreenRef.current = true;
    requestScene(fullscreenIframeRef.current);
    closeTimerRef.current = window.setTimeout(finishClosingFullscreen, 400);
  }, [finishClosingFullscreen, fsReady, requestScene]);

  useEffect(() => {
    const nextElements = Array.isArray(elements) ? elements : [];
    latestElementsRef.current = nextElements;
    if (!fullscreen) postScene(iframeRef.current, viewerReady, nextElements);
  }, [elements, postScene, viewerReady]);

  useEffect(() => {
    if (!fullscreen) postScene(iframeRef.current, viewerReady);
  }, [fullscreen, postScene, viewerReady]);

  useEffect(() => {
    if (!viewerReady || fullscreen) return;
    postScene(iframeRef.current, true);
    requestScene(iframeRef.current);
    const timer = window.setInterval(() => requestScene(iframeRef.current), 750);
    return () => window.clearInterval(timer);
  }, [fullscreen, postScene, requestScene, viewerReady]);

  useEffect(() => {
    if (!fullscreen) return;
    postScene(fullscreenIframeRef.current, fsReady);
  }, [postScene, fullscreen, fsReady]);

  useEffect(() => {
    if (!fullscreen || !fsReady) return;
    requestScene(fullscreenIframeRef.current);
    const timer = window.setInterval(() => requestScene(fullscreenIframeRef.current), 750);
    return () => window.clearInterval(timer);
  }, [fullscreen, fsReady, requestScene]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") requestFullscreenClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [fullscreen, requestFullscreenClose]);

  useEffect(
    () => () => {
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
    },
    [],
  );

  if (!url || !origin) {
    return (
      <WidgetCard title={title || "Whiteboard"} eyebrow="Teaching whiteboard" tone="whiteboard">
        <p className="text-[13px] leading-relaxed text-ink-soft">
          Whiteboard viewer is not configured. Set{" "}
          <code className="font-mono text-[12px]">VITE_WHITEBOARD_VIEWER_URL</code> to the
          InsForge (or local) Excalidraw viewer URL.
        </p>
      </WidgetCard>
    );
  }

  const openFullscreen = (e?: SyntheticEvent) => {
    e?.stopPropagation();
    e?.preventDefault();
    setFsReady(false);
    setFullscreen(true);
  };

  const closeFullscreen = (e?: SyntheticEvent) => {
    e?.stopPropagation();
    e?.preventDefault();
    requestFullscreenClose();
  };

  return (
    <>
      <WidgetCard
        title={title || "Whiteboard"}
        eyebrow="Teaching whiteboard"
        tone="whiteboard"
        footer={
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={openFullscreen}
            className="w-full rounded-full bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-chip btn-press hover:brightness-105"
            aria-label="Open whiteboard fullscreen"
          >
            Fullscreen
          </button>
        }
      >
        {intent ? (
          <p className="mb-3 text-[13px] font-semibold leading-snug text-ink">{intent}</p>
        ) : null}
        <iframe
          ref={iframeRef}
          src={url}
          title={title || "Whiteboard"}
          className="w-full rounded-2xl border-0 bg-paper"
          style={{ height: 360 }}
          allow="clipboard-write"
          onLoad={() => {
            setViewerReady(true);
            window.setTimeout(() => postScene(iframeRef.current, true), 80);
          }}
        />
        {caption ? (
          <p className="mt-3 text-[12px] leading-relaxed text-ink-soft">{caption}</p>
        ) : null}
      </WidgetCard>

      {fullscreen &&
        createPortal(
          <div
            className="fixed inset-0 z-[9999] flex flex-col bg-paper"
            role="dialog"
            aria-modal="true"
            aria-label={title || "Whiteboard fullscreen"}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-ink/5 bg-cream px-4 py-3 text-ink shadow-sm">
              <div className="min-w-0">
                <h3 className="truncate font-archivo text-base font-semibold">
                  {title || "Whiteboard"}
                </h3>
                {intent ? (
                  <p className="truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-brand-dark">
                    {intent}
                  </p>
                ) : null}
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
            <iframe
              ref={fullscreenIframeRef}
              src={url}
              title={title || "Whiteboard fullscreen"}
              className="min-h-0 w-full flex-1 border-0 bg-paper"
              allow="clipboard-write"
              onLoad={() => {
                setFsReady(true);
                window.setTimeout(() => postScene(fullscreenIframeRef.current, true), 80);
              }}
            />
          </div>,
          document.body,
        )}
    </>
  );
}
