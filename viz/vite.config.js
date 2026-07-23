import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' keeps asset paths relative so a static build can be opened anywhere.
export default defineConfig({
  base: './',
  plugins: [react()],
})
