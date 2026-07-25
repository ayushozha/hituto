import { useCallback, useEffect, useRef, useState } from "react";
import { Excalidraw } from "@excalidraw/excalidraw";
import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import {
  MSG_CHANGE,
  MSG_GET,
  MSG_READY,
  MSG_SCENE,
  MSG_SET,
  allowedParentOrigins,
  isAllowedOrigin,
  type WhiteboardSetMessage,
} from "./protocol";

type Scene = {
  elements: unknown[];
  appState?: Record<string, unknown>;
};

let _nonce = 1;

/** Fill required Excalidraw fields so LLM-ish partial elements still render. */
function normalizeElement(raw: unknown, index: number): Record<string, unknown> | null {
  if (!raw || typeof raw !== "object") return null;
  const el = raw as Record<string, unknown>;
  const type = typeof el.type === "string" ? el.type : "rectangle";
  const id = typeof el.id === "string" ? el.id : `el_${index}_${_nonce++}`;
  const base: Record<string, unknown> = {
    type,
    id,
    x: Number(el.x) || 0,
    y: Number(el.y) || 0,
    width: Number(el.width) || (type === "text" ? 120 : 100),
    height: Number(el.height) || (type === "text" ? 40 : 80),
    angle: Number(el.angle) || 0,
    strokeColor: typeof el.strokeColor === "string" ? el.strokeColor : "#1e1e1e",
    backgroundColor: typeof el.backgroundColor === "string" ? el.backgroundColor : "transparent",
    fillStyle: typeof el.fillStyle === "string" ? el.fillStyle : "solid",
    strokeWidth: Number(el.strokeWidth) || 2,
    strokeStyle: typeof el.strokeStyle === "string" ? el.strokeStyle : "solid",
    roughness: el.roughness == null ? 1 : Number(el.roughness),
    opacity: el.opacity == null ? 100 : Number(el.opacity),
    groupIds: Array.isArray(el.groupIds) ? el.groupIds : [],
    frameId: el.frameId ?? null,
    roundness: el.roundness ?? (type === "rectangle" ? { type: 3 } : null),
    seed: typeof el.seed === "number" ? el.seed : Math.floor(Math.random() * 2 ** 31),
    version: typeof el.version === "number" ? el.version : 1,
    versionNonce: typeof el.versionNonce === "number" ? el.versionNonce : _nonce++,
    isDeleted: Boolean(el.isDeleted),
    boundElements: Array.isArray(el.boundElements) ? el.boundElements : null,
    updated: typeof el.updated === "number" ? el.updated : Date.now(),
    link: el.link ?? null,
    locked: Boolean(el.locked),
  };

  if (type === "text") {
    base.text = typeof el.text === "string" ? el.text : "";
    base.fontSize = Number(el.fontSize) || 20;
    base.fontFamily = Number(el.fontFamily) || 1;
    base.textAlign = typeof el.textAlign === "string" ? el.textAlign : "left";
    base.verticalAlign = typeof el.verticalAlign === "string" ? el.verticalAlign : "top";
    base.containerId = el.containerId ?? null;
    base.originalText = typeof el.originalText === "string" ? el.originalText : base.text;
    base.lineHeight = Number(el.lineHeight) || 1.25;
    base.autoResize = el.autoResize !== false;
  }

  if (type === "arrow" || type === "line") {
    const pts = Array.isArray(el.points) ? el.points : [[0, 0], [Number(el.width) || 100, 0]];
    base.points = pts;
    base.lastCommittedPoint = null;
    base.startBinding = el.startBinding ?? null;
    base.endBinding = el.endBinding ?? null;
    base.startArrowhead = el.startArrowhead ?? null;
    base.endArrowhead = type === "arrow" ? (el.endArrowhead ?? "arrow") : (el.endArrowhead ?? null);
  }

  if (type === "freedraw") {
    base.points = Array.isArray(el.points) ? el.points : [];
    base.pressures = Array.isArray(el.pressures) ? el.pressures : [];
    base.simulatePressure = el.simulatePressure !== false;
  }

  return base;
}

function normalizeElements(raw: unknown): unknown[] {
  if (!Array.isArray(raw)) return [];
  const out: unknown[] = [];
  raw.forEach((el, i) => {
    const n = normalizeElement(el, i);
    if (n) out.push(n);
  });
  return out;
}

export default function App() {
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null);
  const parentOriginRef = useRef<string | null>(null);
  const changeTimerRef = useRef<number | null>(null);
  const [scene, setScene] = useState<Scene>({ elements: [] });
  const [ready, setReady] = useState(false);

  const applyScene = useCallback((next: Scene) => {
    setScene(next);
    const api = apiRef.current;
    if (!api) return;
    api.updateScene({
      elements: next.elements as never[],
      ...(next.appState ? { appState: next.appState as never } : {}),
    });
    try {
      api.scrollToContent(undefined, { fitToContent: true, animate: false });
    } catch {
      /* empty scene */
    }
  }, []);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!isAllowedOrigin(event.origin)) return;
      const data = event.data as WhiteboardSetMessage | { type?: string } | null;
      if (!data) return;

      if (data.type === MSG_GET) {
        parentOriginRef.current = event.origin;
        const currentElements = apiRef.current?.getSceneElements() ?? [];
        window.parent?.postMessage(
          { type: MSG_SCENE, elements: Array.from(currentElements) },
          event.origin,
        );
        return;
      }
      if (data.type !== MSG_SET) return;

      parentOriginRef.current = event.origin;
      const setMessage = data as WhiteboardSetMessage;
      applyScene({
        elements: normalizeElements(setMessage.elements),
        appState:
          setMessage.appState && typeof setMessage.appState === "object"
            ? setMessage.appState
            : undefined,
      });
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [applyScene]);

  useEffect(() => {
    if (!ready) return;
    const targets = new Set<string>([
      ...(parentOriginRef.current ? [parentOriginRef.current] : []),
      ...allowedParentOrigins(),
    ]);
    for (const origin of targets) {
      try {
        window.parent?.postMessage({ type: MSG_READY }, origin);
      } catch {
        /* cross-origin / no parent */
      }
    }
  }, [ready]);

  useEffect(
    () => () => {
      if (changeTimerRef.current !== null) window.clearTimeout(changeTimerRef.current);
    },
    [],
  );

  const publishChange = useCallback((elements: readonly unknown[]) => {
    if (changeTimerRef.current !== null) window.clearTimeout(changeTimerRef.current);
    changeTimerRef.current = window.setTimeout(() => {
      const targets = new Set<string>([
        ...(parentOriginRef.current ? [parentOriginRef.current] : []),
        ...allowedParentOrigins(),
      ]);
      for (const origin of targets) {
        try {
          window.parent?.postMessage({ type: MSG_CHANGE, elements: Array.from(elements) }, origin);
        } catch {
          /* cross-origin / no parent */
        }
      }
    }, 250);
  }, []);

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <Excalidraw
        onChange={(elements) => publishChange(elements)}
        excalidrawAPI={(api) => {
          apiRef.current = api;
          if (!ready) setReady(true);
          if (scene.elements.length) {
            api.updateScene({
              elements: scene.elements as never[],
              ...(scene.appState ? { appState: scene.appState as never } : {}),
            });
          }
        }}
        initialData={{
          elements: scene.elements as never[],
          appState: {
            viewBackgroundColor: "#FDF1E7",
            ...(scene.appState ?? {}),
          },
        }}
        UIOptions={{
          canvasActions: {
            changeViewBackgroundColor: false,
            clearCanvas: false,
            export: false,
            loadScene: false,
            saveToActiveFile: false,
            toggleTheme: false,
            saveAsImage: true,
          },
        }}
      />
    </div>
  );
}
