/**
 * Icon-consistency regression spec (frontend-owned, no live stack).
 *
 * Guards the reported UI bug: the app previously relied on the Material
 * Symbols webfont, but the font was never loaded, so every
 * `material-symbols-outlined` span rendered its name as literal text —
 * `expand_more` on every shared Select dropdown and `account_balance` /
 * `upload_file` / `sync` / `fact_check` on the Data Connections tabs.
 *
 * The fix replaces those font spans with lucide-react SVG icons, which
 * render deterministically offline. This spec pins that contract:
 *   1. Tab icons are real inline SVGs.
 *   2. Every shared Select chevron is an SVG sibling of the <select>.
 *   3. No Material icon literal ever appears in page text on the
 *      affected routes.
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

// Exact Material Symbol tokens the broken font spans used to render.
const MATERIAL_ICON_LITERALS = ['expand_more', 'account_balance', 'upload_file', 'fact_check']

test.describe('Icon consistency without the live stack', () => {
  test.beforeEach(async ({ page }) => {
    await installFrontendMocks(page)
  })

  test('Data Connections tab icons render as SVGs, never as literal Material names', async ({ page }) => {
    await openApp(page)

    await page.getByRole('link', { name: 'Data Connections', exact: true }).click()
    await page.waitForURL('**/data-connections')
    await expect(page.getByRole('heading', { name: 'Data Connections', level: 1 })).toBeVisible()

    for (const tabName of ['Accounts', 'Imports', 'Synchronization', 'Data quality']) {
      await expect(
        page.getByRole('tab', { name: tabName, exact: true }).locator('svg'),
      ).toBeVisible()
    }

    const bodyText = await page.locator('body').innerText()
    for (const token of MATERIAL_ICON_LITERALS) {
      expect(bodyText, `literal "${token}" must not render`).not.toContain(token)
    }
    // "sync" only as a standalone Material token — never as a page word.
    expect(bodyText).not.toMatch(/\bsync\b/)
  })

  test('every shared Select chevron is an SVG and no expand_more literal renders', async ({ page }) => {
    await openApp(page)
    await page.getByRole('link', { name: 'Settings', exact: true }).click()
    await page.waitForURL('**/settings')
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()

    // The shared Select renders <select> followed by a lucide ChevronDown
    // <svg> in the same relative wrapper. Every rendered select must have
    // its SVG chevron sibling; zero selects is vacuously valid.
    const selects = page.locator('select')
    const chevrons = page.locator('select ~ svg')
    await expect(chevrons).toHaveCount(await selects.count())

    const bodyText = await page.locator('body').innerText()
    expect(bodyText).not.toContain('expand_more')
  })

  test('no Material icon literal renders on any primary route', async ({ page }) => {
    for (const path of ['/', '/data-connections', '/settings', '/cash-flow', '/plan?view=budget', '/scenario-lab']) {
      await openApp(page, path)
      const bodyText = await page.locator('body').innerText()
      for (const token of MATERIAL_ICON_LITERALS) {
        expect(bodyText, `literal "${token}" on ${path}`).not.toContain(token)
      }
      // NB: prose legitimately uses "sync" (e.g. "now in sync"), so only
      // the exact Material icon tokens are swept on primary routes; the
      // standalone-sync guard lives on the Data Connections page where the
      // literal used to render as a tab icon.
    }
  })
})
