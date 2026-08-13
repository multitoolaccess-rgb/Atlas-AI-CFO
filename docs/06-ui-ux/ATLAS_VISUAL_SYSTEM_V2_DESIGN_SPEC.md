# Atlas Visual System v2

## Design read

Reading this as: a redesign of a data-dense personal AI-CFO command center for a sophisticated wealth owner, with a luminous-precision language, leaning toward a restrained futuristic product system rather than a marketing dashboard template.

Dials: `DESIGN_VARIANCE: 6`, `MOTION_INTENSITY: 6`, `VISUAL_DENSITY: 7`. The design will preserve Atlas's dense financial workflows while replacing decorative glass and profile-specific semantic color drift with a calmer, more deliberate visual hierarchy.

## Audit findings

- `ui/styles/tokens.css` already acts as the primary token source, but its palette mixes electric blue, cyan, violet, gold, and emerald as identity accents and lacks an independent accent-profile contract.
- `.dark` is the canonical mode class, but persistence is a binary `atlas_theme` toggle. There is no Light/Dark/System selection or hydration-safe profile attribute.
- `Space Grotesk` and `JetBrains Mono` are already self-hosted through the existing Next font mechanism and will be retained.
- The shared `.card` currently applies backdrop blur, gradient surfaces, glow, shadow, and hover lift globally. This will be reduced to tonal surfaces and sparse elevation; blur will remain reserved for fixed header/overlay layers.
- The sidebar and header use fixed heights, broad uppercase/tracked labels, and scattered direct palette aliases. They will be migrated to semantic shell tokens without changing routes or labels.
- Chart palettes are partly centralized in `ui/lib/themeColors.ts` and partly inline. The unified palette will preserve emerald gains, rose losses, amber warnings, and neutral information across all profiles while using the active accent only for Atlas-selected context.
- The Settings page has no authoritative appearance section. Appearance controls will be added without moving existing settings workflows.
- Existing focused tests cover binary dark-mode behavior and shared tokens. New tests will cover independent mode/profile persistence, fallback, bootstrap, keyboard selection, and semantic-color invariants.

## Selected architecture

- Mode is stored as `atlas_theme_mode` with `light`, `dark`, or `system`; the existing `.dark` class remains the runtime authority.
- Accent is stored independently as `atlas_accent_profile` with `indigo`, `vermilion`, or `ion`; `data-atlas-accent` on `<html>` is the runtime authority.
- A tiny inline bootstrap in the root layout applies both values before hydration. Invalid values fall back to Light/System-compatible existing behavior and Indigo.
- A client appearance controller observes `storage` events for cross-tab synchronization and `matchMedia('(prefers-color-scheme: dark)')` for System mode.
- Components consume semantic CSS variables. Profile values are defined only in the token layer; financial signal tokens never reference profile tokens.
- The app shell uses one coherent radius scale: 6px controls, 10px panels, 14px focal surfaces, and full pills only for compact status controls.
- Surface hierarchy uses canvas, base, raised, and overlay tokens. Scrolling cards do not use backdrop blur.

## Layout and interaction blueprint

- Desktop: fixed navigation rail, sticky utility header, fluid content canvas capped at 1440px. The dashboard uses an asymmetric 8/4 lead area followed by dense evidence rows.
- Tablet: collapsible rail and two-column content where evidence remains readable; chart containers retain minimum readable labels.
- Mobile: rail becomes an off-canvas drawer, header actions remain reachable, all changed multi-column sections collapse to one column with 16px gutters, and no content relies on hover.
- Settings Appearance: a full-width section near the top with a mode segmented control and three keyboard-operable preview tiles. Each tile has name, description, accent swatch, surface preview, selected state, and screen-reader announcement.
- Archive and command surfaces remain fixed/overlay layers and may use controlled translucency. Ordinary data surfaces stay opaque.
- Active navigation uses accent-subtle background plus a visible accent border/focus treatment. Financial meaning never relies on that accent.

## State matrix

| Surface | Loading | Empty | Error/unavailable | Partial/stale | Selected/focused |
| --- | --- | --- | --- | --- | --- |
| Dashboard | layout-shaped skeletons | actionable import/setup prompt | sanitized inline recovery | freshness/coverage note | keyboard-visible focus and active route |
| Portfolio and charts | chart-shaped skeleton | explain what data is required | source-safe error panel | source/freshness badge | selected series uses profile accent; gains/losses remain semantic |
| Goals | form/list skeleton | add-goal guidance | inline validation and retry | explicit missing-input note | selected goal uses profile accent, progress semantics remain neutral/positive |
| Market Briefs | archive/detail skeleton | evidence-first empty state | stable reason-specific recovery | prior-close/coverage limitation | keyboard archive selection and readable citations |
| Settings Appearance | deterministic shell fallback | never empty | invalid storage silently falls back to Indigo | System mode tracks OS changes | selected tile announces `aria-pressed`/`aria-checked` |
| Activity and recommendations | row skeletons | explain how to create evidence | sanitized retry state | stale-source label | action review focus and approval boundaries |

## Accessibility behavior

- WCAG 2.2 AA minimum; important body text targets AAA where practical.
- All appearance controls are native buttons/radios with visible focus, 44px minimum target size, keyboard selection, and screen-reader names.
- Color is supplemented with labels, icons, direction, patterns, or text for all financial states.
- Theme transitions are short and disabled under `prefers-reduced-motion`; System mode reacts to OS changes without reload.
- Reduced transparency disables fixed-layer blur and preserves solid contrast.
- Charts retain accessible labels, legends, source/freshness context, and a textual/data fallback where the existing component supports it.
- Zoom to 200% is supported through fluid sizing, wrapping, and overflow-safe containers.

## Skill-driven decisions

- `ui-ux-pro-max`: used for the interaction architecture, state matrix, responsive behavior, chart accessibility, and semantic-color boundary.
- `impeccable`: used for audit-first product-register guidance, contrast discipline, typography hierarchy, surface restraint, motion intent, and reduced-motion requirements. Its repository context script was unavailable, so the existing Atlas code and docs were treated as the source of truth.
- The exact `taste-skill`, `design-taste-frontend`, `high-end-visual-design`, `frontend-patterns`, `react-patterns`, `react-testing`, and `e2e-testing` skills were unavailable in this runtime; no replacements were installed. Their requested responsibilities were not represented as completed skill evidence.
- Visual decisions therefore rely on the loaded `ui-ux-pro-max` and `impeccable` guidance, Atlas's existing tokens/components, and the repository's accessibility/testing evidence.
- The `ui-ux-pro-max` repository search script was not present, so its loaded quick-reference guidance was applied directly rather than persisting a generated external design system.

## Rejected alternatives

- A full component-library migration was rejected because it would add dependency and regression risk without improving Atlas's established primitives.
- A marketing-style bento/hero overhaul was rejected because financial evidence density and existing route muscle memory are the product.
- Profile-specific financial colors were rejected because accent identity must not redefine gain, loss, warning, or critical meaning.
- Universal glassmorphism and animated gradients were rejected because they reduce legibility and harm scrolling performance.
- A binary theme toggle was rejected because it cannot express System mode or remain independent from accent selection.

## Validation plan

- Focused Vitest for appearance state, token invariants, settings controls, and representative shell components.
- Full frontend Vitest, TypeScript, lint, and production build.
- Playwright visual journey at 390, 768, 1024, 1440, and 1728 widths across all six mode/profile combinations, plus System mode and reduced motion.
- Axe scans on Settings Appearance, shell, dashboard, Goals, Portfolio, Recommendations, Market Briefs, Activity, and representative charts.
- Synthetic fixtures only; no personal financial data or generated browser artifacts committed.
