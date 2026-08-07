import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  root: "web",
  build: {
    chunkSizeWarningLimit: 1200,
    outDir: "../docs",
    emptyOutDir: true,
  },
});
