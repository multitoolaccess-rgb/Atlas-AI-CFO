import { test, expect } from '@playwright/test'

/**
 * Phase 3 — Financial Universe smoke test.
 *
 * Verifies the /universe route loads without errors and renders its heading.
 * The full 3D scene is covered by Vitest unit tests; this E2E test only
 * checks route-level integration.
 */

async function bootstrapAuth(page: import('@playwright/test').Page): Promise<void> {
  // Call the devlogin endpoint directly to get a token, then inject it into
  // localStorage before the page loads so AuthBootstrapProvider skips its
  // loading splash.
  const response = await page.request.post('http://localhost:8000/api/auth/devlogin?sub=alex')
  expect(response.status(), 'devLogin should 200').toBe(200)
  const { token } = await response.json() as { token: string }

  await page.addInitScript((t) => {
    window.localStorage.setItem('fc_session_token', t)
  }, token)
}

test('universe route loads and shows heading', async ({ page }) => {
  page.on('pageerror', (err) => console.error('Page error:', err))
  page.on('console', (msg) => { if (msg.type() === 'error') console.error('Console error:', msg.text()) })

  await bootstrapAuth(page)
  await page.goto('/universe')
  await expect(page.locator('h1:has-text("Financial Universe")')).toBeVisible({ timeout: 15_000 })
})
