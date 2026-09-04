import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

 test.describe('UI-10 Investment Scout', () => {
  test('renders an accessible, responsive read-only workspace', async ({ page }) => {
    const requests: string[] = []
    page.on('request', (request) => requests.push(request.url()))
    await page.goto('/investments/assistant')
    await expect(page.getByRole('main', { name: 'Investment Scout workspace' })).toBeVisible()
    await expect(page.getByLabel('Context type')).toBeVisible()
    await expect(page.getByLabel('Persisted context ID')).toBeVisible()
    await expect(page.getByText(/security, discovery, and portfolio selectors are not enabled/i)).toBeVisible()
    await expect(page.getByText(/cannot create recommendations/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /load context/i })).toBeDisabled()
    await expect(page.getByRole('button', { name: /ask scout/i })).toHaveCount(0)
    await expect(page.getByText(/JSON.stringify/i)).toHaveCount(0)
    expect(requests.some((url) => /broker|order|trade|transfer|rebalance/i.test(url))).toBe(false)

    await page.addScriptTag({ content: readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8') })
    const axeResults = await page.evaluate(async () => {
      const axe = (window as Window & { axe?: { run: () => Promise<{ violations: Array<{ impact?: string | null }> }> } }).axe
      return axe ? axe.run() : { violations: [] }
    })
    expect(axeResults.violations.some((violation) => violation.impact === 'critical' || violation.impact === 'serious')).toBe(false)

    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.getByRole('main', { name: 'Investment Scout workspace' })).toBeVisible()
    await page.waitForTimeout(350)
    const dimensions = await page.locator('#main-content').evaluate((element) => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
    expect(dimensions.scrollWidth <= dimensions.clientWidth, JSON.stringify(dimensions)).toBe(true)
  })
})
