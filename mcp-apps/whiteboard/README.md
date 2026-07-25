# Hi Tuto Whiteboard MCP App

Portable MCP App packaging of the Excalidraw teaching whiteboard. In the main product,
the primary surface is the native tutor widget (`show_whiteboard`) over AG-UI. This package
exposes the same board contract to MCP hosts (Claude / basic-host).

## Run locally

```bash
cd mcp-apps/whiteboard
npm install
npm run build
npm run serve
# http://localhost:3012/mcp
# demo UI: http://localhost:3012/?demo=1
```

Test with [ext-apps basic-host](https://github.com/modelcontextprotocol/ext-apps):

```bash
SERVERS='["http://localhost:3012/mcp"]' npm start
```

## Tools

- `show_whiteboard` — open the board with `title`, optional `intent` / `caption`, and Excalidraw `elements`
- `update_whiteboard` — replace the scene (same payload shape)
