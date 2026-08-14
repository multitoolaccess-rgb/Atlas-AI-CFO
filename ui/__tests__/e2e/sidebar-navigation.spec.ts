import { test, expect, type Page } from '@playwright/test'

function captureErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' && !/Network Error|Status:\s*401/i.test(message.text())) errors.push(message.text())
  })
  return errors
}

test('consolidated sidebar exposes only active Money destinations and header Scout fallback', async ({ page }) => {
  const errors = captureErrors(page)
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Mission Control' })).toHaveAttribute('href', '/')
  await expect(page.getByRole('link', { name: 'Cash Flow' })).toHaveAttribute('href', '/cash-flow')
  await expect(page.getByRole('link', { name: 'Plan' })).toHaveAttribute('href', '/plan')
  await expect(page.getByTestId('header-scout-link')).toHaveAttribute('href', '/assistant')
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByText('Income', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByText('Budgeting', { exact: true })).toHaveCount(0)
  expect(errors).toEqual([])
})

test.describe('legacy Money URLs', () => {
  const cases = [
    ['/income?range=YTD&search=salary', /\/cash-flow\?range=YTD&search=salary&view=income/, 'Income'],
    ['/expenses?range=30D&account=all', /\/cash-flow\?range=30D&account=all&view=spending/, 'Spending'],
    ['/activity?range=MTD&search=coffee', /\/cash-flow\?range=MTD&search=coffee&view=transactions/, 'Transactions'],
    ['/budgeting?range=YTD&period=2026-08', /\/plan\?range=YTD&period=2026-08&view=budget/, 'Budget'],
  ] as const

  for (const [legacy, target, tab] of cases) {
    test(`${legacy} redirects without losing query state`, async ({ page }) => {
      await page.goto(legacy)
      await expect(page).toHaveURL(target)
      await expect(page.getByTestId('page-tabs').getByRole('button', { name: tab })).toHaveAttribute('aria-current', 'page')
      await expect(page.getByRole('radiogroup', { name: 'Time range' })).toHaveCount(tab === 'Budget' ? 0 : 1)
      if (tab === 'Budget') await expect(page.locator('input[type="month"]')).toHaveValue('2026-08')
    })
  }
})

test('Cash Flow tabs preserve range state and have one current sidebar destination', async ({ page }) => {
  await page.goto('/cash-flow?range=YTD&view=overview')
  await page.getByRole('button', { name: 'Income' }).click()
  await expect(page).toHaveURL(/\/cash-flow\?range=YTD&view=income/)
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Cash Flow' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Activity' })).not.toHaveAttribute('aria-current', 'page')
})

test('Money destinations remain keyboard accessible and do not overflow at supported widths', async ({ page }) => {
  for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 900 }, { width: 1440, height: 1000 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/cash-flow?view=overview')
    await expect(page.getByRole('navigation', { name: 'Page views' })).toBeVisible()
    await page.getByRole('button', { name: 'Overview' }).press('ArrowRight')
    await expect(page.getByRole('button', { name: 'Income' })).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${viewport.width}px overflow`).toBe(true)
  }
})
