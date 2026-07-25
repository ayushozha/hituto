/**
 * AG-UI bridge helpers shared with Hi-Tuto's coding-lab contract.
 * MCP App UI can emit these event shapes; hosts map them to tutor agent turns.
 */
export type CodingLabAgUiEventType =
  | "CODING_LAB_RUN_RESULT"
  | "CODING_LAB_CHECK_RESULT"
  | "CODING_LAB_FILES_CHANGED";

export type CodingLabAgUiEvent = {
  type: CodingLabAgUiEventType;
  ok: boolean;
  passed?: boolean | null;
  stdout: string;
  stderr: string;
  language: string;
  files?: { path: string; content: string }[];
};

export function toAgUiModelNote(event: CodingLabAgUiEvent): string {
  return `[AG-UI ${event.type}] ${JSON.stringify(event)}`;
}
