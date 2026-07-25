import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { RefObject } from "react";
import type { PageSnapshot } from "@guidebridge/react";
import { ChatToolCall, recordTutorCodingLabRun, syncTutorCodingLab, voiceWebSocketUrl } from "../api";
import { renderToolWidget, ToolResult } from "./renderToolWidget";
import WidgetCard from "./WidgetCard";
import { ACTIVITY_TONES, getActivityWidgetMeta } from "./activityWidgetPalette";
import { Mascot } from "./Mascot";
import { compactWhiteboardElements } from "../lib/whiteboardContext";
import { recordQuizResult } from "../lib/learningEvents";

type Status = "idle" | "connecting" | "live" | "error";
type DockMode = "text" | "voice";

const BAR_SCALES = [0.4, 0.7, 1.0, 1.25, 0.9, 0.6, 0.45];
const CARD_TILTS = [-1.7, 1.3, -0.9, 1.9, -1.3, 0.8];
const CARD_W = 400;
const CAPTURE_SAMPLE_RATE = 24000;
const PREROLL_MS = 420;
const HANGOVER_MS = 720;
const TRANSCRIPT_HISTORY_LIMIT = 40;

function singletonWidgetFamily(toolName: string): string | null {
  if (toolName === "show_whiteboard") return "whiteboard";
  if (toolName === "show_coding_lab" || toolName === "update_coding_lab") return "coding_lab";
  return null;
}

type CardMeta = { x: number; y: number; z: number; rot: number };
type RenderedWidget = { toolCallId: string; toolCall: ChatToolCall; pending?: boolean };
export type TutorTranscriptLine = {
  id: string;
  speaker: "learner" | "instructor";
  text: string;
  final: boolean;
  createdAt: number;
};
type TranscriptLine = TutorTranscriptLine;

interface VoiceInstructorProps {
  courseId: string;
  lessonId: string;
  iframeRef?: RefObject<HTMLIFrameElement | null>;
  /** GuideBridge snapshot fn (from useAgentFrame) — feeds the LIVE PAGE MAP tutor context. */
  getPageSnapshot?: (() => Promise<PageSnapshot>) | null;
  autoStart?: boolean;
  initialText?: string;
  initialTranscript?: TutorTranscriptLine[];
  onTranscriptChange?: (lines: TutorTranscriptLine[]) => void;
  onClose?: () => void;
}

export default function VoiceInstructor({
  courseId,
  lessonId,
  iframeRef,
  getPageSnapshot,
  autoStart = false,
  initialText = "",
  initialTranscript = [],
  onTranscriptChange,
  onClose,
}: VoiceInstructorProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [listening, setListening] = useState(false);
  const [dockMode, setDockMode] = useState<DockMode>("text");
  const [draft, setDraft] = useState("");
  const [widgets, setWidgets] = useState<RenderedWidget[]>([]);
  const [transcript, setTranscript] = useState<TranscriptLine[]>(initialTranscript);
  const [chatVisible, setChatVisible] = useState(true);
  const [cardMeta, setCardMeta] = useState<Record<string, CardMeta>>({});

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playbackCursor = useRef(0);
  const playbackSources = useRef<AudioBufferSourceNode[]>([]);
  const voiceAudioEnabled = useRef(false);
  const playbackMuted = useRef(false);
  const ttsSampleRate = useRef(48000);
  const pending = useRef<Record<string, { name: string; args: string }>>({});
  const singletonWidgetIds = useRef<Record<string, string>>({});
  const preRoll = useRef<ArrayBuffer[]>([]);
  const speaking = useRef(false);
  const lastSpeechAt = useRef(0);
  const noiseFloor = useRef(0.012);
  const zTop = useRef(60);
  const cardDrag = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const dealt = useRef(0);
  const pageMapRef = useRef<Record<string, unknown>>({});
  const whiteboardElementsRef = useRef<Record<string, unknown>[]>([]);
  const whiteboardSignatureRef = useRef("");
  const whiteboardMapTimerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const firstText = initialText.trim();
    if (firstText) {
      setDockMode("text");
      timer = window.setTimeout(() => {
        if (!cancelled) void connect({ withMic: false, initialText: firstText });
      }, 0);
    } else if (autoStart) {
      setDockMode("voice");
      timer = window.setTimeout(() => {
        if (!cancelled) void connect({ withMic: true });
      }, 0);
    }
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      void disconnect();
    };
  }, []);

  // Re-push the page map when the capsule iframe reloads mid-session (version switch,
  // refinement, edit-mode toggle) — otherwise the tutor keeps teaching a stale page.
  useEffect(() => {
    const iframe = iframeRef?.current;
    if (!iframe || status !== "live") return;
    const onLoad = () => void pushPageMap();
    iframe.addEventListener("load", onLoad);
    return () => iframe.removeEventListener("load", onLoad);
  }, [status]);

  function sendFrame(frame: Record<string, unknown>) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(frame));
  }

  const publishLiveContext = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "PAGE_MAP",
        content: JSON.stringify({
          // Whiteboard goes first because the backend bounds live context length. Learner edits
          // must survive even when the lesson DOM map is large.
          whiteboard: { elements: whiteboardElementsRef.current },
          ...pageMapRef.current,
        }),
      }),
    );
  }, []);

  const handleWhiteboardChange = useCallback(
    (elements: unknown[], sessionId?: string) => {
      const compact = compactWhiteboardElements(elements);
      const signature = JSON.stringify([sessionId ?? "", compact]);
      if (signature === whiteboardSignatureRef.current) return;
      whiteboardSignatureRef.current = signature;
      whiteboardElementsRef.current = compact;
      if (sessionId) {
        sendFrame({
          type: "WHITEBOARD_SYNC",
          content: JSON.stringify({ session_id: sessionId, elements: compact }),
        });
      }
      if (whiteboardMapTimerRef.current !== null) {
        window.clearTimeout(whiteboardMapTimerRef.current);
      }
      whiteboardMapTimerRef.current = window.setTimeout(publishLiveContext, 300);
    },
    [publishLiveContext],
  );

  const handleCodingLabFilesChange = useCallback(
    (files: { path: string; content: string }[], sessionId?: string) => {
      if (!sessionId) return;
      void syncTutorCodingLab(courseId, lessonId, sessionId, files).catch(() => undefined);
    },
    [courseId, lessonId],
  );

  const handleCodingLabEvent = useCallback(
    (event: {
      type: string;
      sessionId?: string;
      ok: boolean;
      passed?: boolean | null;
      stdout: string;
      stderr: string;
      language: string;
      files?: { path: string; content: string }[];
    }) => {
      if (!event.sessionId) return;
      void recordTutorCodingLabRun(courseId, lessonId, event.sessionId, {
        ok: event.ok,
        passed: event.passed,
        stdout: event.stdout,
        stderr: event.stderr,
        language: event.language,
        event: event.type,
        files: event.files,
      }).catch(() => undefined);
    },
    [courseId, lessonId],
  );

  function sendAudio(chunk: ArrayBuffer) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(chunk);
  }

  function pushTranscript(line: Omit<TranscriptLine, "id" | "createdAt"> & { id?: string }) {
    setTranscript((prev) => {
      const id = line.id ?? `${line.speaker}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const existing = prev.findIndex((item) => item.id === id);
      const next = [...prev];
      if (existing >= 0) {
        next[existing] = { ...next[existing], ...line, id };
      } else {
        next.push({ ...line, id, createdAt: Date.now() });
      }
      return next.sort((a, b) => a.createdAt - b.createdAt).slice(-TRANSCRIPT_HISTORY_LIMIT);
    });
  }

  function finalizeTranscript(currentId: string, line: Omit<TranscriptLine, "id" | "createdAt">) {
    setTranscript((prev) => {
      const next = prev.filter((item) => item.id !== currentId);
      next.push({
        ...line,
        id: `${line.speaker}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        createdAt: Date.now(),
      });
      return next.sort((a, b) => a.createdAt - b.createdAt).slice(-TRANSCRIPT_HISTORY_LIMIT);
    });
  }

  const onTranscriptChangeRef = useRef(onTranscriptChange);
  onTranscriptChangeRef.current = onTranscriptChange;

  useEffect(() => {
    onTranscriptChangeRef.current?.(transcript);
  }, [transcript]);

  function publishResult(toolCallId: string, result: ToolResult) {
    sendFrame({ type: "TOOL_CALL_RESULT", toolCallId, content: JSON.stringify(result) });
    recordQuizResult({ courseId, lessonId }, result);
  }

  // Page observe/act moved to the GuideBridge WebSocket (AgentProvider in Viewer);
  // this component only keeps the LIVE PAGE MAP push, sourced from the SDK snapshot.
  async function pushPageMap(retries = 5) {
    if (!getPageSnapshot) return;
    try {
      const snap = await getPageSnapshot();
      // Keep the PAGE_MAP JSON keys byte-compatible with grounding.py: the SDK
      // snapshot calls them `targets`; the tutor prompt knows them as `controls`.
      const compact = {
        sections: (snap.sections || []).slice(0, 20).map((s) => ({
          id: s.id,
          slug: s.slug,
          title: s.title,
        })),
        controls: (snap.targets || []).slice(0, 30).map((c) => ({
          id: c.id,
          slug: c.slug,
          label: c.label,
          role: c.role,
        })),
        headings: (snap.headings || []).slice(0, 12).map((h) => ({
          id: h.id,
          level: h.level,
          text: h.text,
        })),
      };
      pageMapRef.current = compact;
      publishLiveContext();
    } catch {
      // Runtime not ready yet (capsule iframe still loading). A silent one-shot here
      // leaves the tutor page-blind for the whole session — retry with backoff while
      // the voice socket is still open.
      if (retries > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
        window.setTimeout(() => void pushPageMap(retries - 1), 2500);
      }
    }
  }

  async function handleMessage(event: MessageEvent) {
    if (event.data instanceof ArrayBuffer) {
      playPcm(event.data);
      return;
    }
    if (event.data instanceof Blob) {
      playPcm(await event.data.arrayBuffer());
      return;
    }
    let frame: any;
    try {
      frame = JSON.parse(String(event.data));
    } catch {
      return;
    }
    const id: string = frame.toolCallId;
    switch (frame.type) {
      case "session.ready":
        if (typeof frame.ttsSampleRate === "number") ttsSampleRate.current = frame.ttsSampleRate;
        void pushPageMap();
        break;
      case "stt.partial":
        pushTranscript({ id: "learner-current", speaker: "learner", text: frame.text ?? "", final: false });
        break;
      case "stt.final":
        finalizeTranscript("learner-current", { speaker: "learner", text: frame.text ?? "", final: true });
        break;
      case "agent.delta":
        pushTranscript({ id: "instructor-current", speaker: "instructor", text: frame.text ?? "", final: false });
        break;
      case "agent.final":
        finalizeTranscript("instructor-current", { speaker: "instructor", text: frame.text ?? "", final: true });
        break;
      case "tts.start":
        if (typeof frame.sampleRate === "number") ttsSampleRate.current = frame.sampleRate;
        playbackMuted.current = false;
        break;
      case "tts.interrupt":
        stopPlayback();
        break;
      case "TOOL_CALL_START":
        const singletonFamily = singletonWidgetFamily(frame.toolCallName);
        if (singletonFamily) {
          const previousId = singletonWidgetIds.current[singletonFamily];
          singletonWidgetIds.current[singletonFamily] = id;
          if (previousId && previousId !== id) {
            delete pending.current[previousId];
            setCardMeta((prev) => {
              const { [previousId]: _removed, ...rest } = prev;
              return rest;
            });
          }
        }
        pending.current[id] = { name: frame.toolCallName, args: "" };
        setWidgets((prev) => {
          if (prev.some((item) => item.toolCallId === id)) return prev;
          const title = frame.title || (frame.toolCallName === "generate_ui" ? "Interactive visual" : "Preparing");
          const retained = singletonFamily
            ? prev.filter(
                (item) => singletonWidgetFamily(item.toolCall.name) !== singletonFamily,
              )
            : prev;
          return [
            ...retained,
            {
              toolCallId: id,
              pending: true,
              toolCall: { name: frame.toolCallName, arguments: { title } },
            },
          ];
        });
        dealCard(id);
        break;
      case "TOOL_CALL_ARGS":
        if (pending.current[id]) pending.current[id].args += frame.delta ?? "";
        break;
      case "TOOL_CALL_END": {
        const acc = pending.current[id];
        delete pending.current[id];
        if (!acc) return;
        const singletonFamily = singletonWidgetFamily(acc.name);
        if (singletonFamily && singletonWidgetIds.current[singletonFamily] !== id) {
          return;
        }
        if (frame.error) {
          dismissCard(id);
          return;
        }
        try {
          const toolCall: ChatToolCall = { name: acc.name, arguments: JSON.parse(acc.args || "{}") };
          setWidgets((prev) => {
            const existing = prev.findIndex((item) => item.toolCallId === id);
            if (existing < 0) return [...prev, { toolCallId: id, toolCall }];
            const next = [...prev];
            next[existing] = { toolCallId: id, toolCall, pending: false };
            return next;
          });
        } catch {
          /* malformed args — drop the widget rather than crash */
          dismissCard(id);
        }
        break;
      }
      case "error":
        setError(frame.detail ?? "Voice connection error");
        break;
      case "session.closed":
        void disconnect();
        break;
    }
  }

  function sendTextMessage(text: string): boolean {
    const cleaned = text.trim().replace(/\s+/g, " ");
    if (!cleaned) return false;
    // WebSocket ordering guarantees the refreshed whiteboard context reaches the agent first.
    publishLiveContext();
    sendFrame({ type: "text.message", content: cleaned });
    return true;
  }

  async function connect({ withMic = true, initialText = "" }: { withMic?: boolean; initialText?: string } = {}) {
    setDockMode(withMic ? "voice" : "text");
    const existing = wsRef.current;
    if (existing && existing.readyState === WebSocket.OPEN) {
      if (withMic && !mediaStreamRef.current) await startAudioCapture();
      if (initialText) sendTextMessage(initialText);
      setStatus("live");
      return;
    }
    setStatus("connecting");
    setError(null);
    try {
      const ws = new WebSocket(voiceWebSocketUrl(courseId, lessonId));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onmessage = (event) => void handleMessage(event);
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error("Voice connection failed"));
      });
      ws.onerror = () => setError("Voice connection failed");
      ws.onclose = () => void disconnect();
      sendFrame({ type: "client.ready" });
      if (withMic) await startAudioCapture();
      setStatus("live");
      if (initialText) sendTextMessage(initialText);
    } catch (e) {
      setError((e as Error).message || "Could not connect");
      setStatus("error");
      setDockMode("text");
      await disconnect();
    }
  }

  async function enableVoiceCapture() {
    try {
      setError(null);
      setDockMode("voice");
      if (status === "live" && wsRef.current?.readyState === WebSocket.OPEN) {
        await startAudioCapture();
        return;
      }
      await connect({ withMic: true });
    } catch (e) {
      setError((e as Error).message || "Could not start voice");
      setDockMode("text");
    }
  }

  function submitText(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim().replace(/\s+/g, " ");
    if (!text || status === "connecting") return;
    setDraft("");
    setDockMode("text");
    if (status === "live" && wsRef.current?.readyState === WebSocket.OPEN) {
      sendTextMessage(text);
      return;
    }
    void connect({ withMic: false, initialText: text });
  }

  async function startAudioCapture() {
    if (mediaStreamRef.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    mediaStreamRef.current = stream;
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new AudioCtx();
    captureCtxRef.current = ctx;
    sourceRef.current = ctx.createMediaStreamSource(stream);
    processorRef.current = ctx.createScriptProcessor(2048, 1, 1);
    sourceRef.current.connect(processorRef.current);
    processorRef.current.connect(ctx.destination);
    processorRef.current.onaudioprocess = (event) => processInput(event.inputBuffer.getChannelData(0), ctx.sampleRate);
    voiceAudioEnabled.current = true;
    setListening(true);
  }

  async function stopAudioCapture({ notifyServer = true }: { notifyServer?: boolean } = {}) {
    if (notifyServer && speaking.current) sendFrame({ type: "audio.stop" });
    try {
      processorRef.current?.disconnect();
    } catch {
      /* already disconnected */
    }
    try {
      sourceRef.current?.disconnect();
    } catch {
      /* already disconnected */
    }
    processorRef.current = null;
    sourceRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    await captureCtxRef.current?.close().catch(() => {});
    captureCtxRef.current = null;
    voiceAudioEnabled.current = false;
    preRoll.current = [];
    speaking.current = false;
    setLevel(0);
    setListening(false);
    stopPlayback();
    playbackMuted.current = false;
  }

  async function switchToTextMode() {
    await stopAudioCapture();
    setDockMode("text");
  }

  function processInput(input: Float32Array, sourceRate: number) {
    const rms = calculateRms(input);
    setLevel(Math.min(1, rms * 12));
    const now = performance.now();
    const threshold = Math.max(0.026, noiseFloor.current * 2.6);
    const isSpeech = rms > threshold;
    if (!speaking.current && !isSpeech) {
      noiseFloor.current = noiseFloor.current * 0.96 + rms * 0.04;
    }
    const pcm = floatToPcm16(downsample(input, sourceRate, CAPTURE_SAMPLE_RATE));
    const frameMs = (pcm.byteLength / 2 / CAPTURE_SAMPLE_RATE) * 1000;
    const maxPreRoll = Math.max(1, Math.ceil(PREROLL_MS / Math.max(1, frameMs)));

    if (!speaking.current) {
      preRoll.current.push(pcm);
      preRoll.current = preRoll.current.slice(-maxPreRoll);
      if (isSpeech) {
        speaking.current = true;
        lastSpeechAt.current = now;
        sendFrame({ type: "audio.start" });
        for (const chunk of preRoll.current) sendAudio(chunk);
        preRoll.current = [];
      }
      return;
    }

    sendAudio(pcm);
    if (isSpeech) {
      lastSpeechAt.current = now;
    } else if (now - lastSpeechAt.current > HANGOVER_MS) {
      speaking.current = false;
      sendFrame({ type: "audio.stop" });
    }
  }

  async function disconnect() {
    const ws = wsRef.current;
    wsRef.current = null;
    await stopAudioCapture({ notifyServer: false });
    pending.current = {};
    dealt.current = 0;
    zTop.current = 60;
    if (whiteboardMapTimerRef.current !== null) {
      window.clearTimeout(whiteboardMapTimerRef.current);
      whiteboardMapTimerRef.current = null;
    }
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
    setStatus("idle");
  }

  function playPcm(buffer: ArrayBuffer) {
    if (!buffer.byteLength || playbackMuted.current || !voiceAudioEnabled.current) return;
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = playbackCtxRef.current ?? new AudioCtx();
    playbackCtxRef.current = ctx;
    const samples = new Int16Array(buffer);
    const audioBuffer = ctx.createBuffer(1, samples.length, ttsSampleRate.current);
    const channel = audioBuffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) channel[i] = samples[i] / 32768;
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime + 0.02, playbackCursor.current);
    source.start(startAt);
    playbackCursor.current = startAt + audioBuffer.duration;
    playbackSources.current.push(source);
    source.onended = () => {
      playbackSources.current = playbackSources.current.filter((s) => s !== source);
    };
  }

  // Barge-in: stop and discard any playing/queued tutor audio, and drop late-arriving
  // chunks from the interrupted turn until the next tts.start unmutes playback.
  function stopPlayback() {
    playbackMuted.current = true;
    for (const source of playbackSources.current) {
      try {
        source.onended = null;
        source.stop();
      } catch {
        /* already stopped */
      }
    }
    playbackSources.current = [];
    playbackCursor.current = 0;
  }

  function dealCard(id: string) {
    const i = dealt.current++;
    const w = Math.min(CARD_W, window.innerWidth - 32);
    setCardMeta((prev) => ({
      ...prev,
      [id]: {
        x: Math.max(16, window.innerWidth - w - 44 - (i % 3) * 32),
        y: 96 + (i % 4) * 52,
        z: ++zTop.current,
        rot: CARD_TILTS[i % CARD_TILTS.length],
      },
    }));
  }

  function bringToFront(id: string) {
    setCardMeta((prev) => (prev[id] ? { ...prev, [id]: { ...prev[id], z: ++zTop.current } } : prev));
  }

  function dismissCard(id: string) {
    setWidgets((prev) => {
      const dismissed = prev.find((widget) => widget.toolCallId === id);
      const singletonFamily = dismissed
        ? singletonWidgetFamily(dismissed.toolCall.name)
        : null;
      if (singletonFamily && singletonWidgetIds.current[singletonFamily] === id) {
        delete singletonWidgetIds.current[singletonFamily];
      }
      return prev.filter((w) => w.toolCallId !== id);
    });
    setCardMeta((prev) => {
      const { [id]: _gone, ...rest } = prev;
      return rest;
    });
  }

  function clearWidgets() {
    setWidgets([]);
    setCardMeta({});
    singletonWidgetIds.current = {};
    dealt.current = 0;
    zTop.current = 60;
  }

  function startCardDrag(e: React.PointerEvent, id: string) {
    if ((e.target as HTMLElement).closest("button")) return;
    const meta = cardMeta[id];
    if (!meta) return;
    cardDrag.current = { id, dx: e.clientX - meta.x, dy: e.clientY - meta.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function moveCardDrag(e: React.PointerEvent) {
    const drag = cardDrag.current;
    if (!drag) return;
    const w = Math.min(CARD_W, window.innerWidth - 32);
    setCardMeta((prev) => {
      const meta = prev[drag.id];
      if (!meta) return prev;
      return {
        ...prev,
        [drag.id]: {
          ...meta,
          x: Math.min(Math.max(8, e.clientX - drag.dx), window.innerWidth - w - 8),
          y: Math.min(Math.max(8, e.clientY - drag.dy), window.innerHeight - 120),
        },
      };
    });
  }

  function endCardDrag() {
    cardDrag.current = null;
  }

  const statusMeta =
    status === "live" && listening
      ? { text: "Listening…", cls: "text-lime" }
      : status === "live"
        ? { text: "I’m here", cls: "text-white/60" }
      : status === "connecting"
        ? { text: "One sec…", cls: "text-sky" }
        : status === "error"
          ? { text: "Something’s off", cls: "text-coral" }
          : { text: "Ready", cls: "text-paper/70" };

  const visibleTranscript = useMemo(() => transcript.slice(-3), [transcript]);
  const active = status === "live" || status === "connecting";

  const dealtCards =
    widgets.length > 0 ? (
      <div className="hidden lg:block">
        {widgets.map((w) => {
          const meta = cardMeta[w.toolCallId];
          if (!meta) return null;
          const tab = getActivityWidgetMeta(w.toolCall.name);
          const tabTone = ACTIVITY_TONES[tab.tone];
          return (
            <div
              key={w.toolCallId}
              style={{ left: meta.x, top: meta.y, zIndex: meta.z }}
              className={
                w.toolCall.name === "generate_ui"
                  ? "fixed w-[min(560px,calc(100vw-32px))]"
                  : "fixed w-[min(400px,calc(100vw-32px))]"
              }
              onPointerDown={() => bringToFront(w.toolCallId)}
            >
              <div className="animate-deal-in">
                <div style={{ transform: `rotate(${meta.rot}deg)` }}>
                  <div
                    onPointerDown={(e) => startCardDrag(e, w.toolCallId)}
                    onPointerMove={moveCardDrag}
                    onPointerUp={endCardDrag}
                    onPointerCancel={endCardDrag}
                    className={`relative z-10 -mb-[2px] ml-6 inline-flex cursor-grab touch-none select-none items-center gap-1.5 rounded-t-2xl border-0 py-1.5 pl-3 pr-1.5 active:cursor-grabbing ${tabTone.tab}`}
                    title="Drag to move this card"
                  >
                    <span className="material-symbols-outlined text-[15px]">{tab.icon}</span>
                    <span className="text-[10px] font-semibold uppercase tracking-[0.16em]">{tab.label}</span>
                    <span className="material-symbols-outlined ml-0.5 text-[15px] opacity-50">drag_indicator</span>
                    <button
                      onClick={() => dismissCard(w.toolCallId)}
                      className="ml-0.5 grid h-6 w-6 place-items-center rounded-full transition hover:bg-ink/20"
                      title="Dismiss card"
                    >
                      <span className="material-symbols-outlined text-[14px]">close</span>
                    </button>
                  </div>
                  {w.pending ? (
                    <PendingToolWidget toolCall={w.toolCall} />
                  ) : (
                    renderToolWidget(w.toolCall, {
                      onResult: (result) => publishResult(w.toolCallId, result),
                      onWhiteboardChange: handleWhiteboardChange,
                      onCodingLabFilesChange: handleCodingLabFilesChange,
                      onCodingLabEvent: handleCodingLabEvent,
                      courseId,
                      lessonId,
                    })
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    ) : null;

  return (
    <>
      {dealtCards && createPortal(dealtCards, document.body)}

      <div className="pointer-events-none flex flex-col items-center gap-2.5">
        {widgets.length > 0 && (
          <div className="pointer-events-auto w-[min(880px,calc(100vw-32px))] lg:hidden">
            <div className="flex gap-3 overflow-x-auto pb-2 pr-2">
              {widgets.map((w) => {
                const isVisual = w.toolCall.name === "generate_ui";
                return (
                  <div
                    key={w.toolCallId}
                    className={
                      isVisual
                        ? "w-[min(880px,calc(100vw-32px))] shrink-0"
                        : "w-[320px] shrink-0"
                    }
                  >
                    {w.pending ? (
                      <PendingToolWidget toolCall={w.toolCall} />
                    ) : (
                      renderToolWidget(w.toolCall, {
                        onResult: (result) => publishResult(w.toolCallId, result),
                        onWhiteboardChange: handleWhiteboardChange,
                        onCodingLabFilesChange: handleCodingLabFilesChange,
                        onCodingLabEvent: handleCodingLabEvent,
                        courseId,
                        lessonId,
                      })
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {active && chatVisible && (
          <div className="flex w-[min(580px,calc(100vw-28px))] flex-col gap-2">
            {visibleTranscript.length > 0 ? (
              visibleTranscript.map((line, i) => {
                const learner = line.speaker === "learner";
                return (
                  <div
                    key={line.id}
                    className={`animate-fade-up flex items-start gap-2 ${
                      learner
                        ? "ml-auto w-fit max-w-full justify-end"
                        : "w-full justify-start"
                    }`}
                    style={{ animationDelay: `${i * 40}ms` }}
                  >
                    {!learner && <Mascot mood="mark" className="mt-0.5 h-8 w-8 shrink-0" />}
                    <p
                      className={`rounded-2xl px-4 py-2.5 text-left text-sm font-medium leading-snug ${
                        learner
                          ? "bg-ink text-white"
                          : "min-w-0 flex-1 bg-sky-dark text-white shadow-chip"
                      } ${line.final ? "" : "opacity-85"}`}
                    >
                      <span
                        className={`mr-2 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                          learner ? "text-white/70" : "text-white/75"
                        }`}
                      >
                        {learner ? "You" : "Tutor"}
                      </span>
                      {line.text}
                    </p>
                  </div>
                );
              })
            ) : (
              <div className="animate-fade-in flex w-full items-center gap-2 rounded-2xl bg-sky-dark px-4 py-2.5 text-sm font-medium text-white shadow-chip">
                <Mascot mood="mark" className="h-8 w-8 shrink-0" />
                <span>
                  {status === "connecting"
                    ? "One sec — I’m hopping on…"
                    : listening
                      ? "Listening… just start talking."
                      : "Type a note or tap the mic."}
                </span>
              </div>
            )}
          </div>
        )}

        {dockMode === "voice" ? (
          <VoiceModeDock
            level={level}
            listening={listening}
            status={status}
            statusMeta={statusMeta}
            widgetCount={widgets.length}
            chatVisible={chatVisible}
            onToggleChat={() => setChatVisible((v) => !v)}
            onStopAudio={() => void switchToTextMode()}
            onClearWidgets={clearWidgets}
            onClose={onClose}
          />
        ) : (
          <TextModeDock
            draft={draft}
            status={status}
            widgetCount={widgets.length}
            chatVisible={chatVisible}
            onToggleChat={() => setChatVisible((v) => !v)}
            onDraftChange={setDraft}
            onSubmit={submitText}
            onStartVoice={() => void enableVoiceCapture()}
            onClearWidgets={clearWidgets}
            onClose={onClose}
          />
        )}

        {error &&
          createPortal(
            <div
              role="alert"
              className="pointer-events-auto fixed left-1/2 top-5 z-[60] flex w-[min(420px,calc(100vw-28px))] -translate-x-1/2 items-start gap-3 rounded-2xl border border-coral/25 bg-coral-soft px-4 py-3 text-sm font-semibold text-coral-dark shadow-panel animate-fade-up"
            >
              <span className="material-symbols-outlined mt-0.5 text-[18px] text-coral" aria-hidden="true">
                warning
              </span>
              <p className="min-w-0 flex-1 leading-snug">{error}</p>
              <button
                type="button"
                onClick={() => setError(null)}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-coral-dark/70 transition hover:bg-coral/15 hover:text-coral-dark"
                title="Dismiss"
                aria-label="Dismiss warning"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>,
            document.body,
          )}
      </div>
    </>
  );
}

type StatusMeta = { text: string; cls: string };

type TextModeDockProps = {
  draft: string;
  status: Status;
  widgetCount: number;
  chatVisible: boolean;
  onToggleChat: () => void;
  onDraftChange: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
  onStartVoice: () => void;
  onClearWidgets: () => void;
  onClose?: () => void;
};

function TextModeDock({
  draft,
  status,
  widgetCount,
  chatVisible,
  onToggleChat,
  onDraftChange,
  onSubmit,
  onStartVoice,
  onClearWidgets,
  onClose,
}: TextModeDockProps) {
  const connecting = status === "connecting";
  return (
    <div className="pointer-events-auto flex w-[min(580px,calc(100vw-28px))] items-center gap-2 rounded-2xl bg-ink p-2 text-white shadow-panel ring-2 ring-lime/40 animate-fade-up">
      <button
        type="button"
        onClick={onStartVoice}
        disabled={connecting}
        className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/10 text-white transition hover:bg-white/20 disabled:opacity-50"
        title="Start audio mode"
        aria-label="Start audio mode"
      >
        <span className="material-symbols-outlined text-[20px]" aria-hidden="true" style={{ fontVariationSettings: '"FILL" 1' }}>
          mic
        </span>
      </button>

      <form
        onSubmit={onSubmit}
        className="flex h-11 min-w-0 flex-1 items-center gap-1.5 rounded-full bg-white/10 px-3"
      >
        <input
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          disabled={connecting}
          placeholder="Ask, quiz, or request a visual…"
          className="h-full min-w-0 flex-1 rounded-full border-0 bg-transparent text-[14px] font-medium text-white outline-none placeholder:text-white/40 focus:ring-0 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={!draft.trim() || connecting}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-lime text-white transition hover:brightness-110 disabled:opacity-40"
          title="Send message"
          aria-label="Send message"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">send</span>
        </button>
      </form>

      <DockActions
        widgetCount={widgetCount}
        chatVisible={chatVisible}
        onToggleChat={onToggleChat}
        onClearWidgets={onClearWidgets}
        onClose={onClose}
        variant="dark"
      />
    </div>
  );
}

type VoiceModeDockProps = {
  level: number;
  listening: boolean;
  status: Status;
  statusMeta: StatusMeta;
  widgetCount: number;
  chatVisible: boolean;
  onToggleChat: () => void;
  onStopAudio: () => void;
  onClearWidgets: () => void;
  onClose?: () => void;
};

function VoiceModeDock({
  level,
  listening,
  status,
  statusMeta,
  widgetCount,
  chatVisible,
  onToggleChat,
  onStopAudio,
  onClearWidgets,
  onClose,
}: VoiceModeDockProps) {
  const connecting = status === "connecting";
  return (
    <div className="pointer-events-auto flex w-[min(580px,calc(100vw-28px))] items-center gap-2 rounded-2xl bg-ink p-2 text-white shadow-panel ring-2 ring-lime/40 animate-fade-up">
      <div className="relative ml-1 shrink-0">
        <div className={listening ? "animate-mascot-bob" : undefined}>
          <Mascot mood="tutor" className="h-11 w-11" title="Voice tutor" />
        </div>
      </div>

      <button
        type="button"
        onClick={onStopAudio}
        disabled={connecting}
        className="relative grid h-11 w-11 shrink-0 place-items-center rounded-full bg-lime text-white transition hover:brightness-110 disabled:opacity-50"
        title="Turn off audio mode"
        aria-label="Turn off audio mode"
      >
        <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: '"FILL" 1' }}>
          graphic_eq
        </span>
        {listening && (
          <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-lime ring-2 ring-ink" />
        )}
      </button>

      <div className="flex h-11 min-w-0 flex-1 items-center gap-3 rounded-full bg-white/10 px-3">
        <div className="flex h-7 items-center gap-[3px]" aria-hidden>
          {BAR_SCALES.map((scale, i) => (
            <span
              key={i}
              className={`w-[3px] rounded-full transition-[height] duration-100 motion-reduce:transition-none ${
                listening ? "bg-lime" : "bg-white/35"
              }`}
              style={{
                height: listening ? `${Math.max(4, Math.min(26, 4 + level * 96 * scale))}px` : "5px",
              }}
            />
          ))}
        </div>
        <span className={`truncate text-[12px] font-semibold ${connecting ? "text-white/70" : statusMeta.cls}`}>
          {statusMeta.text}
        </span>
      </div>

      <DockActions
        widgetCount={widgetCount}
        chatVisible={chatVisible}
        onToggleChat={onToggleChat}
        onClearWidgets={onClearWidgets}
        onClose={onClose}
        variant="dark"
      />
    </div>
  );
}

function DockActions({
  widgetCount,
  chatVisible,
  onToggleChat,
  onClearWidgets,
  onClose,
  variant = "light",
}: {
  widgetCount: number;
  chatVisible?: boolean;
  onToggleChat?: () => void;
  onClearWidgets: () => void;
  onClose?: () => void;
  variant?: "light" | "dark";
}) {
  const dark = variant === "dark";
  if (!widgetCount && !onClose && !onToggleChat) return null;
  return (
    <>
      {onToggleChat && (
        <button
          type="button"
          onClick={onToggleChat}
          className={`grid h-9 w-9 place-items-center rounded-full transition ${
            dark ? "text-white/65 hover:bg-white/10 hover:text-white" : "text-ink-faint hover:bg-sand hover:text-ink"
          }`}
          title={chatVisible ? "Hide chat" : "Show chat"}
          aria-label={chatVisible ? "Hide chat" : "Show chat"}
          aria-pressed={chatVisible}
        >
          <span className="material-symbols-outlined text-[20px]">
            {chatVisible ? "keyboard_arrow_down" : "keyboard_arrow_up"}
          </span>
        </button>
      )}

      {widgetCount > 0 && (
        <button
          type="button"
          onClick={onClearWidgets}
          className={`group flex items-center gap-1 rounded-full px-2.5 py-1.5 text-[10px] font-semibold transition ${
            dark
              ? "bg-white/10 text-white/80 hover:bg-white/20 hover:text-white"
              : "bg-sand text-ink-soft hover:bg-line hover:text-ink"
          }`}
          title="Dismiss all cards"
        >
          {widgetCount} card{widgetCount === 1 ? "" : "s"}
          <span className="material-symbols-outlined text-[12px] opacity-0 transition-opacity group-hover:opacity-100">
            close
          </span>
        </button>
      )}

      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className={`grid h-9 w-9 place-items-center rounded-full transition ${
            dark ? "text-white/65 hover:bg-white/10 hover:text-white" : "text-ink-faint hover:bg-sand hover:text-ink"
          }`}
          title="Close voice instructor"
          aria-label="Close voice instructor"
        >
          <span className="material-symbols-outlined text-[18px]">close</span>
        </button>
      )}
    </>
  );
}

function PendingToolWidget({ toolCall }: { toolCall: ChatToolCall }) {
  const isVisual = toolCall.name === "generate_ui";
  const title = String(toolCall.arguments?.title || (isVisual ? "Interactive visual" : "Preparing"));
  return (
    <WidgetCard
      title={title}
      eyebrow={isVisual ? "Building visual" : "Preparing activity"}
      tone={isVisual ? "interactive" : "neutral"}
    >
      <div className="space-y-3">
        <div className="h-36 overflow-hidden rounded-2xl border border-ink/5 bg-white p-4">
          <div className="relative h-full w-full">
            <span className="absolute left-[12%] top-[22%] h-4 w-4 animate-pulse rounded-full bg-brand/40" />
            <span className="absolute left-[42%] top-[46%] h-8 w-8 animate-pulse rounded-full bg-lime/35 delay-150" />
            <span className="absolute right-[16%] top-[28%] h-5 w-5 animate-pulse rounded-full bg-brand/25 delay-300" />
            <span className="absolute bottom-[18%] left-[24%] h-2 w-32 animate-pulse rounded-full bg-sand" />
            <span className="absolute bottom-[32%] right-[14%] h-2 w-24 animate-pulse rounded-full bg-sand" />
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold text-ink-soft">
          <span className="material-symbols-outlined animate-spin text-[16px] text-brand" aria-hidden="true">
            progress_activity
          </span>
          {isVisual ? "Building something you can play with…" : "Getting this ready…"}
        </div>
      </div>
    </WidgetCard>
  );
}

function calculateRms(input: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < input.length; i += 1) sum += input[i] * input[i];
  return Math.sqrt(sum / Math.max(1, input.length));
}

function downsample(input: Float32Array, sourceRate: number, targetRate: number): Float32Array {
  if (sourceRate === targetRate) return input;
  const ratio = sourceRate / targetRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

function floatToPcm16(input: Float32Array): ArrayBuffer {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out.buffer;
}
