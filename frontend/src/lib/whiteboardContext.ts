const WHITEBOARD_FIELDS = [
  "id",
  "type",
  "x",
  "y",
  "width",
  "height",
  "angle",
  "text",
  "points",
  "strokeColor",
  "backgroundColor",
  "fillStyle",
  "strokeWidth",
  "strokeStyle",
  "groupIds",
  "containerId",
  "boundElements",
  "startBinding",
  "endBinding",
  "startArrowhead",
  "endArrowhead",
] as const;

/** Keep model context useful and bounded; Excalidraw elements contain rendering-only metadata. */
export function compactWhiteboardElements(elements: unknown[]): Record<string, unknown>[] {
  return elements
    .filter(
      (element): element is Record<string, unknown> =>
        Boolean(element) &&
        typeof element === "object" &&
        !(element as { isDeleted?: boolean }).isDeleted,
    )
    // New learner edits are appended by Excalidraw, so keep the newest elements when bounded.
    .slice(-40)
    .map((element) => {
      const compact: Record<string, unknown> = {};
      for (const field of WHITEBOARD_FIELDS) {
        if (element[field] !== undefined && element[field] !== null) compact[field] = element[field];
      }
      return compact;
    });
}
