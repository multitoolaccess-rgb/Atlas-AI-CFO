/**
 * Self-hosted font definitions via `next/font/google`.
 *
 * Using `next/font` eliminates layout shift (CLS) by:
 * - Self-hosting font files at build time (no external network request)
 * - Generating a `@font-face` with `size-adjust` so the fallback matches
 *   exactly, producing zero visual shift when the real font loads
 * - Preloading the font files in `<head>` automatically
 *
 * The CSS variables (`--font-primary`, `--font-mono`) are injected on
 * `<body>` so existing references in `tokens.css`, `utilities.css`,
 * and inline `fontFamily` props in chart components keep working.
 */

import { Space_Grotesk, JetBrains_Mono } from 'next/font/google'

export const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-primary',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
})

export const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
  weight: ['400', '500', '600'],
})
