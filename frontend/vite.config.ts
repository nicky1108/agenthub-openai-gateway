import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3002,
    proxy: {
      "/auth": "http://127.0.0.1:8788",
      "/admin": "http://127.0.0.1:8788",
      "/portal/dashboard": "http://127.0.0.1:8788",
      "/portal/catalog": "http://127.0.0.1:8788",
      "/user": "http://127.0.0.1:8788",
      "/v1": "http://127.0.0.1:8788",
      "/healthz": "http://127.0.0.1:8788",
    },
  },
  test: {
    environment: "jsdom",
  },
});
