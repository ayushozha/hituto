import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { GraphCommand, SceneCommand, TextOrMathCommand } from "../types/lesson";
import { FunctionGraph } from "./FunctionGraph";
import { TeachingCanvas } from "./TeachingCanvas";

function note(overrides: Partial<TextOrMathCommand> = {}): TextOrMathCommand {
  return {
    id: "note:one",
    kind: "math",
    space: "board",
    layout: "flow",
    text: "x=4",
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

function labelBox(html: string, id: string): { x: number; y: number; width: number; height: number } {
  const pattern = new RegExp(
    `<foreignObject id="${id}" x="([-\\d.]+)" y="([-\\d.]+)" width="([\\d.]+)" height="([\\d.]+)"`,
  );
  const match = pattern.exec(html);
  if (!match) throw new Error(`no label box rendered for ${id}`);
  return { x: Number(match[1]), y: Number(match[2]), width: Number(match[3]), height: Number(match[4]) };
}

describe("teaching canvas layout", () => {
  it("stacks board notes in one measured flow region", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText="Solve 2x + 3 = 11."
        commands={[note({ id: "note:one", text: "2x+3=11" }), note({ id: "note:two", text: "2x=8" })]}
        caption="Solve it step by step."
        tutorState="speaking"
      />,
    );
    expect(html).toContain("work-notes");
    expect(html).toContain('id="note:one"');
    expect(html).toContain('id="note:two"');
  });

  it("attaches highlights to measured flow notes instead of guessed rectangles", () => {
    const commands: SceneCommand[] = [
      note({ id: "note:answer", text: "x=4" }),
      { id: "highlight:answer", kind: "highlight", space: "board", target_id: "note:answer", x: 0, y: 0, width: 0, height: 0, color: "#f4b400", opacity: 0.25 },
    ];
    const html = renderToStaticMarkup(
      <TeachingCanvas questionText="Solve x + 2 = 6." commands={commands} caption="The answer is four." tutorState="done" />,
    );
    expect(html).toContain("is-highlighted");
    expect(html).not.toContain('id="highlight:answer"');
  });

  it("renders a function and actual coordinate markers", () => {
    const graph: GraphCommand = {
      id: "graph:quadratic",
      kind: "graph",
      space: "board",
      layout: "auto",
      curves: [{ id: "curve", formula: "x^2 - 4*x + 3", color: "#1769e0", label: "" }],
      markers: [{ id: "vertex", x: 2, y: -1, color: "#d93025", label: "(2, -1)" }],
      x_min: -1,
      x_max: 5,
      y_min: -2,
      y_max: 8,
      opacity: 1,
    };
    const html = renderToStaticMarkup(<FunctionGraph command={graph} width={530} height={404} />);
    expect(html).toContain('data-graph-engine="built-in"');
    expect(html).toMatch(/<path[^>]+stroke="#1769e0"/);
    expect(html).toContain('data-graph-marker="vertex"');
    expect(html).toContain("(2, -1)");
    expect(html).not.toContain("NaN");
  });

  it("renders semantic probability and Venn visuals", () => {
    const barHtml = renderToStaticMarkup(
      <TeachingCanvas
        questionText="Use the probability distribution."
        commands={[{ id: "chart:probability", kind: "bar_chart", space: "board", layout: "auto", title: "P(X=x)", x_label: "x", y_label: "Probability", bars: [{ label: "0", value: 0.2, display_value: "0.2", color: "#1769e0" }, { label: "1", value: 0.8, display_value: "0.8", color: "#1769e0" }], opacity: 1 }]}
        caption="Read each probability."
        tutorState="speaking"
      />,
    );
    const vennHtml = renderToStaticMarkup(
      <TeachingCanvas
        questionText="Students join two clubs."
        commands={[{ id: "venn:clubs", kind: "venn", space: "board", layout: "auto", title: "Club membership", left_label: "Art", right_label: "Music", left_only: "35%", overlap: "25%", right_only: "20%", outside: "20%", opacity: 1 }]}
        caption="The overlap belongs to both sets."
        tutorState="speaking"
      />,
    );
    expect(barHtml).toContain('data-visual-engine="bar-chart"');
    expect(barHtml).toContain('data-bar-label="1"');
    expect(vennHtml).toContain('data-visual-engine="venn"');
    expect(vennHtml).toContain("25%");
  });

  it("uses equal x and y units for constructed geometry", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText="A circle has radius 4."
        commands={[{ id: "diagram:circle", kind: "circle", space: "diagram", x: 0.25, y: 0.5, radius: 0.1, color: "#1769e0", size: 0.04, opacity: 1 }]}
        caption="The radius is shown."
        tutorState="speaking"
      />,
    );
    expect(html).toContain('id="diagram:circle"');
    expect(html).toContain('cx="746"');
    expect(html).toContain('cy="502"');
  });

  it("renders a right angle as a square marker without a colliding label", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText="A right triangle has legs 3 and 4."
        commands={[
          { id: "diagram:right-angle", kind: "angle", space: "diagram", x: 0.2, y: 0.75, radius: 0.05, start_angle: -90, end_angle: 0, color: "#1769e0", size: 0.04, opacity: 1 },
          note({ id: "diagram:right-label", kind: "text", space: "diagram", layout: "absolute", text: "90°", x: 0.22, y: 0.7 }),
        ]}
        caption="This is a right angle."
        tutorState="speaking"
      />,
    );
    expect(html).toMatch(/id="diagram:right-angle" d="M [^"]+ L [^"]+ L [^"]+"/);
    expect(html).not.toContain("90°");
  });

  it("fits an uploaded image without distorting source-space annotations", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText=""
        sourceImageUrl="data:image/png;base64,AAAA"
        sourceImageSize={{ width: 400, height: 800 }}
        commands={[{ id: "source:focus", kind: "highlight", space: "source", target_id: "", x: 0.1, y: 0.2, width: 0.5, height: 0.25, color: "#f4b400", opacity: 0.25 }]}
        caption="Look at this part of the uploaded question."
        tutorState="speaking"
      />,
    );
    expect(html).toContain('href="data:image/png;base64,AAAA"');
    expect(html).toContain('id="source:focus"');
    expect(html).toContain('x="551"');
    expect(html).not.toContain("Bring me any SAT question");
  });

  it("gives an image-derived teaching diagram a large stable panel", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText=""
        sourceImageUrl="data:image/png;base64,AAAA"
        sourceImageSize={{ width: 900, height: 600 }}
        commands={[
          { id: "diagram:shape", kind: "rect", space: "diagram", x: 0.1, y: 0.1, width: 0.8, height: 0.8, preserve_aspect: true, color: "#1769e0", size: 0.04, opacity: 1 },
          note({ id: "diagram:label", kind: "text", space: "diagram", layout: "absolute", text: "A", x: 0.08, y: 0.08 }),
        ]}
        caption="I rebuilt the diagram at teaching size."
        tutorState="speaking"
      />,
    );
    expect(html).toContain("ORIGINAL QUESTION");
    expect(html).toContain("ENLARGED TEACHING DIAGRAM");
    expect(html).toContain('id="diagram:shape"');
    expect(html).toContain('x="677"');
    expect(html).toContain('width="368"');
  });

  it("centres an absolute label on the point it names", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText="Label the vertex."
        commands={[note({ id: "diagram:vertex", kind: "text", space: "diagram", layout: "absolute", text: "A", x: 0.5, y: 0.5, size: 0.045 })]}
        caption="That corner is A."
        tutorState="speaking"
      />,
    );
    const box = labelBox(html, "diagram:vertex");
    // The diagram square spans 631..1091 horizontally and 272..732 vertically,
    // so the midpoint of the panel is (861, 502).
    expect(box.x + box.width / 2).toBeCloseTo(861, 1);
    expect(box.y + box.height / 2).toBeCloseTo(502, 1);
  });

  it("separates labels that would otherwise print on top of each other", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText="Two points nearly coincide."
        commands={[
          note({ id: "diagram:b", kind: "text", space: "diagram", layout: "absolute", text: "B", x: 0.5, y: 0.5, size: 0.045 }),
          note({ id: "diagram:c", kind: "text", space: "diagram", layout: "absolute", text: "C", x: 0.5, y: 0.5, size: 0.045 }),
        ]}
        caption="Both corners are named."
        tutorState="speaking"
      />,
    );
    const first = labelBox(html, "diagram:b");
    const second = labelBox(html, "diagram:c");
    const overlapX = Math.min(first.x + first.width, second.x + second.width) - Math.max(first.x, second.x);
    const overlapY = Math.min(first.y + first.height, second.y + second.height) - Math.max(first.y, second.y);
    expect(overlapX <= 0 || overlapY <= 0).toBe(true);
  });

  it("measures a long label instead of clipping it to a fixed box", () => {
    const render = (text: string) => renderToStaticMarkup(
      <TeachingCanvas
        questionText="Measure the side."
        commands={[note({ id: "diagram:measure", kind: "text", space: "diagram", layout: "absolute", text, x: 0.5, y: 0.5, size: 0.045 })]}
        caption="The side is labelled."
        tutorState="speaking"
      />,
    );
    const short = labelBox(render("6"), "diagram:measure");
    const long = labelBox(render("perimeter = 24 cm"), "diagram:measure");
    expect(long.width).toBeGreaterThan(short.width * 3);
  });

  it("keeps a label inside its own space", () => {
    const html = renderToStaticMarkup(
      <TeachingCanvas
        questionText="Label the far corner."
        commands={[note({ id: "diagram:corner", kind: "text", space: "diagram", layout: "absolute", text: "D", x: 1, y: 1, size: 0.045 })]}
        caption="That is the far corner."
        tutorState="speaking"
      />,
    );
    const box = labelBox(html, "diagram:corner");
    expect(box.x + box.width).toBeLessThanOrEqual(1091);
    expect(box.y + box.height).toBeLessThanOrEqual(732);
  });
});
