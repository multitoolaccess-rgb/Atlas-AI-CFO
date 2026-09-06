'use client'

import React, { useMemo, useState, useCallback, useRef } from 'react'
import { sankey, sankeyLinkHorizontal } from 'd3-sankey'
import type { SankeyNode as SankeyNodeType, SankeyLink as SankeyLinkType } from '@/lib/api'
import { useReducedMotion } from '@/lib/useReducedMotion'
import { useThemeMode } from '@/lib/useThemeMode'
import {
  DASHBOARD_COLORS,
  GRADIENT_SOURCE_COLORS,
  getDashboardColor,
  getGradientSourceColor,
} from '@/lib/themeColors'
import { formatCurrency } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SankeyFlowProps {
  nodes: SankeyNodeType[]
  links: SankeyLinkType[]
  /** Optional authoritative labels for nodes whose d3 layout value is
   *  intentionally balanced by synthetic links (e.g. Overspend). */
  displayValues?: Record<string, number>
  height?: number
  onNodeClick?: (nodeName: string) => void
  activeNode?: string | null
  /** In focus mode, cap the rendered height so the whole diagram fits the
   *  viewport (letterboxed via preserveAspectRatio) instead of overflowing. */
  fitViewport?: boolean
}

/** Augmented node type after d3-sankey layout injects geometry fields.
 *  Standalone interface — we do NOT extend the API types (which have fixed
 *  source/target shapes) so d3-sankey can mutate freely. */
interface DatumNode {
  name: string
  node_type: string
  color?: string | null
  role?: string | null
  group?: string | null
  level?: number | null
  index?: number
  x0?: number
  x1?: number
  y0?: number
  y1?: number
  value?: number
  depth?: number
  layer?: number
}

interface DatumLink {
  source: DatumNode | number
  target: DatumNode | number
  value: number
  width?: number
  y0?: number
  y1?: number
}

/** What the pointer is currently over: a link (by layout index) or a node
 *  (by name). One state drives the whole diagram so the highlight cannot
 *  flicker between adjacent elements. */
type HoverTarget = { kind: 'link'; index: number } | { kind: 'node'; name: string } | null

/* ---------------------------------------------------------------------------
 * d3-sankey type gymnastics:
 * The library's generics (SankeyNode<N,L>, SankeyLink<N,L>) are notoriously
 * hard to satisfy because they circle-reference each other. After layout,
 * source/target are mutated from indices to objects with x0/y0/y1 geometry.
 * We use `any` casts for the link path generator — safe because d3-sankey
 * guarantees these fields exist after layout.
 * --------------------------------------------------------------------------- */

// Theme-aware palettes now live in @/lib/themeColors (shared module).
// SankeyFlow imports DASHBOARD_COLORS, GRADIENT_SOURCE_COLORS, and the
// pure helpers (getDashboardColor, getGradientSourceColor, getTextColor,
// getTextSecondaryColor) from there.

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/* formatCurrency is imported from @/lib/format */

/** Resolve the canonical role key for a node (falls back to node_type). */
function getRoleKey(node: { role?: string | null; node_type?: string }): string {
  return (node.role ?? node.node_type ?? '').toLowerCase()
}

/** Phase C — group-aware color map for hierarchical Sankey nodes.
 *  Each group gets a primary color; the `color` field from the backend
 *  is used directly when present (it carries the per-subcategory hue). */
const _GROUP_NODE_COLORS: Record<string, string> = {
  Income: '#059669',
  Expenses: '#DC2626',
  Debt: '#F59E0B',
  Investments: '#0EA5E9',
  Transfer: '#64748b',
}

/** Map node_type values to DASHBOARD_COLORS keys. Sankey special
 *  node types (income, retained, overspend) use `_node` suffixed
 *  keys to avoid collision with trend series keys. */
function nodeColorKey(node: { role?: string | null; node_type?: string }): string {
  const key = getRoleKey(node)
  // These three node_types collide with trend series keys in DASHBOARD_COLORS
  if (key === 'income' || key === 'retained' || key === 'overspend') return `${key}_node`
  return key
}

/** Return the theme-appropriate fill color for a node.
 *  Phase C: prefers the node's explicit `color` field (set by the backend
 *  with per-subcategory hues), then falls back to group color, then role color. */
function getNodeFill(node: { color?: string | null; role?: string | null; node_type?: string; group?: string | null }, isDark: boolean): string {
  // 1. Use the backend-provided color directly (most specific)
  if (node.color && node.color.trim()) return node.color
  // 2. Fall back to group color
  if (node.group && _GROUP_NODE_COLORS[node.group]) return _GROUP_NODE_COLORS[node.group]
  // 3. Fall back to role/node_type color
  return getDashboardColor(nodeColorKey(node), isDark)
}

/** Return the gradient-source variant for a node (theme-aware). */
function getNodeGradientStart(node: { color?: string | null; role?: string | null; node_type?: string; group?: string | null }, isDark: boolean): string {
  // For gradient start, use a lighter version of the node color
  if (node.color && node.color.trim()) return node.color
  if (node.group && _GROUP_NODE_COLORS[node.group]) return _GROUP_NODE_COLORS[node.group]
  return getGradientSourceColor(getRoleKey(node), isDark)
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/** Compute the set of link indices connected to the hovered link
 *  (shares source or target node). Returns an empty set when nothing
 *  is hovered. Called once per render, reused across gradient defs,
 *  link rendering, and node rendering. */
function getConnectedSet(
  hoveredLink: number | null,
  computedLinks: DatumLink[],
): Set<number> {
  if (hoveredLink === null) return new Set()
  const hLink = computedLinks[hoveredLink]
  if (!hLink) return new Set()
  const hSrc = (hLink.source as DatumNode).name
  const hTgt = (hLink.target as DatumNode).name
  const connected = new Set<number>()
  for (let j = 0; j < computedLinks.length; j++) {
    const l = computedLinks[j]
    const s = (l.source as DatumNode).name
    const t = (l.target as DatumNode).name
    if (s === hSrc || s === hTgt || t === hSrc || t === hTgt) {
      connected.add(j)
    }
  }
  return connected
}

// The right margin is the reserved lane for the last column's side labels
// (every node label sits to the right of its bar). 180px fits most labels,
// but the longest realistic one — "Credit Card Payments · $48,718" at 12px
// — measures ~176 viewBox px and used to clip past the viewBox edge; 200px
// keeps even that label fully inside the drawing.
const SANKEY_MARGIN = { top: 8, right: 200, bottom: 16, left: 24 }

/** Default gap between node bars. Sparse columns keep this comfortable
 *  spacing; dense columns trade it for node size (see adaptive padding
 *  below). */
const DEFAULT_NODE_PADDING = 24

/** Fraction of the layout height a single column may spend on padding at
 *  most. d3-sankey sizes every node with ONE global scale bound by the
 *  tightest column, so a dense column with generous gaps consumes the whole
 *  height and collapses every bar to a sliver (e.g. 15 nodes × 24px = 336px
 *  of padding in a 396px layout). Capping the padding budget per column
 *  keeps node bars — and therefore the global scale — legible. */
const MAX_COLUMN_PADDING_FRACTION = 0.3

/** Absolute floor for the node gap. Side labels sit on the page background
 *  next to each bar at the bar's vertical center, so the pitch between
 *  adjacent label baselines can never be smaller than the node padding
 *  (zero-height tail bars are exactly `padding` apart). Without this floor
 *  a dense column's adaptive padding falls to ~8.5px and 10–12px words on
 *  neighboring bars overlap. 13px keeps ~2px of true glyph clearance at
 *  the 10px tiny-bar font while preserving legible bar heights. */
const MIN_NODE_PADDING = 13

const SankeyFlow = React.memo(function SankeyFlow({ nodes, links, displayValues, height = 440, onNodeClick, activeNode, fitViewport }: SankeyFlowProps) {
  const reducedMotion = useReducedMotion()
  const isDark = useThemeMode()
  // Single hover target for the whole diagram. Keeping one state avoids the
  // enter/leave flicker between adjacent links and nodes: the highlight is
  // only cleared when the pointer leaves the entire SVG.
  const [hovered, setHovered] = useState<HoverTarget>(null)
  const [focusedNode, setFocusedNode] = useState<number | null>(null)
  const nodeRefs = useRef<(SVGGElement | null)[]>([])
  const width = 960
  const validLinks = useMemo(
    () => links.filter((link) =>
      Number.isFinite(link.value) &&
      link.value > 0 &&
      Number.isInteger(link.source) &&
      Number.isInteger(link.target) &&
      link.source >= 0 &&
      link.source < nodes.length &&
      link.target >= 0 &&
      link.target < nodes.length,
    ),
    [links, nodes.length],
  )

  // Stable callbacks for hover handlers (avoids inline arrow allocation per link)
  const handleLinkEnter = useCallback((i: number) => setHovered({ kind: 'link', index: i }), [])
  const handleNodeEnter = useCallback((name: string) => setHovered({ kind: 'node', name }), [])
  // The highlight is cleared only when the pointer leaves the whole diagram,
  // never when it moves between adjacent links/nodes (which caused flicker).
  const handleHoverLeave = useCallback(() => setHovered(null), [])
  const margin = SANKEY_MARGIN

  // d3-sankey mutates input — deep clone inside useMemo
  const { computedNodes, computedLinks } = useMemo(() => {
    if (!nodes.length || !validLinks.length) {
      return { computedNodes: [] as DatumNode[], computedLinks: [] as DatumLink[] }
    }

    const clone = (): { nodes: DatumNode[]; links: DatumLink[] } => ({
      nodes: nodes.map((n, i) => ({
        name: n.name,
        node_type: n.node_type,
        color: n.color,
        role: n.role,
        group: n.group,
        level: n.level,
        index: i,
      })),
      links: validLinks.map(l => ({
        source: l.source,
        target: l.target,
        value: l.value,
      })),
    })

    const makeLayout = (padding: number) =>
      sankey<DatumNode, DatumLink>()
        .nodeId((d) => d.index!)
        .nodeWidth(14)
        .nodePadding(padding)
        .extent([
          [SANKEY_MARGIN.left, SANKEY_MARGIN.top],
          [width - SANKEY_MARGIN.right, height - SANKEY_MARGIN.bottom],
        ])

    // Pass 1: run the layout with default padding just to learn d3's own
    // column assignment (layer), then count nodes per column. Padding only
    // affects y geometry, so pass 1's columns are authoritative.
    const pass1 = clone()
    makeLayout(DEFAULT_NODE_PADDING)({ nodes: pass1.nodes, links: pass1.links })
    const counts = new Map<number, number>()
    for (const node of pass1.nodes) {
      const layer = node.layer ?? node.depth ?? 0
      counts.set(layer, (counts.get(layer) ?? 0) + 1)
    }
    const maxColumnLength = Math.max(1, ...Array.from(counts.values()))
    const innerHeight = height - SANKEY_MARGIN.top - SANKEY_MARGIN.bottom
    // Cap each column's padding budget (so dense columns can't crush the
    // global scale), but NEVER below the label-legibility floor: side labels
    // sit at each bar's vertical center, and zero-height tail bars end up
    // exactly `padding` apart, so the padding is also the minimum pitch
    // between adjacent words. 13px keeps ~3px of true glyph clearance at the
    // 10px tiny-bar font.
    const adaptivePadding = Math.min(
      DEFAULT_NODE_PADDING,
      Math.max(
        MIN_NODE_PADDING,
        (innerHeight * MAX_COLUMN_PADDING_FRACTION) / Math.max(1, maxColumnLength - 1),
      ),
    )

    // Pass 2: real layout with the adaptive padding.
    const pass2 = clone()
    const { nodes: sn, links: sl } = makeLayout(adaptivePadding)({
      nodes: pass2.nodes,
      links: pass2.links,
    })
    return { computedNodes: sn, computedLinks: sl }
  }, [nodes, validLinks, width, height])

  const transition = reducedMotion ? 'none' : 'opacity 150ms ease-out'
  const borderStroke = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'

  // Compute the connected link set once per render for hover highlighting.
  const connectedSet = useMemo(() => {
    if (!hovered) return new Set<number>()
    if (hovered.kind === 'link') return getConnectedSet(hovered.index, computedLinks)
    // Node hover: every link touching the hovered node is connected.
    const name = hovered.name
    const set = new Set<number>()
    for (let j = 0; j < computedLinks.length; j++) {
      const link = computedLinks[j]
      if ((link.source as DatumNode).name === name || (link.target as DatumNode).name === name) set.add(j)
    }
    return set
  }, [hovered, computedLinks])

  // Node names that stay bright while something is hovered: for link hover
  // the source and target of that link; for node hover every node sharing a
  // link with the hovered node, so the whole flow path stays visible.
  const connectedNodeNames = useMemo(() => {
    if (!hovered) return new Set<string>()
    if (hovered.kind === 'node') {
      const names = new Set<string>()
      for (const j of connectedSet) {
        const link = computedLinks[j]
        names.add((link.source as DatumNode).name)
        names.add((link.target as DatumNode).name)
      }
      return names
    }
    const hLink = computedLinks[hovered.index]
    if (!hLink) return new Set<string>()
    return new Set<string>([(hLink.source as DatumNode).name, (hLink.target as DatumNode).name])
  }, [hovered, connectedSet, computedLinks])

  if (!nodes.length || !validLinks.length) {
    return (
      <div className="flex items-center justify-center h-[400px] text-[var(--text-tertiary)]">
        <div className="text-center">
          <p className="text-sm font-medium mb-1">No flow data yet</p>
          <p className="text-xs">Upload a statement to see your money flow.</p>
        </div>
      </div>
    )
  }

  // Pre-compute the path generator. d3-sankey's types are circular and
  // hard to satisfy; the `any` cast is safe — layout guarantees geometry.
  const linkPath = sankeyLinkHorizontal<any, any>()

  return (
    <div
      className="w-full"
      role="figure"
      aria-label="Money flow Sankey diagram showing income sources, spending allocations, and outcomes"
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{
          overflow: 'visible',
          // Focus mode: cap the rendered height to the viewport (minus the
          // card chrome and legend — the Sankey focus layer no longer
          // reserves space for the floating bar, which is hidden in favor
          // of the card's own range selector) so the whole diagram is
          // visible without scrolling. preserveAspectRatio="xMidYMid
          // meet" (the default) letterboxes the drawing when height-bound.
          ...(fitViewport ? { maxHeight: 'calc(100vh - 16rem)', height: 'auto' } : {}),
        }}
        onMouseLeave={handleHoverLeave}
      >
        {/* Defs: gradient per link + SVG glow filter for Phase 3 node hover */}
        <defs>
          {/* Soft glow filter for hovered/active nodes. stdDeviation tuned
              for a premium halo without GPU-heavy blur. Uses feMerge so the
              glow sits BEHIND the node fill (not on top). */}
          <filter
            id="sankey-node-glow"
            x="-50%"
            y="-50%"
            width="200%"
            height="200%"
          >
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          {computedLinks.map((link, i) => {
            const src = link.source as DatumNode
            const tgt = link.target as DatumNode
            const isHoverConnected = connectedSet.has(i)
            const baseSrcOpacity = isHoverConnected ? 0.92 : 0.68
            const baseTgtOpacity = isHoverConnected ? 0.88 : 0.62
            // Gradients use userSpaceOnUse coordinates aligned to the link's
            // actual endpoints. objectBoundingBox units are degenerate for
            // perfectly horizontal links (y0 === y1 — e.g. a large category
            // whose source/target centers align), whose zero-height bbox
            // makes the gradient unresolvable and the ribbon invisible.
            return (
              <linearGradient
                key={`grad-${i}`}
                id={`sankey-grad-${i}`}
                gradientUnits="userSpaceOnUse"
                x1={src.x1 ?? 0}
                y1={link.y0 ?? 0}
                x2={tgt.x0 ?? 0}
                y2={link.y1 ?? 0}
              >
                <stop offset="0%" stopColor={getNodeGradientStart(src, isDark)} stopOpacity={baseSrcOpacity} />
                <stop offset="100%" stopColor={getNodeFill(tgt, isDark)} stopOpacity={baseTgtOpacity} />
              </linearGradient>
            )
          })}
        </defs>

        {/* Links — S-curved ribbons with gradient fill */}
        {/* Hover: highlight the full path (source → link → target → connected links) */}
        <g id="sankey-links">
          {computedLinks.map((link, i) => {
            const src = link.source as DatumNode
            const tgt = link.target as DatumNode
            // After layout, source/target are objects with x0/y0/y1 geometry.
            const path = linkPath(link as any)

            // Opacity: hover takes priority over activeNode click
            let linkOpacity = 1
            if (hovered !== null) {
              if (hovered.kind === 'link' && i === hovered.index) {
                linkOpacity = 1 // hovered link is fully bright
              } else if (
                (hovered.kind === 'node' && (src.name === hovered.name || tgt.name === hovered.name)) ||
                connectedSet.has(i)
              ) {
                linkOpacity = 0.85 // connected links stay visible
              } else {
                linkOpacity = 0.08 // disconnected links dim
              }
            } else if (activeNode) {
              const isConnected = src.name === activeNode || tgt.name === activeNode
              linkOpacity = isConnected ? 0.85 : 0.08
            }

            return (
              <g key={`link-${i}`}>
                {/* Invisible wide hit area so thin ribbons are easy to hover.
                    pointerEvents="stroke" keeps the whole ribbon sensitive
                    without a visible stroke change. All interactivity lives
                    here; the visible path and particle cannot steal hover. */}
                <path
                  d={path ?? ''}
                  stroke="transparent"
                  strokeWidth={Math.max(12, (link.width ?? 2) + 8)}
                  fill="none"
                  pointerEvents="stroke"
                  style={{ cursor: 'pointer' }}
                  onClick={() => onNodeClick?.(tgt.name)}
                  onMouseEnter={() => handleLinkEnter(i)}
                />
                <path
                  id={`sankey-link-path-${i}`}
                  d={path ?? ''}
                  stroke={`url(#sankey-grad-${i})`}
                  strokeWidth={Math.max(3, link.width ?? 2)}
                  fill="none"
                  opacity={linkOpacity}
                  pathLength={100}
                  className={reducedMotion ? undefined : 'sankey-link'}
                  style={{
                    transition,
                    pointerEvents: 'none',
                    '--sankey-delay': `${i * 80}ms`,
                  } as React.CSSProperties}
                />
                {/* Energy-flow particle traveling along the link.
                    Hidden for reduced-motion users. pointer-events are
                    disabled so the moving particle never steals hover. */}
                {!reducedMotion && (
                  <circle
                    r="3"
                    className="sankey-particle"
                    opacity={linkOpacity}
                    style={{ transition, pointerEvents: 'none' }}
                  >
                    <animateMotion
                      dur="2s"
                      repeatCount="indefinite"
                      begin={`${i * 120}ms`}
                    >
                      <mpath href={`#sankey-link-path-${i}`} />
                    </animateMotion>
                  </circle>
                )}
              </g>
            )
          })}
        </g>

        {/* Nodes — sharp-cornered bars with labels */}
        <g
          id="sankey-nodes"
          role="listbox"
          aria-label="Flow nodes"
          {...(focusedNode !== null ? { 'aria-activedescendant': `sankey-node-${focusedNode}` } : {})}
        >
          {computedNodes.map((node, i) => {
            const x = node.x0 ?? 0
            const y = node.y0 ?? 0
            const w = (node.x1 ?? 0) - (node.x0 ?? 0)
            const h = (node.y1 ?? 0) - (node.y0 ?? 0)
            const fill = getNodeFill(node, isDark)
            // Short bars use a smaller side-label font. The app font's
            // line box is ~1.5em, so 12px labels on bars under ~16px tall
            // crowd their neighbors' metric boxes; 10px keeps every label
            // visible with real glyphs well clear of adjacent lines.
            const isTiny = h < 16
            const labelX = x + w + 14
            const labelY = y + h / 2

            // Highlight logic — hover takes priority over activeNode click.
            // The hovered element and its connections stay bright; everything
            // else dims so the flow path stays readable.
            let nodeOpacity = 1
            let strokeColor = borderStroke
            let strokeWidth = 1
            let nodeFilter: string | undefined = undefined
            if (hovered !== null) {
              const isHoveredNode = hovered.kind === 'node' && node.name === hovered.name
              const isConnectedToHover = connectedNodeNames.has(node.name)
              if (isHoveredNode) {
                strokeColor = getNodeFill(node, isDark)
                strokeWidth = 2
                nodeFilter = reducedMotion ? undefined : 'url(#sankey-node-glow)'
              } else if (hovered.kind === 'node' && isConnectedToHover) {
                // Connected nodes stay bright so the flow path stays visible,
                // but only the hovered node gets the glow halo.
              } else if (isConnectedToHover) {
                strokeColor = getNodeFill(node, isDark)
                strokeWidth = 2
                nodeFilter = reducedMotion ? undefined : 'url(#sankey-node-glow)'
              } else {
                nodeOpacity = 0.3
              }
            } else if (activeNode) {
              if (node.name === activeNode) {
                strokeColor = 'var(--primary-500)'
                strokeWidth = 2
                nodeFilter = reducedMotion ? undefined : 'url(#sankey-node-glow)'
              } else {
                nodeOpacity = 0.3
              }
            }

            const value = displayValues?.[node.name] ?? node.value ?? 0

            const nodeLabel = `${node.name}${value > 0 ? `, ${formatCurrency(value)}` : ''}`

            return (
              <g
                key={`node-${i}`}
                id={`sankey-node-${i}`}
                ref={(el) => { nodeRefs.current[i] = el }}
                role="option"
                aria-selected={activeNode === node.name}
                aria-label={nodeLabel}
                tabIndex={focusedNode === i || (focusedNode === null && i === 0) ? 0 : -1}
                // The group itself carries NO opacity or filter: both used to
                // apply to the whole subtree, which dimmed the label of every
                // disconnected node to 0.3 (text nearly vanished on hover)
                // and blurred the hovered node's own label with the glow
                // halo. Dimming and the glow now live on the bar rect only;
                // the label clamps to a readable opacity (see the <text>).
                style={{ cursor: 'pointer', outline: 'none' }}
                onClick={() => onNodeClick?.(node.name)}
                onMouseEnter={() => handleNodeEnter(node.name)}
                onFocus={() => setFocusedNode(i)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onNodeClick?.(node.name)
                  } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                    e.preventDefault()
                    const next = (i + 1) % computedNodes.length
                    setFocusedNode(next)
                    nodeRefs.current[next]?.focus()
                  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                    e.preventDefault()
                    const prev = (i - 1 + computedNodes.length) % computedNodes.length
                    setFocusedNode(prev)
                    nodeRefs.current[prev]?.focus()
                  }
                }}
              >
                {/* Focus ring — only visible on keyboard focus */}
                <rect
                  x={x - 3}
                  y={y - 3}
                  width={Math.max(w, 6) + 6}
                  height={Math.max(h, 3) + 6}
                  rx={4}
                  ry={4}
                  fill="none"
                  className="sankey-focus-ring"
                  style={{ pointerEvents: 'none', transition, opacity: nodeOpacity }}
                />

                {/* Node bar — the only element that dims on hover and the
                    only element the glow halo may blur. Opacity and filter
                    live here (not on the group) so labels are never hidden
                    or smeared while the flow is being traced. */}
                <rect
                  x={x}
                  y={y}
                  width={Math.max(w, 6)}
                  height={Math.max(h, 3)}
                  rx={2}
                  ry={2}
                  fill={fill}
                  stroke={strokeColor}
                  strokeWidth={strokeWidth}
                  style={{ transition, opacity: nodeOpacity, filter: nodeFilter }}
                />

                {/* Every node gets ONE label on the SIDE of its bar — never
                    text over the bar or ribbons. Big bars used to carry a
                    centered white name/value ON the 14px-wide bar, which
                    straddled the ribbons and collided with neighboring side
                    labels (a visible mix of "inline over the chart" and
                    "beside the bar"). A single start-anchored line at the
                    bar's vertical center reads consistently for tall income
                    bars and tiny tail categories alike, and each column's
                    labels are spaced by the node padding (see
                    MIN_NODE_PADDING), so adjacent lines cannot collide. The
                    value stays in the aria-label for screen readers. */}
                <text
                  x={labelX}
                  y={labelY}
                  textAnchor="start"
                  dominantBaseline="central"
                  style={{
                    fontSize: isTiny ? '10px' : '12px',
                    fontWeight: 600,
                    fill: isDark ? '#eaeaea' : '#0A0805',
                    fontFamily: 'var(--font-primary)',
                    fontVariantNumeric: 'tabular-nums',
                    // Labels never fully disappear while tracing a flow:
                    // disconnected bars dim to 0.3, but their words stay at
                    // least 0.7 so the diagram remains readable on hover.
                    transition,
                    opacity: Math.max(nodeOpacity, 0.7),
                  }}
                >
                  {node.name}{value > 0 ? ` · ${formatCurrency(value)}` : ''}
                </text>
              </g>
            )
          })}
        </g>

        {/* Re-stroke category endpoints above the node bars. Large first
            categories can otherwise visually swallow their inbound ribbon
            at the target edge, especially when adjacent Debt/Expenses links
            share the same vertical neighborhood. */}
        <g id="sankey-category-endpoints" pointerEvents="none">
          {computedLinks.map((link, i) => {
            const target = link.target as DatumNode
            if (target.level !== 3 || !target.x0 || target.y0 === undefined || target.y1 === undefined) return null
            const color = getNodeFill(target, isDark)
            const opacity = hovered === null || connectedSet.has(i) ? 0.95 : 0.12
            return (
              <line
                key={`category-endpoint-${i}`}
                x1={target.x0 - 2}
                x2={target.x0 + 3}
                y1={target.y0 + (target.y1 - target.y0) / 2}
                y2={target.y0 + (target.y1 - target.y0) / 2}
                stroke={color}
                strokeWidth={Math.max(4, Math.min(10, link.width ?? 4))}
                strokeLinecap="round"
                opacity={opacity}
              />
            )
          })}
        </g>
      </svg>
    </div>
  )
})

export default SankeyFlow
