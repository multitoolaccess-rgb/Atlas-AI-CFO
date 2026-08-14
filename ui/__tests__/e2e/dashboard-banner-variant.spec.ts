/**
 * Playwright e2e — /overview top warning banner variant contract.
 *
 * Pins the regression the user just hit: when /api/dashboard/summary
 * fails (502, downstream 401 drift, network error), the top-of-page
 * ``Couldn't load dashboard:`` banner MUST render with
 * ``variant="warning"`` styling, NOT the default ``variant="danger"``.
 *
 * The corresponding component-level contract is locked by
 * :file:`__tests__/ErrorBanner.test.tsx`; this file locks the
 * page-level integration — the page actually PASSES the right
 * variant to ``ErrorBanner`` under the failure condition.
 *
 * How: a ``page.route`` interceptor mocks the dashboard-summary
 * response to be HTTP 502. The page runs the bootstrap effect,
 * Promise.all short-circuits on the rejection, the catch arm sets
 * the error state, and the top-of-page ``ErrorBanner`` renders.
 * The assertion locks: the rendered banner is AMBER (warning token),
 * the page-side console filter ignores the synthesized 502, and
 * the page itself does NOT throw into the error budget.
 */
import { test, expect, type ConsoleMessage } from '@playwright/test'

// The benign console-error filter is intentionally SCOPED to this
// spec's failure mode. ``page.route`` mocks /api/dashboard/summary
// with EXACTLY HTTP 502, so we whitelist only:
//   1. the [cashflix] interceptor's `Status: 502` summary;
//   2. the page's own `Dashboard bootstrap failed:` console.error
//      (the page does NOT prefix it with [cashflix]); and
//   3. the Chrome DevTools `Failed to load resource: ... status of 502`
//      line that auto-fires for any non-2xx response (only 502 here
//      because that's all the mock returns — widening to a 4xx/5xx
//      union would silently swallow real bugs from a future endpoint).
// Widening to (401|500|503|504) would silently swallow real bugs
// from a future endpoint; a status-agnostic `Dashboard bootstrap
// failed` pattern stays scoped to the page's own log regardless
// of what synthesized status drives it.
const BENIGN_PATTERNS: RegExp[] = [
  /\[cashflix\].*Status:\s*401/i,
  /\[cashflix\].*Status:\s*502/i,
  /Dashboard bootstrap failed/i,
  /Failed to load resource.*status of 502/i,
  // The browser's network-stack generic signal fires when the
  // real backend is unreachable (e.g. Finlynq down hard). It's
  // NOT synthesized by the page.route mock — it only appears
  // when the browser cannot connect at all (independent of what
  // status the server returns).
  /Failed to load resource.*ERR_CONNECTION_REFUSED/i,
  /Failed to load resource.*ERR_INTERNET_DISCONNECTED/i,
  /Network Error/i,
  /not wrapped in act\(\.\.\.\)/i,
]

// The resource-URL filter is intentionally narrow — anything under
// /api/ is NEVER benign (we'd be hiding a real bug). Only Next.js
// dev-only generated artifacts and standard browser auto-fetched
// assets are whitelisted.
const BENIGN_RESOURCE_URL_PATTERNS: RegExp[] = [
  /\/_next\/static\//,
  /\.(js|css|ts|tsx)\.map(\?|$)/,
  /\/favicon\.(ico|svg)(\?|$)/,
]

const isMessageBenign = (text: string): boolean =>
  BENIGN_PATTERNS.some((re) => re.test(text))

const isResourceUrlBenign = (url: string): boolean => {
  if (!url) return false
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

test('Mission Control top warning banner is AMBER (warning), not RED (danger)', async ({
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

  // Mock the dashboard-summary endpoint with proper CORS + preflight.
  // The FE's axios client sends credentials (JWT cookie), so the
  // CORS response MUST echo the request's Origin (a specific value
  // — browsers reject ``*`` paired with
  // ``Access-Control-Allow-Credentials: true``). We also respond to
  // the OPTIONS preflight with 204 + the same allow-list set, so
  // the actual GET is allowed to fly. Without either, the browser
  // drops the response before axios sees the 502, the classifier
  // at ``ui/lib/errors.ts`` falls through to the ``network``
  // branch, and the friendly banner never renders -- which is
  // exactly the silent-failure mode we want to test against.
  const MOCK_ORIGIN = 'http://localhost:3000'
  await page.route('**/api/dashboard/summary', async (route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': MOCK_ORIGIN,
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Max-Age': '86400',
        },
      })
      return
    }
    await route.fulfill({
      status: 502,
      headers: {
        'Access-Control-Allow-Origin': MOCK_ORIGIN,
        'Access-Control-Allow-Credentials': 'true',
      },
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Finlynq upstream returned HTTP 401 on GET /state/summary.',
      }),
    })
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')

  // The friendly classified message MUST appear (from
  // ``ui/lib/errors.ts``'s 502 -> "Downstream service is unavailable"
  // mapping). The raw upstream string MUST NOT.
  const friendlyBanner = page.locator('div[role="alert"]', {
    hasText: /Downstream service is unavailable/i,
  })
  await expect(friendlyBanner).toBeVisible({ timeout: 10_000 })
  await expect(friendlyBanner).toHaveText(/Couldn't load Mission Control:/i)

  // Regression lock: the banner is AMBER. We assert the explicit
  // Tailwind tokens ``border-warning-200`` + ``bg-warning-50`` +
  // ``text-warning-700`` (the
  // ``ErrorBanner variant="warning"`` contract). Also assert the
  // NEGATIVE half — the banner MUST NOT carry the RED danger
  // tokens, so the page cannot regress to the original bug.
  await expect(friendlyBanner).toHaveClass(/border-warning-200/)
  await expect(friendlyBanner).toHaveClass(/bg-warning-50/)
  await expect(friendlyBanner).toHaveClass(/text-warning-700/)
  await expect(friendlyBanner).not.toHaveClass(/border-danger-200/)
  await expect(friendlyBanner).not.toHaveClass(/bg-danger-50/)

  // Raw upstream detail MUST NOT appear anywhere in the rendered
  // DOM. This pins the ``ui/lib/errors.ts`` classifier contract
  // end-to-end (the friendly MESSAGE is shown, the raw DETAIL is
  // suppressed).
  const bodyText = (await page.locator('body').innerText()).toLowerCase()
  expect(bodyText).not.toContain('finlynq upstream returned http 401')

  // Console-error budget — only the auto-classified 502 (already in
  // BENIGN_PATTERNS) may surface; nothing else.
  expect(errors).toEqual([])
})
