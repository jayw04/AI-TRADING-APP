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
    // In Docker Compose the frontend container must proxy to backend:8000,
    // not 127.0.0.1 (which is the frontend container itself). Override via
    // VITE_PROXY_TARGET / VITE_WS_PROXY_TARGET in docker-compose.yml.
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: process.env.VITE_WS_PROXY_TARGET ?? "ws://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
      },
      "/healthz": {
        target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    css: false,
  },
});
