import { useCallback } from "react";
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

export default function ExcalidrawCanvas({ onExtract }: ExcalidrawCanvasProps) {
  const handleChange = useCallback(
    (elements: readonly unknown[]) => {
      onExtract(extractWorking(elements as readonly BoardElement[]));
    },
    [onExtract],
  );

  return (
    <Excalidraw
      onChange={handleChange}
      initialData={{ appState: { viewBackgroundColor: "#fffefb" } }}
      UIOptions={{
        canvasActions: { loadScene: false, saveToActiveFile: false, export: false, saveAsImage: false },
      }}
    />
  );
}
