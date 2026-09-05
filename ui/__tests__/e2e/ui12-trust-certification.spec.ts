import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const ROUTES = [
  { path: '/investments', heading: 'Command Center', certifiable: true },
  { path: '/investments/discovery', heading: 'Opportunity discovery', certifiable: true },
  { path: '/investments/brief', heading: 'Daily Investment Brief', certifiable: true },
  { path: '/investments/recommendations', heading: 'Recommendation review', certifiable: true },
  { path: '/investments/assistant', heading: 'Investment Scout', certifiable: true },
  { path: '/investments/scout', heading: 'Investment Context Scout', certifiable: true },
  { path: '/investments/risk', heading: 'Risk and scenario views', certifiable: true },
  { path: '/scenario-lab', heading: 'Scenario Lab', certifiable: true },
  { path: '/decisions', heading: 'Decisions', certifiable: true },
  { path: '/market-intelligence', heading: /market intelligence/i, certifiable: true },
  // /portfolio is certifiable as of GAP-10/11/12: the 390px overflow was
  // fixed (responsive hero grid), mutation controls are gated behind an
  // explicit manage mode (read-only by default), and all portfolio
  // arithmetic moved to the server valuation projection.
  { path: '/portfolio', heading: 'Portfolio', certifiable: true },
] as const

const SUPPORTED_WIDTHS = [390, 768, 1024, 1440, 1728] as const
const ROUTE_LOAD_BUDGET_MS = 10_000
const MAX_API_RESPONSE_BYTES = 512 * 1024
// GAP-14 — interaction CPU budget. Long tasks (>50ms main-thread blocks)
// are collected during route load plus a bounded keyboard interaction;
// a healthy read-only surface stays under both bounds.
const INTERACTION_LONG_TASK_BUDGET = 4
const INTERACTION_CPU_BUDGET_MS = 600

type LongTaskRecord = { startTime: number; duration: number }

async function installLongTaskMonitor(page: Page) {
  await page.addInitScript(() => {
    const tasks: LongTaskRecord[] = []
    ;(window as unknown as { __ui12LongTasks: LongTaskRecord[] }).__ui12LongTasks = tasks
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          tasks.push({ startTime: entry.startTime, duration: entry.duration })
        }
      }).observe({ type: 'longtask', buffered: false })
    } catch {
      // LongTask timing API unavailable — the budget is trivially met.
    }
  })
}

async function measuredInteractionCpu(page: Page): Promise<{ count: number; totalMs: number }> {
  const tasks = await page.evaluate(() =>
    (window as unknown as { __ui12LongTasks?: LongTaskRecord[] }).__ui12LongTasks ?? [])
  return {
    count: tasks.length,
    totalMs: Math.round(tasks.reduce((sum, task) => sum + task.duration, 0)),
  }
}

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
    await installLongTaskMonitor(page)
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
      // GAP-14 — bounded interaction: two more focus moves, then assert
      // the main-thread interaction CPU budget.
      await page.keyboard.press('Tab')
      await page.keyboard.press('Tab')
      const interactionCpu = await measuredInteractionCpu(page)
      expect(interactionCpu.count, `${route.path} interaction CPU long-task count`).toBeLessThanOrEqual(INTERACTION_LONG_TASK_BUDGET)
      expect(interactionCpu.totalMs, `${route.path} interaction CPU budget`).toBeLessThanOrEqual(INTERACTION_CPU_BUDGET_MS)

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

  test('keeps the included read-only inventory overflow-free at every supported width', async ({ page }) => {
    for (const width of SUPPORTED_WIDTHS) {
      await page.setViewportSize({ width, height: 900 })
      for (const route of ROUTES) {
        if (!route.certifiable) continue
        await openRoute(page, route.path)
        const layout = await page.evaluate(() => {
          const clientWidth = document.documentElement.clientWidth
          const overflowing = Array.from(document.querySelectorAll<HTMLElement>('#main-content *'))
            .map((element) => ({
              tag: element.tagName,
              className: element.className,
              right: Math.round(element.getBoundingClientRect().right),
              width: Math.round(element.getBoundingClientRect().width),
            }))
            .filter((item) => item.right > clientWidth)
            .sort((left, right) => right.right - left.right)
            .slice(0, 5)
          return {
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth,
            overflowing,
          }
        })
        expect(layout.scrollWidth, `${route.path} at ${width}px horizontal overflow: ${JSON.stringify(layout.overflowing)}`).toBeLessThanOrEqual(layout.clientWidth)
      }
    }
  })
})
