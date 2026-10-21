import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In development the backend runs on :8000; the proxy keeps the app same-origin
// (no CORS, no env vars). In production VITE_API_BASE points at Container Apps.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/matches': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/mcp': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
