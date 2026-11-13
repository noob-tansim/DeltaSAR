import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// Deployed on Vercel at the site root. The API lives on Render; its address comes from VITE_API_BASE.
// In development `npm run dev` proxies /api to a local backend (port 8010, or API_PROXY).
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      injectRegister: false,
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,woff2,svg}', 'icons/*.png'],
        maximumFileSizeToCacheInBytes: 4_000_000,
      },
      manifest: {
        id: '/app/',
        name: 'বন্যা সাথী · Bonna Sathi',
        short_name: 'বন্যা সাথী',
        description: 'River water and bank changes seen by NASA-ISRO NISAR radar, checked by a volunteer, spoken in Bangla.',
        lang: 'bn',
        start_url: '/app/',
        scope: '/',
        display: 'standalone',
        background_color: '#EEF3F3',
        theme_color: '#0B6E7F',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 5173,
    proxy: { '/api': process.env.API_PROXY ?? 'http://127.0.0.1:8010' },
  },
  preview: { port: 4173, proxy: { '/api': process.env.API_PROXY ?? 'http://127.0.0.1:8010' } },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
  },
});
