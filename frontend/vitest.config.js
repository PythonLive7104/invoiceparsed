import { defineConfig } from "vite";
import path from "path";

/**
 * Test config, kept separate from vite.config.js.
 *
 * `css.postcss: {}` is the important line. Vite resolves postcss.config.js as
 * part of loading any config, and doing so inside Vitest fails here with
 * "Cannot read properties of undefined (reading 'config')" — the Tailwind v3
 * PostCSS plugin does not initialise in that context. An inline (empty) postcss
 * config stops Vite searching for the file at all.
 *
 * Nothing is lost: these tests cover behaviour, not styling, and Vitest does
 * not render CSS. The app build still uses vite.config.js and the real PostCSS
 * pipeline, so Tailwind output is unaffected.
 *
 * The React plugin is also deliberately absent — add it here when component
 * tests need JSX compiled.
 */
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  css: { postcss: {} },
  test: {
    environment: "node",
    include: ["src/**/*.test.{js,jsx}"],
  },
});
