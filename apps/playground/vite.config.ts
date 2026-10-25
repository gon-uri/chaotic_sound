import { defineConfig } from "vite";

export default defineConfig({
  // The examples and the catalog live at the repository root.
  server: { fs: { allow: ["../.."] }, open: false, port: 5173 },
});
