import { lazy, Suspense } from "react";

// Excalidraw is a large bundle and most sessions never open it, so it only
// loads when the student switches to "Check my work".
const ExcalidrawCanvas = lazy(() => import("./ExcalidrawCanvas"));

interface WhiteboardProps {
  onExtract: (working: string) => void;
  extracted: string;
}

export function Whiteboard({ onExtract, extracted }: WhiteboardProps) {
  const steps = extracted.split("\n").filter(Boolean).length;
  return (
    <section className="whiteboard" aria-label="Your working">
      <div className="whiteboard-header">
        <span>Write your steps — use the text tool, one step per line</span>
        <span className="whiteboard-count">
          {steps === 0 ? "nothing written yet" : `${steps} step${steps === 1 ? "" : "s"} read`}
        </span>
      </div>
      <div className="whiteboard-canvas">
        <Suspense fallback={<div className="whiteboard-loading">Opening the whiteboard…</div>}>
          <ExcalidrawCanvas onExtract={onExtract} />
        </Suspense>
      </div>
    </section>
  );
}
