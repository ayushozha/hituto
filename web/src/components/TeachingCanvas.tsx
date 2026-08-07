import { useMemo } from "react";
import katex from "katex";
import { FunctionGraph } from "./FunctionGraph";
import { BarChart, VennDiagram } from "./SemanticVisuals";
import type {
  BarChartCommand,
  CameraCommand,
  GraphCommand,
  HighlightCommand,
  SceneCommand,
  TextOrMathCommand,
  TutorState,
  VennCommand,
} from "../types/lesson";

const BOARD_WIDTH = 1200;
const BOARD_HEIGHT = 760;
const VISUAL_PANEL = { x: 546, y: 272, width: 630, height: 460 };

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface TeachingCanvasProps {
  questionText: string;
  sourceImageUrl?: string;
  sourceImageSize?: { width: number; height: number };
  commands: SceneCommand[];
  camera?: CameraCommand;
  caption: string;
  tutorState: TutorState;
  errorMessage?: string;
}

function sourceRect(imageSize?: { width: number; height: number }, compact = false): Rect {
  if (!imageSize || imageSize.width <= 0 || imageSize.height <= 0) {
    return { x: 58, y: 46, width: 1084, height: 205 };
  }
  const area = compact
    ? { x: 58, y: 30, width: 470, height: 205 }
    : { x: 58, y: 30, width: 1084, height: 245 };
  const scale = Math.min(area.width / imageSize.width, area.height / imageSize.height);
  const width = imageSize.width * scale;
  const height = imageSize.height * scale;
  return {
    x: area.x + (area.width - width) / 2,
    y: area.y + (area.height - height) / 2,
    width,
    height,
  };
}

interface Positioned {
  space: "board" | "source" | "diagram";
  x: number;
  y: number;
}

interface Sized extends Positioned {
  width: number;
  height: number;
  preserve_aspect?: boolean;
}

function point(command: Positioned, rect: Rect, x = command.x, y = command.y) {
  if (command.space === "source") {
    return { x: rect.x + x * rect.width, y: rect.y + y * rect.height };
  }
  if (command.space === "diagram") {
    const square = diagramSquare();
    return { x: square.x + x * square.width, y: square.y + y * square.height };
  }
  return { x: x * BOARD_WIDTH, y: y * BOARD_HEIGHT };
}

/**
 * The reserved geometry panel, always square so that equal coordinate
 * differences render as equal physical lengths.
 */
function diagramSquare(): Rect {
  const unit = Math.min(VISUAL_PANEL.width, VISUAL_PANEL.height);
  return {
    x: VISUAL_PANEL.x + (VISUAL_PANEL.width - unit) / 2,
    y: VISUAL_PANEL.y + (VISUAL_PANEL.height - unit) / 2,
    width: unit,
    height: unit,
  };
}

function dimensions(command: Sized, rect: Rect) {
  if (command.space === "diagram") {
    const unit = diagramSquare().width;
    return { width: command.width * unit, height: command.height * unit };
  }
  if (command.preserve_aspect) {
    const unit = command.space === "source" ? Math.min(rect.width, rect.height) : Math.min(BOARD_WIDTH, BOARD_HEIGHT);
    return { width: command.width * unit, height: command.height * unit };
  }
  return command.space === "source"
    ? { width: command.width * rect.width, height: command.height * rect.height }
    : { width: command.width * BOARD_WIDTH, height: command.height * BOARD_HEIGHT };
}

function unitScale(command: Pick<Positioned, "space">, rect: Rect): number {
  if (command.space === "source") return Math.min(rect.width, rect.height);
  if (command.space === "diagram") return diagramSquare().width;
  return Math.min(BOARD_WIDTH, BOARD_HEIGHT);
}

/** The region an absolute label may occupy, so a label never escapes its space. */
function spaceBounds(space: Positioned["space"], rect: Rect): Rect {
  if (space === "source") return rect;
  if (space === "diagram") return diagramSquare();
  return { x: 16, y: 16, width: BOARD_WIDTH - 32, height: BOARD_HEIGHT - 32 };
}

function MathContent({ text }: { text: string }) {
  const latex = text
    .replaceAll("½", "\\frac{1}{2}")
    .replaceAll("¼", "\\frac{1}{4}")
    .replaceAll("¾", "\\frac{3}{4}");
  const html = useMemo(
    () => katex.renderToString(latex, {
      throwOnError: false,
      strict: "warn",
      trust: false,
      displayMode: false,
    }),
    [latex],
  );
  return <span className="math-ink" dangerouslySetInnerHTML={{ __html: html }} />;
}

function isMath(command: TextOrMathCommand): boolean {
  return command.kind === "math" || (command.kind === "text" && /\\[a-zA-Z]+/.test(command.text));
}

function colorWithAlpha(color: string, alpha: number): string {
  const match = /^#([0-9a-f]{6})$/i.exec(color);
  if (!match) return `rgba(255, 193, 7, ${alpha})`;
  const value = Number.parseInt(match[1], 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

interface LabelBox extends Rect {
  command: TextOrMathCommand;
  fontSize: number;
}

/**
 * How wide the label reads once rendered. A LaTeX source string is a poor
 * proxy for its rendered width, so control sequences collapse to one glyph.
 */
function renderedLength(text: string, math: boolean): number {
  const visible = math
    ? text.replaceAll(/\\[a-zA-Z]+/g, "n").replaceAll(/[{}\\$]/g, "")
    : text;
  return Math.max(1, visible.trim().length);
}

function clampBox(box: Rect, bounds: Rect): Rect {
  return {
    ...box,
    x: Math.max(bounds.x, Math.min(bounds.x + bounds.width - box.width, box.x)),
    y: Math.max(bounds.y, Math.min(bounds.y + bounds.height - box.height, box.y)),
  };
}

/**
 * Lay out every absolute label at once.
 *
 * A label's (x, y) is the point it names — a vertex, a segment midpoint, a
 * feature in the source image — so the box is centred on it rather than
 * hung from its top-left corner. Boxes are then measured from the text and
 * nudged apart, because neither the planner nor the vision model can know
 * the rendered size of what it asked for.
 */
function layoutLabels(commands: TextOrMathCommand[], rect: Rect): LabelBox[] {
  const boxes: LabelBox[] = commands.map((command) => {
    const anchor = point(command, rect);
    const requested = dimensions(command, rect);
    const math = isMath(command);
    const referenceHeight = command.space === "source"
      ? rect.height
      : command.space === "diagram"
        ? unitScale(command, rect)
        : BOARD_HEIGHT;
    const fontSize = Math.max(14, Math.min(64, command.size * referenceHeight));
    // An explicit width/height is a floor, never a clip: a label that is
    // wider than the model guessed must still be readable.
    const width = Math.max(requested.width, renderedLength(command.text, math) * fontSize * 0.6 + 14);
    const height = Math.max(requested.height, fontSize * 1.5 + 6);
    const bounds = spaceBounds(command.space, rect);
    return {
      command,
      fontSize,
      ...clampBox({ x: anchor.x - width / 2, y: anchor.y - height / 2, width, height }, bounds),
    };
  });

  // Separate overlapping labels along their shallower axis. Labels are the
  // only board content whose size the renderer alone knows, so this is the
  // one place collisions can be resolved.
  for (let pass = 0; pass < 24; pass += 1) {
    let moved = false;
    for (let a = 0; a < boxes.length; a += 1) {
      for (let b = a + 1; b < boxes.length; b += 1) {
        const first = boxes[a];
        const second = boxes[b];
        if (first.command.space !== second.command.space) continue;
        const overlapX = Math.min(first.x + first.width, second.x + second.width) - Math.max(first.x, second.x);
        const overlapY = Math.min(first.y + first.height, second.y + second.height) - Math.max(first.y, second.y);
        if (overlapX <= 0 || overlapY <= 0) continue;
        const bounds = spaceBounds(first.command.space, rect);
        const push = 0.5;
        if (overlapY <= overlapX) {
          const shift = (overlapY + 1) * push;
          const direction = first.y <= second.y ? -1 : 1;
          boxes[a] = { ...first, ...clampBox({ ...first, y: first.y + shift * direction }, bounds) };
          boxes[b] = { ...second, ...clampBox({ ...second, y: second.y - shift * direction }, bounds) };
        } else {
          const shift = (overlapX + 1) * push;
          const direction = first.x <= second.x ? -1 : 1;
          boxes[a] = { ...first, ...clampBox({ ...first, x: first.x + shift * direction }, bounds) };
          boxes[b] = { ...second, ...clampBox({ ...second, x: second.x - shift * direction }, bounds) };
        }
        moved = true;
      }
    }
    if (!moved) break;
  }
  return boxes;
}

function LabelMarkup({ box }: { box: LabelBox }) {
  const { command, fontSize } = box;
  return (
    <foreignObject
      id={command.id}
      x={box.x}
      y={box.y}
      width={box.width}
      height={box.height}
      className="scene-enter"
      opacity={command.opacity}
      overflow="visible"
    >
      <div className={isMath(command) ? "absolute-note math-note" : "absolute-note handwritten-text"} style={{ color: command.color, fontSize }}>
        <span className="label-chip">
          {isMath(command) ? <MathContent text={command.text} /> : command.text}
        </span>
      </div>
    </foreignObject>
  );
}

function workRect(hasVisual: boolean): Rect {
  return hasVisual
    ? { x: 62, y: 272, width: 462, height: 460 }
    : { x: 62, y: 292, width: 1076, height: 320 };
}

function FlowNotes({
  commands,
  highlights,
  hasVisual,
  overSource,
}: {
  commands: TextOrMathCommand[];
  highlights: HighlightCommand[];
  hasVisual: boolean;
  overSource: boolean;
}) {
  const rect = workRect(hasVisual);
  if (!commands.length) return null;
  const fontCap = commands.length >= 5 ? 22 : commands.length === 4 ? 26 : 30;
  const densityClass = commands.length >= 5 ? " is-compact" : commands.length === 4 ? " is-dense" : "";
  return (
    <foreignObject x={rect.x} y={rect.y} width={rect.width} height={rect.height} className="flow-notes-layer">
      <div className={`work-notes${overSource ? " on-source" : ""}${densityClass}`}>
        {commands.map((command) => {
          const highlight = highlights.find((item) => item.target_id === command.id);
          const fontSize = isMath(command)
            ? Math.max(17, Math.min(fontCap, command.size * BOARD_HEIGHT))
            : Math.max(17, Math.min(fontCap + 4, command.size * BOARD_HEIGHT));
          return (
            <div
              id={command.id}
              key={command.id}
              className={`flow-note scene-enter${isMath(command) ? " math-note" : " handwritten-text"}${highlight ? " is-highlighted" : ""}`}
              style={{
                color: command.color,
                fontSize,
                opacity: command.opacity,
                backgroundColor: highlight ? colorWithAlpha(highlight.color, 0.2) : undefined,
                borderColor: highlight ? colorWithAlpha(highlight.color, 0.7) : undefined,
              }}
            >
              {isMath(command) ? <MathContent text={command.text} /> : command.text}
            </div>
          );
        })}
      </div>
    </foreignObject>
  );
}

function AutoVisualMarkup({ command }: { command: GraphCommand | BarChartCommand | VennCommand }) {
  const width = VISUAL_PANEL.width;
  const height = VISUAL_PANEL.height;
  return (
    <foreignObject
      id={command.id}
      x={VISUAL_PANEL.x}
      y={VISUAL_PANEL.y}
      width={width}
      height={height}
      className="scene-enter graph-foreign-object"
      opacity={command.opacity}
    >
      {command.kind === "graph" && <FunctionGraph command={command} width={width} height={height} />}
      {command.kind === "bar_chart" && <BarChart command={command} width={width} height={height} />}
      {command.kind === "venn" && <VennDiagram command={command} width={width} height={height} />}
    </foreignObject>
  );
}

function CommandMarkup({ command, rect }: { command: SceneCommand; rect: Rect }) {
  if (command.kind === "highlight" && command.target_id) return null;
  if (command.kind === "graph" || command.kind === "bar_chart" || command.kind === "venn") {
    return <AutoVisualMarkup command={command} />;
  }
  // Flow notes and absolute labels are both laid out collectively, above.
  if (command.kind === "text" || command.kind === "math") return null;

  if (command.kind === "erase" || command.kind === "clear" || command.kind === "camera") return null;

  if (command.kind === "polyline") {
    const points = command.points.map((item) => point({ ...item, space: command.space }, rect));
    return (
      <polyline
        id={command.id}
        points={points.map((item) => `${item.x},${item.y}`).join(" ")}
        fill="none"
        stroke={command.color}
        opacity={command.opacity}
        strokeWidth={Math.max(3, command.size * 95)}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="draw-path"
      />
    );
  }

  const start = point(command, rect);
  const strokeWidth = command.kind === "highlight" ? 3 : Math.max(3, command.size * 95);

  if (command.kind === "line" || command.kind === "arrow") {
    const end = point(command, rect, command.x2, command.y2);
    return (
      <line
        id={command.id}
        x1={start.x}
        y1={start.y}
        x2={end.x}
        y2={end.y}
        stroke={command.color}
        opacity={command.opacity}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        markerEnd={command.kind === "arrow" ? "url(#arrowhead)" : undefined}
        className="draw-path"
      />
    );
  }

  if (command.kind === "rect" || command.kind === "highlight") {
    const size = dimensions(command, rect);
    return (
      <rect
        id={command.id}
        x={start.x}
        y={start.y}
        width={size.width}
        height={size.height}
        rx={command.kind === "highlight" ? 12 : 5}
        fill={command.kind === "highlight" ? command.color : "none"}
        fillOpacity={command.kind === "highlight" ? Math.min(0.3, command.opacity) : 0}
        stroke={command.kind === "rect" ? command.color : "none"}
        strokeWidth={strokeWidth}
        className="scene-enter"
      />
    );
  }

  if (command.kind === "circle") {
    return (
      <circle
        id={command.id}
        cx={start.x}
        cy={start.y}
        r={Math.max(8, command.radius * unitScale(command, rect))}
        fill="none"
        stroke={command.color}
        opacity={command.opacity}
        strokeWidth={strokeWidth}
        className="draw-path"
      />
    );
  }

  if (command.kind === "bracket") {
    const end = point(command, rect, command.x2, command.y2);
    const horizontal = Math.abs(end.x - start.x) > Math.abs(end.y - start.y);
    const inset = 12;
    const path = horizontal
      ? `M ${start.x} ${start.y + inset} Q ${start.x} ${start.y} ${start.x + inset} ${start.y} L ${end.x - inset} ${end.y} Q ${end.x} ${end.y} ${end.x} ${end.y + inset}`
      : `M ${start.x + inset} ${start.y} Q ${start.x} ${start.y} ${start.x} ${start.y + inset} L ${end.x} ${end.y - inset} Q ${end.x} ${end.y} ${end.x + inset} ${end.y}`;
    return <path id={command.id} d={path} fill="none" stroke={command.color} strokeWidth={strokeWidth} strokeLinecap="round" className="draw-path" />;
  }

  if (command.kind === "angle") {
    const radius = Math.max(18, command.radius * unitScale(command, rect));
    const startRadians = (command.start_angle * Math.PI) / 180;
    const endRadians = (command.end_angle * Math.PI) / 180;
    const arcStart = { x: start.x + radius * Math.cos(startRadians), y: start.y + radius * Math.sin(startRadians) };
    const arcEnd = { x: start.x + radius * Math.cos(endRadians), y: start.y + radius * Math.sin(endRadians) };
    const delta = ((command.end_angle - command.start_angle) % 360 + 360) % 360;
    const isRightAngle = Math.abs(delta - 90) < 0.5;
    const corner = {
      x: arcStart.x + radius * Math.cos(endRadians),
      y: arcStart.y + radius * Math.sin(endRadians),
    };
    return (
      <path
        id={command.id}
        d={isRightAngle
          ? `M ${arcStart.x} ${arcStart.y} L ${corner.x} ${corner.y} L ${arcEnd.x} ${arcEnd.y}`
          : `M ${arcStart.x} ${arcStart.y} A ${radius} ${radius} 0 ${delta > 180 ? 1 : 0} 1 ${arcEnd.x} ${arcEnd.y}`}
        fill="none"
        stroke={command.color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        className="draw-path"
      />
    );
  }
  return null;
}

function cameraViewBox(camera: CameraCommand | undefined, rect: Rect): string {
  if (!camera) return `0 0 ${BOARD_WIDTH} ${BOARD_HEIGHT}`;
  const start = point(camera, rect);
  const size = dimensions(camera, rect);
  const width = Math.max(260, size.width || BOARD_WIDTH * 0.55);
  const height = Math.max(180, size.height || BOARD_HEIGHT * 0.55);
  const x = Math.max(0, Math.min(BOARD_WIDTH - width, start.x));
  const y = Math.max(0, Math.min(BOARD_HEIGHT - height, start.y));
  return `${x} ${y} ${width} ${height}`;
}

export function TeachingCanvas({
  questionText,
  sourceImageUrl,
  sourceImageSize,
  commands,
  camera,
  caption,
  tutorState,
  errorMessage,
}: TeachingCanvasProps) {
  const hasQuestion = Boolean(questionText.trim() || sourceImageUrl);
  const hasRightAngleMarker = commands.some((command) => {
    if (command.kind !== "angle" || command.space !== "diagram") return false;
    const delta = ((command.end_angle - command.start_angle) % 360 + 360) % 360;
    return Math.abs(delta - 90) < 0.5;
  });
  const angleCleanedCommands = commands.filter((command) => !(
    hasRightAngleMarker &&
    (command.kind === "text" || command.kind === "math") &&
    command.space === "diagram" &&
    /^\\?90(?:\\?circ|°)?$/i.test(command.text.trim().replaceAll(" ", ""))
  ));
  const hasFlowCandidate = angleCleanedCommands.some((command) =>
    (command.kind === "text" || command.kind === "math") && command.space === "board" && command.layout === "flow",
  );
  const displayCommands = angleCleanedCommands.filter((command) => !(
    hasFlowCandidate && command.kind === "highlight" && command.space === "board" && !command.target_id
  ));
  const hasGraph = displayCommands.some((command) => ["graph", "bar_chart", "venn"].includes(command.kind));
  const hasDiagram = displayCommands.some((command) =>
    "space" in command && command.space === "diagram" && !["erase", "clear", "camera"].includes(command.kind),
  );
  const rect = sourceRect(sourceImageUrl ? sourceImageSize : undefined, Boolean(sourceImageUrl && hasDiagram));
  const hasVisual = hasGraph || hasDiagram;
  const flowCommands = displayCommands.filter((command): command is TextOrMathCommand =>
    (command.kind === "text" || command.kind === "math") && command.layout === "flow" && command.space === "board",
  );
  const flowHighlights = displayCommands.filter((command): command is HighlightCommand =>
    command.kind === "highlight" && command.space === "board" && Boolean(command.target_id),
  );
  const labelBoxes = layoutLabels(
    displayCommands.filter((command): command is TextOrMathCommand =>
      (command.kind === "text" || command.kind === "math") && command.layout !== "flow",
    ),
    rect,
  );

  return (
    <section className="teaching-surface" aria-label="Live teaching canvas">
      <svg
        className="teaching-canvas"
        viewBox={cameraViewBox(camera, rect)}
        role="img"
        aria-label="The SAT question and the tutor's live written explanation"
      >
        <defs>
          <filter id="paperShadow" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="7" stdDeviation="10" floodColor="#23303f" floodOpacity="0.08" />
          </filter>
          <marker id="arrowhead" markerWidth="12" markerHeight="12" refX="9" refY="6" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 10 6 L 0 12 z" fill="context-stroke" />
          </marker>
          <pattern id="paperDots" width="30" height="30" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1.2" fill="#dfe5e9" />
          </pattern>
        </defs>

        <rect x="8" y="8" width="1184" height="744" rx="26" fill="#fffefb" filter="url(#paperShadow)" />
        <rect x="8" y="8" width="1184" height="744" rx="26" fill="url(#paperDots)" opacity="0.38" />

        {sourceImageUrl ? (
          <g className="source-image">
            <rect
              x={rect.x - 7}
              y={rect.y - 7}
              width={rect.width + 14}
              height={rect.height + 14}
              rx="12"
              fill="#fff"
              stroke="#dce2e5"
              filter="url(#paperShadow)"
            />
            <image
              href={sourceImageUrl}
              x={rect.x}
              y={rect.y}
              width={rect.width}
              height={rect.height}
              preserveAspectRatio="none"
            />
            {hasDiagram && (
              <text x={rect.x} y={Math.max(22, rect.y - 10)} fill="#6a7580" fontSize="14" fontWeight="800" letterSpacing="1.2">
                ORIGINAL QUESTION
              </text>
            )}
          </g>
        ) : questionText.trim() ? (
          <foreignObject x={rect.x} y={rect.y} width={rect.width} height={rect.height} className="source-question">
            <div className="question-paper">
              <span className="question-kicker">SAT question</span>
              <div className="question-copy">{questionText}</div>
            </div>
          </foreignObject>
        ) : null}

        {!hasQuestion && (
          <g className="empty-board">
            <circle cx="600" cy="292" r="52" fill="#eaf2ff" />
            <path d="M570 300 Q600 262 630 300 M580 314 H620" fill="none" stroke="#1769e0" strokeWidth="7" strokeLinecap="round" />
            <text x="600" y="390" textAnchor="middle" className="empty-title">Bring me any SAT question.</text>
            <text x="600" y="430" textAnchor="middle" className="empty-subtitle">Paste it or upload a clear image. I’ll explain it here as I speak.</text>
          </g>
        )}

        <g className="tutor-overlay">
          {hasDiagram && !hasGraph && (
            <g className="scene-enter">
              <text x={VISUAL_PANEL.x} y={VISUAL_PANEL.y - 13} fill="#1769e0" fontSize="15" fontWeight="800" letterSpacing="1.1">
                ENLARGED TEACHING DIAGRAM
              </text>
              <rect
                x={VISUAL_PANEL.x}
                y={VISUAL_PANEL.y}
                width={VISUAL_PANEL.width}
                height={VISUAL_PANEL.height}
                rx="14"
                fill="#fff"
                stroke="#c9d9ea"
                strokeWidth="2"
                filter="url(#paperShadow)"
              />
            </g>
          )}
          {displayCommands.map((command) => <CommandMarkup key={command.id} command={command} rect={rect} />)}
          {/* Labels paint last so a vertex name is never buried under the
              segment it belongs to. */}
          {labelBoxes.map((box) => <LabelMarkup key={box.command.id} box={box} />)}
          <FlowNotes
            commands={flowCommands}
            highlights={flowHighlights}
            hasVisual={hasVisual}
            overSource={false}
          />
        </g>
      </svg>

      {(caption || tutorState === "thinking") && (
        <div className="live-caption" role="status" aria-live="polite">
          <span className={`caption-orb state-${tutorState}`} />
          {tutorState === "thinking" ? (caption || "I’m solving and checking the problem…") : caption}
        </div>
      )}

      {errorMessage && <div className="board-error" role="alert">{errorMessage}</div>}
    </section>
  );
}
