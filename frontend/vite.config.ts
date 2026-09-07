import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8520",
        // Keep Host aligned with the browser Origin for the API's same-origin check.
        changeOrigin: false,
      },
    },
  },
  build: { outDir: "dist" },
});
