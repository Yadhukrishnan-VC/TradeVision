import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// TradeVision frontend — Vite + React + TS + Tailwind.
// The backend base URL is configurable via VITE_API_BASE_URL (default: relative /api/v1).
// Override by setting VITE_API_BASE_URL=https://your-backend/api/v1 in .env.
//
// Port 3000 is required by the system's preview gateway (Caddy proxies the
// external preview URL to localhost:3000).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 3000,
    host: true,
    strictPort: true,
    // Proxy API + WebSocket traffic to the Django backend so the relative
    // API_BASE_URL (/api/v1) works from the Vite dev server without a
    // separate nginx in front. Both containers share the compose network.
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://backend:8000",
        ws: true,
      },
    },
    // Restrict Vite's file-system scope so it doesn't try to process files
    // under skills/ or upload/ (which contain reference HTML that imports
    // packages like `three` not present in this project's node_modules).
    fs: {
      allow: [
        fileURLToPath(new URL(".", import.meta.url)),
        fileURLToPath(new URL("node_modules", import.meta.url)),
      ],
      deny: [
        fileURLToPath(new URL("skills", import.meta.url)),
        fileURLToPath(new URL("upload", import.meta.url)),
      ],
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
