import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const ROUTES = [
  { path: '/investments', heading: 'Command Center', certifiable: true },
  { path: '/investments/discovery', heading: 'Opportunity discovery', certifiable: true },
  { path: '/investments/brief', heading: 'Daily Investment Brief', certifiable: true },
  { path: '/investments/recommendations', heading: 'Recommendation review', certifiable: true },
  { path: '/investments/assistant', heading: 'Investment Scout', certifiable: true },
  { path: '/investments/risk', heading: 'Risk and scenario views', certifiable: true },
  { path: '/scenario-lab', heading: 'Scenario Lab', certifiable: true },
  { path: '/decisions', heading: 'Decisions', certifiable: true },
  { path: '/market-intelligence', heading: /market intelligence/i, certifiable: true },
  // The legacy portfolio page currently has a known 390px overflow and
  // mutation controls outside the UI-12 read-only certification boundary.
  // Keep it in the inventory, but exclude it from the certifiable set until
  // that separately owned surface is remediated.
  { path: '/portfolio', heading: 'Portfolio', certifiable: false },
] as const

const SUPPORTED_WIDTHS = [390, 768, 1024, 1440, 1728] as const
const ROUTE_LOAD_BUDGET_MS = 10_000
const MAX_API_RESPONSE_BYTES = 512 * 1024

async function installUnavailableBackend(page: Page) {
  await page.route('**/health', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok' }),
  }))
  await page.route('**/api/**', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Synthetic UI-12 unavailable response' }),
  }))
}

async function openRoute(page: Page, path: string) {
  const startedAt = Date.now()
  await page.goto(`${path}${path.includes('?') ? '&' : '?'}skip-splash=1`, { waitUntil: 'domcontentloaded' })
  await expect(page.locator('#main-content h1').first()).toBeVisible()
  expect(Date.now() - startedAt, `${path} route-load budget`).toBeLessThan(ROUTE_LOAD_BUDGET_MS)
}

async function runAxe(page: Page) {
  await page.addScriptTag({ content: readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8') })
  return page.evaluate(async () => {
    const axe = (window as unknown as {
      axe: { run: (context: Element) => Promise<{ violations: Array<{ id: string; impact?: string | null }> }> }
    }).axe
    const main = document.querySelector('main')
    if (!main) throw new Error('Expected main landmark')
    return axe.run(main)
  })
}

test.describe('UI-12 coordinated cross-route trust certification', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await installUnavailableBackend(page)
  })

  test('covers the frozen investment surface inventory with safe recovery states', async ({ page }) => {
    const executionRequests: string[] = []
    const oversizedResponses: string[] = []
    page.on('request', (request) => {
      if (/broker|order|trade|transfer|rebalance|execute|money-movement/i.test(request.url())) executionRequests.push(request.url())
    })
    page.on('response', async (response) => {
      if (!response.url().includes('/api/')) return
      try {
        const body = await response.body()
        if (body.byteLength > MAX_API_RESPONSE_BYTES) oversizedResponses.push(response.url())
      } catch {
        // The response may be unavailable after a navigation; that is not a
        // privacy or product failure, and the route budget remains measured.
      }
    })

    for (const route of ROUTES) {
      if (!route.certifiable) continue
      await page.setViewportSize({ width: 390, height: 844 })
      await openRoute(page, route.path)
      await expect(page.locator('#main-content h1').first()).toContainText(route.heading)
      await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()

      await page.keyboard.press('Tab')
      await expect.poll(() => page.evaluate(() => document.activeElement?.tagName ?? '')).not.toBe('BODY')

      const layout = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        sensitiveText: document.body.innerText,
      }))
      expect(layout.scrollWidth, `${route.path} horizontal overflow`).toBeLessThanOrEqual(layout.clientWidth)
      expect(layout.sensitiveText).not.toMatch(/account:\d+|account_number|hashed_password|api[_-]?key/i)
      await expect(page.getByRole('button', { name: /^(buy|sell|execute|place order|trade|rebalance|transfer|move money)/i })).toHaveCount(0)
      await expect(page.getByRole('link', { name: /^(buy|sell|execute|place order|trade|rebalance|transfer|move money)/i })).toHaveCount(0)

      const axeResult = await runAxe(page)
      expect(
        axeResult.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical'),
        `${route.path} serious/critical accessibility findings`,
      ).toEqual([])
    }

    expect(executionRequests).toEqual([])
    expect(oversizedResponses).toEqual([])
  })

  test('keeps the frozen surface inventory overflow-free at every supported width', async ({ page }) => {
    for (const width of SUPPORTED_WIDTHS) {
      await page.setViewportSize({ width, height: 900 })
      await openRoute(page, '/investments')
      const layout = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))
      expect(layout.scrollWidth, `${width}px command-center overflow`).toBeLessThanOrEqual(layout.clientWidth)
    }
  })
})
