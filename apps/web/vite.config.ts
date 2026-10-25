import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // Relative asset paths, so the build can be hosted under any sub-path (GitHub Pages…).
  base: "./",
  server: { fs: { allow: ["../.."] }, port: 5174, open: false },
  test: { environment: "node", include: ["test/**/*.test.ts"] },
});
