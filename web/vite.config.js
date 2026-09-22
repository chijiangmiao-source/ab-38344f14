import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During local development /api and /health(api) are proxied to the API.
// In the container the static build is served by nginx, which performs the
// same proxying, so the browser always uses same-origin relative URLs.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
