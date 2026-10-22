import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
// defineConfig sale de vitest/config, no de vite: es la variante que acepta el bloque `test`.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Sólo la máquina, como el backend del panel (ADR-025). 5174 para no chocar con la SPA
    // pública, que usa 5173.
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
