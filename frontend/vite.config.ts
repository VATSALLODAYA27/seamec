import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// During development the API runs on port 8000; requests to /api are forwarded there.
export default defineConfig({
  plugins: [react()],
  server: { port: 5180, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
