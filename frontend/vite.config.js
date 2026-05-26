import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy API calls to the FastAPI backend in dev mode
    proxy: {
      '/health':    { target: 'http://localhost:8000', changeOrigin: true },
      '/ingest':    { target: 'http://localhost:8000', changeOrigin: true },
      '/query':     { target: 'http://localhost:8000', changeOrigin: true },
      '/anomalies': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
