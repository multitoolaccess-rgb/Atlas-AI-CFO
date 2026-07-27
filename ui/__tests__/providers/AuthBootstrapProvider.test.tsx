/**
 * Vitest unit test for `ui/components/providers/AuthBootstrapProvider.tsx`.
 *
 * Phase 9 ship target: every page is wrapped in this provider so the
 * cold-start devLogin (which mints a JWT cookie) is centralized —
 * the previous per-page hook fired only on the Overview, which is
 * why /portfolio, /goals, /settings showed a one-frame "Session
 * expired" flash on cold start. The state machine has 3 phases:
 *   1. loading — splash with animated "Securing your session…"
 *   2. ready   — children render (the devLogin call has succeeded)
 *   3. error   — hard-stop UI with the underlying error message and
 *                a Retry button (so a transient ECONNREFUSED doesn't
 *                permanently lock the user out).
 *
 * Plus a module-level singleton promise (``bootstrapPromise``) so
 * concurrent mounts (Next.js dev fast-refresh firing multiple
 * children simultaneously) only issue ONE round-trip.
 *
 * Tests below pin all 4 invariants.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

// Mock state — bound BEFORE vi.mock via vitest's hoisted callback.
// Vitest hoists `vi.mock(...)` calls to the top of the module; the
// mock FACTORY runs at hoist time but the closure references inside
// the factory would be in the temporal dead zone (TDZ) if we declared
// `devLoginMock` with a plain `const`. ``vi.hoisted`` registers the
// binding first so the factory can safely close over it.
const {
  devLoginMock,
  healthMock,
  clearStoredTokenMock,
  markBootstrapWarmMock,
  clearBootstrapWarmMock,
  isBootstrapWarmMock,
} = vi.hoisted(() => ({
  devLoginMock: vi.fn(),
  healthMock: vi.fn(),
  // Hoisted so tests can assert clearStoredToken was called on the
  // "Clear session & reload" path. The mock impl below delegates
  // to window.localStorage.removeItem so the side-effect assertion
  // stays meaningful (without delegation, the assertion would
  // silently pass even when the production clearStoredToken is
  // broken — localStorage.started empty + vi.fn() removes nothing).
  clearStoredTokenMock: vi.fn(),
  // Warm-bootstrap helpers — used in the runBootstrap success
  // path, the mount-time short-circuit, and the reset-and-reload
  // path. The mock impls delegate to the SAME localStorage key
  // the production code writes so the side-effect assertions
  // (warm flag persisted, warm flag cleared) stay meaningful.
  markBootstrapWarmMock: vi.fn(),
  clearBootstrapWarmMock: vi.fn(),
  isBootstrapWarmMock: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  rulesService: {
    devLogin: (...args: unknown[]) => devLoginMock(...args),
    health: (...args: unknown[]) => healthMock(...args),
  },
  clearStoredToken: (...args: unknown[]) => {
    clearStoredTokenMock(...args)
    window.localStorage.removeItem('fc_session_token')
  },
  // markBootstrapWarm persists the warm timestamp so isBootstrapWarm
  // can short-circuit on the next mount. The mock impl writes to
  // fc_bootstrap_warm_at (the production key) so the warm-skip test
  // can pre-set it via the mock factory and the production short-
  // circuit reads through isBootstrapWarm and observes the truthy
  // value.
  // Mirror production exactly: markBootstrapWarm() is called with
  // NO arguments — production derives the timestamp from Date.now()
  // internally. An earlier version of this mock accepted a
  // `timestamp` parameter and wrote `String(undefined)` when
  // production called it arg-less, leaving localStorage with the
  // literal string `"undefined"`. isBootstrapWarm would then read
  // Number("undefined") → NaN → !isFinite → false, silently
  // breaking the warm-skip behavior in any test that re-mounted
  // after a successful bootstrap.
  markBootstrapWarm: () => {
    markBootstrapWarmMock()
    window.localStorage.setItem('fc_bootstrap_warm_at', String(Date.now()))
  },
  clearBootstrapWarm: (...args: unknown[]) => {
    clearBootstrapWarmMock(...args)
    window.localStorage.removeItem('fc_bootstrap_warm_at')
  },
  isBootstrapWarm: () => {
    isBootstrapWarmMock()
    return Boolean(window.localStorage.getItem('fc_bootstrap_warm_at'))
  },
}))

import AuthBootstrapProvider, {
  resetAuthBootstrap,
  BOOTSTRAP_TIMEOUT_MS,
  HARD_SKIP_AFTER_MS,
  HEALTH_TIMEOUT_MS,
} from '@/components/providers/AuthBootstrapProvider'

// Flush pending microtasks (resolved promises from the async bootstrap
// state machine) without sleeping. Used by the
// module-singleton-dedupe test which renders three trees in the same
// tick and needs to wait for the shared ``bootstrapPromise`` to settle.
const flushPromises = () =>
  new Promise<void>((resolve) => setTimeout(resolve, 0))

// Yield to the microtask queue. Safe under `vi.useFakeTimers()`
// because it does not rely on mocked timers.
const flushMicrotasks = async () => {
  for (let i = 0; i < 3; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await Promise.resolve()
  }
}

beforeEach(() => {
  // Move localStorage to a clean in-memory store between tests.
  const store: Record<string, string> = {}
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: (k: string): string | null =>
        Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null,
      setItem: (k: string, v: string): void => {
        store[k] = v
      },
      removeItem: (k: string): void => {
        delete store[k]
      },
      clear: (): void => {
        for (const k of Object.keys(store)) delete store[k]
      },
      key: (i: number): string | null => Object.keys(store)[i] ?? null,
      length: 0,
    },
    configurable: true,
    writable: true,
  })
  devLoginMock.mockReset()
  healthMock.mockReset()
  clearStoredTokenMock.mockReset()
  markBootstrapWarmMock.mockReset()
  clearBootstrapWarmMock.mockReset()
  isBootstrapWarmMock.mockReset()
  // Default to a synchronous-looking resolved health so tests that don't
  // care about the probe keep behaving like the old devLogin-only flow.
  healthMock.mockResolvedValue({ status: 'ok' })
  resetAuthBootstrap()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('AuthBootstrapProvider — state machine', () => {
  it('renders the loading splash on first paint', () => {
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    // The splash announces itself via aria-label="Securing your session".
    const splash = screen.getByRole('status', { name: /Securing your session/i })
    expect(splash).toBeInTheDocument()
    expect(screen.queryByTestId('child')).not.toBeInTheDocument()
  })

  it('transitions to ready and renders the children after devLogin resolves', async () => {
    devLoginMock.mockResolvedValueOnce({ token: 'NEW', subject: 'alex' })
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    // Splash should be gone (no second status landmark).
    expect(
      screen.queryByRole('status', { name: /Securing your session/i }),
    ).not.toBeInTheDocument()
    expect(devLoginMock).toHaveBeenCalledTimes(1)
  })

  it('skips devLogin when localStorage already has a token', async () => {
    window.localStorage.setItem('fc_session_token', 'PRE-EXISTING')
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    // No fresh devLogin round-trip needed — the axios interceptor
    // handles mid-session expiry via 401 retry. This pins the
    // "no-flash on warm-start" invariant that the previous behavior
    // regressed (every mount would mint a new cookie even if the
    // user was already authed).
    expect(devLoginMock).not.toHaveBeenCalled()
  })

  it('renders the backend-down error when the health probe fails fast', async () => {
    healthMock.mockRejectedValueOnce(new Error('connect ECONNREFUSED 127.0.0.1:8000'))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await waitFor(() =>
      expect(screen.getByText(/Backend is unreachable/i)).toBeInTheDocument(),
    )
    expect(
      screen.getByText(/Start the backend with `bash scripts\/start\.sh`/i),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('child')).not.toBeInTheDocument()
    // devLogin should NOT have been called when health fails.
    expect(devLoginMock).not.toHaveBeenCalled()
  })

  it('renders the backend-slow error when the health probe times out', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    healthMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    try {
      vi.advanceTimersByTime(HEALTH_TIMEOUT_MS + 500)
      await waitFor(() =>
        expect(screen.getByText(/Backend is slow/i)).toBeInTheDocument(),
      )
      expect(
        screen.getByText(/service may be starting up or under load/i),
      ).toBeInTheDocument()
      expect(devLoginMock).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('on devLogin rejection, renders the error UI with the surfaced message', async () => {
    const cause = new Error('connect ECONNREFUSED 127.0.0.1:8000')
    devLoginMock.mockRejectedValueOnce(cause)
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    // The error UI announces itself via the
    // "Authentication bootstrap failed" title.
    await waitFor(() =>
      expect(
        screen.getByText(/Authentication bootstrap failed/i),
      ).toBeInTheDocument(),
    )
    // The underlying axios/Network error message is surfaced in a
    // <pre aria-live="polite"> — pinned by data-testid.
    const pre = await screen.findByLabelText(/Underlying error message/i)
    expect(pre.textContent).toMatch(/ECONNREFUSED/)
    // Children MUST NOT be rendered when in the error phase — every
    // downstream call would 401-loop.
    expect(screen.queryByTestId('child')).not.toBeInTheDocument()
  })

  it('Retry button resets bootstrapPromise + transitions back to loading', async () => {
    devLoginMock.mockRejectedValueOnce(new Error('first try fails'))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    // Wait for the error UI to render.
    const retryBtn = await screen.findByRole('button', { name: /Retry/i })
    // Second attempt succeeds.
    devLoginMock.mockResolvedValueOnce({ token: 'OK', subject: 'alex' })
    fireEvent.click(retryBtn)
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    // First call failed, second succeeded — exactly 2 round-trips.
    expect(devLoginMock).toHaveBeenCalledTimes(2)
  })

  it('module-level singleton dedupes concurrent mounts to ONE devLogin call', async () => {
    devLoginMock.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({ token: 'X' }), 5)),
    )
    render(
      <AuthBootstrapProvider>
        <div data-testid="a">A</div>
      </AuthBootstrapProvider>,
    )
    render(
      <AuthBootstrapProvider>
        <div data-testid="b">B</div>
      </AuthBootstrapProvider>,
    )
    render(
      <AuthBootstrapProvider>
        <div data-testid="c">C</div>
      </AuthBootstrapProvider>,
    )
    await flushPromises()
    await waitFor(() =>
      expect(
        screen.getByTestId('a') &&
          screen.getByTestId('b') &&
          screen.getByTestId('c'),
      ).toBeTruthy(),
    )
    // 3 mounts, but the singleton promise means ONE round-trip.
    expect(devLoginMock).toHaveBeenCalledTimes(1)
  })

  it('on devLogin rejection, the singleton promise is reset so Retry can succeed', async () => {
    devLoginMock.mockRejectedValueOnce(new Error('first try'))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await screen.findByText(/Authentication bootstrap failed/i)
    devLoginMock.mockResolvedValueOnce({ token: 'OK', subject: 'alex' })
    const retryBtn = await screen.findByRole('button', { name: /Retry/i })
    fireEvent.click(retryBtn)
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
  })
})

describe('AuthBootstrapProvider — accessibility', () => {
  it('splash has role="status" + aria-live="polite"', () => {
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    const splash = screen.getByRole('status', { name: /Securing your session/i })
    expect(splash.getAttribute('aria-live')).toBe('polite')
  })

  it('error UI exposes a Retry button with aria-label', async () => {
    devLoginMock.mockRejectedValueOnce(new Error('boom'))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    const retryBtn = await screen.findByRole('button', { name: /Retry/i })
    expect(retryBtn).toBeInTheDocument()
    expect(retryBtn.getAttribute('aria-label')).toMatch(/Retry/i)
  })

  it('shows a "Continue to app" button immediately on splash (no delay)', async () => {
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    // The button is visible from first paint so a user who presses
    // Tab + Enter immediately (or sits next to the splash for any
    // length of time) never sees a "stuck" state where the only
    // visible interactive element is the "Skip to main content"
    // accessibility link. This is the central recovery affordance.
    const skipBtn = await screen.findByRole('button', { name: /Continue to app/i })
    expect(skipBtn).toBeInTheDocument()

    // Clicking skip renders the children without waiting for devLogin.
    fireEvent.click(skipBtn)
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    expect(devLoginMock).toHaveBeenCalledTimes(1)
  })

  it('renders the backend-slow error when health succeeds but devLogin times out', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await flushMicrotasks()

    try {
      vi.advanceTimersByTime(BOOTSTRAP_TIMEOUT_MS + 1_000)
      await waitFor(() =>
        expect(screen.getByText(/Backend is slow/i)).toBeInTheDocument(),
      )
      expect(
        screen.getByText(/service may be starting up or under load/i),
      ).toBeInTheDocument()
      expect(screen.queryByTestId('child')).not.toBeInTheDocument()
      expect(devLoginMock).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('transitions to error UI after the auth bootstrap timeout', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    // Let the health probe resolve before the devLogin timeout path is tested.
    await flushMicrotasks()

    try {
      // Advance past the bootstrap timeout.
      vi.advanceTimersByTime(BOOTSTRAP_TIMEOUT_MS + 1_000)
      await waitFor(() =>
        expect(screen.getByText(/Backend is slow/i)).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('child')).not.toBeInTheDocument()

      // Retry should issue a fresh devLogin call.
      devLoginMock.mockResolvedValueOnce({ token: 'OK', subject: 'alex' })
      const retryBtn = screen.getByRole('button', { name: /Retry/i })
      fireEvent.click(retryBtn)
      await waitFor(() =>
        expect(screen.getByTestId('child')).toBeInTheDocument(),
      )
      expect(devLoginMock).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('clicking skip is not overwritten by a later devLogin rejection', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await flushMicrotasks()

    try {
      // Skip button is visible immediately — no timer advance needed.
      const skipBtn = await screen.findByRole('button', { name: /Continue to app/i })
      fireEvent.click(skipBtn)
      await waitFor(() =>
        expect(screen.getByTestId('child')).toBeInTheDocument(),
      )

      // Advance well past the timeout. The late rejection must not
      // replace the ready state with an error UI.
      vi.advanceTimersByTime(BOOTSTRAP_TIMEOUT_MS)
      expect(screen.queryByText(/Authentication bootstrap failed/i)).not.toBeInTheDocument()
      expect(screen.getByTestId('child')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('clicking skip is not overwritten by a later successful devLogin', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let resolveDevLogin: (() => void) | undefined
    devLoginMock.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveDevLogin = resolve
        }),
    )

    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await flushMicrotasks()

    try {
      // Skip button is visible immediately.
      const skipBtn = await screen.findByRole('button', { name: /Continue to app/i })
      fireEvent.click(skipBtn)
      await waitFor(() =>
        expect(screen.getByTestId('child')).toBeInTheDocument(),
      )

      // Resolve the original devLogin call after the skip.
      resolveDevLogin!()
      await waitFor(() => expect(devLoginMock).toHaveBeenCalledTimes(1))

      // The app should still be ready, not re-render the splash/error.
      expect(screen.getByTestId('child')).toBeInTheDocument()
      expect(
        screen.queryByRole('status', { name: /Securing your session/i }),
      ).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('hard-skip forces the ready phase after HARD_SKIP_AFTER_MS', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await flushMicrotasks()

    try {
      // Before hard-skip fires the splash is still visible.
      expect(
        screen.queryByRole('status', { name: /Securing your session/i }),
      ).toBeInTheDocument()
      expect(screen.queryByTestId('child')).not.toBeInTheDocument()

      vi.advanceTimersByTime(HARD_SKIP_AFTER_MS)

      // After the hard-skip deadline, children render even though
      // devLogin never resolved.
      await waitFor(() =>
        expect(screen.getByTestId('child')).toBeInTheDocument(),
      )
      expect(
        screen.queryByRole('status', { name: /Securing your session/i }),
      ).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('"Clear session & reload" button clears the stored token + reloads', async () => {
    // No token in localStorage → bootstrap calls devLogin → it rejects
    // → error UI surfaces → reset button is now the recovery affordance.
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      configurable: true,
      writable: true,
    })

    devLoginMock.mockRejectedValueOnce(new Error('first try fails'))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )

    const resetBtn = await screen.findByTestId('auth-bootstrap-reset-reload')
    expect(resetBtn).toBeInTheDocument()
    fireEvent.click(resetBtn)

    expect(window.localStorage.getItem('fc_session_token')).toBeNull()
    // The warm flag MUST also be cleared so the next load does NOT
    // short-circuit and silently fall into the broken JWT state
    // we just cleared. If we forgot clearBootstrapWarm here, the
    // user would re-mount and immediately see the children — but
    // every authed call would 401-loop because the JWT was just
    // nuked. Worse than the original bug.
    expect(window.localStorage.getItem('fc_bootstrap_warm_at')).toBeNull()
    expect(reloadMock).toHaveBeenCalledTimes(1)
    expect(clearStoredTokenMock).toHaveBeenCalledTimes(1)
    expect(clearBootstrapWarmMock).toHaveBeenCalledTimes(1)
  })

  it('warm reload (within WARM_WINDOW_MS) skips the splash entirely', async () => {
    // Pre-set the warm flag so the mount-time short-circuit fires
    // BEFORE runBootstrap is called. The user reloaded their tab
    // tab 60 seconds after a successful bootstrap — they should
    // NOT see the splash, wait for the devLogin round-trip, or
    // flicker. The token (if present) is enough for children;
    // any 401 refresh happens in the axios interceptor.
    window.localStorage.setItem('fc_bootstrap_warm_at', String(Date.now()))

    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )

    // Children render synchronously after the mount effect flips
    // the phase to 'ready'. No waiting for devLogin.
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    // Splash is gone — this is the user's "why is the splash
    // showing again" complaint, only inverted: now it should NOT
    // show on warm reloads.
    expect(
      screen.queryByRole('status', { name: /Securing your session/i }),
    ).not.toBeInTheDocument()
    // The whole point: no devLogin round-trip on warm reload.
    expect(devLoginMock).not.toHaveBeenCalled()
    expect(healthMock).not.toHaveBeenCalled()
    // The provider re-arms the warm window so the next reload
    // is still warm — the same call path that the success
    // branch takes.
    expect(markBootstrapWarmMock).toHaveBeenCalled()
  })

  it('successful runBootstrap persists the warm flag for the next reload', async () => {
    // Fresh mount with no warm flag → cold start path → runBootstrap
    // → ensureAuth → devLogin resolves → markBootstrapWarm should
    // fire so the next reload (the user's most common flow —
    // refresh the tab after using the app for a few minutes) is
    // a warm short-circuit.
    devLoginMock.mockResolvedValueOnce({ token: 'NEW', subject: 'alex' })
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    expect(markBootstrapWarmMock).toHaveBeenCalled()
    expect(window.localStorage.getItem('fc_bootstrap_warm_at')).toBeTruthy()
  })

  it('failed runBootstrap does NOT persist the warm flag (failed auth is not "warm")', async () => {
    // Cold start → devLogin rejects → error UI → warm flag MUST
    // stay unset. If a stale mount persisted warm=true after a
    // 401/500, the next reload would skip the splash but every
    // downstream call would 401-loop in the error lane. The user
    // seeing the error UI again is far better than the silent broken
    // state.
    devLoginMock.mockRejectedValueOnce(new Error('first try fails'))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await screen.findByText(/Authentication bootstrap failed/i)
    expect(markBootstrapWarmMock).not.toHaveBeenCalled()
    expect(window.localStorage.getItem('fc_bootstrap_warm_at')).toBeNull()
  })

describe('AuthBootstrapProvider — escape hatches', () => {
  // Tests for the user-recovery paths added when Continue-to-app was
  // observed to be a no-op in the field. The surface layer is the
  // intended fix (Continue flips React state synchronously, render
  // commits in <2 rAFs); the URL-param escape hatch below is the
  // bulletproof fallback when React state updates fail to unmount
  // the splash (HMR replay bug, dev-mode error boundary, ad
  // blocker interference with React 18 internals). Without these
  // escapes the user is stranded; with them, one hard-refresh with
  // the query (or one extra setTimeout-tap) and they're out.
  it('?skip-splash=1 query param bypasses the splash entirely', async () => {
    Object.defineProperty(window, 'location', {
      value: { search: '?skip-splash=1', href: 'http://localhost/?skip-splash=1' },
      configurable: true,
      writable: true,
    })
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    // No round-trips on the escape-hatch path — the user has
    // declared "do not bother logging me in this session".
    expect(devLoginMock).not.toHaveBeenCalled()
    expect(healthMock).not.toHaveBeenCalled()
    // Splash landmark gone.
    expect(
      screen.queryByRole('status', { name: /Securing your session/i }),
    ).not.toBeInTheDocument()
    // Warm flag was set as a side effect — the next reload without
    // the query is another warm short-circuit. Mock factory writes
    // the production-shaped value to localStorage so this assertion
    // is real, not just a spy tick.
    expect(markBootstrapWarmMock).toHaveBeenCalled()
    expect(window.localStorage.getItem('fc_bootstrap_warm_at')).toBeTruthy()
  })

  it('Continue-to-app bulletproof escape redirects to ?skip-splash when the splash is still in the DOM after two rAFs', async () => {
    // Stub window.location.assign + mock the splash as still mounted
    // even after the React state update commits, then verify the
    // rAF fallback fires and URL-escapes the user out of the stuck
    // state. Without this, a hung React commit (e.g. dev-mode HMR
    // replay) leaves the splash visible and the only escape is
    // "Clear session & reload" which loses the warm cache.
    const assignMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: {
        search: '',
        href: 'http://localhost/',
        assign: assignMock,
      },
      configurable: true,
      writable: true,
    })

    // Force document.querySelector('aria-label="Securing your session"')
    // to return truthy even after React committed the ready phase.
    // Testing-library's render tree does NOT include a phantom splash
    // post-commit, so we attach one manually.
    const fakeSplash = document.createElement('div')
    fakeSplash.setAttribute('aria-label', 'Securing your session')
    document.body.appendChild(fakeSplash)

    try {
      devLoginMock.mockImplementation(() => new Promise(() => {}))
      render(
        <AuthBootstrapProvider>
          <div data-testid="child">HOME</div>
        </AuthBootstrapProvider>,
      )
      const skipBtn = await screen.findByRole('button', {
        name: /Continue to app/i,
      })
      fireEvent.click(skipBtn)

      // Children render in this controlled test (React's setPhase
      // worked). But the fake splash we attached is still in document
      // body — the rAF fallback sees it and triggers URL escape.
      await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1))
      const escapedUrl = assignMock.mock.calls[0]?.[0] as string
      expect(escapedUrl).toContain('skip-splash=')
    } finally {
      fakeSplash.remove()
    }
  })
})

  it('clicking "Continue to app" persists the warm flag so next reload skips splash', async () => {
    // A user who explicitly skips login MUST still benefit from
    // the warm-reload optimization — clicking the button means
    // they understand the page works without a token, and the
    // splash appearing again on every refresh is the same UX
    // problem we are fixing.
    devLoginMock.mockImplementation(() => new Promise(() => {}))
    render(
      <AuthBootstrapProvider>
        <div data-testid="child">HOME</div>
      </AuthBootstrapProvider>,
    )
    const skipBtn = await screen.findByRole('button', { name: /Continue to app/i })
    fireEvent.click(skipBtn)
    await waitFor(() =>
      expect(screen.getByTestId('child')).toBeInTheDocument(),
    )
    expect(markBootstrapWarmMock).toHaveBeenCalled()
    expect(window.localStorage.getItem('fc_bootstrap_warm_at')).toBeTruthy()
  })
})
