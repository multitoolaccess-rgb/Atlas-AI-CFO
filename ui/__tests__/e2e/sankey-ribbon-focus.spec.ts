import { test, expect } from '@playwright/test'

/**
 * Regression coverage for two Sankey / focus-mode defects:
 *
 * 1. Horizontal ribbon invisibility — link strokes are painted with
 *    `url(#sankey-grad-*)` gradients. Gradients in the default
 *    `objectBoundingBox` units are degenerate for perfectly horizontal
 *    links (y0 === y1 → zero-height bbox), so the browser paints
 *    nothing. The gradients must use `gradientUnits="userSpaceOnUse"`
 *    with coordinates following the link's endpoints.
 *
 * 2. Focus-mode overlap — the floating range bar is pinned `fixed` at
 *    `top: 4.5rem` while a chart is in focus mode. The page's `space-y`
 *    sibling margin must not push it down onto the focused content, and
 *    the focus layer's top padding must clear the bar.
 */

const flows = {
  nodes: [
    { name: 'Base Salary', node_type: 'income', color: '#059669', role: 'earn', group: 'Income', level: 0 },
    { name: 'Total Income', node_type: 'income', color: '#059669', role: 'earn', group: 'Income', level: 1 },
    { name: 'Expenses', node_type: 'expense', color: '#DC2626', role: 'spend', group: 'Expenses', level: 2 },
    { name: 'Debt', node_type: 'expense', color: '#F59E0B', role: 'spend', group: 'Debt', level: 2 },
    { name: 'Investments', node_type: 'expense', color: '#0EA5E9', role: 'spend', group: 'Investments', level: 2 },
    { name: 'Retained', node_type: 'outcome', color: '#6366F1', role: 'save', level: 2 },
    { name: 'Overspend', node_type: 'outcome', color: '#F59E0B', role: 'spend', level: 0 },
    { name: 'Uncategorized', node_type: 'expense', color: '#DC2626', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Credit Card Payments', node_type: 'expense', color: '#F59E0B', role: 'spend', group: 'Debt', level: 3 },
    { name: 'Mortgage', node_type: 'expense', color: '#dc2626', role: 'spend', group: 'Debt', level: 3 },
    { name: 'Transportation', node_type: 'expense', color: '#ea580c', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Bills & Utilities', node_type: 'expense', color: '#f97316', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Life Insurance', node_type: 'expense', color: '#b91c1c', role: 'spend', group: 'Debt', level: 3 },
    { name: 'Loan Payments', node_type: 'expense', color: '#991b1b', role: 'spend', group: 'Debt', level: 3 },
    { name: 'Shopping', node_type: 'expense', color: '#a855f7', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Brokerage Buys', node_type: 'expense', color: '#8b5cf6', role: 'spend', group: 'Investments', level: 3 },
    { name: 'Travel', node_type: 'expense', color: '#ec4899', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Interest Paid', node_type: 'expense', color: '#f87171', role: 'spend', group: 'Debt', level: 3 },
    { name: 'Groceries', node_type: 'expense', color: '#eab308', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Food & Dining', node_type: 'expense', color: '#0ea5e9', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Housing', node_type: 'expense', color: '#3b82f6', role: 'spend', group: 'Expenses', level: 3 },
    { name: 'Education', node_type: 'expense', color: '#ef4444', role: 'spend', group: 'Expenses', level: 3 },
  ],
  // This dataset is constructed so the large Expenses → Uncategorized link
  // (52,150 of 84,628 Expenses) lays out perfectly horizontal (y0 === y1):
  // its source slice center aligns with the Uncategorized bar center. That
  // zero-height geometry is exactly what used to make its gradient invisible.
  links: [
    { source: 0, target: 1, value: 122534 },
    { source: 6, target: 1, value: 114396 },
    { source: 1, target: 2, value: 84628 },
    { source: 1, target: 3, value: 84275 },
    { source: 1, target: 4, value: 1200 },
    { source: 2, target: 7, value: 52150 },
    { source: 3, target: 8, value: 48718 },
    { source: 3, target: 9, value: 23906 },
    { source: 2, target: 10, value: 19578 },
    { source: 2, target: 11, value: 10538 },
    { source: 3, target: 12, value: 8519 },
    { source: 3, target: 13, value: 2848 },
    { source: 2, target: 14, value: 1354 },
    { source: 4, target: 15, value: 1200 },
    { source: 2, target: 16, value: 463 },
    { source: 3, target: 17, value: 285 },
    { source: 2, target: 18, value: 241 },
    { source: 2, target: 19, value: 199 },
    { source: 2, target: 20, value: 80 },
    { source: 2, target: 21, value: 25 },
  ],
  period_start: '2026-01-01',
  period_end: '2026-09-04',
  total_income: 122534,
}

async function mockCashFlow(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/dashboard/flows**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(flows) }),
  )
  for (const url of [
    '**/api/v1/dashboard/summary**',
    '**/api/v1/dashboard/trends**',
    '**/api/v1/dashboard/breakdown**',
    '**/api/v1/transactions**',
    '**/api/v1/categories**',
  ]) {
    await page.route(url, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
    )
  }
  await page.goto('/cash-flow')
  await expect(page.getByTestId('sankey-hero')).toBeVisible({ timeout: 25000 })
  // Let the entrance animations (draw-on delay up to ~2s) finish.
  await page.waitForTimeout(3500)
}

test('horizontal Sankey ribbons use flow-aligned user-space gradients', async ({ page }) => {
  await mockCashFlow(page)

  const result = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg')
    if (!svg) return { error: 'no sankey svg' }
    const grads = Array.from(svg.querySelectorAll('linearGradient[id^="sankey-grad-"]'))
    const bad = grads
      .filter((g) => g.getAttribute('gradientUnits') !== 'userSpaceOnUse')
      .map((g) => g.id)
    // Confirm this dataset actually exercises the degenerate geometry: at
    // least one link whose path bbox has zero height (perfectly horizontal).
    const links = Array.from(svg.querySelectorAll('#sankey-links > g'))
    let horizontalCount = 0
    for (const g of links) {
      const p = g.querySelector('[id^="sankey-link-path-"]') as SVGGraphicsElement | null
      if (!p) continue
      let h = -1
      try { h = p.getBBox().height } catch { /* noop */ }
      if (h === 0) horizontalCount++
    }
    return { gradCount: grads.length, badGradients: bad, horizontalLinks: horizontalCount }
  })

  expect(result.error).toBeUndefined()
  expect(result.gradCount).toBeGreaterThan(0)
  // Regression: every gradient must be userSpaceOnUse so horizontal
  // (zero-height bbox) ribbons resolve instead of painting nothing.
  expect(result.badGradients).toEqual([])
  // And this fixture must genuinely contain a horizontal link, or the
  // test would silently stop covering the bug.
  expect(result.horizontalLinks).toBeGreaterThan(0)
})

test('dense category columns keep income bars legible (adaptive padding)', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockCashFlow(page)

  const heights = await page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll('#sankey-nodes > g'))
    const get = (label: string) => {
      const g = nodes.find((n) => (n.querySelector('text')?.textContent ?? '').startsWith(label))
      const r = g?.querySelector('rect')
      if (!r) return -1
      // Layout units (viewBox), independent of the container's render scale.
      return Number(r.getAttribute('height'))
    }
    return { baseSalary: get('Base Salary'), overspend: get('Overspend') }
  })

  // Regression: 15 category nodes × 24px gaps used to collapse the global
  // scale to ~26px for Base Salary (24px in layout units for Overspend).
  // The adaptive padding budget must keep the biggest income flows clearly
  // visible in layout units (>120px in this fixture).
  expect(heights.baseSalary).toBeGreaterThan(120)
  expect(heights.overspend).toBeGreaterThan(120)
})

test('focus mode fits the whole chart in the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockCashFlow(page)

  await page.getByTestId('dashboard-focus-toggle').first().click()
  await page.waitForTimeout(500)

  const state = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg') as SVGSVGElement | null
    if (!svg) return { error: 'no svg' }
    const s = svg.getBoundingClientRect()
    return {
      viewportH: window.innerHeight,
      svgTop: s.top,
      svgBottom: s.bottom,
      svgHeight: s.height,
      // Pixels of the chart that fall below the visible viewport (must be 0).
      hiddenBelowFold: Math.max(0, s.bottom - window.innerHeight),
      // getComputedStyle resolves calc() to px; 'none' means no cap applied.
      maxHeight: getComputedStyle(svg).maxHeight,
    }
  })

  expect(state.error).toBeUndefined()
  // The chart is height-capped to the viewport (computed resolves to px)…
  expect(state.maxHeight).not.toBe('none')
  // …so the full diagram is visible without scrolling.
  expect(state.hiddenBelowFold!).toBe(0)
  expect(state.svgBottom!).toBeLessThanOrEqual(state.viewportH!)
})

test('focus mode pins the range bar clear of the focused chart', async ({ page }) => {
  await mockCashFlow(page)

  await page.getByTestId('dashboard-focus-toggle').first().click()
  await page.waitForTimeout(400)

  const state = await page.evaluate(() => {
    const barEl = document.querySelector('[data-testid="floating-time-range-bar"]')
    const sankey = document.querySelector('[data-testid="sankey-hero"]')
    if (!barEl || !sankey) return { error: 'missing elements' }
    const bar = barEl.getBoundingClientRect()
    const card = sankey.getBoundingClientRect()
    const cs = getComputedStyle(barEl)
    return {
      barTop: bar.top,
      barBottom: bar.bottom,
      cardTop: card.top,
      position: cs.position,
      marginTop: cs.marginTop,
      overlapPx: Math.max(0, bar.bottom - card.top),
      focusLayerActive: document.documentElement.classList.contains('dashboard-focus-active'),
    }
  })

  expect(state.error).toBeUndefined()
  expect(state.focusLayerActive).toBe(true)
  // The bar is promoted to a fixed viewport control…
  expect(state.position).toBe('fixed')
  // …ignores the page's space-y sibling margin (which used to push it
  // 24px down onto the chart)…
  expect(state.marginTop).toBe('0px')
  // …and never covers the focused chart.
  expect(state.overlapPx!).toBe(0)
  expect(state.barBottom!).toBeLessThanOrEqual(state.cardTop!)
})