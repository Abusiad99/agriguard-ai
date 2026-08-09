import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// AgriGuard AI — frontend build configuration.
// Dev server proxies /api and /storage to the FastAPI backend (see
// backend/app/main.py) so the frontend can call relative paths in both dev and
// production (NGINX performs the equivalent proxying in production — see
// docker/nginx/nginx.conf).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/storage": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
