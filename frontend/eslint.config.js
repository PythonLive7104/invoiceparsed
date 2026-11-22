import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

/**
 * Minimal, high-signal lint config.
 *
 * The rule that earns its keep here is `no-undef`. This is plain JS with no
 * type checker, so a reference to an identifier that does not exist builds
 * cleanly and only fails in the browser — which is exactly how `plan is not
 * defined` reached production. Everything stylistic is left off deliberately,
 * so a lint failure always means a real defect.
 */
export default [
  { ignores: ["dist/**", "node_modules/**", "public/**"] },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx,mjs}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { react, "react-hooks": reactHooks },
    settings: { react: { version: "detect" } },
    rules: {
      // JSX counts as "using" a component, so React components are not unused.
      "react/jsx-uses-vars": "error",
      "react/jsx-uses-react": "off",
      // Hooks called conditionally or out of order are a real runtime bug.
      "react-hooks/rules-of-hooks": "error",
      // Unused vars are warnings, not errors: often mid-refactor, never a crash.
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
];
