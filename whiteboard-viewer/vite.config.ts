import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // The viewer is bundled into the main frontend at /whiteboard/. Without an
  // explicit base, Vite emits /assets/* URLs that resolve to the parent SPA.
  base: "/whiteboard/",
  plugins: [react()],
  server: {
    port: 5174,
    // Allow Hi Tuto parent to embed during local dev.
    headers: {
      "Content-Security-Policy": "frame-ancestors *",
    },
  },
  preview: {
    port: 5174,
    headers: {
      "Content-Security-Policy": "frame-ancestors *",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
