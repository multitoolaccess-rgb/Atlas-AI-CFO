'use client';

import { useEffect, useLayoutEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

/** New localStorage key — the old 'darkMode' key may contain stale
 *  'enabled' values from the broken OS-preference-following logic.
 *  We read from THEME_KEY and one-time-migrate the old key. */
const THEME_KEY = 'atlas_theme'
const OLD_KEY = 'darkMode'

export default function DarkModeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const ls = window.localStorage;

    // --- One-time migration: DELETE stale old key (don't copy) ---
    // The old 'darkMode' key was auto-set by broken OS-preference
    // code. Copying it would keep users stuck in dark mode. Users
    // who genuinely want dark can re-toggle (writes to THEME_KEY).
    if (ls.getItem(OLD_KEY) !== null) {
      ls.removeItem(OLD_KEY);
    }

    const stored = ls.getItem(THEME_KEY);
    // Default to LIGHT mode. Only switch to dark when the user has
    // explicitly toggled (stored === 'enabled').
    const initial = stored === 'enabled';
    setIsDark(initial);
    if (initial) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, []);

  // React hydration sentinel — Playwright E2E tests wait for this
  // attribute on ``<html>`` before dispatching click events on this
  // component's button. The button itself is server-rendered with
  // a fixed ``aria-label`` (so ``expect(toggle).toBeVisible()``
  // returns true on the static HTML before React onClick is
  // attached), so a paint-only check is racy. Setting this
  // attribute here guarantees it only appears after the first
  // effect runs post-hydration, and it cleans up on unmount so it
  // never leaks into the next page.
  //
  // We use ``useLayoutEffect`` (not ``useEffect``) so the attribute
  // is set SYNCHRONOUSLY after the DOM commit but BEFORE the
  // browser paints. A regular ``useEffect`` fires asynchronously
  // and can race against Playwright's ``waitForSelector`` poll —
  // the polling tick can land in the gap between paint and the
  // effect tick and time out even though hydration completed.
  //
  // No unmount cleanup: the DarkModeToggle lives in the persistent
  // Header layout, so it doesn't unmount across soft navigations.
  // Removing the cleanup branch keeps the effect body to a single
  // statement and matches the actual unmount cadence of this app.
  useLayoutEffect(() => {
    document.documentElement.dataset.darkmodeHydrated = 'true'
  }, []);

  const toggleDarkMode = () => {
    const next = !isDark;
    setIsDark(next);
    const ls = window.localStorage;
    if (next) {
      document.documentElement.classList.add('dark');
      ls.setItem(THEME_KEY, 'enabled');
    } else {
      document.documentElement.classList.remove('dark');
      ls.setItem(THEME_KEY, 'disabled');
    }
  };

  return (
    <button
      onClick={toggleDarkMode}
      className="p-2 text-on-surface-variant hover:text-primary transition-colors rounded-md focus-ring"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? (
        <Sun className="w-5 h-5" aria-hidden="true" />
      ) : (
        <Moon className="w-5 h-5" aria-hidden="true" />
      )}
    </button>
  );
}
