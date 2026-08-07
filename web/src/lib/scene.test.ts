import { describe, expect, it } from "vitest";
import { lessonPlanSchema, sceneCommandSchema, type SceneCommand, type TextOrMathCommand } from "../types/lesson";
import { applySceneCommand, emptyScene } from "./scene";

function note(overrides: Partial<TextOrMathCommand> = {}): TextOrMathCommand {
  return {
    id: "work:one",
    kind: "text",
    space: "board",
    layout: "flow",
    text: "x = 4",
    color: "#1769e0",
    size: 0.04,
    opacity: 1,
    x: 0,
    y: 0,
    width: 0,
    height: 0,
    ...overrides,
  } as TextOrMathCommand;
}

describe("scene command validation", () => {
  it("rejects executable or unknown command kinds", () => {
    expect(() => sceneCommandSchema.parse({ id: "bad", kind: "javascript" })).toThrow();
  });

  it("rejects coordinates outside the normalized canvas", () => {
    expect(() => sceneCommandSchema.parse({ id: "circle", kind: "circle", x: 1.2, y: 0.5, radius: 0.1 })).toThrow();
  });

  it("requires a stable target for erase", () => {
    expect(() => sceneCommandSchema.parse({ id: "erase:one", kind: "erase" })).toThrow();
  });

  it("accepts a semantic graph with real markers", () => {
    const graph = sceneCommandSchema.parse({
      id: "graph:quadratic",
      kind: "graph",
      curves: [{ id: "curve", formula: "x^2 - 4*x + 3" }],
      markers: [{ id: "vertex", x: 2, y: -1, label: "(2, -1)" }],
      x_min: -1,
      x_max: 5,
      y_min: -2,
      y_max: 8,
    });
    expect(graph.kind).toBe("graph");
    if (graph.kind === "graph") expect(graph.markers[0].y).toBe(-1);
  });
});

describe("scene reducer", () => {
  it("replaces an element with the same stable id", () => {
    const first = applySceneCommand(emptyScene, note({ text: "x = 3" }));
    const second = applySceneCommand(first, note({ text: "x = 4" }));
    expect(second.elements).toHaveLength(1);
    expect(second.elements[0].kind).toBe("text");
    if (second.elements[0].kind === "text") expect(second.elements[0].text).toBe("x = 4");
  });

  it("erases one target without touching the rest of the board", () => {
    const first = applySceneCommand(emptyScene, note());
    const second = applySceneCommand(first, note({ id: "work:two", text: "y = 8" }));
    const erase: SceneCommand = { id: "erase:one", kind: "erase", target_id: "work:one" };
    const erased = applySceneCommand(second, erase);
    expect(erased.elements.map((item) => item.id)).toEqual(["work:two"]);
  });

  it("keeps camera state separate from drawable elements", () => {
    const scene = applySceneCommand(emptyScene, { id: "camera:focus", kind: "camera", space: "board", x: 0, y: 0, width: 0.5, height: 0.5 });
    expect(scene.elements).toEqual([]);
    expect(scene.camera?.id).toBe("camera:focus");
  });

  it("keeps exactly one deterministic visual panel", () => {
    const graph: SceneCommand = { id: "graph:one", kind: "graph", space: "board", layout: "auto", curves: [{ id: "curve", formula: "x^2", color: "#1769e0", label: "" }], markers: [], x_min: -2, x_max: 2, y_min: -1, y_max: 4, opacity: 1 };
    const chart: SceneCommand = { id: "chart:one", kind: "bar_chart", space: "board", layout: "auto", title: "Distribution", x_label: "x", y_label: "P(X=x)", bars: [{ label: "0", value: 0.4, display_value: "", color: "#1769e0" }, { label: "1", value: 0.6, display_value: "", color: "#1769e0" }], opacity: 1 };
    const withGraph = applySceneCommand(emptyScene, graph);
    const withChart = applySceneCommand(withGraph, chart);
    expect(withChart.elements.map((element) => element.kind)).toEqual(["bar_chart"]);
  });
});

describe("lesson plan validation", () => {
  it("accepts a bounded two-beat lesson", () => {
    const plan = lessonPlanSchema.parse({
      domain: "math",
      question_summary: "Solve a linear equation.",
      final_answer: "4",
      answer_explanation: "Substitution confirms the answer.",
      confidence: 0.98,
      beats: [
        { id: "beat:one", teaching_goal: "Identify the inverse operation", spoken_text: "We need to undo the addition first.", caption: "Undo the addition.", strategy: "algebra", commands: [note()], pause_after_ms: 0, checkpoint: false },
        { id: "beat:two", teaching_goal: "Confirm the result", spoken_text: "Substitute four to check the original equation.", caption: "Check the answer.", strategy: "substitution", commands: [note({ id: "work:check", text: "4 + 2 = 6" })], pause_after_ms: 0, checkpoint: false },
      ],
    });
    expect(plan.beats).toHaveLength(2);
  });
});
