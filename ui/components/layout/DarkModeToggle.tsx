'use client'

import { useEffect, useLayoutEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { useAppearance } from '@/components/providers/AppearanceProvider'
import { applyAppearance, persistAppearance, type ThemeMode } from '@/lib/appearance'

export default function DarkModeToggle() {
  const { mode, accent, resolvedTheme, setMode } = useAppearance()
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    setIsDark(resolvedTheme === 'dark')
  }, [resolvedTheme])

  useLayoutEffect(() => {
    document.documentElement.dataset.darkmodeHydrated = 'true'
  }, [])

  const toggleDarkMode = () => {
    const nextMode: ThemeMode = isDark ? 'light' : 'dark'
    const next = { mode: nextMode, accent }
    setIsDark(!isDark)
    setMode(nextMode)
    applyAppearance(next)
    persistAppearance(next)
  }

  return (
    <button
      type="button"
      onClick={toggleDarkMode}
      className="min-h-11 min-w-11 rounded-[var(--radius-md)] p-2 text-on-surface-variant transition-[color,background-color,transform] duration-200 ease-out hover:bg-surface-container hover:text-accent-primary active:scale-[0.97] focus-ring"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      data-testid="dark-mode-toggle"
      data-theme-mode={mode}
    >
      {isDark ? <Sun className="h-5 w-5" aria-hidden="true" /> : <Moon className="h-5 w-5" aria-hidden="true" />}
    </button>
  )
}
