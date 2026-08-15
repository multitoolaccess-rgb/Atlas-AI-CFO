/**
 * Frontend-owned navigation smoke test.
 *
 * This deliberately does not start Rules Service, Finlynq, OCR, or the live
 * stack. The page shell and System routes own this behavior; unavailable API
 * responses are mocked so the test proves navigation, URL state, and honest
 * degraded rendering without installing unrelated service environments.
 */
import { test, expect } from '@playwright/test'

async function installFrontendMocks(page: import('@playwright/test').Page) {
  await page.route('**/health', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' }),
  )
  await page.route('**/api/**', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Synthetic route-mocked response' }),
    }),
  )
}

async function openApp(page: import('@playwright/test').Page, path = '/') {
  await page.goto(`${path}${path.includes('?') ? '&' : '?'}skip-splash=1`)
  await page.waitForLoadState('domcontentloaded')
  await expect(page.locator('nav[aria-label="Primary"]')).toBeVisible()
}

test.describe('System navigation without the live stack', () => {
  test.beforeEach(async ({ page }) => {
    await installFrontendMocks(page)
  })

  test('opens Data Connections and preserves tab URL state', async ({ page }) => {
    await openApp(page)

    await page.getByRole('link', { name: 'Data Connections', exact: true }).click()
    await page.waitForURL('**/data-connections')
    await expect(page.getByRole('heading', { name: 'Data Connections', level: 1 })).toBeVisible()

    await page.getByRole('tab', { name: 'Imports', exact: true }).click()
    await expect(page).toHaveURL(/\/data-connections\?view=imports/)
    await expect(page.locator('[data-testid="imports-tab-panel"]')).toBeVisible()

    await page.getByRole('tab', { name: 'Data quality', exact: true }).press('ArrowLeft')
    await page.getByRole('tab', { name: 'Data quality', exact: true }).click()
    await expect(page.locator('[data-testid="data-quality-tab-panel"]')).toBeVisible()
  })

  test('keeps the legacy Accounts bookmark on Data Connections', async ({ page }) => {
    await openApp(page, '/accounts?tab=all')
    const redirected = new URL(page.url())
    expect(redirected.pathname).toBe('/data-connections')
    expect(redirected.searchParams.get('tab')).toBe('all')
    expect(redirected.searchParams.get('view')).toBe('accounts')
    await expect(page.getByRole('heading', { name: 'Data Connections', level: 1 })).toBeVisible()
    await expect(page.locator('[data-testid="accounts-tab-panel"]')).toBeVisible()
  })

  test('navigates Settings and Help with an unavailable source state', async ({ page }) => {
    await openApp(page)

    await page.getByRole('link', { name: 'Settings', exact: true }).click()
    await page.waitForURL('**/settings')
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()

    await page.getByRole('link', { name: 'Help', exact: true }).click()
    await page.waitForURL('**/help')
    await expect(page.getByRole('heading', { name: 'Help', level: 1 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Recovery and privacy', level: 2 })).toBeVisible()
  })
})
