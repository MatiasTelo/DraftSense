import react from '@vitejs/plugin-react';
// defineConfig sale de vitest/config, no de vite: es la variante que acepta el bloque `test`.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // En desarrollo el frontend habla con el backend local sin CORS.
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    // RNF-03: el bundle inicial no debe pasar de 200 KB gzip.
    chunkSizeWarningLimit: 250,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
