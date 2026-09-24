import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the Vite server proxies /api to the backend so cookies and the
// SSE stream behave the same as behind nginx in docker.
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // three.js is lazy-loaded into its own ~530 kB chunk on purpose (sign-in page only)
  build: { chunkSizeWarningLimit: 600 },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
    },
  },
  test: {
    environment: "node",
  },
});
