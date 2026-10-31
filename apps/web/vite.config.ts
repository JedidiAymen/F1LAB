import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  server: {
    proxy: { "/api": process.env.F1LAB_API_URL ?? "http://127.0.0.1:8000" },
  },
  plugins: [
    react(),
    tailwindcss(),
  ],
  // Discover the lazy research chart dependency before navigation; otherwise
  // the first dev-only optimizer reload resets the selected workspace.
  optimizeDeps: { include: ['recharts'] },
  resolve: {
    alias: {
      "@": import.meta.dirname + "/src",
    },
  },
})
