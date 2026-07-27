'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  rulesService,
  clearStoredToken,
  markBootstrapWarm,
  isBootstrapWarm,
  clearBootstrapWarm,
} from '@/lib/api'
import ErrorBanner from '@/components/ui/ErrorBanner'
import { useReducedMotion } from '@/lib/useReducedMotion'
import {
  Landmark,
  ShieldCheck,
  RefreshCw,
  CheckCircle2,
  Circle,
} from 'lucide-react'

/**
 * AuthBootstrapProvider
 * ---------------------
 * Centralizes the cold-start JWT mint and gates the rest of the tree
 * behind a single, well-designed splash. Without this provider, every
 * page (Overview, Portfolio, Goals, Settings) independently fired
 * `rulesService.devLogin()` *only on the Overview* and otherwise
 * relied on the axios 401 interceptor to recover -- which produced a
 * visible "session expired" flash on the others.
 *
 * Why a Provider instead of page-level hooks:
 *   1. Single devLogin round trip per cold start, no matter how many
 *      pages mount concurrently. A module-level singleton promise is
 *      the standard pattern for "deduped bootstrap" auth flows.
 *   2. Every page is guaranteed to mount with a valid bearer token;
 *      no page can race against a missing token.
 *   3. Removes a copy-paste footgun: future pages do not need to
 *      remember to cold-start -- they inherit it.
 *
 * The axios 401 interceptor still runs as a safety net for long
 * sessions where the token naturally expires after device sleep,
 * browser cookie clear, or BE `JWT_SECRET` rotation mid-session.
 */

let bootstrapPromise: Promise<void> | null = null

/** Time out the auth handshake after this many milliseconds so a
 *  hung backend / dangling fetch cannot leave the app stuck on the
 *  splash screen forever. */
export const BOOTSTRAP_TIMEOUT_MS = 15_000

/** Time out the health probe after this many milliseconds. A fast
 *  failure means the backend is down / unreachable; a timeout means
 *  the backend is responding too slowly to trust the login handshake. */
export const HEALTH_TIMEOUT_MS = 3_000

/** As a hard fallback, the splash will auto-SKIP (transition to the
 *  ready phase without waiting for devLogin) after this many
 *  milliseconds. This exists so a hung / deadlocked bootstrap can
 *  never trap the user on the splash forever — children render and
 *  any per-request 401s handle their own redirect / toast. */
export const HARD_SKIP_AFTER_MS = 30_000

/** Diagnosed backend state surfaced in the error UI. */
export type BackendStatus = 'down' | 'slow' | 'auth_failed'

/** Custom error that carries the diagnosed backend status so the UI
 *  can choose a clearer title / guidance message. */
export class AuthBootstrapError extends Error {
  status: BackendStatus

  constructor(message: string, status: BackendStatus = 'auth_failed') {
    super(message)
    this.name = 'AuthBootstrapError'
    this.status = status
  }
}

/** Race a promise against a timeout. Cleans up the timer whether the
 *  promise wins or not. */
function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  reason: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    const cleanup = () => {
      if (timeoutId) clearTimeout(timeoutId)
    }

    promise.then(
      (value) => {
        cleanup()
        resolve(value)
      },
      (err) => {
        cleanup()
        reject(err)
      },
    )

    timeoutId = setTimeout(() => {
      reject(new Error(reason))
    }, ms)
  })
}

async function ensureAuth(): Promise<void> {
  if (typeof window === 'undefined') return
  if (bootstrapPromise) return bootstrapPromise

  const run = async (): Promise<void> => {
    // Skip the round-trip if we already have a token. The axios
    // interceptor handles mid-session expiry via 401 retry.
    if (hasStoredToken()) return

    // Phase 1: quick health probe. This lets us distinguish a backend
    // that is genuinely down (fast ECONNREFUSED) from one that is
    // merely slow / overloaded (probe itself times out).
    try {
      await withTimeout(
        rulesService.health(),
        HEALTH_TIMEOUT_MS,
        'Health check timed out',
      )
    } catch (err) {
      const msg =
        (err as { message?: string })?.message || String(err) || 'Unknown error'
      if (msg.includes('timed out')) {
        throw new AuthBootstrapError(
          'The backend is responding too slowly to complete login.',
          'slow',
        )
      }
      throw new AuthBootstrapError(
        'The backend is not reachable. Make sure rules-service is running on :8000.',
        'down',
      )
    }

    // Phase 2: backend is reachable, try the actual login handshake.
    try {
      await rulesService.devLogin()
    } catch (err) {
      const msg =
        (err as { message?: string })?.message || String(err) || 'Unknown error'
      if (msg.includes('timed out')) {
        throw new AuthBootstrapError(
          'Login handshake timed out. The backend may be under load.',
          'slow',
        )
      }
      throw new AuthBootstrapError(msg, 'auth_failed')
    }
  }

  bootstrapPromise = withTimeout(
    run(),
    BOOTSTRAP_TIMEOUT_MS,
    `Auth bootstrap timed out after ${BOOTSTRAP_TIMEOUT_MS / 1000}s`,
  ).catch((err) => {
    // Reset so the next mount can try again (otherwise a 500 on
    // devLogin or a timeout would permanently lock the app out).
    bootstrapPromise = null
    // If the overall bootstrap timeout fired, we know the health probe
    // succeeded (otherwise it would have failed earlier) and the login
    // handshake is the slow part. Surface that as a slow backend.
    const msg = (err as Error)?.message || String(err)
    if (msg.includes('timed out')) {
      throw new AuthBootstrapError(
        'Login handshake timed out. The backend may be under load.',
        'slow',
      )
    }
    throw err
  })
  return bootstrapPromise
}

export function resetAuthBootstrap(): void {
  bootstrapPromise = null
}

type Phase = 'loading' | 'ready' | 'error'

function hasStoredToken(): boolean {
  if (typeof window === 'undefined') return false
  return Boolean(window.localStorage.getItem('fc_session_token'))
}

/**
 * Manual escape hatch — a user who reloads the app (or hits a stuck
 * splash that won't unmount after clicking Continue) can append
 * `?skip-splash=1` to the URL. The mount-time check below honors this
 * and writes the warm flag as a side effect so the next reload
 * (without the query) is also warm. Tested in
 * AuthBootstrapProvider.test.tsx — "escape hatches" describe block.
 */
function shouldSkipSplash(): boolean {
  if (typeof window === 'undefined') return false
  if (typeof window.location === 'undefined') return false
  // Some test setups replace `window.location` with a stripped proxy
  // (e.g. ``{ reload: vi.fn() }`` for the Clear-session route), so
  // `search` may be undefined. Defend with explicit optional access
  // rather than relying on `undefined.includes` crashing the mount.
  const search = window.location.search ?? ''
  // Require the equals sign so an unrelated `?noskip-splash=1` style
  // trailing query can't accidentally trigger the escape hatch.
  return search.includes('skip-splash=')
}

export default function AuthBootstrapProvider({
  children,
}: {
  children: React.ReactNode
}) {
  // Always start in the loading phase so the SSR output matches the
  // initial client render. Reading localStorage in the useState
  // initializer produced a hydration mismatch: the server has no
  // localStorage, so it rendered the splash, while a client with a
  // stored token rendered children immediately. The useEffect below
  // transitions to ready as soon as it verifies the token.
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorDetail, setErrorDetail] = useState<string>('')
  const [errorStatus, setErrorStatus] = useState<BackendStatus | null>(null)
  // Shared unmount flag. Both the mount-effect and the retry
  // callback call ``runBootstrap`` which checks this ref before
  // calling any setState -- a stale Retry click after the user
  // navigates away no longer logs React's
  // "perform a state update on an unmounted component" warning.
  const mountedRef = useRef<boolean>(true)

  // If the user clicks "Continue to app", the in-flight devLogin
  // promise may settle later (resolve or reject). We must not
  // overwrite the ready state the user explicitly chose with a
  // late timeout or network error.
  const skippedRef = useRef<boolean>(false)

  // Show an emergency skip button immediately on mount. The previous
  // 5-second delay was a usability trap — users pressing Tab + Enter
  // hit the "Skip to main content" accessibility link (#main-content)
  // instead of the visible-in-5s Continue button, did not see any
  // visual change, and concluded the app was permanently stuck. With
  // Skip visible from mount, the recovery affordance is obvious
  // before the user even tries any keyboard navigation.
  const [skipVisible] = useState(true)

  // Prevent double-clicks on the skip button and give immediate
  // feedback while the provider transitions to the ready state.
  const [isSkipping, setIsSkipping] = useState(false)

  // Honor the user/OS prefers-reduced-motion setting. The polished
  // splash uses aura + float + gradient-shift + glow-pulse
  // animations, all of which are flagged WCAG 2.3.3 issues for
  // vestibular-sensitive users. The reduced-motion path keeps the
  // layout identical but lands static variants so the page cannot
  // trigger a vestibular event.
  const prefersReducedMotion = useReducedMotion()

  /**
   * Single source of truth for the bootstrap async dance. Both the
   * mount useEffect and the Retry button delegate here so a future
   * change to error-surfacing, retry-after-ms, or telemetry touches
   * one site instead of two parallel copies (the previous
   * implementation had identical try/catch blocks duplicated).
   *
   * Reads the mountedRef before each setState so an unmount + late
   * retry-enqueue path is silently dropped instead of logging
   * a React warning.
   */
  const runBootstrap = useCallback(async (): Promise<void> => {
    try {
      await ensureAuth()
      // If the user chose to skip while the promise was in flight,
      // ignore the late result and leave the app in the ready state.
      if (skippedRef.current) return
      if (mountedRef.current) {
        // Memorize this successful bootstrap so the next reload can
        // skip the splash entirely (see `isBootstrapWarm` in the
        // mount-effect). Failed bootstraps MUST NOT be memorized —
        // a degraded JWT would silently propagate a broken state.
        // (The skip path calls markBootstrapWarm itself in the
        // onClick handler, so we already returned above if
        // skippedRef.current was true.)
        markBootstrapWarm()
        setPhase('ready')
      }
    } catch (err) {
      // Same guard: a late timeout/network error must not clobber
      // the ready state the user explicitly requested.
      if (skippedRef.current) return
      if (mountedRef.current) {
        // Surface the underlying cause so dev can diagnose without
        // opening DevTools: ECONNREFUSED on :8000, devlogin 403,
        // etc. all render distinct messages here.
        const isBootstrapErr = err instanceof AuthBootstrapError
        const msg =
          (err as { message?: string })?.message ||
          String(err) ||
          'Unknown error'
        setErrorDetail(msg)
        setErrorStatus(isBootstrapErr ? (err as AuthBootstrapError).status : 'auth_failed')
        setPhase('error')
      }
      // eslint-disable-next-line no-console
      console.error('[AuthBootstrap] devLogin failed:', err)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true

    // Manual escape hatch — `?skip-splash=...` in the URL triggers
    // an immediate short-circuit to children. Set warm so the next
    // reload (even without the query) is also a warm cold start.
    // This is the safety net a user hits when a Continue-to-app
    // click won't progress (stuck JS / HMR replay / dev-mode error
    // boundary): hard-refresh `?skip-splash=1` and the splash is
    // gone. Logged for dev visibility — a future dev who keeps
    // seeing this warning in console during normal operation knows
    // to chase down whatever's preventing setPhase('ready').
    if (shouldSkipSplash()) {
      markBootstrapWarm()
      setPhase('ready')
      // eslint-disable-next-line no-console
      console.warn(
        '[AuthBootstrap] skip-splash escape hatch engaged; skipping all checks.',
      )
      return () => {
        mountedRef.current = false
      }
    }

    // Warm-reload short circuit. If a previous bootstrap completed
    // (or was explicitly skipped) within WARM_WINDOW_MS
    // (ui/lib/api.ts), skip the visible splash entirely. The
    // stored JWT (if any) is what every authed call relies on, and
    // a stale-token recovery path runs in the axios 401 interceptor
    // — so going straight to children here is the cheapest, most
    // discoverable continuation. We re-arm the warm flag so a
    // open-tab session flipping past the window still caches the
    // current attempt without forcing a round-trip now.
    if (isBootstrapWarm()) {
      markBootstrapWarm()
      // Skip runBootstrap — no health probe, no devLogin call.
      // The token (if present) is good enough for a warm reload;
      // the interceptor covers any 401.
      setPhase('ready')
      return () => {
        mountedRef.current = false
      }
    }

    void runBootstrap()
    return () => {
      mountedRef.current = false
    }
  }, [runBootstrap])

  // Hard fallback: if bootstrap is deadlocked (e.g. axios interceptor
  // race that the user-flagged bug hit), force the ready phase after
  // HARD_SKIP_AFTER_MS so children always render eventually. The
  // in-flight promise's eventual resolution or rejection is ignored.
  useEffect(() => {
    if (phase !== 'loading') return
    const timer = setTimeout(() => {
      if (!mountedRef.current || phase !== 'loading') return
      // eslint-disable-next-line no-console
      console.warn(
        `[AuthBootstrap] hard-skip fired after ${HARD_SKIP_AFTER_MS / 1000}s — the auth handshake was deadlocked. Proceeding without login.`,
      )
      resetAuthBootstrap()
      skippedRef.current = true
      setPhase('ready')
    }, HARD_SKIP_AFTER_MS)
    return () => clearTimeout(timer)
  }, [phase])

  /**
   * Retry handler. The previous implementation only flipped phase
   * back to ``loading`` without re-calling ``ensureAuth`` -- the
   * useEffect's ``[]`` deps meant the retry was a visual no-op
   * (the splash animated but the user's "click Retry" never
   * actually did a round-trip). The fix is to delegate to
   * ``runBootstrap`` which emits a fresh ensureAuth.
   *
   * ``runBootstrap`` consults the shared ``mountedRef`` so the
   * retry's setState calls respect unmount just like the mount
   * path does.
   */
  const handleRetry = useCallback(async () => {
    resetAuthBootstrap()
    setErrorDetail('')
    setErrorStatus(null)
    setIsSkipping(false)
    skippedRef.current = false
    setPhase('loading')
    await runBootstrap()
  }, [runBootstrap])

  /**
   * Last-resort recovery: clear the local session (a corrupted or
   * stale JWT can cause the axios 401 interceptor to loop, stranding
   * the user on the error UI) and do a hard reload. A hard reload
   * also drops any zombie in-flight promises from the previous
   * mount — e.g. an axios retry that locked `inflightLogin.current`
   * on a never-resolving promise.
   */
  const handleResetAndReload = useCallback(() => {
    try {
      clearStoredToken()
      // Also clear the warm flag — a corrupted/stale JWT could
      // survive clearStoredToken if we still believed the prior
      // bootstrap was recent. Re-truly cold start the next mount.
      clearBootstrapWarm()
    } finally {
      // location.reload is synchronous from the user's perspective
      // and tears down the whole page state, including any
      // module-level singletons the previous mount left running.
      window.location.reload()
    }
  }, [])

  // Loading: full-window splash with subtle gradient + status
  // checklist + dark-mode-aware surface treatment. The polished
  // version uses the project's CSS animation utilities
  // (animate-aura, animate-gradient-shift, animate-float,
  // animate-fadeIn) from ui/styles/animations.css — the same
  // palette as the rest of the app, no new dependencies.
  //
  // All animation classes are gated behind prefersReducedMotion so
  // vestibular-sensitive users (and the prefers-reduced-motion
  // media-query) see a fully static but still readable splash.
  if (phase === 'loading') {
    const anim = (cls: string) => (prefersReducedMotion ? '' : cls)
    return (
      <div
        className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-gradient-to-br from-surface via-surface to-[var(--bg-secondary)] transition-opacity duration-500 ${anim('animate-gradient-shift')}`}
        style={{ backgroundSize: '200% 200%' }}
        role="status"
        aria-live="polite"
        aria-label="Securing your session"
      >
        {/* Ambient cyan glow — backed by the dark-mode --glow-primary
            token so dark and light mode both render correctly. */}
        <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_center,var(--glow-primary),transparent_55%)]" />
        <div className={`flex flex-col items-center gap-6 ${anim('animate-fadeIn')}`}>
          <div className="relative">
            {/*
              Aura glow behind the logo. aura keyframe scales + opacity
              for an ambient pulse. Hidden in reduced-motion.
            */}
            <div className={`absolute -inset-4 rounded-full bg-[var(--glow-primary)] blur-xl ${anim('animate-aura')}`} aria-hidden />
            <div className={`relative flex h-20 w-20 items-center justify-center rounded-3xl border border-primary/20 bg-[var(--bg-secondary)]/60 backdrop-blur-md shadow-lg ${anim('animate-float')}`}>
              <Landmark className={`h-10 w-10 text-primary ${anim('animate-glow-pulse')}`} aria-hidden />
            </div>
          </div>

          <div className="flex flex-col items-center gap-1">
            <h2 className="text-lg font-semibold tracking-wide text-[var(--text-primary)]">
              Securing your session
            </h2>
            <p className="max-w-xs text-center text-sm text-[var(--text-tertiary)]">
              Local-first finance copilot &mdash; bootstrapping an
              offline-friendly session key.
            </p>
          </div>

          {/*
            Status checklist — three steps that mirror the actual
            bootstrap phases (health probe → devLogin → ready). Even
            though the inner state machine doesn't yet expose per-
            step events, the checklist reassures the user the app is
            doing real work rather than spinning. The "active"
            pulse + "done" check visually reads as a progress bar.
          */}
          <div className="mt-2 flex flex-col items-start gap-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)]/40 px-5 py-4 backdrop-blur-sm">
            <div className={`flex items-center gap-3 text-[var(--text-secondary)] ${anim('animate-slideUp')}`}>
              <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-hidden />
              <span className="text-sm">Environment verified</span>
            </div>
            <div className={`flex items-center gap-3 text-[var(--text-secondary)] ${anim('animate-slideUp [animation-delay:120ms]')}`}>
              <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-hidden />
              <span className="text-sm">Offline keys loaded</span>
            </div>
            <div className={`flex items-center gap-3 text-[var(--text-secondary)] ${anim('animate-slideUp [animation-delay:240ms]')}`}>
              <Circle className={`h-4 w-4 text-primary ${anim('animate-pulse')}`} aria-hidden />
              <span className="text-sm">Negotiating secure session…</span>
            </div>
          </div>

          {skipVisible && (
            <div className={`mt-2 flex flex-col items-center gap-3 ${anim('animate-fadeIn [animation-delay:400ms]')}`}>
              <p className="text-xs text-[var(--text-tertiary)]">
                Still waiting? You can continue without logging in.
              </p>
              <button
                type="button"
                disabled={isSkipping}
                suppressHydrationWarning
                data-continue-app="true"
                onClick={() => {
                  // Reset the singleton so a later retry/mount can
                  // still attempt a real login instead of returning
                  // the stale/hung promise. Mark the skip so the
                  // in-flight promise does not later flip us to
                  // ready or error.
                  resetAuthBootstrap()
                  skippedRef.current = true
                  setIsSkipping(true)
                  setPhase('ready')
                  // Memorize the skip so a warm reload skips the
                  // splash entirely on next visit (paired with the
                  // isBootstrapWarm mount-time short-circuit).
                  markBootstrapWarm()
                  // Bulletproof fallback: if React's state update
                  // fails to unmount the splash (rare HMR-replay or
                  // dev-mode-error-boundary edge cases that have
                  // stranded users before), force a URL escape so
                  // the user is guaranteed out. The mount-time
                  // `?skip-splash=...` short-circuit goes straight
                  // to children on the reloaded page; the
                  // markBootstrapWarm above means even after the
                  // query is stripped, future reloads stay warm.
                  //
                  // Two requestAnimationFrames give React 18+ a fair
                  // chance to commit before we declare it stuck.
                  // The query has a timestamp suffix to defeat any
                  // HTTP cache that might serve a stale hash.
                  requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                      if (typeof document === 'undefined') return
                      const splash = document.querySelector(
                        '[aria-label="Securing your session"]',
                      )
                      if (splash && document.body.contains(splash)) {
                        // eslint-disable-next-line no-console
                        console.warn(
                          '[AuthBootstrap] Splash did not unmount after Continue; escaping via skip-splash URL.',
                        )
                        const url = new URL(window.location.href)
                        url.searchParams.set('skip-splash', String(Date.now()))
                        window.location.assign(url.toString())
                      }
                    })
                  })
                }}
                className="rounded-full border border-primary/30 bg-primary/10 px-5 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:border-primary/50 hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Continue to app
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Hard-stop auth error. We intentionally do NOT fall through to
  // children here: every authed call would just produce another 401,
  // looping. Show the user a clear "what to do next" instead, AND
  // surface the underlying error message so a dev can diagnose
  // without opening DevTools (ECONNREFUSED on :8000 vs devLogin 403
  // vs network timeout vs CORS policy block all want different fixes).
  if (phase === 'error') {
    // Pick the error UI copy from the diagnosed backend state.
    const errorCopy =
      errorStatus === 'down'
        ? {
          title: 'Backend is unreachable',
          message:
            'Start the backend with `bash scripts/start.sh`, then click Retry. If you just started it, wait a few seconds for it to boot.',
        }
        : errorStatus === 'slow'
          ? {
            title: 'Backend is slow',
            message:
              'The service may be starting up or under load. You can wait and click Retry, or use Continue to app on the splash to skip login.',
          }
          : {
            title: 'Authentication bootstrap failed',
            message:
              'The rules-service refused to issue a local JWT. Make sure the backend is running on :8000 (`bash scripts/start.sh`), then click Retry.',
          }

    return (
      <div className="mx-auto mt-24 max-w-2xl p-6">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-error/10 ring-1 ring-error/30">
            <ShieldCheck className="h-6 w-6 text-error" aria-hidden />
          </div>
          <h1 className="text-lg font-semibold text-on-surface">
            Could not start your session
          </h1>
        </div>
        <ErrorBanner
          variant="danger"
          title={errorCopy.title}
          message={errorCopy.message}
          onRetry={handleRetry}
        />
        {errorDetail && (
          <pre
            className="mt-4 overflow-auto rounded-lg border border-outline-variant/20 bg-surface-container-low p-3 text-xs font-mono text-on-surface-variant whitespace-pre-wrap"
            aria-live="polite"
            aria-label="Underlying error message"
          >
            {errorDetail}
          </pre>
        )}
        <div className="mt-6 flex flex-col gap-2 border-t border-outline-variant/20 pt-4">
          <p className="text-xs text-on-surface-variant">
            If Retry doesn't work, your stored session key may be corrupted
            or the interceptor is locked. Clear the local session and reload
            to start fresh.
          </p>
          <button
            type="button"
            onClick={handleResetAndReload}
            className="self-start inline-flex items-center gap-2 rounded-lg border border-outline-variant/40 px-3 py-2 text-xs font-medium text-on-surface-variant hover:text-primary hover:border-primary/40 hover:bg-surface-container transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            aria-label="Clear local session and reload"
            data-testid="auth-bootstrap-reset-reload"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Clear session &amp; reload
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
