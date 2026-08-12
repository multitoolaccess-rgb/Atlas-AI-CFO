/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      scale: {
        '98': '0.98',
      },
      colors: {
        // === Brand & status scales (mapped from styles/tokens.css) ===
        // Single source of truth is tokens.css — Tailwind builds utilities from these.

        // Primary brand (deep professional blue)
        primary: {
          50: 'var(--primary-50)',
          100: 'var(--primary-100)',
          200: 'var(--primary-200)',
          300: 'var(--primary-300)',
          400: 'var(--primary-400)',
          DEFAULT: 'var(--primary-500)',
          500: 'var(--primary-500)',
          600: 'var(--primary-600)',
          700: 'var(--primary-700)',
          800: 'var(--primary-800)',
          900: 'var(--primary-900)',
        },
        // Success / prosperity (finance vocabulary)
        success: {
          50: 'var(--success-50)',
          100: 'var(--success-100)',
          200: 'var(--success-200)',
          300: 'var(--success-300)',
          400: 'var(--success-400)',
          DEFAULT: 'var(--success-500)',
          500: 'var(--success-500)',
          600: 'var(--success-600)',
          700: 'var(--success-700)',
          800: 'var(--success-800)',
          900: 'var(--success-900)',
        },
        // Warning / volatility
        warning: {
          50: 'var(--warning-50)',
          100: 'var(--warning-100)',
          200: 'var(--warning-200)',
          300: 'var(--warning-300)',
          400: 'var(--warning-400)',
          DEFAULT: 'var(--warning-500)',
          500: 'var(--warning-500)',
          600: 'var(--warning-600)',
          700: 'var(--warning-700)',
          800: 'var(--warning-800)',
          900: 'var(--warning-900)',
        },
        // Danger / losses
        danger: {
          50: 'var(--danger-50)',
          100: 'var(--danger-100)',
          200: 'var(--danger-200)',
          300: 'var(--danger-300)',
          400: 'var(--danger-400)',
          DEFAULT: 'var(--danger-500)',
          500: 'var(--danger-500)',
          600: 'var(--danger-600)',
          700: 'var(--danger-700)',
          800: 'var(--danger-800)',
          900: 'var(--danger-900)',
        },
        // Info / neutral action
        info: {
          50: 'var(--info-50)',
          100: 'var(--info-100)',
          200: 'var(--info-200)',
          300: 'var(--info-300)',
          400: 'var(--info-400)',
          DEFAULT: 'var(--info-500)',
          500: 'var(--info-500)',
          600: 'var(--info-600)',
          700: 'var(--info-700)',
          800: 'var(--info-800)',
          900: 'var(--info-900)',
        },

        // === Finance semantic vocabulary (single colors) ===
        positive: 'var(--signal-positive)',
        negative: 'var(--signal-negative)',
        neutral: 'var(--signal-neutral)',
        critical: 'var(--signal-critical)',
        recommended: 'var(--signal-recommended)',

        // === Background & surface tokens (used as Tailwind utilities) ===
        background: 'var(--bg-primary)',
        // M3 `on-background` — the conventional text color rendered on
        // `bg-background`. MUST reference a CSS variable (NOT a hex
        // literal) so the value flips in dark mode via tokens.css.
        // Pinned hex `#0b1c30` (dark navy) renders invisible on the
        // dark `--slate-50` background — exactly the bug this alias
        // exists to PREVENT. `--text-primary` flips via tokens.css
        // `.dark { ... }` block to the light side of the slate ladder
        // for parity contrast in both modes.
        'on-background': 'var(--text-primary)',
        // M3 surface elevation ladder. Nesting generates the full
        // `bg-surface-container-low[*]` utility set in Tailwind v3.
        // Tokens.css flips the underlying --slate-* values inside the
        // `.dark { ... }` block, so any `bg-surface-*` utility flips in
        // dark mode automatically.
        surface: {
          DEFAULT: 'var(--surface-color)',
          container: {
            lowest: 'var(--slate-50)',
            low: 'var(--slate-100)',
            DEFAULT: 'var(--slate-200)',
            high: 'var(--slate-300)',
            highest: 'var(--slate-200)',
          },
          base: 'var(--surface-base)',
          raised: 'var(--surface-raised)',
          overlay: 'var(--surface-overlay)',
          selected: 'var(--surface-selected)',
        },

        // === Semantic roles / text-on =====
        'on-primary': 'var(--on-primary-color)',
        'on-primary-container': 'var(--on-primary-container-color)',
        'on-primary-fixed': 'var(--on-primary-fixed-color)',
        'on-primary-fixed-variant': 'var(--slate-100)',
        'on-surface': 'var(--text-primary)',
        // M3 `on-surface-variant` — secondary text rendered over the
        // surface tier; follows the same `var(--text-secondary)`
        // source-of-truth that flips in dark mode via tokens.css.
        'on-surface-variant': 'var(--text-secondary)',
        'text-on-brand': '#ffffff',
        tertiary: 'var(--text-tertiary)',
        // M3 `primary-container` — the most common container tint in
        // AppBar/Card backgrounds. MUST reference a variable so the
        // value flips in dark mode; a pinned hex `#131b2e` would be
        // invisible on a dark `--bg-primary` background. `--primary-50`
        // flips correctly via tokens.css to the deep navy `#1a2358`
        // on dark, providing tonal contrast in both modes.
        'primary-container': 'var(--primary-50)',

        // === Borders ===
        'border-color': 'var(--border-color)',
        'border-subtle': 'var(--border-subtle)',
        'divider-color': 'var(--divider-color)',

        // === Outline (hex so /opacity modifier works e.g. border-outline-variant/30) ===
        outline: 'var(--outline-color)',
        'outline-variant': 'var(--outline-variant)',

        // === Sidebar dark mode tokens (deep teal/cyan palette) ===
        sidebar: {
          bg: 'var(--sidebar-bg)',
          hover: 'var(--sidebar-hover)',
          active: 'var(--sidebar-active)',
          'text-active': 'var(--sidebar-text-active)',
          'text-inactive': 'var(--sidebar-text-inactive)',
          brand: 'var(--sidebar-brand)',
        },

        // === Futuristic accent palette (Atlas design system) ===
        accent: {
          primary: 'var(--accent-primary)',
          hover: 'var(--accent-hover)',
          active: 'var(--accent-active)',
          subtle: 'var(--accent-subtle)',
          muted: 'var(--accent-muted)',
          border: 'var(--accent-border)',
          focus: 'var(--accent-focus)',
          electric: 'var(--accent-electric)',
          cyan: 'var(--accent-cyan)',
          emerald: 'var(--accent-emerald)',
          violet: 'var(--accent-violet)',
          gold: 'var(--accent-gold)',
          rose: 'var(--accent-rose)',
        },
        glow: {
          primary: 'var(--glow-primary)',
          cyan: 'var(--glow-cyan)',
          emerald: 'var(--glow-emerald)',
          violet: 'var(--glow-violet)',
          gold: 'var(--glow-gold)',
          rose: 'var(--glow-rose)',
        },

        // === Backwards-compatible single-color entries ===
        // FIX (Phase 46 -- cyan text unreadable in light mode):
        // The previous ``secondary: '#6df5e1'`` (mint cyan hex) was a
        // pinned default for EVERY ``text-secondary`` / ``bg-secondary``
        // / ``border-secondary`` / ``bg-secondary/15`` Tailwind class.
        // 20+ components use these classes (RecentActivity, Sidebar,
        // RecommendationCard, AccountAllocation, SpendingByCategory,
        // TrendChart, SecondaryInsights, etc.), so the value rendered
        // as cyan BOTH in light mode (where mint is unreadably pale
        // against white) AND in dark mode (where cyan was fine --
        // ``--slate-50`` backdrop). Pointing at ``var(--secondary-color)``
        // (defined in styles/tokens.css) flips per-theme: dark-gray in
        // light mode (``--slate-600`` = #4b5563 = 7.5:1 contrast on
        // white) AND cyan in dark mode (preserves the user's "looks
        // fine in dark mode" endorsement, including the RecentActivity
        // translucent cyan status-badge highlight). The brand-cyan
        // sidebar identity is preserved via unchanged
        // --sidebar-text-inactive / --sidebar-brand tokens, used only
        // under ``dark:`` prefixes.
        secondary: 'var(--secondary-color)',
        error: 'var(--error-color)',
        'secondary-container': 'var(--secondary-container-color)',
        'error-container': 'var(--error-container-color)',
      },
      fontFamily: {
        sans: ['var(--font-primary)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        '24px': '24px',
        '8px': '8px',
        xl: '0.75rem',
        lg: '0.5rem',
        md: '0.375rem',
        sm: '0.25rem',
        full: '9999px',
      },
      fontSize: {
        'headline-xl': ['2.25rem', { lineHeight: '2.5rem', fontWeight: '800' }],
        'headline-lg': ['1.75rem', { lineHeight: '2.25rem', fontWeight: '600' }],
        'headline-md': ['1.25rem', { lineHeight: '1.75rem', fontWeight: '600' }],
        'body-md': ['1rem', { lineHeight: '1.5rem', fontWeight: '400' }],
        'body-sm': ['0.875rem', { lineHeight: '1.25rem', fontWeight: '400' }],
        'label-md': ['0.875rem', { lineHeight: '1.25rem', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }],
        'label-sm': ['0.75rem', { lineHeight: '1rem', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }],
      },
    }
  }
}
