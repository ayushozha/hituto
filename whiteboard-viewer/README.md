# Hi Tuto whiteboard viewer

Minimal Excalidraw SPA embedded by the tutor `show_whiteboard` widget via iframe + `postMessage`.

## Local

```bash
npm install
npm run dev   # http://localhost:5174
```

Set in `frontend/.env`:

```
VITE_WHITEBOARD_VIEWER_URL=http://localhost:5174
```

## Protocol

Parent → iframe:

```json
{ "type": "hituto:whiteboard:set", "elements": [ /* Excalidraw elements */ ], "appState": {} }
```

Iframe → parent:

```json
{ "type": "hituto:whiteboard:ready" }
```

Parent origins are allowlisted via `VITE_ALLOWED_PARENT_ORIGINS` (comma-separated).

## Deploy with the Hi Tuto frontend

```bash
npm run build
rsync -a --delete --exclude _headers dist/ ../frontend/public/whiteboard/
```

The Vite base is `/whiteboard/`, so the generated HTML loads its assets from
`/whiteboard/assets/`. Deploy the main frontend through InsForge after copying
the build output.
