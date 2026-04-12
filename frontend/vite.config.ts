import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      // No /ws proxy: useWebSocket connects directly to ws://127.0.0.1:8000/ws
      // in dev mode to avoid Vite-middleman EPIPE on uvicorn reloads.
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
