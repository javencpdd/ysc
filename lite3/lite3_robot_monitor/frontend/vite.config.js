import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端服务地址，可通过环境变量覆盖
// 开发环境通过 Vite proxy 转发 /api 与 /ws，生产环境可直接指向后端
const backend = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      // REST 接口代理
      '/api': {
        target: backend,
        changeOrigin: true
      },
      // WebSocket 代理，必须显式开启 ws
      '/ws': {
        target: backend.replace(/^http/, 'ws'),
        ws: true,
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200
  }
})
