import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom", "zod"] },
  server: {
    host: true,
    port: parseInt(process.env.PORT ?? "5173", 10),
  },
  test: {
    environment: "jsdom",
  },
});
