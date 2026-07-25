console.log("Starting Hi-Tuto Coding Lab MCP App server...");

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import cors from "cors";
import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

const resourceUri = "ui://coding-lab/mcp-app.html";

const FileSchema = z.object({
  path: z.string(),
  content: z.string(),
});

function createServer(): McpServer {
  const server = new McpServer({
    name: "Hi-Tuto Coding Lab",
    version: "0.1.0",
  });

  registerAppTool(
    server,
    "open_exercise",
    {
      title: "Open coding exercise",
      description:
        "Open the coding lab UI with an exercise (multi-file tree + instructions). " +
        "Pass as many files as needed — e.g. index.html + styles.css + script.js for a mini " +
        "website (language=html; Preview injects CSS/JS). language: javascript (run), " +
        "python (Pyodide), html (preview), or any other (typescript, java, go, c++, …) " +
        "for editor + tutor review.",
      inputSchema: {
        title: z.string(),
        language: z
          .string()
          .describe("e.g. javascript, python, html (multi-file web), java, go, cpp"),
        instructions: z.string(),
        files: z
          .array(FileSchema)
          .describe("Full starter workspace; multi-file projects are supported"),
        expectedStdout: z.string().optional(),
        hint: z.string().optional(),
        entrypoint: z.string().optional(),
      },
      _meta: { ui: { resourceUri } },
    },
    async (args) => {
      const payload = {
        title: args.title,
        language: args.language,
        instructions: args.instructions,
        files: args.files,
        expectedStdout: args.expectedStdout ?? null,
        hint: args.hint ?? null,
        entrypoint: args.entrypoint ?? null,
      };
      return {
        content: [{ type: "text", text: JSON.stringify(payload) }],
        structuredContent: payload,
      };
    },
  );

  registerAppTool(
    server,
    "check_solution",
    {
      title: "Check coding solution",
      description:
        "Record a learner run/check result (AG-UI CODING_LAB_* shape) for the host tutor.",
      inputSchema: {
        ok: z.boolean(),
        passed: z.boolean().nullable().optional(),
        stdout: z.string(),
        stderr: z.string().optional(),
        language: z.string(),
        event: z
          .enum(["CODING_LAB_RUN_RESULT", "CODING_LAB_CHECK_RESULT", "CODING_LAB_FILES_CHANGED"])
          .optional(),
      },
      _meta: { ui: { resourceUri } },
    },
    async (args) => {
      const event = {
        type: args.event || "CODING_LAB_CHECK_RESULT",
        ok: args.ok,
        passed: args.passed ?? null,
        stdout: args.stdout,
        stderr: args.stderr || "",
        language: args.language,
      };
      return {
        content: [{ type: "text", text: JSON.stringify(event) }],
        structuredContent: event,
      };
    },
  );

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      const html = await fs.readFile(
        path.join(import.meta.dirname, "dist", "mcp-app.html"),
        "utf-8",
      );
      return {
        contents: [
          {
            uri: resourceUri,
            mimeType: RESOURCE_MIME_TYPE,
            text: html,
            _meta: {
              ui: {
                csp: {
                  resourceDomains: ["https://cdn.jsdelivr.net", "blob:"],
                  connectDomains: ["https://cdn.jsdelivr.net"],
                },
              },
            },
          },
        ],
      };
    },
  );

  return server;
}

const expressApp = express();
expressApp.use(cors());
expressApp.use(express.json({ limit: "1mb" }));

expressApp.post("/mcp", async (req, res) => {
  // One McpServer + transport per request (Streamable HTTP cannot reuse a connected server).
  const server = createServer();
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

// Standalone browser demo (no MCP host): http://localhost:3011/?demo=1
expressApp.get(["/", "/demo", "/index.html"], async (_req, res) => {
  const html = await fs.readFile(
    path.join(import.meta.dirname, "dist", "mcp-app.html"),
    "utf-8",
  );
  res.type("html").send(html);
});

expressApp.listen(3011, (err?: Error) => {
  if (err) {
    console.error("Error starting server:", err);
    process.exit(1);
  }
  console.log("Coding Lab MCP App listening on http://localhost:3011/mcp");
  console.log("Browser demo: http://localhost:3011/?demo=1");
});
