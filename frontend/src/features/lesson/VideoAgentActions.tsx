import { useAgentAction } from "@guidebridge/react";
import type { RefObject } from "react";

/**
 * Registers video playback actions on the lesson's GuideBridge session
 * (specs/design_agents §6). The voice tutor discovers these via `observe_page`
 * (customActions) and invokes them via `app_action` — the same session and calling
 * convention as capsule page tools; only the handler runs host-side instead of in
 * an iframe runtime. Drives the native <video> inside the container; embedded
 * players (YouTube) report unavailability instead of failing.
 */
export function VideoAgentActions({
  containerRef,
}: {
  containerRef: RefObject<HTMLDivElement | null>;
}) {
  const video = () => containerRef.current?.querySelector("video") ?? null;

  useAgentAction(
    "seek_to",
    "Seek the lesson video to a time. Args: {seconds: number}.",
    (args) => {
      const el = video();
      if (!el) return "video element not available (embedded player)";
      const seconds = Number((args as { seconds?: unknown }).seconds);
      if (!Number.isFinite(seconds)) return "seek_to needs args {seconds: number}";
      el.currentTime = Math.max(0, Math.min(seconds, el.duration || seconds));
      void el.play().catch(() => {});
      return `seeked to ${Math.round(seconds)}s and playing`;
    },
  );

  useAgentAction("play_video", "Play the lesson video.", () => {
    const el = video();
    if (!el) return "video element not available (embedded player)";
    void el.play().catch(() => {});
    return "playing";
  });

  useAgentAction("pause_video", "Pause the lesson video.", () => {
    const el = video();
    if (!el) return "video element not available (embedded player)";
    el.pause();
    return "paused";
  });

  return null;
}
