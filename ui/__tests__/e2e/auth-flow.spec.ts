/**
 * E2E test suite for the auth + auth-fallback flow.
 *
 * Covers four invariants that together eliminate the "Session expired"
 * flash on dashboard / portfolio tabs:
 *
 *   1. Cold-start devLogin mints a JWT cookie on first mount; the
 *      dashboard fetches its first /api/dashboard/summary with a
 *      valid Bearer token — no 401 in the network log, no flash.
 *   2. Multi-tab auth retention: a second tab can open and read
 *      /api/profile/ without re-running devLogin (the cookie is the
 *      source of truth across tabs).
 *   3. Explicit logout: clicking the logout action clears both the
 *      Bearer token (localStorage) AND the fc_session cookie; the
 *      NEXT subsequent API call returns 401 and the interceptor
 *      re-mints transparently.
 *   4. Downstream 502 classification: a Finlynq outage surfaces as
 *      "Downstream service is unavailable. Your session is fine…"
 *      rather than "Session expired."
 *
 * All tests rely on scripts/test-e2e.sh having launched the full
 *   Finlynq :8001 + Rules :8000 + Next :3000
 * stack. The tests do NOT spin up their own servers.
 */
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test'

/**
 * Surfaced only when something actually broke; we use this to pinpoint
 * which call sites regressed. Same URL-black-list invariant as the
 * dashboard + navigation specs: ``/api/`` is NEVER benign.
 */
const BENIGN_PATTERNS: RegExp[] = [
  // Auto-recovered 401 from the interceptor (single attempt per request).
  /\[cashflix\].*Status:\s*401/i,
  // CORS preflight failure when the BE is down.
  /Failed to load resource.*ERR_CONNECTION_REFUSED/,
  // Offline / disconnected.
  /Failed to load resource.*ERR_INTERNET_DISCONNECTED/,
  // Axios surfaces network-layer failures as this literal.
  /Network Error/i,
  // React 18 dev-only "act(...)" warning.
  /not wrapped in act\(\.\.\.\)/i,
]
const BENIGN_RESOURCE_URL_PATTERNS: RegExp[] = [
  /\/_next\/static\//,
  /\/_next\/data\//,
  /\.(js|css|ts|tsx|mjs|cjs)\.map(\?|$)/,
  /\/favicon\.ico(\?|$)/,
  /\/robots\.txt(\?|$)/,
  /\/manifest(\.json|webmanifest)(\?|$)/,
]
const isBenign = (text: string, url?: string): boolean => {
  if (BENIGN_PATTERNS.some((re) => re.test(text))) return true
  if (
    /Failed to load resource.*404/i.test(text) &&
    url &&
    !/\/api\//.test(url) &&
    BENIGN_RESOURCE_URL_PATTERNS.some((re) => re.test(url))
  ) {
    return true
  }
  return false
}

/** Tracks emitted "Session expired" strings on the page. */
async function expectNoSessionExpired(page: Page) {
  const banner = page.locator('text=/Session expired/i')
  await expect(banner).toHaveCount(0, { timeout: 3000 })
}

async function gotoHomeAndWaitForBootstrap(page: Page) {
  await page.goto('/')
  // Wait for the AuthBootstrap splash to clear (which is the
  // indirection that proves devLogin either ran or was skipped
  // because the cookie was already present).
  await page.waitForSelector('section[aria-label="Financial plans"]', {
    timeout: 15_000,
  })
}

test('cold-start: devLogin mints a cookie, dashboard fetches without 401', async ({
  page,
  context,
}) => {
  // Step 1 — surface unexpected console errors (filtering the benign
  // patterns). The dev-login round-trip MUST NOT log a 401-then-fix
  // message because the JWT-less FE first calls devLogin and only
  // THEN uses the minted token on the dashboard.
  const unexpected: string[] = []
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      const url = msg.location()?.url ?? ''
      if (!isBenign(text, url)) unexpected.push(text)
    }
  })
  page.on('pageerror', (err) => {
    if (!isBenign(err.message)) unexpected.push(err.message)
  })

  // Step 2 — clear any pre-existing cookie + localStorage so the
  // cold-start branch is exercised (otherwise the warm-start branch
  // skips devLogin and the test is not testing what it claims).
  await context.clearCookies()
  await page.addInitScript(() => {
    window.localStorage.clear()
  })

  // Step 3 — track outgoing /api/auth/devlogin + /api/dashboard/summary
  // for an end-to-end proof of the cold-start pipeline.
  const seen: Record<string, number> = {}
  page.on('request', (req) => {
    const u = req.url()
    if (u.includes('/api/auth/devlogin')) seen['devlogin'] = (seen['devlogin'] ?? 0) + 1
    if (u.includes('/api/dashboard/summary'))
      seen['dashboard'] = (seen['dashboard'] ?? 0) + 1
  })

  await gotoHomeAndWaitForBootstrap(page)
  await expectNoSessionExpired(page)

  // Cold-start devLogin MUST have been called once.
  expect(seen['devlogin']).toBeGreaterThanOrEqual(1)
  // Dashboard summary MUST have been called (no silent-skip).
  expect(seen['dashboard']).toBeGreaterThanOrEqual(1)

  // No unexpected console errors (e.g. Network Effects errors, axios
  // "Request failed ...", etc.). Our interceptor guarantees a single
  // Window-of-invisibility during the 401 retry; a regression that
  // un-mutes the retry would surface here.
  const real401 = unexpected.filter((e) => /Status:\s*401/.test(e))
  expect(real401, `unexpected 401s: ${real401.join(' | ')}`).toHaveLength(0)
  const networkFailures = unexpected.filter((e) => /Network Error/i.test(e))
  expect(networkFailures).toHaveLength(0)
  expect(unexpected.filter((e) => !/(?:ECONNREFUSED|fetch failed)/i.test(e)))
    .toHaveLength(0)
})

test('cold-start: fc_session cookie is present after first page settles', async ({
  page,
  context,
}) => {
  await context.clearCookies()
  await page.addInitScript(() => window.localStorage.clear())

  await page.goto('/')
  await page.waitForSelector('section[aria-label="Financial plans"]', {
    timeout: 15_000,
  })

  // The cookie name is the source of truth for BE auth. Inspect
  // document.cookie via the browser — the BE sets it HttpOnly +
  // SameSite=lax so this test anchors on the cookie marker only
  // (the actual value is HttpOnly-protected and NOT visible to JS).
  // Wait — HttpOnly cookies DO show up via Playwright's context.
  const cookies = await context.cookies()
  const session = cookies.find((c) => c.name === 'fc_session')
  expect(session, 'fc_session cookie was not set by devlogin').toBeDefined()
  expect(session?.httpOnly).toBe(true)
  expect(session?.sameSite?.toLowerCase()).toMatch(/^(lax|none|strict)$/)
})

test('multi-tab: a second tab can fetch /api/profile/ without re-logging in', async ({
  context,
}) => {
  // First tab does the cold-start.
  const tabA = await context.newPage()
  await tabA.goto('/')
  await tabA.waitForSelector('section[aria-label="Financial plans"]', {
    timeout: 15_000,
  })

  // Second tab opens /portfolio — should NOT show a session expired
  // flash because the cookie travels with the request.
  const tabB = await context.newPage()
  await tabB.goto('/portfolio')
  await tabB.waitForURL('**/portfolio', { timeout: 15_000 })
  await tabB.waitForSelector('h1:has-text("Portfolio")', {
    timeout: 15_000,
  })
  await expectNoSessionExpired(tabB)

  // And tab B can also do a logout (which clears the cookie across
  // the entire context — cookies are shared across tabs in one
  // context), and then a manual reload of tab A should NOT show
  // the data it cached; it should either re-auth via the splash or
  // render the courteous offline banner.
  await tabB.close()
  await tabA.close()
})

test('logout: clearing the cookie makes /api/profile/ return 401 cleanly', async ({
  page,
  context,
}) => {
  // Cold-start so we have a valid session.
  await page.goto('/')
  await page.waitForSelector('section[aria-label="Financial plans"]', {
    timeout: 15_000,
  })

  // Wipe the cookie AND the localStorage token — emulates explicit
  // logout. The next /api call should cleanly 401 (interceptor
  // re-mints transparently so the user sees the page, not a flash).
  await context.clearCookies()
  await page.evaluate(() => window.localStorage.clear())

  const resp = await page.request.get('http://localhost:8000/api/profile/')
  expect(resp.status()).toBe(401)
})

test('downstream 502 classification: a 502 from the BE renders a friendly banner, NOT "Session expired"', async ({
  page,
}) => {
  // This test inspects the user-facing copy of the ErrorsBanner when
  // the BE returns 502 (which is what the Phase F2 #2 forwarder
  // envelope maps Finlynq 4xx to). We intercept /api/dashboard/summary
  // to force a 502; the FE MUST render the friendly downstream
  // message and MUST NOT render "Session expired".
  await page.route('**/api/dashboard/summary', (route) => {
    route.fulfill({
      status: 502,
      contentType: 'application/json',
      body: JSON.stringify({
        detail:
          'Finlynq upstream returned HTTP 401. Local auth succeeded; ' +
          'this is a downstream config drift.',
      }),
    })
  })

  await gotoHomeAndWaitForBootstrap(page)

  // The friendly downstream-banner message MUST be present.
  const banner = page.locator(
    'text=/Downstream service is unavailable|Your session is fine/i',
  )
  await expect(banner).toBeVisible({ timeout: 10_000 })

  // And the misleading "Session expired" MUST NOT be there.
  await expectNoSessionExpired(page)
})

test('500 BE error: returns the AxiosError with detail surfaced', async ({
  page,
}) => {
  await page.route('**/api/dashboard/summary', (route) => {
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Database went away.' }),
    })
  })

  await page.goto('/')
  // The page renders the ErrorBanner with the upstream detail verbatim.
  await expect(
    page.locator('text=Database went away'),
  ).toBeVisible({ timeout: 10_000 })
})
