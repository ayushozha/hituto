import { lazy, Suspense } from "react";

// Excalidraw is a large bundle and most sessions never open it, so it only
// loads when the student switches to "Check my work".
const ExcalidrawCanvas = lazy(() => import("./ExcalidrawCanvas"));

interface WhiteboardProps {
  onExtract: (working: string) => void;
  extracted: string;
  collapsed: boolean;
  onToggle: () => void;
}

export function Whiteboard({ onExtract, extracted, collapsed, onToggle }: WhiteboardProps) {
  const steps = extracted.split("\n").filter(Boolean).length;
  const read = steps === 0 ? "nothing written yet" : `${steps} step${steps === 1 ? "" : "s"} read`;
  return (
    <section className={`whiteboard${collapsed ? " is-collapsed" : ""}`} aria-label="Your working">
      <div className="whiteboard-header">
        <span>
          {collapsed ? "Your working is still here" : "Write your steps — use the text tool, one step per line"}
        </span>
        <span className="whiteboard-count">{read}</span>
        <button type="button" className="whiteboard-toggle" onClick={onToggle}>
          {collapsed ? "Show board" : "Hide board"}
        </button>
      </div>
      {/* Kept mounted while collapsed so the scene is not thrown away. */}
      <div className="whiteboard-canvas" aria-hidden={collapsed}>
        <Suspense fallback={<div className="whiteboard-loading">Opening the whiteboard…</div>}>
          <ExcalidrawCanvas onExtract={onExtract} />
        </Suspense>
      </div>
    </section>
  );
}
