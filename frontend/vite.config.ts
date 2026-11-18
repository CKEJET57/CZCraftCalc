import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Только для локальной разработки и Codespaces.
// В production запросы /api обслуживает Nginx.
const BACKEND_URL = 'http://127.0.0.1:8000'
const allowedHosts = ['localhost', '.app.github.dev']

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts,
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    strictPort: true,
    allowedHosts,
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
})
