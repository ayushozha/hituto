/**
 * AG-UI-shaped events for the coding lab ↔ tutor agent contract.
 * Agent → lab uses TOOL_CALL_* for show_coding_lab / update_coding_lab (existing stream).
 * Lab → agent uses these learner activity events (persisted + attached to the next user turn).
 */

export type CodingLabFile = { path: string; content: string };

export type CodingLabAgUiEventType =
  | "CODING_LAB_RUN_RESULT"
  | "CODING_LAB_CHECK_RESULT"
  | "CODING_LAB_FILES_CHANGED";

export type CodingLabRunPayload = {
  type: CodingLabAgUiEventType;
  sessionId?: string;
  ok: boolean;
  passed?: boolean | null;
  stdout: string;
  stderr: string;
  language: string;
  files?: CodingLabFile[];
};

export type CodingLabState = {
  session_id?: string;
  coding_lab_session_id?: string;
  title?: string;
  language?: string;
  instructions?: string;
  files?: CodingLabFile[];
  entrypoint?: string | null;
  expectedStdout?: string | null;
  hint?: string | null;
  last_run?: {
    ok?: boolean;
    passed?: boolean | null;
    stdout?: string;
    stderr?: string;
    language?: string;
    event?: string;
  } | null;
};

export function codingLabStateFromRun(
  sessionId: string | undefined,
  run: CodingLabRunPayload,
  files: CodingLabFile[],
): CodingLabState {
  return {
    session_id: sessionId,
    coding_lab_session_id: sessionId,
    files,
    last_run: {
      ok: run.ok,
      passed: run.passed,
      stdout: run.stdout,
      stderr: run.stderr,
      language: run.language,
      event: run.type,
    },
  };
}
