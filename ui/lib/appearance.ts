export const THEME_MODE_KEY = 'atlas_theme_mode'
export const ACCENT_PROFILE_KEY = 'atlas_accent_profile'
export const LEGACY_THEME_KEY = 'atlas_theme'

export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'
export type AccentProfile = 'indigo' | 'vermilion' | 'ion'

export interface AppearancePreferences {
  mode: ThemeMode
  accent: AccentProfile
}

export const DEFAULT_APPEARANCE: AppearancePreferences = {
  mode: 'light',
  accent: 'indigo',
}

const VALID_MODES = new Set<ThemeMode>(['light', 'dark', 'system'])
const VALID_ACCENTS = new Set<AccentProfile>(['indigo', 'vermilion', 'ion'])

export function isThemeMode(value: string | null | undefined): value is ThemeMode {
  return Boolean(value && VALID_MODES.has(value as ThemeMode))
}

export function isAccentProfile(value: string | null | undefined): value is AccentProfile {
  return Boolean(value && VALID_ACCENTS.has(value as AccentProfile))
}

export function resolveTheme(mode: ThemeMode, prefersDark: boolean): ResolvedTheme {
  if (mode === 'system') return prefersDark ? 'dark' : 'light'
  return mode
}

function prefersDarkMode(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function readStoredAppearance(): AppearancePreferences {
  if (typeof window === 'undefined') return DEFAULT_APPEARANCE

  try {
    const storedMode = window.localStorage.getItem(THEME_MODE_KEY)
    const legacyMode = window.localStorage.getItem(LEGACY_THEME_KEY)
    const mode = isThemeMode(storedMode)
      ? storedMode
      : legacyMode === 'enabled'
        ? 'dark'
        : legacyMode === 'disabled'
          ? 'light'
          : DEFAULT_APPEARANCE.mode
    const storedAccent = window.localStorage.getItem(ACCENT_PROFILE_KEY)
    return {
      mode,
      accent: isAccentProfile(storedAccent) ? storedAccent : DEFAULT_APPEARANCE.accent,
    }
  } catch {
    return DEFAULT_APPEARANCE
  }
}

export function readDomAppearance(): AppearancePreferences {
  if (typeof document === 'undefined') return DEFAULT_APPEARANCE
  const root = document.documentElement
  return {
    mode: isThemeMode(root.dataset.atlasTheme) ? root.dataset.atlasTheme : DEFAULT_APPEARANCE.mode,
    accent: isAccentProfile(root.dataset.atlasAccent) ? root.dataset.atlasAccent : DEFAULT_APPEARANCE.accent,
  }
}

export function applyAppearance(preferences: AppearancePreferences): ResolvedTheme {
  if (typeof document === 'undefined') return 'light'
  const root = document.documentElement
  const resolved = resolveTheme(preferences.mode, prefersDarkMode())
  root.dataset.atlasTheme = preferences.mode
  root.dataset.atlasAccent = preferences.accent
  root.classList.toggle('dark', resolved === 'dark')
  root.style.colorScheme = resolved
  return resolved
}

export function persistAppearance(preferences: AppearancePreferences): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(THEME_MODE_KEY, preferences.mode)
    window.localStorage.setItem(ACCENT_PROFILE_KEY, preferences.accent)
    // Preserve the old key for existing integrations and browser journeys.
    window.localStorage.setItem(LEGACY_THEME_KEY, preferences.mode === 'dark' ? 'enabled' : 'disabled')
  } catch {
    // Private browsing and restricted storage must not break the UI.
  }
}

export function subscribeToSystemTheme(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => listener()
  media.addEventListener?.('change', handler)
  return () => media.removeEventListener?.('change', handler)
}
