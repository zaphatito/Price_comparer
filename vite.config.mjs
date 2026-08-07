import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  root: "web",
  assetsInclude: ["**/*.xlsx"],
  build: {
    chunkSizeWarningLimit: 1200,
    outDir: "../docs",
    emptyOutDir: true,
  },
});
