import QuizComponent from "./QuizComponent";
import FlipCardComponent from "./FlipCardComponent";
import CodeInputComponent from "./CodeInputComponent";
import CodingLabComponent from "./CodingLabComponent";
import GameComponent from "./GameComponent";
import { DiagramComponent, FormulaCalculator } from "./ExtraWidgets";
import A2UIRenderer from "./A2UIRenderer";
import GenerativeUiComponent from "./GenerativeUiComponent";
import WhiteboardComponent from "./WhiteboardComponent";
import WidgetCard from "./WidgetCard";
import { ChatToolCall } from "../api";
import type { CodingLabFile, CodingLabRunPayload } from "../lib/codingLabAgUi";

/** A widget result reported back to the caller (text tutor ignores it; voice reacts to it). */
export type ToolResult = { toolName: string; [k: string]: unknown };

export type RenderOptions = {
  /** Only the voice instructor wires this — it forwards results to the agent. Text tutor omits it. */
  onResult?: (result: ToolResult) => void;
  /** Receives editable Excalidraw scene updates for inclusion in the next tutor turn. */
  onWhiteboardChange?: (elements: unknown[], sessionId?: string) => void;
  /** Sync coding-lab files to the server / next tutor turn. */
  onCodingLabFilesChange?: (files: CodingLabFile[], sessionId?: string) => void;
  /** AG-UI learner events from the coding lab (run/check). */
  onCodingLabEvent?: (event: CodingLabRunPayload) => void;
  /** Needed to build the same-origin iframe `src` for a Path B (generate_ui) capsule. */
  courseId?: string;
  lessonId?: string;
};

/**
 * Single source of truth mapping a tutor tool call → its trusted React widget.
 * Both LessonTutorChat (text) and VoiceInstructor (voice) render through here, so a new
 * widget is added in exactly one place. Keep tool names in sync with backend _TOOL_DEFS.
 */
export function renderToolWidget(toolCall: ChatToolCall, opts: RenderOptions = {}) {
  const { name, arguments: args } = toolCall;
  const {
    onResult,
    onWhiteboardChange,
    onCodingLabFilesChange,
    onCodingLabEvent,
    courseId,
    lessonId,
  } = opts;

  switch (name) {
    case "create_quiz":
      return (
        <QuizComponent
          topic={typeof args.topic === "string" ? args.topic : "Quiz"}
          questions={Array.isArray(args.questions) ? args.questions : []}
          onResult={
            onResult
              ? (score, total, metadata) =>
                  onResult({ toolName: "create_quiz", score, total, ...metadata })
              : undefined
          }
          onRetry={
            onResult
              ? (attempt) => onResult({ toolName: "practice_retried", attempt })
              : undefined
          }
        />
      );

    case "show_flashcards":
      return <FlipCardComponent topic={args.topic} cards={args.cards} />;

    case "show_coding_lab":
    case "update_coding_lab":
      return (
        <CodingLabComponent
          title={typeof args.title === "string" ? args.title : "Coding Lab"}
          language={typeof args.language === "string" ? args.language : "javascript"}
          instructions={typeof args.instructions === "string" ? args.instructions : ""}
          files={Array.isArray(args.files) ? args.files : []}
          entrypoint={typeof args.entrypoint === "string" ? args.entrypoint : null}
          expectedStdout={typeof args.expectedStdout === "string" ? args.expectedStdout : null}
          hint={typeof args.hint === "string" ? args.hint : null}
          coding_lab_session_id={
            typeof args.coding_lab_session_id === "string" ? args.coding_lab_session_id : undefined
          }
          onFilesChange={onCodingLabFilesChange}
          onLabEvent={onCodingLabEvent}
          onResult={onResult}
        />
      );

    case "show_code_exercise":
      return (
        <CodeInputComponent
          title={args.title}
          language={args.language}
          initialCode={args.initialCode}
          instructions={args.instructions}
          expectedOutput={args.expectedOutput}
          hint={args.hint}
        />
      );

    case "create_game":
      return <GameComponent gameType={args.gameType} topic={args.topic} content={args.content} />;

    case "show_diagram":
      return (
        <DiagramComponent
          title={args.title}
          mermaidDefinition={args.mermaidDefinition}
          nodes={args.nodes}
        />
      );

    case "show_formula_calculator":
      return (
        <FormulaCalculator
          title={args.title}
          formula={args.formula}
          variables={args.variables}
          steps={args.steps}
        />
      );

    case "show_whiteboard":
      return (
        <WhiteboardComponent
          title={args.title}
          intent={args.intent}
          elements={args.elements}
          caption={args.caption}
          whiteboard_session_id={args.whiteboard_session_id}
          onSceneChange={onWhiteboardChange}
        />
      );

    case "render_ui":
      return (
        <WidgetCard title={args.title || "Interactive"} eyebrow="Interactive surface" tone="interactive">
          <A2UIRenderer root={args.root} onResult={onResult} />
        </WidgetCard>
      );

    case "generate_ui":
      return (
        <GenerativeUiComponent
          courseId={courseId}
          lessonId={lessonId}
          uiId={args.ui_id}
          title={args.title}
        />
      );

    default:
      return (
        <div className="rounded-2xl border border-coral/20 bg-coral-soft p-3 text-xs leading-relaxed text-coral-dark">
          <strong>Unknown tool request:</strong> {name}
        </div>
      );
  }
}
