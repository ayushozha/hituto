import { App } from "@modelcontextprotocol/ext-apps";
import { toAgUiModelNote, type CodingLabAgUiEvent } from "./aguiBridge";
import {
  buildHtmlPreview,
  canExecute,
  defaultFiles,
  normalizeLang,
  runJavaScript,
  runPython,
} from "./runners";

type LabFile = { path: string; content: string };
type Exercise = {
  title?: string;
  language?: string;
  instructions?: string;
  files?: LabFile[];
  expectedStdout?: string | null;
  hint?: string | null;
  entrypoint?: string | null;
};

const titleEl = document.getElementById("title")!;
const instructionsEl = document.getElementById("instructions")!;
const editorEl = document.getElementById("editor") as HTMLTextAreaElement;
const consoleEl = document.getElementById("console")!;
const previewEl = document.getElementById("preview") as HTMLIFrameElement;
const fileListEl = document.getElementById("file-list")!;
const gutterEl = document.getElementById("gutter")!;
const langPill = document.getElementById("lang-pill")!;
const runBtn = document.getElementById("run-btn") as HTMLButtonElement;
const hintBtn = document.getElementById("hint-btn") as HTMLButtonElement;
const formatBtn = document.getElementById("format-btn") as HTMLButtonElement;
const supportNote = document.getElementById("support-note");
const tabConsoleBtn = document.getElementById("tab-console") as HTMLButtonElement;
const tabPreviewBtn = document.getElementById("tab-preview") as HTMLButtonElement;

let exercise: Exercise = {};
let files: LabFile[] = [];
let activePath = "";
let hintShown = false;

function syncGutter() {
  const lines = Math.max(editorEl.value.split("\n").length, 1);
  gutterEl.textContent = Array.from({ length: lines }, (_, i) => String(i + 1)).join("\n");
}

function setTab(name: "code" | "console" | "preview") {
  const kind = normalizeLang(exercise.language || "javascript");
  const resolved = name === "preview" && kind !== "html" ? "console" : name;
  document.querySelectorAll(".tab").forEach((el) => {
    el.classList.toggle("active", (el as HTMLElement).dataset.tab === resolved);
  });
  document.querySelectorAll(".pane").forEach((el) => {
    el.classList.toggle("active", el.id === `pane-${resolved}`);
  });
}

function syncLanguageTabs() {
  const kind = normalizeLang(exercise.language || "javascript");
  const isHtml = kind === "html";
  tabPreviewBtn.hidden = !isHtml;
  tabConsoleBtn.textContent = kind === "python" ? "Console (Python)" : "Console";
  if (!isHtml && tabPreviewBtn.classList.contains("active")) setTab("console");
}

function renderConsoleLines(lines: Array<{ text: string; className?: "ok" | "err" }>) {
  consoleEl.replaceChildren();
  lines.forEach((line, index) => {
    if (index > 0) consoleEl.append("\n");
    if (line.className) {
      const span = document.createElement("span");
      span.className = line.className;
      span.textContent = line.text;
      consoleEl.append(span);
    } else {
      consoleEl.append(line.text);
    }
  });
}

function updateRunButton() {
  const lang = exercise.language || "javascript";
  const executable = canExecute(lang);
  runBtn.textContent = executable ? "Run" : "Submit for review";
  runBtn.title = executable
    ? "Run in sandbox"
    : `${lang}: no in-browser runner yet — submit code for the tutor to check`;
  if (supportNote) {
    supportNote.textContent = executable
      ? `Runs in-browser: JavaScript, Python, HTML/CSS`
      : `${lang}: write code here, then Submit — the tutor reviews (Java, Go, C++, etc. use tutor review)`;
  }
}

function renderFileList() {
  fileListEl.innerHTML = "";
  for (const file of files) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `file-item${file.path === activePath ? " active" : ""}`;
    btn.textContent = file.path;
    btn.addEventListener("click", () => {
      persistActive();
      activePath = file.path;
      editorEl.value = file.content;
      syncGutter();
      renderFileList();
      setTab("code");
    });
    fileListEl.appendChild(btn);
  }
}

function persistActive() {
  const idx = files.findIndex((f) => f.path === activePath);
  if (idx >= 0) files[idx] = { ...files[idx], content: editorEl.value };
}

function applyExercise(next: Exercise) {
  exercise = next || {};
  titleEl.textContent = exercise.title || "Coding Lab";
  instructionsEl.textContent = exercise.instructions || "Waiting for an exercise…";
  langPill.textContent = exercise.language || "javascript";
  files =
    Array.isArray(exercise.files) && exercise.files.length > 0
      ? exercise.files.map((f) => ({
          path: String(f.path || "main.txt"),
          content: String(f.content ?? ""),
        }))
      : defaultFiles(exercise.language);
  activePath = exercise.entrypoint || files[0]?.path || "main.js";
  const active = files.find((f) => f.path === activePath) || files[0];
  editorEl.value = active?.content || "";
  consoleEl.textContent = "No output yet. Press Run.";
  previewEl.srcdoc = "";
  hintShown = false;
  hintBtn.hidden = !exercise.hint;
  syncGutter();
  renderFileList();
  updateRunButton();
  syncLanguageTabs();
  setTab("code");
}

function parseToolResult(result: { content?: Array<{ type: string; text?: string }> }): Exercise {
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return {};
  try {
    return JSON.parse(text) as Exercise;
  } catch {
    return { instructions: text };
  }
}

async function emitEvent(event: CodingLabAgUiEvent) {
  try {
    await app.callServerTool({
      name: "check_solution",
      arguments: {
        ok: event.ok,
        passed: event.passed,
        stdout: event.stdout,
        stderr: event.stderr,
        language: event.language,
        event: event.type,
      },
    });
  } catch {
    // Host may not proxy app-only tools.
  }
  const maybeUpdate = (app as { updateModelContext?: (p: unknown) => Promise<unknown> })
    .updateModelContext;
  if (maybeUpdate) {
    try {
      await maybeUpdate({ content: [{ type: "text", text: toAgUiModelNote(event) }] });
    } catch {
      // Optional on older hosts
    }
  }
}

const app = new App({ name: "Hi-Tuto Coding Lab", version: "0.1.0" });

app.ontoolresult = (result) => {
  applyExercise(parseToolResult(result));
};

app.ontoolinput = (params) => {
  if (params?.arguments && typeof params.arguments === "object") {
    applyExercise(params.arguments as Exercise);
  }
};

void (async () => {
  const demoMode =
    new URLSearchParams(location.search).has("demo") || window.parent === window;
  if (!demoMode) {
    try {
      await app.connect();
    } catch {
      // Host unavailable — fall through to local wiring.
    }
  }

  const demoExercise: Exercise = {
    title: "Python demo",
    language: "python",
    instructions: "Print 2 + 2, then switch to Console (Python).",
    files: [
      {
        path: "main.py",
        content: "print(2 + 2)\n",
      },
    ],
    expectedStdout: "4",
  };
  applyExercise(demoMode ? demoExercise : {});

  document.querySelectorAll(".tab").forEach((el) => {
    el.addEventListener("click", () => {
      const name = (el as HTMLElement).dataset.tab as "code" | "console" | "preview";
      if (name) setTab(name);
    });
  });

  editorEl.addEventListener("input", () => {
    syncGutter();
    persistActive();
  });
  editorEl.addEventListener("scroll", () => {
    gutterEl.scrollTop = editorEl.scrollTop;
  });
  // Tab indents code (needed for Python) instead of leaving the editor.
  editorEl.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const start = editorEl.selectionStart;
    const end = editorEl.selectionEnd;
    const value = editorEl.value;
    const indent = "    ";
    if (e.shiftKey) {
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const removable = value.slice(lineStart).match(/^( {1,4}|\t)/)?.[0] ?? "";
      if (!removable) return;
      editorEl.value =
        value.slice(0, lineStart) + value.slice(lineStart + removable.length);
      const pos = Math.max(lineStart, start - removable.length);
      editorEl.selectionStart = editorEl.selectionEnd = pos;
    } else {
      editorEl.value = value.slice(0, start) + indent + value.slice(end);
      editorEl.selectionStart = editorEl.selectionEnd = start + indent.length;
    }
    syncGutter();
    persistActive();
  });

  hintBtn.addEventListener("click", () => {
    hintShown = !hintShown;
    setTab("console");
    renderConsoleLines(
      hintShown && exercise.hint
        ? [
            { text: "Hint:", className: "ok" },
            { text: ` ${exercise.hint}` },
          ]
        : [{ text: "No output yet. Press Run." }],
    );
  });

  formatBtn.addEventListener("click", () => {
    try {
      const trimmed = editorEl.value.trim();
      if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
        editorEl.value = JSON.stringify(JSON.parse(trimmed), null, 2) + "\n";
      }
      syncGutter();
      persistActive();
    } catch {
      // ignore non-JSON
    }
  });

  runBtn.addEventListener("click", async () => {
    persistActive();
    const language = exercise.language || "javascript";
    const kind = normalizeLang(language);
    const entry =
      files.find((f) => f.path === (exercise.entrypoint || activePath)) || files[0];
    const code = entry?.content || editorEl.value;
    let stdout = "";
    let stderr = "";
    let ok = true;
    let passed: boolean | null = null;

    runBtn.disabled = true;
    try {
      if (kind === "html") {
        previewEl.srcdoc = buildHtmlPreview(files);
        setTab("preview");
        stdout = "Preview updated.";
      } else if (kind === "python") {
        setTab("console");
        consoleEl.textContent = "Loading Python packages (first run may take a minute)…";
        const result = await runPython(code, { files });
        stdout = result.stdout;
        stderr = result.stderr;
        ok = result.ok;
      } else if (kind === "javascript") {
        setTab("console");
        const result = await runJavaScript(code);
        stdout = result.stdout;
        stderr = result.stderr;
        ok = result.ok;
      } else {
        // Java, Go, C++, etc. — no in-browser runner; send to tutor for review
        setTab("console");
        stdout = `Submitted ${language} solution for tutor review.\n\n--- ${entry?.path || "main"} ---\n${code}`;
        ok = true;
        passed = null;
        renderConsoleLines([
          { text: "Submitted for tutor review.", className: "ok" },
          {
            text:
              `No in-browser runner for ${language} yet (Java, Go, C++, Rust, …). ` +
              "The tutor will check your code from this submission.",
          },
        ]);
        const event: CodingLabAgUiEvent = {
          type: "CODING_LAB_CHECK_RESULT",
          ok: true,
          passed: null,
          stdout,
          stderr: "",
          language,
          files,
        };
        await emitEvent(event);
        return;
      }

      const expected = exercise.expectedStdout;
      passed =
        expected != null && expected !== "" ? stdout.trim() === expected.trim() : null;

      const lines: Array<{ text: string; className?: "ok" | "err" }> = [
        { text: stdout || "(no stdout)" },
      ];
      if (stderr) lines.push({ text: stderr, className: "err" });
      if (passed === true) lines.push({ text: "✓ Check passed", className: "ok" });
      if (passed === false) {
        lines.push({ text: "✗ Does not match expectedStdout", className: "err" });
      }
      renderConsoleLines(lines);

      await emitEvent({
        type: passed != null ? "CODING_LAB_CHECK_RESULT" : "CODING_LAB_RUN_RESULT",
        ok,
        passed,
        stdout,
        stderr,
        language,
        files,
      });
    } finally {
      runBtn.disabled = false;
    }
  });
})();
