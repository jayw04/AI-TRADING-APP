/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: process.env.VITE_DEV_HOST ?? "127.0.0.1",
    port: 5173,
    strictPort: true,
    // P5 §3: proxy the API + WebSocket through Vite so the browser sees a
    // single origin. The httpOnly, SameSite=Strict session cookie set by the
    // backend then flows on every request without CORS-credentials gymnastics
    // — the same posture as a real same-origin reverse-proxied deployment.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true, changeOrigin: true },
      "/healthz": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    css: false,
  },
});
