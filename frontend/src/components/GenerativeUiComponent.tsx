import { useEffect, useRef, useState } from "react";
import WidgetCard from "./WidgetCard";
import { tutorUiUrl } from "../api";
import { subscribeUiHeight } from "../lib/lessonBridge";

/** Leave room for the fixed voice dock + card chrome so tall capsules stay on-screen. */
function viewportBodyCap(): number {
  if (typeof window === "undefined") return 480;
  return Math.max(220, Math.round(window.innerHeight - 220));
}

/**
 * Path B (generate_ui) surface: a bespoke HTML capsule served same-origin with the strict
 * artifact CSP and mounted in a `sandbox="allow-scripts"` iframe via `src=` (never `srcdoc`) — the
 * exact opaque-origin isolation the lesson viewer uses. The model's raw HTML never touches the app
 * DOM; only a `ui_id` crossed the wire. The iframe auto-sizes from the capsule's `HT_UI_HEIGHT`
 * reports (see backend `ensure_artifact_runtime`), capped to the viewport with an internal scroll
 * so the whole visual stays reachable in the bottom dock / dealt-card layouts.
 */
export default function GenerativeUiComponent({
  courseId,
  lessonId,
  uiId,
  title,
}: {
  courseId?: string;
  lessonId?: string;
  uiId?: string;
  title?: string;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [contentHeight, setContentHeight] = useState(320);
  const [maxBodyHeight, setMaxBodyHeight] = useState(viewportBodyCap);

  useEffect(() => {
    const onResize = () => setMaxBodyHeight(viewportBodyCap());
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    return subscribeUiHeight(iframe, (h) =>
      setContentHeight(Math.min(1600, Math.max(160, h)))
    );
  }, [uiId]);

  if (!courseId || !lessonId || !uiId) {
    return (
      <WidgetCard title={title || "Interactive visual"} eyebrow="Interactive visual" tone="interactive">
        <p className="text-[13px] leading-relaxed text-ink-soft">
          This interactive visual can't be displayed here.
        </p>
      </WidgetCard>
    );
  }

  // Keep the iframe at the full reported content height and scroll the wrapper — more reliable
  // than relying on the sandboxed document's own overflow (many capsules set overflow:hidden).
  // Width is always 100% of the card; the server shell clamps img/canvas/svg to max-width:100%.
  const bodyHeight = Math.min(contentHeight, maxBodyHeight);

  return (
    <WidgetCard
      title={title || "Interactive visual"}
      eyebrow="Interactive visual"
      tone="interactive"
      className="flex max-h-[calc(100dvh-10rem)] w-full max-w-full flex-col overflow-x-hidden"
    >
      <div
        className="min-h-0 w-full max-w-full overflow-x-hidden overflow-y-auto overscroll-contain rounded-2xl"
        style={{ maxHeight: bodyHeight }}
      >
        <iframe
          ref={iframeRef}
          src={tutorUiUrl(courseId, lessonId, uiId)}
          title={title || "Interactive visual"}
          sandbox="allow-scripts"
          className="block w-full max-w-full border-0 bg-paper"
          style={{ height: contentHeight, minHeight: 160 }}
        />
      </div>
    </WidgetCard>
  );
}
