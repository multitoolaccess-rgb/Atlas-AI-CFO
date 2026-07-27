// =============================================================================
// Phase 48 — SSR-safe branch tests for ``ui/lib/holdingsPrefs.ts``.
//
// This file is split out from ``holdingsPrefs.test.ts`` so the
// ``// @vitest-environment node`` directive below applies to the WHOLE
// file (cleaner than per-block). A previous attempt used the
// per-block directive inside a describe block in the main file; that
// caused worker-level env inheritance where the main file's
// jsdom-based tests also ran in node env (typeof window ===
// 'undefined' → every getAutoRefreshMinutes call returned DEFAULT
// instead of the stored value, breaking the round-trip tests).
//
// Splitting into a separate file eliminates the env-inheritance
// concern: this file runs in node, the main file runs in jsdom,
// no cross-contamination.
// =============================================================================
// @vitest-environment node

import { describe, expect, it } from 'vitest'
import {
  DEFAULT_REFRESH_MINUTES,
  getAutoRefreshMinutes,
  MAX_REFRESH_MINUTES,
  setAutoRefreshMinutes,
} from '@/lib/holdingsPrefs'

describe('SSR-safe branch (node env, no window)', () => {
  it('getAutoRefreshMinutes returns DEFAULT when window is undefined', () => {
    // The read-path's first statement is
    //   ``if (typeof window === 'undefined') return DEFAULT_REFRESH_MINUTES``
    // — that's the branch under test. Asserts the FE's Next.js
    // server-render path (if the page is ever rendered server-side
    // instead of 'use client') doesn't crash on the localStorage
    // read.
    expect(getAutoRefreshMinutes()).toBe(DEFAULT_REFRESH_MINUTES)
  })

  it('setAutoRefreshMinutes returns clamped value when window is undefined (no throw)', () => {
    // The write path's same ``typeof window === 'undefined'``
    // guard means the function returns the clamped value without
    // touching storage. The caller in Next.js server-rendering is
    // the only place this branch fires (the portfolio page is
    // 'use client' so the runtime is always browser, but the
    // SSR-safety contract is worth pinning here so a future
    // re-architecture that adds server-rendered pages doesn't
    // silently break).
    expect(setAutoRefreshMinutes(60)).toBe(60)
    expect(setAutoRefreshMinutes(0)).toBe(0)
    expect(setAutoRefreshMinutes(MAX_REFRESH_MINUTES + 1)).toBe(MAX_REFRESH_MINUTES)
  })
})
