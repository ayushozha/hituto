/**
 * In-browser runners for the coding lab (JS sandbox, HTML preview, Pyodide Python).
 * Never execute learner code in the parent window.
 */

export type RunResult = {
  ok: boolean;
  stdout: string;
  stderr: string;
};

const RUN_TIMEOUT_MS = 8000;
const PYODIDE_LOAD_TIMEOUT_MS = 45_000;
/** Package download (numpy etc.) can take a while on first run. */
const PYODIDE_PACKAGE_TIMEOUT_MS = 90_000;
const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";


type RunnerWorkerMessage =
  | { type: "ready" }
  | { type: "packages_ready" }
  | { type: "result"; result: RunResult };

export type PythonRunOptions = {
  stdin?: string;
  /** Extra project files written into Pyodide's virtual FS (for multi-file imports). */
  files?: { path: string; content: string }[];
};

function createRunnerWorker(source: string): { worker: Worker; dispose: () => void } {
  const url = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
  const worker = new Worker(url);
  return {
    worker,
    dispose: () => {
      worker.terminate();
      URL.revokeObjectURL(url);
    },
  };
}

const JAVASCRIPT_WORKER_SOURCE = `
self.onmessage = async (event) => {
  const logs = [];
  const errors = [];
  const format = (value) => {
    if (typeof value === "string") return value;
    try {
      const json = JSON.stringify(value);
      return json === undefined ? String(value) : json;
    } catch (_) {
      return String(value);
    }
  };
  const record = (...args) => logs.push(args.map(format).join(" "));
  console.log = record;
  console.info = record;
  console.warn = record;
  console.error = record;
  try {
    const execute = new Function("return (async () => {\\n" + String(event.data.code || "") + "\\n})()");
    await execute();
  } catch (error) {
    errors.push(String(error && error.message ? error.message : error));
  }
  self.postMessage({
    type: "result",
    result: { ok: errors.length === 0, stdout: logs.join("\\n"), stderr: errors.join("\\n") }
  });
};
`;

export function runJavaScript(code: string): Promise<RunResult> {
  return new Promise((resolve) => {
    let runner: ReturnType<typeof createRunnerWorker>;
    try {
      runner = createRunnerWorker(JAVASCRIPT_WORKER_SOURCE);
    } catch (error) {
      resolve({ ok: false, stdout: "", stderr: String(error) });
      return;
    }
    let settled = false;
    const finish = (result: RunResult) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      runner.dispose();
      resolve(result);
    };
    const timer = window.setTimeout(
      () => finish({ ok: false, stdout: "", stderr: "Run timed out" }),
      RUN_TIMEOUT_MS,
    );
    runner.worker.onmessage = (event: MessageEvent<RunnerWorkerMessage>) => {
      if (event.data?.type === "result") finish(event.data.result);
    };
    runner.worker.onerror = (event) => {
      finish({ ok: false, stdout: "", stderr: event.message || "JavaScript worker failed" });
    };
    runner.worker.postMessage({ code });
  });
}

export function buildHtmlPreviewDocument(files: { path: string; content: string }[]): string {
  const byPath = new Map(files.map((f) => [f.path.replace(/^\.\//, ""), f.content]));
  let html =
    byPath.get("index.html") ||
    byPath.get("main.html") ||
    `<!DOCTYPE html><html><body><pre>Add an index.html file</pre></body></html>`;
  const css = [...byPath.entries()]
    .filter(([p]) => p.endsWith(".css"))
    .map(([, c]) => c)
    .join("\n");
  const js = [...byPath.entries()]
    .filter(([p]) => p.endsWith(".js") && !p.includes("node_modules"))
    .map(([, c]) => c)
    .join("\n");
  if (css) {
    const bundledCss = css.replace(/<\/style/gi, "<\\/style");
    if (/<\/head>/i.test(html)) {
      html = html.replace(/<\/head>/i, `<style data-coding-lab-bundle>${bundledCss}</style></head>`);
    } else {
      html = `<style data-coding-lab-bundle>${bundledCss}</style>` + html;
    }
  }
  if (js) {
    const bundledJs = js.replace(/<\/script/gi, "<\\/script");
    if (/<\/body>/i.test(html)) {
      html = html.replace(/<\/body>/i, `<script data-coding-lab-bundle>${bundledJs}<\/script></body>`);
    } else {
      html += `<script data-coding-lab-bundle>${bundledJs}<\/script>`;
    }
  }
  return html;
}

// Pyodide workers have no interactive stdin — raw input() raises OSError errno 29.
// Also: third-party imports need loadPackagesFromImports (numpy, pandas, …) before run.
const PYTHON_WORKER_SOURCE = `
self.onmessage = async (event) => {
  const stdout = [];
  const stderr = [];
  try {
    importScripts(${JSON.stringify(`${PYODIDE_INDEX_URL}pyodide.js`)});
    const pyodide = await self.loadPyodide({ indexURL: ${JSON.stringify(PYODIDE_INDEX_URL)} });
    self.postMessage({ type: "ready" });
    pyodide.setStdout({ batched: (value) => stdout.push(value) });
    pyodide.setStderr({ batched: (value) => stderr.push(value) });
    const code = String(event.data.code || "");
    const files = Array.isArray(event.data.files) ? event.data.files : [];
    for (const file of files) {
      const path = String(file && file.path ? file.path : "").replace(/^\\.\\//, "");
      if (!path || path.includes("..")) continue;
      const parts = path.split("/");
      if (parts.length > 1) {
        let dir = "";
        for (let i = 0; i < parts.length - 1; i++) {
          dir = dir ? dir + "/" + parts[i] : parts[i];
          try { pyodide.FS.mkdir(dir); } catch (_) {}
        }
      }
      pyodide.FS.writeFile(path, String(file.content ?? ""));
    }
    // Download Pyodide-built packages referenced by import statements (numpy, pandas, …).
    await pyodide.loadPackagesFromImports(code);
    self.postMessage({ type: "packages_ready" });
    const stdinText = String(event.data.stdin || "");
    const stdinLines = stdinText.length
      ? stdinText.replace(/\\r\\n/g, "\\n").replace(/\\r/g, "\\n").split("\\n")
      : [];
    if (stdinLines.length && stdinLines[stdinLines.length - 1] === "") stdinLines.pop();
    const linesLiteral = JSON.stringify(stdinLines);
    await pyodide.runPythonAsync(
      "import builtins\\n" +
      "_coding_lab_stdin_lines = " + linesLiteral + "\\n" +
      "_coding_lab_stdin_index = 0\\n" +
      "def _coding_lab_input(prompt=\\"\\"):\\n" +
      "    global _coding_lab_stdin_index\\n" +
      "    if _coding_lab_stdin_index >= len(_coding_lab_stdin_lines):\\n" +
      "        raise RuntimeError(\\n" +
      "            \\"input() needs a value, but this lab has no interactive keyboard. \\"\\n" +
      "            \\"Use a fixed assignment (e.g. name = 'Ada') or print()-only exercises.\\"\\n" +
      "        )\\n" +
      "    value = _coding_lab_stdin_lines[_coding_lab_stdin_index]\\n" +
      "    _coding_lab_stdin_index += 1\\n" +
      "    return value\\n" +
      "builtins.input = _coding_lab_input\\n"
    );
    await pyodide.runPythonAsync(code);
  } catch (error) {
    let message = String(error && error.message ? error.message : error);
    if (/ModuleNotFoundError|No module named/i.test(message)) {
      message +=
        "\\n\\nHint: this browser lab uses Pyodide. Stdlib and common scientific packages " +
        "(numpy, pandas, matplotlib, scipy, …) are supported; many PyPI packages are not. " +
        "Prefer those, or rewrite without the missing import.";
    }
    stderr.push(message);
  }
  self.postMessage({
    type: "result",
    result: { ok: stderr.length === 0, stdout: stdout.join(""), stderr: stderr.join("") }
  });
};
`;

export function runPython(
  code: string,
  options: PythonRunOptions | string = {},
): Promise<RunResult> {
  const opts: PythonRunOptions =
    typeof options === "string" ? { stdin: options } : options || {};
  return new Promise((resolve) => {
    let runner: ReturnType<typeof createRunnerWorker>;
    try {
      runner = createRunnerWorker(PYTHON_WORKER_SOURCE);
    } catch (error) {
      resolve({ ok: false, stdout: "", stderr: String(error) });
      return;
    }
    let timer: number;
    let settled = false;
    const finish = (result: RunResult) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      runner.dispose();
      resolve(result);
    };
    timer = window.setTimeout(
      () => finish({ ok: false, stdout: "", stderr: "Python runtime failed to load" }),
      PYODIDE_LOAD_TIMEOUT_MS,
    );
    runner.worker.onmessage = (event: MessageEvent<RunnerWorkerMessage>) => {
      if (event.data?.type === "ready") {
        window.clearTimeout(timer);
        timer = window.setTimeout(
          () =>
            finish({
              ok: false,
              stdout: "",
              stderr: "Timed out loading Python packages (check network / try again)",
            }),
          PYODIDE_PACKAGE_TIMEOUT_MS,
        );
      } else if (event.data?.type === "packages_ready") {
        window.clearTimeout(timer);
        timer = window.setTimeout(
          () => finish({ ok: false, stdout: "", stderr: "Run timed out" }),
          RUN_TIMEOUT_MS,
        );
      } else if (event.data?.type === "result") {
        finish(event.data.result);
      }
    };
    runner.worker.onerror = (event) => {
      finish({ ok: false, stdout: "", stderr: event.message || "Python worker failed" });
    };
    runner.worker.postMessage({
      code,
      stdin: opts.stdin || "",
      files: opts.files || [],
    });
  });
}

export function normalizeLang(language: string): "javascript" | "python" | "html" | "other" {
  const lang = language.trim().toLowerCase();
  if (["js", "javascript"].includes(lang)) return "javascript";
  if (["py", "python"].includes(lang)) return "python";
  if (["html", "css", "web"].includes(lang)) return "html";
  return "other";
}

export function pickEntrypoint(
  files: { path: string; content: string }[],
  entrypoint?: string | null,
  language?: string,
): { path: string; content: string } | null {
  if (entrypoint) {
    const hit = files.find((f) => f.path === entrypoint);
    if (hit) return hit;
  }
  const kind = normalizeLang(language || "");
  const rawLanguage = (language || "").trim().toLowerCase();
  const prefer =
    kind === "python"
      ? ["main.py", "app.py"]
      : kind === "html"
        ? ["index.html", "main.html"]
        : ["typescript", "ts"].includes(rawLanguage)
          ? ["main.ts", "index.ts", "app.ts"]
          : ["main.js", "index.js", "app.js"];
  for (const name of prefer) {
    const hit = files.find((f) => f.path === name || f.path.endsWith("/" + name));
    if (hit) return hit;
  }
  return files[0] || null;
}

export function checkExpectedStdout(stdout: string, expected?: string | null): boolean | null {
  if (expected == null || expected === "") return null;
  return stdout.trim() === expected.trim();
}
