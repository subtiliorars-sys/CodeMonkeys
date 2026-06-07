/** @type {import('tailwindcss').Config} */
// Vendored-Tailwind build config (Wave 4 #3). Scans the frontend so the JIT
// compiler emits exactly the utility + arbitrary-value classes the app uses
// (e.g. text-[var(--gold)], bg-yellow-900/20). Output → static/forge/tailwind.css.
module.exports = {
  content: ["./static/forge/*.html", "./static/forge/*.js"],
  theme: { extend: {} },
  plugins: [],
};
