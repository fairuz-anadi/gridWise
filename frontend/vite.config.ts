import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Build output stays in frontend/dist (gitignored). The Dockerfile copies it and
// FastAPI serves it at "/", so all API calls are same-origin in production.
// In dev, /health and /optimize-energy are proxied to the local uvicorn.
export default defineConfig({
  plugins: [react()],
  server: {
    // lets src/samples.ts import ../../tests/fixtures/public_cases.json (one source of truth)
    fs: { allow: ['..'] },
    proxy: {
      '/health': 'http://localhost:8000',
      '/optimize-energy': 'http://localhost:8000',
    },
  },
  // Inline (empty) PostCSS config so Vite never walks up the tree and picks up an unrelated
  // postcss.config.* from a parent directory on someone's machine.
  css: { postcss: {} },
  build: { sourcemap: false },
})
