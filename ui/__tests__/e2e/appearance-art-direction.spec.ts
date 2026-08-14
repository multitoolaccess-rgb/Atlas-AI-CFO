import { test, expect } from '@playwright/test'
import { readFileSync } from 'fs'

test.describe('Atlas art direction appearance matrix', () => {
  test('uses the resolved primary UI font and avoids accidental serif rendering', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByTestId('appearance-section')).toBeVisible({ timeout: 10_000 })

    const fontState = await page.locator('body').evaluate((body) => {
      const computed = getComputedStyle(body)
      const primary = computed.getPropertyValue('--font-primary').trim()
      return { computedFamily: computed.fontFamily, primary }
    })

    expect(fontState.primary).not.toBe('')
    const primaryFamily = fontState.primary.split(',')[0].trim().replace(/[\"']/g, '')
    expect(fontState.computedFamily).toContain(primaryFamily)
    expect(fontState.computedFamily).not.toMatch(/Times|Georgia/i)
  })

  test('keeps profile identity independent from light and dark mode', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByTestId('appearance-section')).toBeVisible({ timeout: 10_000 })

    for (const mode of ['light', 'dark'] as const) {
      for (const accent of ['indigo', 'vermilion', 'ion'] as const) {
        await page.getByTestId(`appearance-mode-${mode}`).click()
        await page.getByTestId(`appearance-accent-${accent}`).click()
        await expect(page.getByTestId(`appearance-mode-${mode}`)).toHaveAttribute('aria-checked', 'true')
        await expect(page.getByTestId(`appearance-accent-${accent}`)).toHaveAttribute('aria-checked', 'true')
        await expect(page.locator('html')).toHaveAttribute('data-atlas-theme', mode)
        await expect(page.locator('html')).toHaveAttribute('data-atlas-accent', accent)
        const surfaceState = await page.evaluate(() => {
          const root = getComputedStyle(document.documentElement)
          const body = getComputedStyle(document.body)
          const probes = ['surface-ambient', 'surface-working', 'surface-focal'].map((role) => {
            const node = document.createElement('div')
            node.className = role
            document.body.appendChild(node)
            const style = getComputedStyle(node)
            const background = style.backgroundColor
            node.remove()
            return { role, background, border: style.borderTopColor, shadow: style.boxShadow }
          })
          return {
            canvas: root.getPropertyValue('--canvas-base').trim(),
            working: root.getPropertyValue('--surface-working').trim(),
            focal: root.getPropertyValue('--surface-focal').trim(),
            atmosphere: root.getPropertyValue('--atmosphere-primary').trim(),
            semanticPositive: root.getPropertyValue('--signal-positive').trim(),
            semanticNegative: root.getPropertyValue('--signal-negative').trim(),
            bodyBackground: body.backgroundColor,
            probes,
          }
        })
        expect(surfaceState.canvas).not.toBe('')
        expect(surfaceState.working).not.toBe(surfaceState.canvas)
        expect(surfaceState.focal).not.toBe(surfaceState.working)
        expect(surfaceState.atmosphere).toContain('rgb')
        expect(surfaceState.semanticPositive).not.toBe(surfaceState.atmosphere)
        expect(surfaceState.semanticNegative).not.toBe(surfaceState.atmosphere)
        expect(surfaceState.bodyBackground).not.toBe('rgb(255, 255, 255)')
        expect(surfaceState.probes.map((probe) => probe.role)).toEqual([
          'surface-ambient',
          'surface-working',
          'surface-focal',
        ])
        expect(surfaceState.probes[1].background).not.toBe(surfaceState.probes[2].background)
      }
    }
  })

  test('shell, Settings, and Plan have no serious or critical axe violations', async ({ page }) => {
    const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8')
    for (const route of ['/settings', '/plan?view=budget']) {
      await page.goto(route)
      await expect(page.locator('#main-content')).toBeVisible({ timeout: 10_000 })
      if (route === '/settings') {
        await expect(page.getByTestId('appearance-section')).toBeVisible({ timeout: 10_000 })
      } else {
        await expect(page.locator('h1', { hasText: 'Plan' })).toBeVisible({ timeout: 10_000 })
      }
      await page.addScriptTag({ content: axeSource })
      const axeResult = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: (root: Element) => Promise<{ violations: Array<{ id: string; impact?: string | null }> }> } }).axe
        return axe.run(document.documentElement)
      })
      expect(axeResult.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical'), route).toEqual([])
    }
  })

  test('decorative Plan budget motion becomes static under reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/plan?view=budget')
    await expect(page.getByTestId('budget-orbit')).toBeVisible({ timeout: 10_000 })
    const animationNames = await page.locator('[data-testid="budget-orbit"] span').evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node).animationName),
    )
    expect(animationNames.every((name) => name === 'none')).toBe(true)
  })

  test('Plan stays within the viewport at supported widths', async ({ page }) => {
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 768, height: 900 },
      { width: 1024, height: 900 },
      { width: 1440, height: 1000 },
      { width: 1728, height: 1000 },
    ]) {
      await page.setViewportSize(viewport)
      await page.goto('/plan?view=budget')
      await expect(page.locator('h1', { hasText: 'Plan' })).toBeVisible({ timeout: 10_000 })
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
      expect(overflow, `horizontal overflow at ${viewport.width}px`).toBe(false)
    }
  })
})
