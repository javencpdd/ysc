import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发态：Vite 5173 直连后端 8080（REST + WS 同源）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8080', ws: true }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
