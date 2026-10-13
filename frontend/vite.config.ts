import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// RTD.MUAR — dev проксирует /api и /ws на backend:8000.
// Для стенда без Vite: `npm run build` + любой сервер с реверсом (см. deploy/nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,            // слушает 0.0.0.0 — доступно извне контейнера
    port: Number(process.env.PORT || 5173),
    allowedHosts: ['rtd.heartwins.ru', '.heartwins.ru', 'host.docker.internal'],
    proxy: {
      '/api': { target: process.env.BACKEND_URL || 'http://localhost:8000', changeOrigin: true },
      '/ws':  { target: (process.env.BACKEND_URL || 'http://localhost:8000').replace('http','ws'), ws: true },
    },
  },
});
