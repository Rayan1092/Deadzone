import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: the web app runs on :5173 and proxies the sim server on :8000.
// Demo: `npm run build` and the FastAPI server serves web/dist on :8000 directly.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
