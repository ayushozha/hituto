import { useCallback, useEffect, useState } from "react";
import { Excalidraw } from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";

interface ExcalidrawCanvasProps {
  /** Called with the board's text, read top-to-bottom, whenever it changes. */
  onExtract: (working: string) => void;
}

interface BoardElement {
  type: string;
  isDeleted?: boolean;
  text?: string;
  x: number;
  y: number;
}

/**
 * Read the student's working off the canvas.
 *
 * Only text elements are extracted: they are typed, so there is nothing to
 * recognise. Shapes and arrows are theirs to think with and are ignored.
 * Reading order is top-to-bottom, then left-to-right, which is how steps get
 * written — a line 20px lower is the next step, not a second column.
 */
function extractWorking(elements: readonly BoardElement[]): string {
  const rows = elements
    .filter((element) => element.type === "text" && !element.isDeleted && element.text?.trim())
    .slice()
    .sort((a, b) => (Math.abs(a.y - b.y) > 12 ? a.y - b.y : a.x - b.x));
  return rows.map((element) => (element.text ?? "").trim()).join("\n");
}

interface CanvasApi {
  setActiveTool: (tool: { type: string }) => void;
}

export default function ExcalidrawCanvas({ onExtract }: ExcalidrawCanvasProps) {
  const [api, setApi] = useState<CanvasApi>();

  // Open on the text tool. Otherwise writing a step means hunting for the tool
  // first, and a stray click with the default selection tool grabs an existing
  // line instead of starting a new one. Set after mount — calling it from the
  // `excalidrawAPI` callback runs before the initial app state is applied and
  // is overwritten.
  useEffect(() => {
    api?.setActiveTool({ type: "text" });
  }, [api]);
  const handleChange = useCallback(
    (elements: readonly unknown[]) => {
      onExtract(extractWorking(elements as readonly BoardElement[]));
    },
    [onExtract],
  );

  return (
    <Excalidraw
      excalidrawAPI={(instance: unknown) => setApi(instance as CanvasApi)}
      onChange={handleChange}
      initialData={{
        appState: {
          viewBackgroundColor: "#fffefb",
          // Open ready to write, not ready to select.
          activeTool: { type: "text", customType: null, locked: false, lastActiveTool: null },
        },
      }}
      UIOptions={{
        canvasActions: { loadScene: false, saveToActiveFile: false, export: false, saveAsImage: false },
      }}
    />
  );
}
