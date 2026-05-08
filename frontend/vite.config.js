import { defineConfig } from "vite";

const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:18777";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
