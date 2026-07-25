import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API + tool-server routes to the backend so the dashboard and the
// artifact iframe (which uses relative /gen, /image, ...) work same-origin in dev.
// Auth-disabled e2e API (AUTH_DISABLED=1). Use IPv4 loopback — uvicorn binds 127.0.0.1,
// and `localhost` can resolve to ::1 first and break the Vite proxy.
const backend = "http://127.0.0.1:8078";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Cloudflare quick tunnels (*.trycloudflare.com) hit Vite with a foreign Host header.
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/courses": { target: backend, changeOrigin: true, ws: true },
      "/sources": { target: backend, changeOrigin: true },
      "/shared": { target: backend, changeOrigin: true },
      "/insights": { target: backend, changeOrigin: true },
      "/profile": { target: backend, changeOrigin: true },
      "/billing": { target: backend, changeOrigin: true },
      "/gen": backend,
      "/image": backend,
      "/audio": backend,
      "/mesh": backend,
      "/maps": backend,
      "/health": backend,
    },
  },
});
