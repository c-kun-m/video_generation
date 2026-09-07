import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: { build: { externalizeDeps: false } },
  preload: {
    build: {
      externalizeDeps: false,
      rollupOptions: { output: { format: "cjs" } },
    },
  },
  renderer: {
    plugins: [react()],
    server: { host: "127.0.0.1", port: 5173, strictPort: true },
  },
});
