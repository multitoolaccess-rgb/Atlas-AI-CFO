#!/usr/bin/env bash
# scripts/check-build.sh
#
# Canonical pre-flight build check for the Finance Copilot UI.
# Runs:
#   1. cd ui && npx tsc --noEmit      (typecheck)
#   2. cd ui && npx next build        (production build — catches PostCSS / CSS / RSC issues)
#
# Used by:
#   - .husky/pre-commit                (git pre-commit hook)
#   - CI                                (manual:  bash scripts/check-build.sh)
#   - Contributors                      (manual:  npm run check-build  from ui/)
#
# Escape hatch: SKIP_CHECK_BUILD=1 bash scripts/check-build.sh
#
# Why this exists:
#   The project previously shipped with ui/postcss.config.ts. Next.js 14's
#   postcss-load-config silently ignores .ts PostCSS config files, so the
#   Tailwind plugin never ran and every `@tailwind` directive passed through
#   untouched — the UI rendered as raw HTML. Running `next build` here catches
#   that failure mode (and similar config-time silent regressions) before
#   they reach a contributor's browser.

set -euo pipefail

# Resolve paths relative to THIS script, not the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"

# Allow escape hatch (don't ship a CI loop-hole though — recommit with --no-verify).
if [ "${SKIP_CHECK_BUILD:-0}" = "1" ]; then
  echo "⚠️  SKIP_CHECK_BUILD=1 — skipping typecheck and build (do not commit this state)."
  exit 0
fi

# Sanity checks.
if [ ! -d "$UI_DIR" ]; then
  echo "❌  Expected ui/ at $UI_DIR but it is missing."
  echo "    Run this script from the project root, or update UI_DIR in scripts/check-build.sh."
  exit 1
fi

if [ ! -d "$UI_DIR/node_modules" ]; then
  echo "❌  $UI_DIR/node_modules is missing."
  echo "    Run:  (cd $UI_DIR && npm install)"
  exit 1
fi

# PostCSS config guardrail — re-run defensively each commit.
if [ -f "$UI_DIR/postcss.config.ts" ] && [ ! -f "$UI_DIR/postcss.config.js" ]; then
  cat <<'EOF' >&2

❌  Build-time regression detected: ui/postcss.config.ts exists but ui/postcss.config.js does not.

    Next.js 14's postcss-load-config does NOT support postcss.config.ts — it
    silently falls back to its baseline config and the Tailwind plugin never
    runs. Result: @tailwind directives pass through to output untouched and
    the UI renders as raw HTML.

    Fix:    rm ui/postcss.config.ts  (or rename it) and ensure ui/postcss.config.js
            uses CommonJS:
              module.exports = { plugins: { tailwindcss: {}, autoprefixer: {} } }

EOF
  exit 2
fi

# Pretty banner.
echo ""
echo "========================================="
echo "🔍 Pre-flight build check (Finance Copilot UI)"
echo "========================================="
echo "Project root:  $PROJECT_ROOT"
echo "UI directory:  $UI_DIR"
echo ""

# Use local binaries from node_modules instead of `npx` so the script never
# silently fetches a different registry version during CI / fresh clones.
TSC_BIN="$UI_DIR/node_modules/.bin/tsc"
NEXT_BIN="$UI_DIR/node_modules/.bin/next"

if [ ! -x "$TSC_BIN" ] || [ ! -x "$NEXT_BIN" ]; then
  echo "❌  Missing local binaries: $TSC_BIN or $NEXT_BIN"
  echo "    Run:  (cd \"$UI_DIR\" && npm install)"
  exit 1
fi

# 1. TypeScript typecheck.
# NOTE: use `if ! ... then` (NOT a bare subshell) so `set -e` doesn't exit early
# and we can print the friendly remediation guidance on failure.
echo "➡️  Step 1/2:  tsc --noEmit  (typecheck, local)"
echo "-----------------------------------------"
if ! ( cd "$UI_DIR" && "$TSC_BIN" --noEmit ); then
  cat <<'EOF' >&2

❌  Typecheck failed (exit 1).

    If this is your first time seeing this after a clean clone, run:
        (cd ui && npm install)
    then re-run:  bash scripts/check-build.sh

EOF
  exit 1
fi

echo ""
echo "✅  Typecheck passed."
echo ""

# 2. ESLint — catches dark: semantic token overrides + next/core-web-vitals.
echo "➡️  Step 2/3:  next lint  (ESLint, local)"
echo "-----------------------------------------"
if ! ( cd "$UI_DIR" && "$NEXT_BIN" lint --max-warnings 0 ); then
  cat <<'EOF' >&2

❌  ESLint failed (exit 1).

    Fix the warnings/errors above. The custom rule
    local-rules/no-semantic-dark-overrides catches dark: overrides on
    semantic color tokens (warning, danger, success, info, primary)
    which fight the CSS variable inversion in tokens.css.

EOF
  exit 1
fi

echo ""
echo "✅  Lint passed."
echo ""

# 3. Production build — catches Tailwind/PostCSS silent regressions, RSC errors, etc.
echo "➡️  Step 3/3:  next build  (production build, local)"
echo "-----------------------------------------"
if ! ( cd "$UI_DIR" && "$NEXT_BIN" build ); then
  cat <<'EOF' >&2

❌  Production build failed (exit 1).

    This guardrail catches the same categories enumerated at the top of this
    script (PostCSS / Tailwind config regressions, missing color ramps in
    tailwind.config.ts, broken @import paths in app/globals.css, RSC errors).

    For the most common category (Tailwind utility not generated), check that
    the class exists in tailwind.config.ts OR is a built-in Tailwind utility.

EOF
  exit 1
fi

echo ""
echo "========================================="
echo "========================================="
echo "✅  All checks passed (typecheck + lint + build). Safe to commit."
echo "========================================="
echo "========================================="
