import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Em desenvolvimento, as chamadas a /api vão para o FastAPI (sem CORS).
const API = process.env.VITE_DEV_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // O Plotly (~1 MB) é carregado sob demanda, só quando o primeiro gráfico aparece.
  build: { chunkSizeWarningLimit: 1200 },
  server: { port: 5173, proxy: { "/api": API } },
  preview: { port: 4173, proxy: { "/api": API } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
