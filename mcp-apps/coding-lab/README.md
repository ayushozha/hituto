# Hi-Tuto Coding Lab MCP App

Portable MCP App packaging of the coding-practice lab. In Hi-Tuto, the primary surface is the
native tutor widget (`show_coding_lab`) over AG-UI. This package exposes the same exercise
contract to MCP hosts (Claude / basic-host).

## Run locally

```bash
cd mcp-apps/coding-lab
npm install
npm run build
npm run serve
# http://localhost:3011/mcp
```

Test with [ext-apps basic-host](https://github.com/modelcontextprotocol/ext-apps):

```bash
SERVERS='["http://localhost:3011/mcp"]' npm start
```

## AG-UI contract

Learner run/check events use the same types as Hi-Tuto:

- `CODING_LAB_RUN_RESULT`
- `CODING_LAB_CHECK_RESULT`
- `CODING_LAB_FILES_CHANGED`

See `src/aguiBridge.ts` and `frontend/src/lib/codingLabAgUi.ts`.
