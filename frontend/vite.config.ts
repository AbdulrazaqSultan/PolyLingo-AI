import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwind from "@tailwindcss/vite";
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwind()],
  server: {
    proxy: Object.fromEntries(
      ["/api", "/docs", "/redoc", "/openapi.json"].map((path) => [
        path,
        {
          target:
            loadEnv(mode, process.cwd(), "POLYLINGO_")
              .POLYLINGO_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      ]),
    ),
  },
}));
