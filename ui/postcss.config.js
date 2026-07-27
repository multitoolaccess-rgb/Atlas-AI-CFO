// IMPORTANT: must be .js (not .ts).
// Next.js 14's postcss-load-config does not support postcss.config.ts —
// when the file has a .ts extension it is silently ignored and Tailwind
// plugin never runs, breaking all @tailwind directives.
// Note: ui/tailwind.config.ts is supported (Tailwind's own loader handles .ts).
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
