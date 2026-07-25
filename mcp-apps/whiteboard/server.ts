console.log("Starting Hi Tuto Whiteboard MCP App server...");

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

const resourceUri = "ui://whiteboard/mcp-app.html";
const PORT = 3012;

const ElementSchema = z.record(z.unknown());

function createServer(): McpServer {
  const server = new McpServer({
    name: "Hi Tuto Whiteboard",
    version: "0.1.0",
  });

  registerAppTool(
    server,
    "show_whiteboard",
    {
      title: "Show whiteboard",
      description:
        "Open an Excalidraw teaching whiteboard seeded with diagram elements. " +
        "Prefer rectangles, ellipses, diamonds, arrows, lines, and text. " +
        "Each element needs type, id, x, y, width, height; text also needs text/fontSize; " +
        "arrows need points. Keep under 80 elements.",
      inputSchema: {
        title: z.string().describe("Short title for the whiteboard"),
        intent: z
          .string()
          .optional()
          .describe("One-line teaching goal shown to the student"),
        caption: z.string().optional().describe("Optional short caption"),
        elements: z
          .array(ElementSchema)
          .optional()
          .describe("Excalidraw elements to seed the canvas"),
      },
      _meta: { ui: { resourceUri } },
    },
    async (args) => {
      const elements = Array.isArray(args.elements) ? args.elements.slice(0, 80) : [];
      const payload = {
        title: args.title,
        intent: args.intent ?? "",
        caption: args.caption ?? null,
        elements,
      };
      return {
        content: [{ type: "text", text: JSON.stringify(payload) }],
        structuredContent: payload,
      };
    },
  );

  registerAppTool(
    server,
    "update_whiteboard",
    {
      title: "Update whiteboard",
      description:
        "Replace the whiteboard scene with a new set of Excalidraw elements (same shape as show_whiteboard).",
      inputSchema: {
        title: z.string().optional(),
        intent: z.string().optional(),
        caption: z.string().optional(),
        elements: z.array(ElementSchema).optional(),
      },
      _meta: { ui: { resourceUri } },
    },
    async (args) => {
      const elements = Array.isArray(args.elements) ? args.elements.slice(0, 80) : [];
      const payload = {
        title: args.title ?? "Whiteboard",
        intent: args.intent ?? "",
        caption: args.caption ?? null,
        elements,
      };
      return {
        content: [{ type: "text", text: JSON.stringify(payload) }],
        structuredContent: payload,
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
                  // Single-file build is self-contained; blob: covers Excalidraw workers.
                  resourceDomains: ["blob:", "data:"],
                  connectDomains: ["blob:"],
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
expressApp.use(express.json({ limit: "2mb" }));

expressApp.post("/mcp", async (req, res) => {
  const server = createServer();
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

expressApp.get(["/", "/demo", "/index.html"], async (_req, res) => {
  const html = await fs.readFile(
    path.join(import.meta.dirname, "dist", "mcp-app.html"),
    "utf-8",
  );
  res.type("html").send(html);
});

expressApp.listen(PORT, (err?: Error) => {
  if (err) {
    console.error("Error starting server:", err);
    process.exit(1);
  }
  console.log(`Whiteboard MCP App listening on http://localhost:${PORT}/mcp`);
  console.log(`Browser demo: http://localhost:${PORT}/?demo=1`);
});
