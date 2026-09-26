import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Share the repo-root .env; only VITE_* variables are exposed to the browser bundle.
  envDir: "..",
  server: {
    host: true,
    port: 5173,
    // Public HTTPS tunnel hostnames (e.g. for Meta OAuth/webhook testing), comma-separated.
    allowedHosts: process.env.VITE_ALLOWED_HOSTS?.split(",").filter(Boolean),
    // Docker Desktop bind mounts on Windows/macOS don't forward file-change events.
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
