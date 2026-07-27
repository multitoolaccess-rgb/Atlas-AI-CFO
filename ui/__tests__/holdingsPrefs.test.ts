// @vitest-environment jsdom
//
// The explicit pragma is REQUIRED because the SSR sibling file
// (holdingsPrefs.ssr.test.ts) uses ``// @vitest-environment node``
// and vitest's thread-pool can leak the node environment into this
// file's worker when both files share a pool. Without the pragma,
// ``typeof window === 'undefined'`` fires inside
// ``getAutoRefreshMinutes`` and every read/write test returns
// DEFAULT_REFRESH_MINUTES (60) instead of the stored value.
//
// Phase 48 — vitest test for ``ui/lib/holdingsPrefs.ts``.
//
// The module is pure logic over ``window.localStorage`` + arithmetic,
// so the test surface is small but high-signal: every clamp edge
// case + every SSR/non-browser branch. A regression in
// ``clampAutoRefreshMinutes`` (e.g. floor-rounding a decimal value
// to 0 instead of the integer below, or losing the 0 sentinel) would
// silently flip the auto-refresh loop ON for users who intentionally
// set it to off — exactly the kind of bug we want to catch here
// before it lands in the UI.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clampAutoRefreshMinutes,
  DEFAULT_REFRESH_MINUTES,
  getAutoRefreshMinutes,
  MAX_REFRESH_MINUTES,
  MIN_REFRESH_MINUTES,
  setAutoRefreshMinutes,
} from '@/lib/holdingsPrefs'

// jsdom provides a fully functional, spec-compliant ``window.localStorage``
// in memory. Clear it between tests to prevent cross-test state leaks.
// The explicit ``// @vitest-environment jsdom`` pragma above guarantees
// ``window`` is always defined (prevents the SSR sibling's node env
// from leaking via the shared thread pool).
beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  window.localStorage.clear()
  vi.restoreAllMocks()
})

describe('constants', () => {
  it('MIN < DEFAULT < MAX so the default sits inside the clamp range', () => {
    expect(MIN_REFRESH_MINUTES).toBeLessThan(DEFAULT_REFRESH_MINUTES)
    expect(DEFAULT_REFRESH_MINUTES).toBeLessThan(MAX_REFRESH_MINUTES)
  })

  it('MIN is 5 (5-min floor protects the Finnhub 60/min free tier)', () => {
    expect(MIN_REFRESH_MINUTES).toBe(5)
  })

  it('MAX is 1440 (24h ceiling)', () => {
    expect(MAX_REFRESH_MINUTES).toBe(1440)
  })

  it('DEFAULT is 60 (1 hour, the cadence the user asked for)', () => {
    expect(DEFAULT_REFRESH_MINUTES).toBe(60)
  })
})

describe('clampAutoRefreshMinutes', () => {
  it('preserves 0 as the "off" sentinel (NOT clamped up to MIN)', () => {
    expect(clampAutoRefreshMinutes(0)).toBe(0)
  })

  it('clamps values < MIN (and != 0) up to MIN', () => {
    expect(clampAutoRefreshMinutes(1)).toBe(MIN_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(2)).toBe(MIN_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(MIN_REFRESH_MINUTES - 1)).toBe(MIN_REFRESH_MINUTES)
  })

  it('keeps values inside [MIN, MAX] verbatim', () => {
    expect(clampAutoRefreshMinutes(MIN_REFRESH_MINUTES)).toBe(MIN_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(60)).toBe(60)
    expect(clampAutoRefreshMinutes(MAX_REFRESH_MINUTES)).toBe(MAX_REFRESH_MINUTES)
  })

  it('clamps values > MAX down to MAX', () => {
    expect(clampAutoRefreshMinutes(MAX_REFRESH_MINUTES + 1)).toBe(MAX_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(9999)).toBe(MAX_REFRESH_MINUTES)
  })

  it('floors decimal values to the integer below (no rounding up)', () => {
    // 7.9 → 7 (NOT 8). Math.floor is intentional; rounding up would
    // let a future "1.0001 minute" fat-finger escape the floor.
    expect(clampAutoRefreshMinutes(7.9)).toBe(7)
    expect(clampAutoRefreshMinutes(60.4)).toBe(60)
  })

  it('returns DEFAULT for non-finite input (NaN, Infinity, -Infinity)', () => {
    expect(clampAutoRefreshMinutes(Number.NaN)).toBe(DEFAULT_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(Number.POSITIVE_INFINITY)).toBe(DEFAULT_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(Number.NEGATIVE_INFINITY)).toBe(DEFAULT_REFRESH_MINUTES)
  })

  it('clamps negative non-zero values to MIN (not 0 — 0 is the off sentinel)', () => {
    expect(clampAutoRefreshMinutes(-1)).toBe(MIN_REFRESH_MINUTES)
    expect(clampAutoRefreshMinutes(-100)).toBe(MIN_REFRESH_MINUTES)
  })
})

describe('getAutoRefreshMinutes', () => {
  it('returns DEFAULT when the localStorage key is missing', () => {
    expect(getAutoRefreshMinutes()).toBe(DEFAULT_REFRESH_MINUTES)
  })

  it('returns the stored value verbatim when inside the clamp range', () => {
    window.localStorage.setItem(
      'fc_holdings_auto_refresh_minutes',
      String(15)
    )
    expect(getAutoRefreshMinutes()).toBe(15)
  })

  it('returns 0 (off sentinel) when the stored value is exactly 0', () => {
    window.localStorage.setItem('fc_holdings_auto_refresh_minutes', '0')
    expect(getAutoRefreshMinutes()).toBe(0)
  })

  it('clamps an out-of-bounds stored value on read (defence against corrupted storage)', () => {
    window.localStorage.setItem(
      'fc_holdings_auto_refresh_minutes',
      String(MAX_REFRESH_MINUTES + 1)
    )
    expect(getAutoRefreshMinutes()).toBe(MAX_REFRESH_MINUTES)
  })

  it('returns DEFAULT for non-numeric stored values (corrupted storage)', () => {
    window.localStorage.setItem('fc_holdings_auto_refresh_minutes', 'not-a-number')
    expect(getAutoRefreshMinutes()).toBe(DEFAULT_REFRESH_MINUTES)
  })

  // SSR-safe contract is exercised in the dedicated ``SSR-safe branch``
  // describe block at the bottom of this file (uses per-block
  // ``// @vitest-environment node`` so the read-path's
  // ``typeof window === 'undefined'`` branch fires naturally without
  // any globalThis stub dance).
})

describe('setAutoRefreshMinutes — write + return contract', () => {
  it('writes the CLAMPED value to localStorage (not the raw input)', () => {
    setAutoRefreshMinutes(1)  // below MIN → clamps to 5
    expect(window.localStorage.getItem('fc_holdings_auto_refresh_minutes')).toBe(
      String(MIN_REFRESH_MINUTES)
    )
  })

  it('returns the clamped value so the caller can sync React state to the same value storage just stored', () => {
    expect(setAutoRefreshMinutes(1)).toBe(MIN_REFRESH_MINUTES)
    expect(setAutoRefreshMinutes(0)).toBe(0)
    expect(setAutoRefreshMinutes(MAX_REFRESH_MINUTES + 5)).toBe(MAX_REFRESH_MINUTES)
    expect(setAutoRefreshMinutes(60)).toBe(60)
  })

  it('preserves the 0 sentinel on write', () => {
    expect(setAutoRefreshMinutes(0)).toBe(0)
    expect(window.localStorage.getItem('fc_holdings_auto_refresh_minutes')).toBe('0')
  })

  // SSR-safe write path is exercised in the dedicated ``SSR-safe
  // branch`` describe block at the bottom of this file.
})

// SSR-safe branch tests live in a separate file
// (``holdingsPrefs.ssr.test.ts``) so the ``// @vitest-environment
// node`` directive at file top doesn't leak to this file's jsdom
// worker. Splitting out was needed after a per-block directive in
// this file caused worker-level env inheritance that broke the
// round-trip tests below (they'd all see ``window`` as undefined
// and return DEFAULT instead of the stored value).

describe('set → get round-trip', () => {
  it('a value committed via setAutoRefreshMinutes reads back identically', () => {
    setAutoRefreshMinutes(15)
    expect(getAutoRefreshMinutes()).toBe(15)
  })

  it('the 0 sentinel survives the round-trip', () => {
    setAutoRefreshMinutes(0)
    expect(getAutoRefreshMinutes()).toBe(0)
  })

  it('an out-of-bounds write is read back as the clamped value', () => {
    setAutoRefreshMinutes(MAX_REFRESH_MINUTES * 10)
    expect(getAutoRefreshMinutes()).toBe(MAX_REFRESH_MINUTES)
  })
})
