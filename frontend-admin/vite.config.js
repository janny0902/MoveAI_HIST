import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/admin/',
  server: { host: true, port: 5174 },
  build: { outDir: 'dist', sourcemap: true },
})
