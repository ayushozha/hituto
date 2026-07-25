/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Required unless VITE_AUTH_DISABLED=1. */
  readonly VITE_CLERK_PUBLISHABLE_KEY?: string;
  readonly VITE_INSFORGE_URL: string;
  readonly VITE_INSFORGE_ANON_KEY: string;
  readonly VITE_API_BASE_URL?: string;
  /** When "1", skip Clerk auth and use a synthetic local "dev" user. */
  readonly VITE_AUTH_DISABLED?: string;
  /** Excalidraw whiteboard viewer origin (defaults to same-origin /whiteboard). */
  readonly VITE_WHITEBOARD_VIEWER_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
