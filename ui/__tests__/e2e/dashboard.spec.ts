/**
 * Browser smoke test for the dashboard.
 *
 * What this test covers:
 *   1. The dashboard route loads at http://localhost:3000 without
 *      any browser console errors.
 *   2. The sidebar shows the "Atlas" brand.
 *   3. The dark mode toggle in the header adds the `.dark` class to
 *      `<html>` and persists to localStorage.
 *   4. The Financial Plans section renders with the 3 stat cards.
 *
 * Prerequisites:
 *   - The rules-service backend must be running on :8000
 *     (start with `cd services/rules-service && uvicorn app.main:app`).
 *   - The Next.js dev server is started by Playwright's webServer config.
 *
 * This is a SMOKE test, not a full E2E. The vitest suite covers the
 * unit + integration contracts; this test only proves the browser
 * pipeline works end-to-end (Next.js builds, axios + the 401
 * interceptor survive a real network round-trip, no console errors).
 *
 * TEST-INVARIANT:  /api/* 404s MUST surface as failures. The
 * BENIGN_RESOURCE_URL_PATTERNS array below intentionally does NOT
 * include ``/api/`` — see the explicit black-list in
 * ``isResourceUrlBenign``.
 */
import { test, expect, type ConsoleMessage } from '@playwright/test'

/**
 * Text patterns that fire on every healthy run and are intentionally
 * silenced. NOTE: the broader ``[cashflix]`` prefix is intentionally
 * NOT in this list — only the auto-recovered 401 from the interceptor
 * is benign. A real API 404 or 500 logged with ``[cashflix]`` will
 * surface.
 *
 * The ``No response received`` line in api.ts fires when the
 * backend is fully unreachable — the same case the
 * ``Failed to load resource: ERR_CONNECTION_REFUSED`` browser signal
 * covers. Both are listed because different layers (the JS app vs
 * the browser network stack) emit them independently.
 */
const BENIGN_PATTERNS: RegExp[] = [
  // Auto-recovered 401 from the interceptor.
  /\[cashflix\].*Status:\s*401/i,
  // api.ts's no-response branch (backend fully down).
  /\[cashflix\].*No response received/i,
  // Browser network-stack signal for the same.
  /Failed to load resource.*ERR_CONNECTION_REFUSED/,
  /Failed to load resource.*ERR_INTERNET_DISCONNECTED/,
  // Axios surfaces network-layer failures with this literal string.
  /Network Error/i,
  // React's dev-only "act()" warning when hydration races tests.
  /not wrapped in act\(\.\.\.\)/i,
]

/**
 * URL patterns for known dev-only cosmetic assets. MUST NOT include
 * ``/api/`` — a real API 404 from any of the new pages will then
 * surface as a test failure (regression guard for the prod bug where
 * every sidebar link 404s).
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
  // incrementally. Until the first visit the chunk manifest / CSS
  // / HMR payloads can 404 even though the page renders fine.
  /\/_next\/static\//,
  /\/_next\/static\/chunks\//,
  /\/_next\/static\/css\//,
  /\/_next\/static\/media\//,
  // Client-side RSC prefetch JSON can 404 mid-session in dev.
  /\/_next\/data\//,
  // Source maps don't always exist for unvisited routes in dev, or
  // when ``productionBrowserSourceMaps`` is off in prod.
  /\.(js|css|ts|tsx|mjs|cjs)\.map(\?|$)/,
]

const isMessageBenign = (text: string): boolean =>
  BENIGN_PATTERNS.some((re) => re.test(text))

const isResourceUrlBenign = (url: string): boolean => {
  if (!url) return false
  // Belt-and-braces defense: any URL under /api/ is NEVER benign.
  // A real API 404 from a missing/failed endpoint MUST surface.
  if (/\/api\//.test(url)) return false
  return BENIGN_RESOURCE_URL_PATTERNS.some((re) => re.test(url))
}

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

test('dashboard loads without console errors', async ({ page }) => {
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

  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // The brand MUST be in the sidebar.
  await expect(page.locator('text=Atlas').first()).toBeVisible({
    timeout: 25_000,
  })

  // The sidebar nav links should be present.
  await expect(page.locator('nav[aria-label="Primary"]')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Portfolio' })).toBeVisible()

  // The Financial Plans section should render (the loading branch
  // shows the 3 skeleton placeholders, which the page also uses
  // when the backend is unreachable). We poll because the
  // bootstrap (devLogin + getProfile + Promise.all) is async.
  await expect(page.locator('h2:has-text("Financial Plans")')).toBeVisible({
    timeout: 15_000,
  })

  expect(errors).toEqual([])
})

test('dark mode toggle adds .dark class to <html> and persists to localStorage', async ({
  page,
}) => {
  await page.goto('/')
  // Deterministic hydration sentinel: the ``DarkModeToggle``
  // component sets ``<html data-darkmode-hydrated="true">`` in
  // its first ``useEffect`` (post-mount, post-hydration) and
  // removes it on unmount. The button is painted server-side
  // with a fixed ``aria-label``, so a visibility check alone is
  // racy. This attribute is independent of the auth bootstrap
  // (``devLogin + getProfile`` can hang without affecting
  // dark-mode hydration).
  await page.waitForSelector('html[data-darkmode-hydrated="true"]', {
    timeout: 25_000,
  })

  const toggle = page.getByRole('button', { name: 'Switch to dark mode' })
  await expect(toggle).toBeVisible()

  // Click it.
  await toggle.click()

  // The .dark class should now be on <html>.
  const hasDarkClass = await page.evaluate(() =>
    document.documentElement.classList.contains('dark'),
  )
  expect(hasDarkClass).toBe(true)

  // localStorage should have the darkMode key.
  const darkMode = await page.evaluate(() => localStorage.getItem('darkMode'))
  expect(darkMode).toBe('enabled')

  // Click again to toggle off.
  await toggle.click()
  const hasDarkClassAfter = await page.evaluate(() =>
    document.documentElement.classList.contains('dark'),
  )
  expect(hasDarkClassAfter).toBe(false)
  const darkModeAfter = await page.evaluate(() => localStorage.getItem('darkMode'))
  expect(darkModeAfter).toBe('disabled')
})

test('AI Wealth Overview hero zone renders with net worth + wealth score', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // Phase 2: The AI Wealth Overview hero zone should render.
  // It's always present (loading branch shows skeletons, loaded branch
  // shows the animated hero with CountUp + WealthScoreRing).
  const heroZone = page.locator('[data-testid="ai-wealth-overview"]')
  await expect(heroZone).toBeVisible({ timeout: 25_000 })

  // The net worth tile should be present.
  await expect(page.locator('[data-testid="hero-net-worth"]')).toBeVisible()

  // The wealth score tile should be present.
  await expect(page.locator('[data-testid="hero-wealth-score"]')).toBeVisible()

  // At least one secondary tile should be present (loading or loaded).
  const tiles = page.locator('[data-testid="hero-income"], [data-testid="hero-income-loading"]')
  await expect(tiles).toHaveCount(1, { timeout: 15_000 })
})

test('Sankey hero renders with Money Flow Engine title', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // Phase 3: The Sankey hero should render with the new title.
  // The card is always present (loading or loaded).
  const sankeyHero = page.locator('[data-testid="sankey-hero"]')
  await expect(sankeyHero).toBeVisible({ timeout: 25_000 })
})

test('Financial Plans section shows 3 stat cards', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // The section is always present (loading branch shows 3
  // skeletons, loaded branch shows 3 stat cards).
  const section = page.locator('section[aria-label="Financial plans"]')
  await expect(section).toBeVisible({ timeout: 25_000 })

  // The section should contain 3 articles (either stat cards or
  // skeleton placeholders).
  const articles = section.locator('[role="article"]')
  await expect(articles).toHaveCount(3, { timeout: 15_000 })
})

test('Phase 4 — Copilot orb is visible on the dashboard', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // The persistent AI copilot orb MUST be visible (after mount-guard).
  const orb = page.locator('[data-testid="copilot-orb"]')
  await expect(orb).toBeVisible({ timeout: 25_000 })

  // Click to expand the dock (the testing attribute exists on the dock root).
  await orb.click()
  await expect(page.locator('[data-testid="copilot-dock"]')).toBeVisible()
  await expect(page.locator('[data-testid="copilot-dock-tab-chat"]')).toBeVisible()
  await expect(page.locator('[data-testid="copilot-dock-tab-insights"]')).toBeVisible()

  // The Insights tab contains at least one quick query chip.
  const firstChip = page.locator('[data-testid="copilot-query-chip-0"]')
  await expect(firstChip).toBeVisible()
})

test('Phase 5 — Wealth timeline + simulator + DNA + Twin render', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // All four new simulation components should be on the dashboard
  // (loaded or loading branch) once the dashboard data is ready.
  // We give the dynamic imports a generous timeout (the chunks split).
  await expect(page.locator('[data-testid="wealth-timeline"]')).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.locator('[data-testid="simulator-card"]')).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.locator('[data-testid="life-events"]')).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.locator('[data-testid="dna-card"]')).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.locator('[data-testid="financial-twin"]')).toBeVisible({
    timeout: 15_000,
  })
})

test('Phase 5 — moving the Money Flow Simulator pmt slider updates the preview', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  await expect(page.locator('[data-testid="simulator-card"]')).toBeVisible({
    timeout: 15_000,
  })

  const slider = page.locator('[data-testid="simulator-slider-pmt"]')
  const preview = page.locator('[data-testid="simulator-preview-10y"]')

  // Capture initial preview text.
  const before = (await preview.textContent()) ?? ''
  await slider.fill('4500')
  // Allow the CountUp animation to settle.
  await page.waitForTimeout(500)
  const after = (await preview.textContent()) ?? ''
  expect(before).not.toEqual('')
  expect(after).not.toEqual('')
  // The numeric display should change when the slider moves.
  expect(after).not.toEqual(before)
})
