/**
 * Full-stack navigation E2E test.
 *
 * This is the test that would have caught the "every sidebar link
 * throws 404" production bug. It runs the live stack (rules-service
 * backend on :8000, Next.js dev on :3000) and clicks through ALL 8
 * sidebar nav items, asserting:
 *
 *   1. The URL changes to the expected path
 *   2. The page body does NOT contain 404 / "not found" / "could not be found"
 *   3. The page has a visible <h1> or <h2> (rendered, not blank)
 *   4. The sidebar stays visible across navigations
 *   5. No unexpected browser console errors fire on any route
 *
 * It also asserts that the sidebar marks the current route with
 * ``aria-current="page"`` (regression guard for the active-link
 * highlight).
 *
 * Prerequisites (handled by scripts/test-e2e.sh):
 *   - The rules-service backend must be running on :8000
 *   - The Next.js dev server must be running on :3000
 *
 * The benign-resource filter below whitelists Next.js dev-only
 * artifacts and standard browser auto-fetched assets that are
 * 100% safe to silence. The filter is URL-based, not message-based:
 * a real 404 on an API route will NOT match, so genuine bugs still
 * fail the test.
 */
import { test, expect, type ConsoleMessage } from '@playwright/test'

const NAV_ITEMS: Array<{ name: string; expectedPath: string }> = [
  { name: 'Overview', expectedPath: '/' },
  { name: 'Portfolio', expectedPath: '/portfolio' },
  { name: 'Goals', expectedPath: '/goals' },
  { name: 'Recommendations', expectedPath: '/recommendations' },
  { name: 'Accounts', expectedPath: '/accounts' },
  { name: 'Activity', expectedPath: '/activity' },
  { name: 'Settings', expectedPath: '/settings' },
  { name: 'Help', expectedPath: '/help' },
]

// ----------------------------------------------------------------------
//  TEST-INVARIANT:  /api/* 404s are NEVER benign.
//  Anything matching ``/api/`` MUST surface a console error.
// ----------------------------------------------------------------------

/**
 * Text patterns that fire on every healthy run and are intentionally
 * silenced. NOTE: the broader ``[cashflix]`` prefix is intentionally
 * NOT included here — a real API 404 or 500 from one of the new
 * pages (e.g. /api/recommendations) would log that prefix with
 * ``Status: 404`` (or 500), and silencing it would mask a real
 * product bug. Only the auto-recovered 401 case is benign.
 */
const BENIGN_PATTERNS: RegExp[] = [
  // Auto-recovered 401 from the interceptor (single attempt per request).
  /\[cashflix\].*Status:\s*401/i,
  // CORS preflight failures when the backend is fully down.
  /Failed to load resource.*ERR_CONNECTION_REFUSED/,
  // Browser offline / network disconnected.
  /Failed to load resource.*ERR_INTERNET_DISCONNECTED/,
  // Axios surfaces network-layer failures with this literal string.
  /Network Error/i,
  // React's dev-only "act()" warning when hydration races the test.
  /not wrapped in act\(\.\.\.\)/i,
]

/**
 * URL patterns for known dev-only cosmetic assets. NOTE: any URL
 * under ``/api/`` is intentionally NOT in this list — a 404 from
 * ``/api/...`` is a real bug this test must surface. Same for
 * any user-facing page route under ``/app-name/*`` (those 404s
 * render the Next.js 404 page, which the body-text check below
 * catches anyway).
 *
 * Drive-from-data: a manual diagnostic showed 5 Next.js dev
 * chunks 404 after a fresh server restart before any navigation:
 *   - /_next/static/css/app/layout.css
 *   - /_next/static/chunks/main-app.js
 *   - /_next/static/chunks/app/page.js
 *   - /_next/static/chunks/app-pages-internals.js
 *   - /_next/static/chunks/app/portfolio/page.js
 * All five are within ``/_next/static/`` so a single prefix
 * whitelist covers them, and any real API 404 still surfaces.
 */
const BENIGN_RESOURCE_URL_PATTERNS: RegExp[] = [
  // ---- Browser-auto-fetched standard assets ----
  /\/favicon\.ico(\?|$)/,
  /\/favicon\.svg(\?|$)/,
  /\/apple-touch-icon[^/]*\.(png|jpg|jpeg)(\?|$)/,
  /\/manifest(\.json|webmanifest)(\?|$)/,
  /\/browserconfig\.xml(\?|$)/,
  /\/sitemap\.xml(\?|$)/,
  /\/robots\.txt(\?|$)/,
  /\/\.well-known\//,
  /\/sw\.js(\?|$)/,
  /\/workbox-[^/]*\.js(\?|$)/,
  // ---- Next.js dev-only generated artifacts ----
  // After a server restart the next dev server rebuilds chunks
  // incrementally. Until a route is first visited its chunk
  // manifest / CSS / HMR payloads can 404 even though the page
  // renders fine. Whitelisting the whole ``/_next/static/`` prefix
  // is safe because nothing user-facing lives there in the current
  // architecture (real app code lives under ``/app/<route>/page.tsx``
  // which is reached via the App Router, not direct static fetches).
  /\/_next\/static\//,
  /\/_next\/static\/chunks\//,
  /\/_next\/static\/css\//,
  /\/_next\/static\/media\//,
  // Client-side __next/data/... RSC prefetch JSON can 404 when a
  // route is changed mid-session in dev mode.
  /\/_next\/data\//,
  // ---- Source maps ----
  // Next.js dev compiles app code on demand; source maps for routes
  // that haven't been visited yet may 404. Production builds also
  // produce 404s when ``productionBrowserSourceMaps`` is off.
  // Always dev-only papercut.
  /\.(js|css|ts|tsx|mjs|cjs)\.map(\?|$)/,
]

const isMessageBenign = (text: string): boolean =>
  BENIGN_PATTERNS.some((re) => re.test(text))

const isResourceUrlBenign = (url: string): boolean => {
  if (!url) return false
  // Invariant assertion: /api/* 404s must NEVER be silenced.
  if (/\/api\//.test(url)) return false
  return BENIGN_RESOURCE_URL_PATTERNS.some((re) => re.test(url))
}

/**
 * Combined filter. A console error is benign when:
 *   1. Its text matches one of the BENIGN_PATTERNS (e.g. the
 *      auto-recovered 401 from the interceptor), OR
 *   2. It's a "Failed to load resource: ... 404" AND the resource
 *      URL matches one of the BENIGN_RESOURCE_URL_PATTERNS.
 *
 * A real API 404 (logged as ``[cashflix] API Error: ... Status: 404``)
 * does NOT match (2) — text mismatch — and matches neither pattern in
 * (1), so genuine bugs fail the test. The ``/api/*`` black-list in
 * ``isResourceUrlBenign`` is a belt-and-braces defense.
 */
const isBenign = (text: string, url?: string): boolean => {
  if (isMessageBenign(text)) return true
  if (
    /Failed to load resource.*404/i.test(text) &&
    url &&
    isResourceUrlBenign(url)
  ) {
    return true
  }
  return false
}

const NOT_FOUND_PATTERNS = [
  '404',
  'not found',
  'could not be found',
  'this page could not be found',
]

for (const item of NAV_ITEMS) {
  test(`sidebar "${item.name}" navigates to ${item.expectedPath} without 404`, async ({
    page,
  }) => {
    const errors: string[] = []
    page.on('console', (msg: ConsoleMessage) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        const url = msg.location()?.url ?? ''
        if (!isBenign(text, url)) errors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      if (!isBenign(err.message)) errors.push(err.message)
    })
    /**
     * Capture dev-mode ``requestfailed`` events (e.g. an API call
     * blocked by CORS, an aborted XHR). These surface as console
     * errors too but capturing them explicitly gives us URLs in
     * the test failure message for easier debugging. We exempt
     * the same cosmetic-asset paths the URL-whitelist covers and
     * skip any ERR_ABORTED — Next dev aggressively cancels
     * in-flight prefetches/RSC fetches on every fast navigation.
     */
    page.on('requestfailed', (req) => {
      const url = req.url()
      const failure = req.failure()?.errorText ?? ''
      if (failure.includes('ERR_ABORTED') || failure.includes('ERR_CANCELED')) {
        return
      }
      if (!isResourceUrlBenign(url)) {
        errors.push(`requestfailed: ${url} -> ${failure || 'unknown'}`)
      }
    })

    // Start from the Overview so the sidebar is guaranteed to be
    // mounted. ``networkidle`` (not just ``domcontentloaded``)
    // waits for React hydration to complete so a subsequent click
    // on a sidebar <Link> actually fires the React onClick handler.
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const sidebar = page.locator('nav[aria-label="Primary"]')
    await expect(sidebar).toBeVisible()

    // Click the sidebar link by visible name. ``.first()`` is
    // defensive in case a future header has duplicate text.
    const link = sidebar.getByRole('link', { name: item.name }).first()
    await expect(link).toBeVisible()
    await link.click()
    // Wait explicitly for the URL to settle on the destination
    // path. ``networkidle`` alone can resolve before the soft-nav
    // commits the new URL in dev mode, which previously caused
    // intermittent "URL still /" failures even though the click
    // fired correctly.
    await page.waitForURL(`**${item.expectedPath}`, { timeout: 10000 })
    await page.waitForLoadState('networkidle')

    // 1) URL must match the expected path.
    const url = new URL(page.url())
    expect(url.pathname).toBe(item.expectedPath)

    // 2) The sidebar must STILL be visible after navigation
    //    (catches the case where a route forgot to render <Sidebar />).
    await expect(sidebar).toBeVisible()

    // 3) The body must NOT contain any 404 indicator. This is
    //    the critical regression guard for the "every nav link
    //    throws 404" bug.
    const bodyText = (await page.locator('body').innerText()).toLowerCase()
    for (const pattern of NOT_FOUND_PATTERNS) {
      expect(
        bodyText,
        `${item.name} page body contains "${pattern}" (got: "${bodyText.slice(0, 200)}...")`,
      ).not.toContain(pattern)
    }

    // 4) The page must have a visible <h1> or <h2> (proves the
    //    page actually rendered its own content, not a fallback).
    const heading = page.locator('h1, h2').first()
    await expect(heading).toBeVisible()
    const headingText = (await heading.innerText()).trim()
    expect(headingText.length).toBeGreaterThan(0)

    // 5) No unexpected console errors. The benign filter covers
    //    the auto-recovered 401 + transient devLogin noise +
    //    dev-only cosmetic asset 404s (incl. Next.js chunk
    //    rebuilds after server restart). Anything else is a real
    //    bug — including a real API 404, which the test now
    //    catches by NOT matching the broad ``[cashflix]`` prefix
    //    and by the explicit ``/api/`` black-list.
    expect(
      errors,
      `Unexpected console errors on ${item.name}: ${errors.join(' | ')}`,
    ).toEqual([])
  })
}

test('sidebar marks the current route with aria-current="page"', async ({ page }) => {
  // /portfolio is data-driven, so we wait for it to render before
  // checking the active state.
  await page.goto('/portfolio')
  await page.waitForURL('**/portfolio')
  await page.waitForLoadState('networkidle')

  const portfolioLink = page
    .locator('nav[aria-label="Primary"]')
    .getByRole('link', { name: 'Portfolio' })
    .first()
  await expect(portfolioLink).toHaveAttribute('aria-current', 'page')

  // And Overview should NOT be active on /portfolio.
  const overviewLink = page
    .locator('nav[aria-label="Primary"]')
    .getByRole('link', { name: 'Overview' })
    .first()
  await expect(overviewLink).not.toHaveAttribute('aria-current', 'page')
})

test('dark mode toggle works on a sub-route (not just Overview)', async ({ page }) => {
  // Pin the regression: dark mode must work on every route, not
  // just the one the original test happened to land on. ``networkidle``
  // gives React time to hydrate the DarkModeToggle's onClick handler
  // before we click — otherwise the click is a no-op against the
  // server-rendered DOM and the post-click class assertion fails
  // for a hydration race, not a real product bug.
  // Also waits for the Header's profile-avatar label to flip from
  // "Loading user profile" to "Signed in as …" (a strict
  // post-hydration signal tied to React state, not just the
  // static HTML being painted).
  await page.goto('/settings')
  // Deterministic hydration sentinel: the ``DarkModeToggle``
  // component sets ``<html data-darkmode-hydrated="true">`` in
  // its first ``useEffect`` (post-mount, post-hydration) and
  // removes it on unmount. The button is painted server-side
  // with a fixed ``aria-label``, so a visibility check alone is
  // racy. This attribute is independent of the auth bootstrap
  // (``devLogin + getProfile`` can hang without affecting
  // dark-mode hydration).
  await page.waitForSelector('html[data-darkmode-hydrated="true"]', {
    timeout: 10_000,
  })

  const toggle = page.getByRole('button', {
    // Exact initial state in a fresh Playwright context (localStorage
    // starts empty, so the toggle advertises the action it would
    // perform: "Switch to dark mode").
    name: 'Switch to dark mode',
  })
  await expect(toggle).toBeVisible()
  await toggle.click()

  const hasDark = await page.evaluate(() =>
    document.documentElement.classList.contains('dark'),
  )
  expect(hasDark).toBe(true)
  const stored = await page.evaluate(() => localStorage.getItem('atlas_theme'))
  expect(stored).toBe('enabled')
})
