/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // Same origin as the API in development, so the session cookie just works.
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      include: ['src/**'],
      // shadcn/ui primitives are vendored library code; main.tsx only mounts the app.
      exclude: ['src/components/ui/**', 'src/test/**', 'src/main.tsx', '**/*.test.*'],
    },
  },
})
