import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { Connect, ViteDevServer } from 'vite'
import { defineConfig } from 'vitest/config'

function setupConsoleCanonicalUrl() {
  const rewrite: Connect.NextHandleFunction = (req, _res, next) => {
    const raw = req.url || ''
    const [pathName, query] = raw.split('?')
    const clean = (pathName || '').replace(/\/+$/, '') || '/'
    if (clean === '/setup-console' || clean === '/setup-console.html') {
      req.url = `/dashboard/setup-console.html${query ? `?${query}` : ''}`
    }
    next()
  }
  return {
    name: 'setup-console-canonical-url',
    configureServer(server: ViteDevServer) {
      server.middlewares.use(rewrite)
    },
    configurePreviewServer(server: ViteDevServer) {
      server.middlewares.use(rewrite)
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  base: '/dashboard/',
  plugins: [react(), tailwindcss(), setupConsoleCanonicalUrl()],
  server: {
    proxy: {
      '/dashboard/superadmin': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      input: {
        dashboard: path.resolve(__dirname, 'index.html'),
        setupConsole: path.resolve(__dirname, 'setup-console.html'),
      },
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/')) {
            return 'react-vendor'
          }
          if (id.includes('node_modules/@tanstack/react-query/')) {
            return 'react-query'
          }
          if (id.includes('node_modules/lucide-react/')) {
            return 'lucide'
          }
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
