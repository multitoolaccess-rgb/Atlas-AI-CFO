'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  ACCENT_PROFILE_KEY,
  DEFAULT_APPEARANCE,
  THEME_MODE_KEY,
  applyAppearance,
  persistAppearance,
  readDomAppearance,
  readStoredAppearance,
  subscribeToSystemTheme,
  type AccentProfile,
  type AppearancePreferences,
  type ResolvedTheme,
  type ThemeMode,
} from '@/lib/appearance'

interface AppearanceContextValue {
  mode: ThemeMode
  resolvedTheme: ResolvedTheme
  accent: AccentProfile
  setMode: (mode: ThemeMode) => void
  setAccent: (accent: AccentProfile) => void
  setAppearance: (preferences: AppearancePreferences) => void
}

const defaultContext: AppearanceContextValue = {
  ...DEFAULT_APPEARANCE,
  resolvedTheme: 'light',
  setMode: () => {},
  setAccent: () => {},
  setAppearance: () => {},
}

const AppearanceContext = createContext<AppearanceContextValue>(defaultContext)

export default function AppearanceProvider({ children }: { children: ReactNode }) {
  const initial = readDomAppearance()
  const [preferences, setPreferences] = useState<AppearancePreferences>(initial)
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? 'dark' : 'light',
  )

  const applyAndStore = useCallback((next: AppearancePreferences, persist = true) => {
    const resolved = applyAppearance(next)
    if (persist) persistAppearance(next)
    setPreferences(next)
    setResolvedTheme(resolved)
  }, [])

  useEffect(() => {
    const stored = readStoredAppearance()
    applyAndStore(stored)

    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_MODE_KEY && event.key !== ACCENT_PROFILE_KEY) return
      applyAndStore(readStoredAppearance(), false)
    }
    window.addEventListener('storage', onStorage)
    const unsubscribeSystem = subscribeToSystemTheme(() => {
      const current = readStoredAppearance()
      if (current.mode === 'system') applyAndStore(current, false)
    })
    return () => {
      window.removeEventListener('storage', onStorage)
      unsubscribeSystem()
    }
  }, [applyAndStore])

  const value = useMemo<AppearanceContextValue>(() => ({
    mode: preferences.mode,
    resolvedTheme,
    accent: preferences.accent,
    setMode: (mode) => applyAndStore({ ...preferences, mode }),
    setAccent: (accent) => applyAndStore({ ...preferences, accent }),
    setAppearance: applyAndStore,
  }), [applyAndStore, preferences, resolvedTheme])

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>
}

export function useAppearance(): AppearanceContextValue {
  return useContext(AppearanceContext)
}
