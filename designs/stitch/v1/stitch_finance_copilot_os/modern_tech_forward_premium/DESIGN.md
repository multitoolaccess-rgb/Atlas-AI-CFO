---
name: CashFlix Glass Portfolio
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#45464d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#006b5f'
  on-secondary: '#ffffff'
  secondary-container: '#9cefdf'
  on-secondary-container: '#0b6f63'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#131b2e'
  on-tertiary-container: '#7c839b'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#9ff2e2'
  secondary-fixed-dim: '#83d5c6'
  on-secondary-fixed: '#00201c'
  on-secondary-fixed-variant: '#005047'
  tertiary-fixed: '#dae2fc'
  tertiary-fixed-dim: '#bec6e0'
  on-tertiary-fixed: '#131b2e'
  on-tertiary-fixed-variant: '#3f465b'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
  surface-gradient-start: '#f8f9ff'
  surface-gradient-end: '#eff4ff'
  glass-border: rgba(255, 255, 255, 0.4)
  glass-bg: rgba(255, 255, 255, 0.9)
  success-green: '#006b5f'
  error-red: '#ba1a1a'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.25'
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: '1.4'
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: '1'
    letterSpacing: 0.01em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '700'
    lineHeight: '1.2'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  stack-tight: 8px
  stack-loose: 16px
  card-gap: 24px
  container-padding: 32px
  gutter: 24px
---

## Brand & Style
The brand personality is sophisticated, intelligent, and highly professional, positioned as a "Financial Copilot." It targets high-net-worth individuals and tech-savvy investors who value clarity and data density without feeling overwhelmed.

The visual style is **Glassmorphism mixed with Modern Corporate**. It utilizes translucent, blurred surfaces to create a sense of depth and lightness, while maintaining a rigorous structural grid. The interface should feel like a premium command center—airy yet authoritative, using light-blue tints and radial gradients to evoke a sense of continuous flow and technological advancement.

## Colors
The palette is rooted in deep "Slate" blacks and crisp "Ice" blues. 

- **Primary (#0f172a):** Used for high-emphasis text, icons, and core brand elements.
- **Secondary (#006b5f):** A teal-heavy green representing growth and financial health. Used for positive trends and primary actions.
- **Backgrounds:** Instead of flat colors, use a radial gradient from `#f8f9ff` to `#eff4ff`. 
- **Glass Surfaces:** Components utilize a semi-transparent white background with a heavy backdrop blur.
- **Accents:** Use low-opacity tints of primary and secondary colors for status indicators (e.g., 10% opacity fills).

## Typography
The system relies exclusively on **Inter** to maintain a clean, systematic, and utilitarian feel. 

Hierarchy is established primarily through font-weight and letter-spacing rather than massive size shifts. Large headlines (`headline-xl`) should use negative letter-spacing for a "tight" editorial look. Data labels (`label-md`) use uppercase transformations and wider tracking to differentiate themselves from prose. Tables and dense data views utilize `body-md` for optimal legibility within constrained spaces.

## Layout & Spacing
The layout uses a **12-column Bento Grid** system. This allows for modular data "widgets" that can span various widths (e.g., 8-column main charts paired with 4-column sidebars).

- **Margins:** 32px page margins on desktop, reducing to 16px on mobile.
- **Gaps:** A consistent 24px gap between all major dashboard modules.
- **Sidebar:** A fixed 256px (w-64) sidebar for primary navigation.
- **Mobile Adaptation:** Columns stack vertically (12-span) and glass effects are simplified to reduce GPU load. Spacing units are based on a 4px baseline.

## Elevation & Depth
Depth is achieved through **Glassmorphism** and soft ambient shadows. 

1.  **Base Layer:** The radial gradient background.
2.  **Surface Layer:** Semi-transparent containers with `backdrop-filter: blur(10px)`. These feature a thin `1px` border of `rgba(255, 255, 255, 0.4)` to simulate light catching the edge of the glass.
3.  **Shadows:** Use extra-diffused, low-opacity shadows (`rgba(0, 0, 0, 0.04)`) with a large blur radius (40px) and a downward offset (20px).
4.  **Active State:** Interactive cards should lift slightly on hover (translate -2px) with a subtle increase in shadow spread.

## Shapes
The shape language is generous and friendly, utilizing high corner radii to soften the data-heavy nature of the app.

- **Main Cards/Widgets:** 24px (rounded-3xl) for a distinctive "bento" look.
- **Standard Buttons/Inputs:** 12px (rounded-xl).
- **Navigation Items:** 8px (rounded-lg).
- **Search Bars/Pills:** Fully rounded (9999px) to provide visual variety and signify "utility" elements.

## Components
- **Buttons:** Primary buttons use solid fills (Dark Slate or Teal). Secondary buttons use a white-glass base with thin borders. All buttons should have a 200ms scale transition (scale-98) on click.
- **Input Fields:** Search bars should be pill-shaped with `surface-container-low` fills and no borders, using icons as leading elements.
- **Glass Cards:** The "Bento" cards are the hero component. They must include a `linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(248, 249, 255, 0.7))` fill.
- **Data Tables:** Use a "Ghost" style—transparent backgrounds with 1px horizontal dividers. Highlight rows on hover with a subtle `surface-container-low` tint.
- **Progress Bars:** Thin 8px tracks with fully rounded ends. Use primary color for standard goals and secondary color for "bonus" or specific financial targets.
- **Navigation:** Vertical sidebar with high-contrast active states (using `surface-container-high`) and icon-label pairings using Material Symbols (Outlined style).