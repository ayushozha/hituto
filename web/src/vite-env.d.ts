/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_REBOOT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
