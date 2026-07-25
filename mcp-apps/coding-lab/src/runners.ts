/** In-browser runners for the MCP coding lab. */

export type RunResult = { ok: boolean; stdout: string; stderr: string };

export type LangKind = "javascript" | "python" | "html" | "tutor_review";

const RUN_TIMEOUT_MS = 8000;
const PYODIDE_LOAD_TIMEOUT_MS = 45_000;
const PYODIDE_PACKAGE_TIMEOUT_MS = 90_000;
const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

type RunnerWorkerMessage =
  | { type: "ready" }
  | { type: "packages_ready" }
  | { type: "result"; result: RunResult };

export type PythonRunOptions = {
  stdin?: string;
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

export function normalizeLang(language: string): LangKind {
  const lang = language.trim().toLowerCase();
  if (["js", "javascript"].includes(lang)) return "javascript";
  if (["py", "python"].includes(lang)) return "python";
  if (["html", "css", "web"].includes(lang)) return "html";
  return "tutor_review";
}

export function canExecute(language: string): boolean {
  const kind = normalizeLang(language);
  return kind === "javascript" || kind === "python" || kind === "html";
}

export function defaultFiles(language?: string): { path: string; content: string }[] {
  const kind = normalizeLang(language || "javascript");
  if (kind === "python") {
    return [{ path: "main.py", content: "# Write your solution\nprint('hello')\n" }];
  }
  if (kind === "html") {
    return [
      {
        path: "index.html",
        content:
          "<!DOCTYPE html>\n<html>\n<head>\n  <meta charset=\"utf-8\" />\n  <title>Lab</title>\n</head>\n<body>\n  <h1 id=\"title\">Hello</h1>\n</body>\n</html>\n",
      },
      {
        path: "styles.css",
        content: "body {\n  font-family: system-ui, sans-serif;\n  margin: 2rem;\n}\n",
      },
      {
        path: "script.js",
        content: "document.getElementById('title')?.addEventListener('click', () => {\n  console.log('clicked');\n});\n",
      },
    ];
  }
  if (kind === "tutor_review") {
    const rawLanguage = (language || "code").toLowerCase();
    const ext =
      ["typescript", "ts"].includes(rawLanguage)
        ? "ts"
        : rawLanguage.includes("java")
          ? "java"
          : rawLanguage.includes("go")
            ? "go"
            : rawLanguage.includes("rust")
              ? "rs"
              : rawLanguage.includes("c++") || rawLanguage === "cpp"
                ? "cpp"
                : rawLanguage.includes("c#") || rawLanguage === "csharp"
                  ? "cs"
                  : "txt";
    const name = ext === "java" ? "Main.java" : ext === "go" ? "main.go" : `main.${ext}`;
    return [
      {
        path: name,
        content: `// ${language || "code"} fundamentals practice\n// Write your solution, then Submit for tutor review.\n`,
      },
    ];
  }
  return [{ path: "main.js", content: "// Write your solution\nconsole.log('hello');\n" }];
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
      clearTimeout(timer);
      runner.dispose();
      resolve(result);
    };
    const timer = setTimeout(
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

// Pyodide workers have no interactive stdin — raw input() raises OSError errno 29.
// Third-party imports need loadPackagesFromImports (numpy, pandas, …) before run.
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
    let timer: ReturnType<typeof setTimeout>;
    let settled = false;
    const finish = (result: RunResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      runner.dispose();
      resolve(result);
    };
    timer = setTimeout(
      () => finish({ ok: false, stdout: "", stderr: "Python runtime failed to load" }),
      PYODIDE_LOAD_TIMEOUT_MS,
    );
    runner.worker.onmessage = (event: MessageEvent<RunnerWorkerMessage>) => {
      if (event.data?.type === "ready") {
        clearTimeout(timer);
        timer = setTimeout(
          () =>
            finish({
              ok: false,
              stdout: "",
              stderr: "Timed out loading Python packages (check network / try again)",
            }),
          PYODIDE_PACKAGE_TIMEOUT_MS,
        );
      } else if (event.data?.type === "packages_ready") {
        clearTimeout(timer);
        timer = setTimeout(
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

export function buildHtmlPreview(files: { path: string; content: string }[]): string {
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
