import { z } from "zod";

const stableId = z.string().min(1).max(80).regex(/^[A-Za-z0-9_:-]+$/);
const color = z.string().max(24).default("#1769e0");
const space = z.enum(["board", "source", "diagram"]);
const layout = z.enum(["absolute", "flow", "auto"]);
const normalized = z.number().min(0).max(1);
const opacity = z.number().min(0).max(1).default(1);
const size = z.number().min(0.001).max(0.2).default(0.04);

export const pointSchema = z.object({ x: normalized, y: normalized });

const inkFields = {
  id: stableId,
  space: space.default("board"),
  layout: layout.default("absolute"),
  text: z.string().min(1).max(240),
  color,
  size,
  opacity,
  x: normalized.default(0),
  y: normalized.default(0),
  width: normalized.default(0),
  height: normalized.default(0),
};

const textCommandSchema = z.object({ kind: z.literal("text"), ...inkFields });
const mathCommandSchema = z.object({ kind: z.literal("math"), ...inkFields });

const segmentCommandSchema = z.object({
  id: stableId,
  kind: z.enum(["line", "arrow", "bracket"]),
  space: space.default("diagram"),
  x: normalized,
  y: normalized,
  x2: normalized,
  y2: normalized,
  color,
  size,
  opacity,
});

const rectCommandSchema = z.object({
  id: stableId,
  kind: z.literal("rect"),
  space: space.default("diagram"),
  x: normalized,
  y: normalized,
  width: normalized.refine((value) => value > 0, "width must be positive"),
  height: normalized.refine((value) => value > 0, "height must be positive"),
  color,
  size,
  opacity,
  preserve_aspect: z.boolean().default(false),
});

const highlightCommandSchema = z.object({
  id: stableId,
  kind: z.literal("highlight"),
  space: z.enum(["board", "source"]).default("board"),
  target_id: z.union([stableId, z.literal("")]).default(""),
  x: normalized.default(0),
  y: normalized.default(0),
  width: normalized.default(0),
  height: normalized.default(0),
  color: z.string().max(24).default("#f4b400"),
  opacity: z.number().min(0).max(1).default(0.25),
}).refine((command) => Boolean(command.target_id) || (command.width > 0 && command.height > 0), {
  message: "highlight requires a target or positive area",
});

const circleCommandSchema = z.object({
  id: stableId,
  kind: z.literal("circle"),
  space: space.default("diagram"),
  x: normalized,
  y: normalized,
  radius: z.number().gt(0).max(0.5),
  color,
  size,
  opacity,
});

const angleCommandSchema = z.object({
  id: stableId,
  kind: z.literal("angle"),
  space: space.default("diagram"),
  x: normalized,
  y: normalized,
  radius: z.number().gt(0).max(0.5),
  start_angle: z.number().min(-360).max(360),
  end_angle: z.number().min(-360).max(360),
  color,
  size,
  opacity,
});

const polylineCommandSchema = z.object({
  id: stableId,
  kind: z.literal("polyline"),
  space: space.default("diagram"),
  points: z.array(pointSchema).min(2).max(40),
  color,
  size,
  opacity,
});

export const graphCurveSchema = z.object({
  id: stableId,
  formula: z.string().min(1).max(240),
  color,
  label: z.string().max(80).default(""),
});

export const graphMarkerSchema = z.object({
  id: stableId,
  x: z.number().min(-1_000_000).max(1_000_000),
  y: z.number().min(-1_000_000).max(1_000_000),
  label: z.string().max(80).default(""),
  color: z.string().max(24).default("#d93025"),
});

export const graphCommandSchema = z.object({
  id: stableId,
  kind: z.literal("graph"),
  space: z.literal("board").default("board"),
  layout: z.literal("auto").default("auto"),
  curves: z.array(graphCurveSchema).max(6).default([]),
  markers: z.array(graphMarkerSchema).max(12).default([]),
  x_min: z.number().min(-1_000_000).max(1_000_000),
  x_max: z.number().min(-1_000_000).max(1_000_000),
  y_min: z.number().min(-1_000_000).max(1_000_000),
  y_max: z.number().min(-1_000_000).max(1_000_000),
  opacity,
}).superRefine((command, context) => {
  if (!command.curves.length && !command.markers.length) {
    context.addIssue({ code: "custom", message: "graph requires a curve or marker" });
  }
  if (command.x_max <= command.x_min || command.y_max <= command.y_min) {
    context.addIssue({ code: "custom", message: "graph bounds must increase" });
  }
  if (command.markers.some((marker) => marker.x < command.x_min || marker.x > command.x_max || marker.y < command.y_min || marker.y > command.y_max)) {
    context.addIssue({ code: "custom", message: "graph markers must be inside the bounds" });
  }
});

export const barDatumSchema = z.object({
  label: z.string().min(1).max(48),
  value: z.number().min(0).max(1_000_000),
  display_value: z.string().max(48).default(""),
  color,
});

export const barChartCommandSchema = z.object({
  id: stableId,
  kind: z.literal("bar_chart"),
  space: z.literal("board").default("board"),
  layout: z.literal("auto").default("auto"),
  title: z.string().max(100).default(""),
  x_label: z.string().max(80).default(""),
  y_label: z.string().max(80).default(""),
  bars: z.array(barDatumSchema).min(2).max(12),
  opacity,
});

export const vennCommandSchema = z.object({
  id: stableId,
  kind: z.literal("venn"),
  space: z.literal("board").default("board"),
  layout: z.literal("auto").default("auto"),
  title: z.string().max(100).default(""),
  left_label: z.string().min(1).max(64),
  right_label: z.string().min(1).max(64),
  left_only: z.string().min(1).max(64),
  overlap: z.string().min(1).max(64),
  right_only: z.string().min(1).max(64),
  outside: z.string().max(64).default(""),
  opacity,
});

const eraseCommandSchema = z.object({ id: stableId, kind: z.literal("erase"), target_id: stableId });
const clearCommandSchema = z.object({ id: stableId, kind: z.literal("clear") });
const cameraCommandSchema = z.object({
  id: stableId,
  kind: z.literal("camera"),
  space: space.default("board"),
  x: normalized.default(0),
  y: normalized.default(0),
  width: z.number().gt(0).max(1).default(0.55),
  height: z.number().gt(0).max(1).default(0.55),
});

export const sceneCommandSchema = z.union([
  textCommandSchema,
  mathCommandSchema,
  segmentCommandSchema,
  rectCommandSchema,
  highlightCommandSchema,
  circleCommandSchema,
  angleCommandSchema,
  polylineCommandSchema,
  graphCommandSchema,
  barChartCommandSchema,
  vennCommandSchema,
  eraseCommandSchema,
  clearCommandSchema,
  cameraCommandSchema,
]);

export const teachingBeatSchema = z.object({
  id: stableId,
  teaching_goal: z.string().min(3).max(180),
  spoken_text: z.string().min(3).max(900),
  caption: z.string().min(1).max(220),
  strategy: z.string().min(2).max(80),
  commands: z.array(sceneCommandSchema).max(12),
  pause_after_ms: z.number().int().min(0).max(3000),
  checkpoint: z.boolean(),
});

export const lessonPlanSchema = z.object({
  domain: z.enum(["math", "reading_writing"]),
  question_summary: z.string().min(5).max(600),
  final_answer: z.string().min(1).max(300),
  answer_explanation: z.string().min(5).max(1200),
  confidence: z.number().min(0).max(1),
  beats: z.array(teachingBeatSchema).min(2).max(8),
});

export type Point = z.infer<typeof pointSchema>;
export type GraphCurve = z.infer<typeof graphCurveSchema>;
export type GraphMarker = z.infer<typeof graphMarkerSchema>;
export type GraphCommand = z.infer<typeof graphCommandSchema>;
export type BarChartCommand = z.infer<typeof barChartCommandSchema>;
export type VennCommand = z.infer<typeof vennCommandSchema>;
export type SceneCommand = z.infer<typeof sceneCommandSchema>;
export type TextOrMathCommand = Extract<SceneCommand, { kind: "text" | "math" }>;
export type HighlightCommand = Extract<SceneCommand, { kind: "highlight" }>;
export type CameraCommand = Extract<SceneCommand, { kind: "camera" }>;
export type TeachingBeat = z.infer<typeof teachingBeatSchema>;
export type LessonPlan = z.infer<typeof lessonPlanSchema>;

export type TutorState = "idle" | "thinking" | "speaking" | "listening" | "paused" | "done" | "error";
