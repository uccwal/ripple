import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // 하위 경로 호스팅(GitHub Pages: /ripple/)은 VITE_BASE 로 지정한다
  base: process.env.VITE_BASE || '/',
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    target: 'es2022',
    // ECharts(S4)·Vue Flow(S3)는 라우트 단위 지연 로딩으로 분리된다. ECharts 청크가 커서 경고 한도만 올린다.
    chunkSizeWarningLimit: 1200,
  },
})
