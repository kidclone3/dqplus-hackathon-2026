import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The gateway has no CORS layer; the dev/preview servers proxy /api/* to it instead.
const proxy = {
  '/api': {
    target: process.env.GATEWAY_URL || 'http://localhost:3000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 5173, proxy },
});
