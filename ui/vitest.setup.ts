/**
 * Vitest setup file. Imported once per test file BEFORE any test
 * block, registered via vitest.config.ts -> setupFiles. Provides:
 *
 * 1. ``@testing-library/jest-dom`` matchers (toBeInTheDocument,
 *    toHaveTextContent, toHaveAttribute, toBeVisible, etc.) — these
 *    are NOT part of @testing-library/react, you need the
 *    jest-dom add-on for the matchers.
 * 2. ``afterEach`` cleanup that unmounts any React tree RTL installed
 *    in the test, so a hard-coded ``<Component />`` in test #1
 *    doesn't bleed into test #2.
 * 3. A ``window.localStorage`` stub — jsdom + happy-dom both
 *    *normally* provide it, but several downstream components (e.g.
 *    ``DarkModeToggle`` reached via ``PageLayout`` in the
 *    recommendations test) call ``window.localStorage.getItem(...)``
 *    at module-evaluation time. If our environment doesn't ship a
 *    writable localStorage the read throws "Cannot read properties
 *    of undefined (reading 'getItem')" and aborts every renderable
 *    test on the page. Polyfill with an in-memory map so this is
 *    independent of the configured env.
 *
 * Without this file, every Vitest test that uses
 * ``expect(...).toBeInTheDocument()`` fails with
 *   ``TypeError: ...toBeInTheDocument is not a function``
 * because the matcher never registers (TypeScript also complains in
 * the tsc check + the tsc --noEmit step).
 */
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})

// ---- localStorage stub --------------------------------------------------
// jsdom PROVIDES `window.localStorage` by default but it's an
// unassignable builtin Storage (not writable). Component tests that
// mount `DarkModeToggle` (or any component in its render tree)
// call `window.localStorage.getItem(...)`; if a previous test left
// the builtin Storage in an unusable state `getItem` blows up with
// "Cannot read properties of undefined (reading 'getItem')".
//
// The fix: unconditionally redefine `window.localStorage` as OUR
// in-memory fake using `Object.defineProperty` with `configurable +
// writable` so we cover both `window.localStorage` AND the bare
// `localStorage` global (vi.stubGlobal covers the bare global;
// Object.defineProperty covers window). The previous
// `if (!window.localStorage)` gate incorrectly suppressed the stub
// when jsdom already supplied a builtin Storage, leaving DarkModeToggle
// to bind to the wrong instance.
beforeAll(() => {
  if (typeof window === 'undefined') return
  const memoryStore = new Map<string, string>()
  const fakeStorage = {
    getItem: (key: string): string | null =>
      memoryStore.has(key) ? memoryStore.get(key)! : null,
    setItem: (key: string, value: string): void => {
      memoryStore.set(key, value)
    },
    removeItem: (key: string): void => {
      memoryStore.delete(key)
    },
    clear: (): void => {
      memoryStore.clear()
    },
    key: (index: number): string | null => {
      const keys = Array.from(memoryStore.keys())
      return keys[index] ?? null
    },
    get length(): number {
      return memoryStore.size
    },
  }
  Object.defineProperty(window, 'localStorage', {
    value: fakeStorage,
    configurable: true,
    writable: true,
  })
  vi.stubGlobal('localStorage', fakeStorage)

  // ---- matchMedia stub --------------------------------------------------
  // Components using useReducedMotion read window.matchMedia at mount time.
  // jsdom's matchMedia is not present by default, so provide a minimal stub.
  const fakeMatchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
    addListener: () => {},
    removeListener: () => {},
  }) as unknown as MediaQueryList
  vi.stubGlobal('matchMedia', fakeMatchMedia)
})

// ---- next/navigation stub ---------------------------------------------
// AtlasFilterProvider (rendered by every page via PageLayout) calls
// useRouter() and useSearchParams() from next/navigation. jsdom has no
// App Router mounted, so these throw "invariant expected app router to
// be mounted". Provide a no-op stub globally so any test that renders
// a page component doesn't each need its own mock.
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/',
}))

// ---- NotificationContext mock ------------------------------------------
// Header calls useNotifications() which throws without a provider.
// Provide a global no-op mock so test files that render page components
// (which include Header via PageLayout) don't each need their own mock.
vi.mock('@/components/providers/NotificationContext', () => ({
  useNotifications: () => ({
    notifications: [],
    unreadCount: 0,
    addNotification: () => '',
    markAsRead: () => {},
    markAllAsRead: () => {},
    removeNotification: () => {},
    clearAll: () => {},
    toasts: [],
    toast: () => {},
    dismissToast: () => {},
  }),
  NotificationProvider: ({ children }: { children: unknown }) => children,
}))
