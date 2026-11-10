import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// AgriGuard AI — frontend build configuration.
// Dev server proxies /api and /storage to the FastAPI backend (see
// backend/app/main.py) so the frontend can call relative paths in both dev and
// production (in the optional Docker deployment NGINX does the same proxying —
// see docker/nginx/nginx.conf). No NGINX is needed for local development.
//
// 127.0.0.1 rather than "localhost": on Windows "localhost" can resolve to ::1
// first, while the backend dev server listens on IPv4 only.
const apiTarget = process.env.AGRIGUARD_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/storage": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
