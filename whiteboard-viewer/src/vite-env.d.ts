/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ALLOWED_PARENT_ORIGINS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
