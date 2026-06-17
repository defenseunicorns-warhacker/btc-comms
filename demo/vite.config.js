import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The STABLE recorder the demo drives. Override with STABLE_URL when needed.
const TARGET = process.env.STABLE_URL || 'http://localhost:8001'

// Every backend route the demo touches is proxied so the app can use
// same-origin relative URLs in dev *and* when served from the recorder
// itself (air-gapped). EventSource (SSE) is proxied too.
const proxied = ['/stream', '/events', '/verify', '/entries', '/anchors',
  '/anchor', '/seed', '/tamper', '/demo', '/info', '/keys', '/agent']

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      proxied.map((p) => [p, { target: TARGET, changeOrigin: true }]),
    ),
  },
  build: { outDir: 'dist' },
})
