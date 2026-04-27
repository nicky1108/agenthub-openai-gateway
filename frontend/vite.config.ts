import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/auth": backendTarget,
      "/admin": backendTarget,
      "/admin-api": {
        target: backendTarget,
        rewrite: (path) => path.replace(/^\/admin-api/, "/admin"),
      },
      "/portal/dashboard": backendTarget,
      "/portal/catalog": backendTarget,
      "/portal/sync/retry": backendTarget,
      "/portal/usage/records": backendTarget,
      "/user": backendTarget,
      "/v1": backendTarget,
      "/healthz": backendTarget,
    },
  },
  test: {
    environment: "jsdom",
  },
});
