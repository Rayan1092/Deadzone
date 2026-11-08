import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: the web app runs on :5173 and proxies the sim server on :8000.
// Demo: `npm run build` and the FastAPI server serves web/dist on :8000 directly.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      // keep the browser's Host so /api/join builds a phone link to this dev server (:5173)
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/crops': 'http://localhost:8000', // detector thermal crops (served by the backend)
      '/ai-lab': 'http://localhost:8000', // AI Lab exports (DZ_AI_LAB=1)
    },
  },
})
