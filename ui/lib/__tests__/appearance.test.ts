import { beforeEach, describe, expect, it } from 'vitest'
import {
  ACCENT_PROFILE_KEY,
  DEFAULT_APPEARANCE,
  THEME_MODE_KEY,
  applyAppearance,
  persistAppearance,
  readStoredAppearance,
  resolveTheme,
} from '@/lib/appearance'

const store: Record<string, string> = {}

beforeEach(() => {
  for (const key of Object.keys(store)) delete store[key]
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => { store[key] = value },
      removeItem: (key: string) => { delete store[key] },
      clear: () => { for (const key of Object.keys(store)) delete store[key] },
    },
  })
  document.documentElement.className = ''
  document.documentElement.removeAttribute('data-atlas-theme')
  document.documentElement.removeAttribute('data-atlas-accent')
})

describe('appearance contract', () => {
  it('falls back safely when stored values are invalid', () => {
    store[THEME_MODE_KEY] = 'neon'
    store[ACCENT_PROFILE_KEY] = 'ultraviolet'
    expect(readStoredAppearance()).toEqual(DEFAULT_APPEARANCE)
  })

  it('migrates the legacy binary theme key without coupling accent state', () => {
    store.atlas_theme = 'enabled'
    store[ACCENT_PROFILE_KEY] = 'ion'
    expect(readStoredAppearance()).toEqual({ mode: 'dark', accent: 'ion' })
  })

  it('persists mode and accent independently and applies the DOM contract', () => {
    const preferences = { mode: 'dark' as const, accent: 'vermilion' as const }
    persistAppearance(preferences)
    const resolved = applyAppearance(preferences)
    expect(resolved).toBe('dark')
    expect(readStoredAppearance()).toEqual(preferences)
    expect(document.documentElement.dataset.atlasTheme).toBe('dark')
    expect(document.documentElement.dataset.atlasAccent).toBe('vermilion')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('resolves System mode from the OS preference without changing the stored mode', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
    expect(resolveTheme('light', true)).toBe('light')
  })
})
