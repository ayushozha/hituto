/**
 * Best-effort parse of an INCOMPLETE JSON string as it streams in.
 *
 * The tutor's `render_ui` tool arguments arrive as a growing raw string over `TOOL_CALL_ARGS`
 * deltas. To mount the A2UI tree node-by-node we need to parse what has arrived so far, even when
 * the tail is truncated mid-object/array/string. We close any open strings/brackets and retry.
 *
 * This is intentionally lenient and safe: it only ever runs `JSON.parse` (never `eval`), and the
 * authoritative tree is always the fully-validated payload delivered at `TOOL_CALL_END`. A partial
 * parse that can't be salvaged just returns null (the caller shows a skeleton).
 */
export function parsePartialJson<T = unknown>(raw: string): T | null {
  const s = raw.trim();
  if (!s) return null;

  try {
    return JSON.parse(s) as T;
  } catch {
    // fall through to repair
  }

  const stack: string[] = [];
  let inStr = false;
  let esc = false;

  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === "{") stack.push("}");
    else if (c === "[") stack.push("]");
    else if (c === "}" || c === "]") stack.pop();
  }

  let repaired = s;
  if (inStr) repaired += '"';
  // Drop a dangling comma or an incomplete `"key":` with no value yet.
  repaired = repaired.replace(/,\s*$/, "").replace(/"[^"]*"\s*:\s*$/, "").replace(/,\s*$/, "");
  for (let k = stack.length - 1; k >= 0; k--) repaired += stack[k];

  try {
    return JSON.parse(repaired) as T;
  } catch {
    return null;
  }
}
