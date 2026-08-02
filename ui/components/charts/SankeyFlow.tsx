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
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SankeyFlowProps {
  nodes: SankeyNodeType[]
  links: SankeyLinkType[]
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

/* formatNumber is imported from @/lib/format */

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

const SankeyFlow = React.memo(function SankeyFlow({ nodes, links, height = 440, onNodeClick, activeNode }: SankeyFlowProps) {
  const reducedMotion = useReducedMotion()
  const isDark = useThemeMode()
  const [hoveredLink, setHoveredLink] = useState<number | null>(null)
  const [focusedNode, setFocusedNode] = useState<number | null>(null)
  const nodeRefs = useRef<(SVGGElement | null)[]>([])
  const width = 960

  // Stable callbacks for hover handlers (avoids inline arrow allocation per link)
  const handleLinkEnter = useCallback((i: number) => setHoveredLink(i), [])
  const handleLinkLeave = useCallback(() => setHoveredLink(null), [])
  const margin = SANKEY_MARGIN

  // d3-sankey mutates input — deep clone inside useMemo
  const { computedNodes, computedLinks } = useMemo(() => {
    if (!nodes.length) return { computedNodes: [] as DatumNode[], computedLinks: [] as DatumLink[] }

    const clonedNodes: DatumNode[] = nodes.map((n, i) => ({
      name: n.name,
      node_type: n.node_type,
      color: n.color,
      role: n.role,
      group: n.group,
      level: n.level,
      index: i,
    }))
    const clonedLinks: DatumLink[] = links.map(l => ({
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
  }, [nodes, links, width, height])

  const transition = reducedMotion ? 'none' : 'opacity 150ms ease-out'
  const borderStroke = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'

  // Compute the connected link set once per render for hover highlighting
  const connectedSet = useMemo(
    () => getConnectedSet(hoveredLink, computedLinks),
    [hoveredLink, computedLinks],
  )

  if (!nodes.length) {
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
            const baseSrcOpacity = isHoverConnected ? 0.85 : 0.5
            const baseTgtOpacity = isHoverConnected ? 0.8 : 0.45
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
            if (hoveredLink !== null) {
              if (i === hoveredLink) {
                linkOpacity = 1 // hovered link is fully bright
              } else if (connectedSet.has(i)) {
                linkOpacity = 0.6 // connected links stay visible
              } else {
                linkOpacity = 0.06 // disconnected links dim
              }
            } else if (activeNode) {
              const isConnected = src.name === activeNode || tgt.name === activeNode
              linkOpacity = isConnected ? 0.85 : 0.06
            }

            return (
              <g key={`link-${i}`}>
                <path
                  id={`sankey-link-path-${i}`}
                  d={path ?? ''}
                  stroke={`url(#sankey-grad-${i})`}
                  strokeWidth={Math.max(2, link.width ?? 2)}
                  fill="none"
                  opacity={linkOpacity}
                  pathLength={100}
                  className={reducedMotion ? undefined : 'sankey-link'}
                  style={{
                    transition,
                    cursor: 'pointer',
                    '--sankey-delay': `${i * 80}ms`,
                  } as React.CSSProperties}
                  onClick={() => onNodeClick?.(tgt.name)}
                  onMouseEnter={() => handleLinkEnter(i)}
                  onMouseLeave={handleLinkLeave}
                />
                {/* Energy-flow particle traveling along the link.
                    Hidden for reduced-motion users. */}
                {!reducedMotion && (
                  <circle
                    r="3"
                    className="sankey-particle"
                    opacity={linkOpacity}
                    style={{ transition }}
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

            // Check if this node is connected to the hovered link
            let isConnectedToNodeHover = false
            if (hoveredLink !== null) {
              const hLink = computedLinks[hoveredLink]
              if (hLink) {
                const hSrc = (hLink.source as DatumNode).name
                const hTgt = (hLink.target as DatumNode).name
                isConnectedToNodeHover = node.name === hSrc || node.name === hTgt
              }
            }

            // Highlight logic — hover takes priority over activeNode click.
            // Phase 3: hovered/active nodes get the glow filter for a premium
            //       halo effect (reduced-motion users skip the filter).
            let nodeOpacity = 1
            let strokeColor = borderStroke
            let strokeWidth = 1
            let nodeFilter: string | undefined = undefined
            if (hoveredLink !== null) {
              if (isConnectedToNodeHover) {
                strokeColor = getNodeFill(node, isDark)
                strokeWidth = 2
                nodeFilter = reducedMotion ? undefined : 'url(#sankey-node-glow)'
              } else {
                nodeOpacity = 0.25
              }
            } else if (activeNode) {
              if (node.name === activeNode) {
                strokeColor = 'var(--primary-500)'
                strokeWidth = 2
                nodeFilter = reducedMotion ? undefined : 'url(#sankey-node-glow)'
              } else {
                nodeOpacity = 0.25
              }
            }

            const value = node.value ?? 0
            const textColor = getTextColor(fill)
            const textSecondary = getTextSecondaryColor(fill)

            const nodeLabel = `${node.name}${value > 0 ? `, ${formatNumber(value)}` : ''}`

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
                    {formatNumber(value)}
                  </text>
                )}
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
})

export default SankeyFlow
