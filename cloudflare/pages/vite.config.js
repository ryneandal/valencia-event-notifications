import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  publicDir: 'static',
  plugins: [react()],
  build: {
    outDir: 'public',
    emptyOutDir: true
  }
});
