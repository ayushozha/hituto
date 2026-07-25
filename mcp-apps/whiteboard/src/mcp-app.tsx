import { StrictMode, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Excalidraw } from "@excalidraw/excalidraw";
import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import { App } from "@modelcontextprotocol/ext-apps";
import { normalizeElements } from "./normalize";
import "@excalidraw/excalidraw/index.css";

type BoardPayload = {
  title?: string;
  intent?: string;
  caption?: string;
  elements?: unknown[];
};

const DEMO: BoardPayload = {
  title: "Water cycle",
  intent: "Trace evaporation → condensation → precipitation",
  elements: [
    {
      type: "ellipse",
      id: "sun",
      x: 40,
      y: 40,
      width: 80,
      height: 80,
      backgroundColor: "#fbbf24",
      strokeColor: "#b45309",
    },
    {
      type: "text",
      id: "sun_label",
      x: 55,
      y: 70,
      width: 50,
      height: 24,
      text: "Sun",
      fontSize: 18,
    },
    {
      type: "rectangle",
      id: "ocean",
      x: 40,
      y: 220,
      width: 220,
      height: 70,
      backgroundColor: "#93c5fd",
      strokeColor: "#1d4ed8",
    },
    {
      type: "text",
      id: "ocean_label",
      x: 110,
      y: 245,
      width: 80,
      height: 24,
      text: "Ocean",
      fontSize: 18,
    },
    {
      type: "arrow",
      id: "up",
      x: 150,
      y: 130,
      width: 0,
      height: 80,
      points: [
        [0, 80],
        [0, 0],
      ],
      endArrowhead: "arrow",
      strokeColor: "#0f172a",
    },
    {
      type: "text",
      id: "evap",
      x: 160,
      y: 150,
      width: 110,
      height: 24,
      text: "evaporation",
      fontSize: 16,
    },
  ],
};

function Board({
  title,
  intent,
  elements,
}: {
  title: string;
  intent: string;
  elements: unknown[];
}) {
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null);
  const [ready, setReady] = useState(false);

  const applyScene = useCallback((next: unknown[]) => {
    const api = apiRef.current;
    if (!api) return;
    api.updateScene({ elements: next as never[] });
    try {
      api.scrollToContent(undefined, { fitToContent: true, animate: false });
    } catch {
      /* empty */
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    applyScene(elements);
  }, [ready, elements, applyScene]);

  return (
    <div className="shell">
      <header className="topbar">
        <h1>{title || "Whiteboard"}</h1>
        {intent ? <p>{intent}</p> : null}
      </header>
      <div className="canvas">
        <Excalidraw
          excalidrawAPI={(api) => {
            apiRef.current = api;
            if (!ready) setReady(true);
          }}
          initialData={{
            elements: elements as never[],
            appState: { viewBackgroundColor: "#FDF1E7" },
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
    </div>
  );
}

function parsePayload(raw: unknown): BoardPayload {
  if (!raw || typeof raw !== "object") return {};
  const obj = raw as Record<string, unknown>;
  // Hosts sometimes wrap structuredContent as { content: "..." } JSON text only.
  return {
    title: typeof obj.title === "string" ? obj.title : undefined,
    intent: typeof obj.intent === "string" ? obj.intent : undefined,
    caption: typeof obj.caption === "string" ? obj.caption : undefined,
    elements: Array.isArray(obj.elements) ? obj.elements : undefined,
  };
}

function render(payload: BoardPayload) {
  const root = document.getElementById("root");
  if (!root) return;
  createRoot(root).render(
    <StrictMode>
      <Board
        title={payload.title || "Whiteboard"}
        intent={payload.intent || payload.caption || ""}
        elements={normalizeElements(payload.elements)}
      />
    </StrictMode>,
  );
}

const mcp = new App({ name: "Hi Tuto Whiteboard", version: "0.1.0" });

mcp.ontoolresult = (result) => {
  const structured = result.structuredContent;
  if (structured && typeof structured === "object") {
    render(parsePayload(structured));
    return;
  }
  const text = result.content?.find((c) => c.type === "text" && "text" in c);
  if (text && "text" in text) {
    try {
      render(parsePayload(JSON.parse(String(text.text))));
      return;
    } catch {
      /* ignore */
    }
  }
};

(async () => {
  const demoMode =
    new URLSearchParams(location.search).has("demo") || window.parent === window;

  if (!demoMode) {
    try {
      await mcp.connect();
    } catch {
      /* host unavailable */
    }
  }

  render(demoMode ? DEMO : { title: "Whiteboard", elements: [] });
})();
