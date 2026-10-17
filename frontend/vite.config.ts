/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@tests': fileURLToPath(new URL('./tests', import.meta.url)),
    },
  },
  server: {
    // Same origin as the API in development, so the session cookie just works.
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/support/setup.ts'],
    css: false,
    coverage: {
      include: ['src/**'],
      // shadcn/ui primitives are vendored library code; main.tsx only mounts the app.
      exclude: ['src/components/ui/**', 'src/main.tsx'],
      // `npm run coverage` (and CI) fails if coverage drops below these.
      thresholds: { statements: 96, branches: 93, functions: 94, lines: 97 },
    },
  },
})
