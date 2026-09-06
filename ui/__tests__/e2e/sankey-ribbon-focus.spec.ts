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

test('small-node labels never overlap in dense columns', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockCashFlow(page)

  const result = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg')
    if (!svg) return { error: 'no svg' }
    const texts = Array.from(svg.querySelectorAll('#sankey-nodes text')).map((t) => {
      const r = t.getBoundingClientRect()
      return {
        text: (t.textContent ?? '').slice(0, 30),
        left: r.left, right: r.right, top: r.top, bottom: r.bottom,
        parentId: t.closest('g')?.id ?? '',
      }
    })
    const overlaps: string[] = []
    let maxOverlapH = 0
    for (let i = 0; i < texts.length; i++) {
      for (let j = i + 1; j < texts.length; j++) {
        const a = texts[i], b = texts[j]
        if (a.parentId === b.parentId) continue
        const interW = Math.min(a.right, b.right) - Math.max(a.left, b.left)
        const interH = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
        if (interW > 1 && interH > 1) {
          maxOverlapH = Math.max(maxOverlapH, interH)
          if (interH >= 4) overlaps.push(`${a.text} ⟷ ${b.text} (${interH.toFixed(1)}px)`)
        }
      }
    }
    return { textCount: texts.length, overlapCount: overlaps.length, maxOverlapH, overlaps: overlaps.slice(0, 6) }
  })

  expect(result.error).toBeUndefined()
  // Regression: stacked name/value lines used to collide once adaptive
  // padding packed dense columns together (34 collisions, up to 9px deep).
  // Single combined lines must never overlap by more than ~3px — that is
  // only the font's empty ascender/descender metric box (the app font's
  // line box is ~1.5em), which does not touch the visible glyphs.
  expect(result.overlapCount).toBe(0)
  expect(result.maxOverlapH!).toBeLessThan(4)
})

test('every category node keeps a visible label in dense columns', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockCashFlow(page)

  const result = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg')
    if (!svg) return { error: 'no svg' }
    const rendered = Array.from(svg.querySelectorAll('#sankey-nodes text')).map((t) => t.textContent ?? '')
    const expected = ['Uncategorized', 'Credit Card Payments', 'Mortgage', 'Transportation', 'Bills & Utilities', 'Life Insurance', 'Loan Payments', 'Shopping', 'Brokerage Buys', 'Travel', 'Interest Paid', 'Groceries', 'Food & Dining', 'Housing', 'Education']
    const missing = expected.filter((name) => !rendered.some((t) => t.includes(name)))
    return { renderedCount: rendered.length, expectedCount: expected.length, missing }
  })

  expect(result.error).toBeUndefined()
  // Regression: sub-8px bars used to hide their label entirely (hover
  // only), which made several categories impossible to identify. Every
  // category must now be labeled, even the tiny tail bars.
  expect(result.missing).toEqual([])
})

test('every node label sits on the side of its bar with one consistent color', async ({ page }) => {
  await mockCashFlow(page)

  const result = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg')
    if (!svg) return { error: 'no svg' }
    // Inline labels used to live INSIDE the bar (textAnchor=middle, centered
    // over the 14px bar, straddling ribbons). Side labels are start-anchored
    // at the bar's right edge.
    const middleAnchored = Array.from(svg.querySelectorAll('#sankey-nodes text[text-anchor="middle"]')).length
    const side = Array.from(svg.querySelectorAll('#sankey-nodes text[text-anchor="start"]'))
    const fills = new Set(side.map((t) => getComputedStyle(t).fill))
    return {
      middleCount: middleAnchored,
      sideCount: side.length,
      nodeCount: svg.querySelectorAll('#sankey-nodes > g').length,
      distinctFills: Array.from(fills),
    }
  })

  expect(result.error).toBeUndefined()
  // Regression: large bars used to carry white centered text ON the bar next
  // to dark side labels for small bars — a visually mixed "inline over the
  // chart" + "beside the bar" scheme, with text straddling ribbons and
  // colliding with neighbors. Every node must now render exactly one label on
  // the side of its bar, and all labels share one theme color (no white/black
  // split by bar fill).
  expect(result.middleCount!).toBe(0)
  expect(result.sideCount!).toBe(result.nodeCount!)
  expect(result.distinctFills!.length).toBe(1)
})

test('side labels never overlap and stay inside the chart in dense columns', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 })
  await mockCashFlow(page)

  const result = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg')
    if (!svg) return { error: 'no svg' }
    const sr = svg.getBoundingClientRect()
    const texts = Array.from(svg.querySelectorAll('#sankey-nodes text')).map((t) => {
      const r = t.getBoundingClientRect()
      return {
        txt: (t.textContent ?? '').slice(0, 30),
        left: r.left, right: r.right, top: r.top, bottom: r.bottom,
        parentId: t.closest('g')?.id ?? '',
      }
    })
    const overlaps: string[] = []
    for (let i = 0; i < texts.length; i++) {
      for (let j = i + 1; j < texts.length; j++) {
        const a = texts[i], b = texts[j]
        if (a.parentId === b.parentId) continue
        const interW = Math.min(a.right, b.right) - Math.max(a.left, b.left)
        const interH = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
        if (interW > 1 && interH > 1) overlaps.push(`${a.txt} ⟷ ${b.txt}`)
      }
    }
    // The longest last-column label ("Credit Card Payments · $48,718") used
    // to run past the viewBox's right edge and clip at the card boundary.
    const outside = texts.filter((t) => t.right > sr.right + 2 || t.left < sr.left - 2).map((t) => t.txt)
    return { textCount: texts.length, overlaps, outside }
  })

  expect(result.error).toBeUndefined()
  expect(result.textCount!).toBeGreaterThan(0)
  expect(result.overlaps!).toEqual([])
  expect(result.outside!).toEqual([])
})

test('focused Sankey shows an in-card range selector and hides the floating bar', async ({ page }) => {
  await mockCashFlow(page)

  await page.getByTestId('dashboard-focus-toggle').first().click()
  await page.waitForTimeout(400)

  const state = await page.evaluate(() => {
    const barEl = document.querySelector('[data-testid="floating-time-range-bar"]')
    const cardSel = document.querySelector('[data-testid="sankey-hero"] [role="radiogroup"]')
    const layer = document.querySelector('[data-testid="dashboard-focus-layer"]')
    const sankey = document.querySelector('[data-testid="sankey-hero"]')
    if (!layer || !sankey) return { error: 'missing elements' }
    const card = sankey.getBoundingClientRect()
    return {
      floatingBarHidden: barEl ? getComputedStyle(barEl).display === 'none' : true,
      inCardSelectorVisible: !!cardSel && cardSel.getBoundingClientRect().height > 0,
      // The selector sits INSIDE the card (normal flow), so it can never
      // be occluded by the focused layer.
      selectorInsideCard: !!cardSel,
      focusLayerActive: document.documentElement.classList.contains('dashboard-focus-active'),
      sankeyFocusClass: document.documentElement.classList.contains('dashboard-focus-sankey'),
      cardTop: card.top,
    }
  })

  expect(state.error).toBeUndefined()
  expect(state.focusLayerActive).toBe(true)
  expect(state.sankeyFocusClass).toBe(true)
  // The floating bar is replaced by the card's own selector in focus mode…
  expect(state.floatingBarHidden).toBe(true)
  expect(state.inCardSelectorVisible).toBe(true)
  // …and the card reclaims the reserved top space (selector sits at the
  // top of the layer, not below a 160px reserved band).
  expect(state.cardTop!).toBeLessThan(80)
})

test('hovering a node never hides or blurs any label', async ({ page }) => {
  await mockCashFlow(page)

  // Hover the Uncategorized category node — the flow the user reported:
  // its label "disappeared" (dimmed with its group) and the hovered
  // node's own label was smeared by the glow halo.
  const node = page.getByRole('option', { name: /^Uncategorized,/ })
  await node.hover()
  await page.waitForTimeout(300)

  const state = await page.evaluate(() => {
    const svg = document.querySelector('#sankey-links')?.closest('svg')
    if (!svg) return { error: 'no svg' }
    const texts = Array.from(svg.querySelectorAll('#sankey-nodes text'))
    const hidden = texts
      .map((t) => {
        const opacity = Number(getComputedStyle(t).opacity)
        const parentStyle = (t.closest('g') as SVGElement | null)?.getAttribute('style') ?? ''
        return {
          label: (t.textContent ?? '').slice(0, 24),
          opacity,
          // If the parent group carried the glow filter, the label text
          // would inherit the blur (stdDeviation 3 smears 10–12px words).
          blurred: parentStyle.includes('filter'),
        }
      })
      .filter((t) => t.opacity < 0.65 || t.blurred)
    return { textCount: texts.length, hidden }
  })

  expect(state.error).toBeUndefined()
  // Regression: node hover used to dim the whole <g> — every disconnected
  // label dropped to 0.3 (nearly invisible on the dark canvas) — and the
  // glow filter applied to the group, blurring the hovered node's own
  // label. Labels must now stay ≥ 0.65 and never sit inside a filtered
  // group.
  expect(state.textCount!).toBeGreaterThan(0)
  expect(state.hidden!).toEqual([])
})

test('changing the range inside focused Sankey refetches that range', async ({ page }) => {
  await mockCashFlow(page)

  await page.getByTestId('dashboard-focus-toggle').first().click()
  await page.waitForTimeout(400)

  // The in-card selector reflects the current range…
  await expect(page.locator('[data-testid="sankey-hero"] [role="radiogroup"]')).toBeVisible()
  // …clicking a pill updates the URL-synced range while staying focused.
  await page.locator('[data-testid="sankey-hero"] [role="radiogroup"] button', { hasText: '90D' }).click()
  await page.waitForTimeout(300)
  expect(page.url()).toContain('range=90D')
  await expect(page.locator('[data-testid="dashboard-focus-layer"]')).toBeVisible()
})