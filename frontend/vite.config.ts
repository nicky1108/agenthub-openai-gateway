import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/auth": "http://127.0.0.1:8787",
      "/admin": "http://127.0.0.1:8787",
      "/v1": "http://127.0.0.1:8787",
      "/healthz": "http://127.0.0.1:8787",
    },
  },
  test: {
    environment: "jsdom",
  },
});
