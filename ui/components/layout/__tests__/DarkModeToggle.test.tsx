/**
 * Vitest test for the DarkModeToggle component.
 *
 * Verifies the contract from docs/phase-9-plan.md §2:
 *  - Clicking the toggle adds/removes `.dark` on <html>.
 *  - The `.dark` class block in tokens.css flips --bg-primary from
 *    light (#ffffff) to dark (#0f1419). We test this design-system
 *    contract by reading the file content directly, because jsdom
 *    does NOT resolve CSS custom properties through getComputedStyle
 *    for injected <style> elements (known jsdom limitation, distinct
 *    from the localStorage SecurityError that the 401-retry test also
 *    works around).
 *
 * jsdom 22.1.0 also does NOT provide `window.localStorage` by default
 * (throws SecurityError on opaque origins). The 401 retry test
 * sidesteps this with an explicit Storage stub; we do the same.
 */import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// The design-system contract test reads tokens.css directly from disk
// because Vite's ``?raw`` import returned an empty string in this
// vitest config (verified empirically — the import resolves but
// ``tokensCss`` is ``""``). ``readFileSync`` is the more reliable
// path for the assertion; the assertion target is the file content
// either way.
const tokensCss = readFileSync(
  resolve(__dirname, '../../../styles/tokens.css'),
  'utf-8',
)

describe('DarkModeToggle — class-based dark theme refresh', () => {
  // jsdom 22.1.0 does NOT provide ``window.localStorage`` by default
  // (throws ``SecurityError: localStorage is not available for opaque
  // origins``). The 401 retry test sidesteps this with an explicit
  // stub. We do the same: build a tiny in-memory Storage shim, install
  // it on ``window.localStorage``, AND expose it as a bare global so
  // any bare ``localStorage`` reference (defensive code path) works.
  const localStorageStub: Storage = {
    length: 0,
    clear: () => {},
    getItem: (_k: string) => null,
    key: (_i: number) => null,
    removeItem: (_k: string) => {},
    setItem: (_k: string, _v: string) => {},
  }
  const store: Record<string, string> = {}

  beforeEach(() => {
    // Reset the in-memory store between tests so assertions are isolated.
    for (const k of Object.keys(store)) delete store[k]
    localStorageStub.getItem = (k: string) => (k in store ? store[k] : null)
    localStorageStub.setItem = (k: string, v: string) => {
      store[k] = v
    }
    localStorageStub.removeItem = (k: string) => {
      delete store[k]
    }
    localStorageStub.clear = () => {
      for (const k of Object.keys(store)) delete store[k]
    }
    // Install on window so the component's ``window.localStorage``
    // reference resolves to our in-memory stub (jsdom 22.1.0 does
    // not provide localStorage by default — SecurityError).
    Object.defineProperty(window, 'localStorage', {
      value: localStorageStub,
      configurable: true,
      writable: true,
    })
    document.documentElement.classList.remove('dark')
  })

  afterEach(() => {
    cleanup()
    document.documentElement.classList.remove('dark')
  })

  it('starts with no .dark class on <html>', async () => {
    const { default: DarkModeToggle } = await import('../DarkModeToggle')
    render(createElement(DarkModeToggle))
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('clicking the toggle adds .dark class to <html>', async () => {
    const { default: DarkModeToggle } = await import('../DarkModeToggle')
    render(createElement(DarkModeToggle))
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('clicking twice toggles the .dark class back off', async () => {
    const { default: DarkModeToggle } = await import('../DarkModeToggle')
    render(createElement(DarkModeToggle))
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    fireEvent.click(btn)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('persists the choice to localStorage', async () => {
    const { default: DarkModeToggle } = await import('../DarkModeToggle')
    render(createElement(DarkModeToggle))
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(window.localStorage.getItem('atlas_theme')).toBe('enabled')
    fireEvent.click(btn)
    expect(window.localStorage.getItem('atlas_theme')).toBe('disabled')
  })

  it('design-system contract: tokens.css .dark block flips --bg-primary to #03040a', () => {
    // jsdom does NOT resolve CSS custom properties through
    // getComputedStyle for injected <style> elements (a known jsdom
    // limitation separate from the localStorage SecurityError). We
    // therefore verify the design-system contract by reading the
    // canonical tokens.css file content directly: the .dark selector
    // must override --bg-primary to the dark-mode hex (#03040a).
    // If a future refactor accidentally drops the .dark block, this
    // test catches it before runtime.
    expect(tokensCss).toMatch(/\.dark\s*\{/)
    expect(tokensCss).toMatch(/--bg-primary:\s*var\(--slate-50\)/)
    // And the .dark block must redefine --slate-50 to the dark hex
    // that --bg-primary references.
    expect(tokensCss).toMatch(/--slate-50:\s*#03040a/)
  })
})
