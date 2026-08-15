import { test, expect } from '@playwright/test'
import { mkdirSync } from 'fs'
import { resolve } from 'path'

test.describe('Atlas v2.1 screenshot evidence', () => {
  test('captures route inventory and representative archetype matrix', async ({ page }) => {
    test.setTimeout(600_000)
    const root = resolve(process.cwd(), 'artifacts/v2.1')
    mkdirSync(root, { recursive: true })

    const routes = [
      ['overview', '/'],
      ['budgeting', '/budgeting'],
      ['income', '/income'],
      ['expenses', '/expenses'],
      ['debts', '/debts'],
      ['universe', '/universe'],
      ['portfolio', '/portfolio'],
      ['goals', '/goals'],
      ['recommendations', '/recommendations'],
      ['activity', '/activity'],
      ['market-briefs', '/market-briefs'],
      ['data-connections', '/data-connections'],
      ['settings', '/settings'],
      ['help', '/help'],
      ['assistant', '/assistant'],
    ] as const

    const setAppearance = async (mode: 'light' | 'dark', accent: 'indigo' | 'vermilion' | 'ion') => {
      await page.evaluate(({ mode, accent }) => {
        localStorage.setItem('atlas_theme_mode', mode)
        localStorage.setItem('atlas_accent_profile', accent)
      }, { mode, accent })
      await page.reload({ waitUntil: 'networkidle' })
      await expect(page.locator('#main-content')).toBeVisible({ timeout: 15_000 })
      await expect(page.locator('#main-content h1').first()).toBeVisible({ timeout: 15_000 })
      await expect(page.locator('html')).toHaveAttribute('data-atlas-theme', mode)
      await expect(page.locator('html')).toHaveAttribute('data-atlas-accent', accent)
    }

    // Every navigable route gets an Indigo light/dark desktop capture.
    for (const [slug, route] of routes) {
      await page.goto(route, { waitUntil: 'networkidle' })
      await setAppearance('light', 'indigo')
      await page.screenshot({ path: resolve(root, `${slug}-indigo-light-1440.png`), fullPage: false })
      await setAppearance('dark', 'indigo')
      await page.screenshot({ path: resolve(root, `${slug}-indigo-dark-1440.png`), fullPage: false })
    }

    // Representative archetypes receive the full six-combination desktop
    // matrix plus mobile/tablet captures. The screenshots use real route
    // states; they do not seed or fabricate financial values.
    const representative = [
      ['overview', '/'],
      ['budgeting', '/budgeting'],
      ['portfolio', '/portfolio'],
      ['goals', '/goals'],
      ['market-briefs', '/market-briefs'],
      ['settings', '/settings'],
    ] as const
    const profiles = [
      ['indigo', 'light'],
      ['indigo', 'dark'],
      ['vermilion', 'light'],
      ['vermilion', 'dark'],
      ['ion', 'light'],
      ['ion', 'dark'],
    ] as const
    const viewports = [
      ['390', { width: 390, height: 844 }],
      ['768', { width: 768, height: 900 }],
      ['1440', { width: 1440, height: 1000 }],
    ] as const

    for (const [slug, route] of representative) {
      await page.goto(route, { waitUntil: 'networkidle' })
      for (const [accent, mode] of profiles) {
        await setAppearance(mode, accent)
        await page.screenshot({ path: resolve(root, `${slug}-${accent}-${mode}-1440.png`), fullPage: false })
      }
      for (const [accent, mode] of profiles) {
        for (const [width, viewport] of viewports) {
          await page.setViewportSize(viewport)
          await setAppearance(mode, accent)
          await page.screenshot({ path: resolve(root, `${slug}-${accent}-${mode}-${width}.png`), fullPage: false })
        }
      }
      await page.setViewportSize({ width: 1440, height: 1000 })
    }
  })
})
