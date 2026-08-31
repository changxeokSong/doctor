import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 8777,
    host: true, // 네트워크에 노출 (0.0.0.0:8777) — 2026-07-27부로 8501에서 변경
    proxy: {
      // 백엔드(Django, http://localhost:8000)로 그대로 프록시 — CORS 설정과 별개로 개발 편의용.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
