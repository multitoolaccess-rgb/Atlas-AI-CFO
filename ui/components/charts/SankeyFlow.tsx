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
  getTextColor,
  getTextSecondaryColor,
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

const SANKEY_MARGIN = { top: 8, right: 180, bottom: 16, left: 24 }

const SankeyFlow = React.memo(function SankeyFlow({ nodes, links, displayValues, height = 440, onNodeClick, activeNode }: SankeyFlowProps) {
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

    const clonedNodes: DatumNode[] = nodes.map((n, i) => ({
      name: n.name,
      node_type: n.node_type,
      color: n.color,
      role: n.role,
      group: n.group,
      level: n.level,
      index: i,
    }))
    const clonedLinks: DatumLink[] = validLinks.map(l => ({
      source: l.source,
      target: l.target,
      value: l.value,
    }))

    const sankeyLayout = sankey<DatumNode, DatumLink>()
      .nodeId((d) => d.index!)
      .nodeWidth(14)
      .nodePadding(24)
      .extent([
        [SANKEY_MARGIN.left, SANKEY_MARGIN.top],
        [width - SANKEY_MARGIN.right, height - SANKEY_MARGIN.bottom],
      ])

    const { nodes: sn, links: sl } = sankeyLayout({
      nodes: clonedNodes,
      links: clonedLinks,
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
        style={{ overflow: 'visible' }}
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
            return (
              <linearGradient
                key={`grad-${i}`}
                id={`sankey-grad-${i}`}
                x1="0%"
                y1="0%"
                x2="100%"
                y2="0%"
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
            const isLarge = h > 36
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
            const textColor = getTextColor(fill)
            const textSecondary = getTextSecondaryColor(fill)

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
                style={{ cursor: 'pointer', transition, opacity: nodeOpacity, outline: 'none', filter: nodeFilter }}
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
                  style={{ pointerEvents: 'none' }}
                />

                {/* Node bar */}
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
                />

                {/* Inline label for large nodes (Income / Retained bars) */}
                {isLarge && (
                  <text
                    x={x + w / 2}
                    y={y + h / 2 - 1}
                    textAnchor="middle"
                    dominantBaseline="central"
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      fill: textColor,
                      fontFamily: 'var(--font-primary)',
                      letterSpacing: '0.01em',
                    }}
                  >
                    {node.name}
                  </text>
                )}

                {/* Side label — name (hardcoded hex: CSS vars can fail in SVG fills) */}
                {!isLarge && (
                  <text
                    x={labelX}
                    y={labelY - 7}
                    textAnchor="start"
                    dominantBaseline="central"
                    style={{
                      fontSize: '12px',
                      fontWeight: 600,
                      fill: isDark ? '#eaeaea' : '#0A0805',
                      fontFamily: 'var(--font-primary)',
                    }}
                  >
                    {node.name}
                  </text>
                )}

                {/* Side label — currency value (hardcoded hex: CSS vars can fail in SVG fills) */}
                {value > 0 && (
                  <text
                    x={isLarge ? x + w / 2 : labelX}
                    y={isLarge ? y + h / 2 + 13 : labelY + 8}
                    textAnchor={isLarge ? 'middle' : 'start'}
                    dominantBaseline="central"
                    style={{
                      fontSize: '11px',
                      fontWeight: isLarge ? 600 : 500,
                      fill: isLarge ? textSecondary : (isDark ? '#999999' : '#6B6860'),
                      fontFamily: 'var(--font-mono)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {formatCurrency(value)}
                  </text>
                )}
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
