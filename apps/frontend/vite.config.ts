import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api/auth": {
        target: "http://127.0.0.1:3001",
      },
      // Same origin as the session cookie. A direct call to port 8000 is a
      // different site for some browsers, so the cookie is left behind.
      "/me": {
        target: "http://127.0.0.1:8000",
      },
      "/health": {
        target: "http://127.0.0.1:8000",
      },
      "/api/documents": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/api/search": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
})
