module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  plugins: ["react-refresh"],
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    // streaming read döngüleri (`while (true) { ... if (done) break; }`) için gerekli
    "no-constant-condition": ["error", { checkLoops: false }],
  },
  ignorePatterns: ["dist", "node_modules", "*.cjs", "*.js"],
};
