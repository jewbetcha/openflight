import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom gives tests a real DOM so React Testing Library can render,
    // query, and fire events (clicks, typing) — not just inspect HTML strings.
    environment: 'jsdom',
    // A concrete origin enables window.localStorage (disabled under the default
    // about:blank), matching real browser behaviour the app relies on.
    environmentOptions: { jsdom: { url: 'http://localhost:8080/' } },
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
