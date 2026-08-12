'use client'

import { useState, useEffect } from 'react'

/**
 * Returns `true` when the page is in dark mode.
 *
 * Single source of truth: the `.dark` class on `<html>`, applied by
 * the AppearanceProvider and its pre-hydration bootstrap. System mode
 * is resolved there, so charts only observe the settled runtime class.
 *
 * Re-evaluates when the class attribute changes (MutationObserver).
 */
export function useThemeMode(): boolean {
  const [dark, setDark] = useState(() =>
    typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
  )

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
