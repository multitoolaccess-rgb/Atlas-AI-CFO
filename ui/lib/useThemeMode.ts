'use client'

import { useState, useEffect } from 'react'

/**
 * Returns `true` when the page is in dark mode.
 *
 * Single source of truth: the `.dark` class on `<html>`, toggled by
 * DarkModeToggle.tsx. No longer checks `prefers-color-scheme` media
 * query — that caused a race condition where CSS variables flipped
 * before the `.dark` class was added by React hydration.
 *
 * Re-evaluates when the class attribute changes (MutationObserver).
 */
export function useThemeMode(): boolean {
  const [dark, setDark] = useState(false)

  useEffect(() => {
    const root = document.documentElement

    function evaluate() {
      setDark(root.classList.contains('dark'))
    }

    evaluate()

    // Watch Tailwind class toggle
    const observer = new MutationObserver(evaluate)
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })

    return () => {
      observer.disconnect()
    }
  }, [])

  return dark
}
