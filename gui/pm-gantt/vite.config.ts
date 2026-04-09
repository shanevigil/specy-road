import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const outDir = path.resolve(__dirname, "../../specy_road/pm_gantt_static");

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir,
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
