'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useReducedMotion } from '@/lib/useReducedMotion'
import { Orbit, Target, CreditCard, Landmark } from 'lucide-react'
import { formatNumber } from '@/lib/format'
import type { Account, Goal, DebtItem } from '@/lib/api'

/**
 * Phase 3 — FinancialUniverse.
 *
 * A CSS/SVG-based 3D financial galaxy. No WebGL/Three.js — the scene is built
 * with CSS 3D transforms so it stays lightweight and respects
 * prefers-reduced-motion out of the box.
 *
 * Nodes:
 *   - Accounts (planets) — sized by balance, colored by account type.
 *   - Goals (stars) — small glowing targets.
 *   - Debts (black holes) — dark nodes with accretion rings.
 *
 * Interactions:
 *   - Drag to rotate the galaxy.
 *   - Scroll to zoom.
 *   - Click a node to focus it.
 *   - Auto-rotation pauses on hover/focus and respects reduced motion.
 *
 * data-testid surface:
 *   - ``financial-universe`` — root container
 *   - ``universe-scene`` — the 3D scene
 *   - ``universe-node-{id}`` — each celestial body
 *   - ``universe-orbit`` — orbital ring
 */

export interface UniverseBody {
  id: string
  type: 'account' | 'goal' | 'debt'
  name: string
  value: number
  /** 0-1 normalized magnitude used for sizing. */
  magnitude: number
  color: string
  meta?: string
  /** 3D position in the scene. */
  x: number
  y: number
  z: number
}

export interface FinancialUniverseProps {
  accounts: Account[]
  goals: Goal[]
  debts: DebtItem[]
  className?: string
}

const TYPE_COLORS: Record<string, string> = {
  checking: 'var(--accent-electric)',
  savings: 'var(--accent-cyan)',
  investment: 'var(--accent-violet)',
  crypto: 'var(--accent-violet)',
  '401k': 'var(--accent-violet)',
  ira: 'var(--accent-violet)',
  hsa: 'var(--accent-violet)',
  '529': 'var(--accent-violet)',
  credit_card: 'var(--negative-500)',
  loan: 'var(--negative-500)',
  mortgage: 'var(--negative-500)',
  debit_card: 'var(--warning-500)',
  other: 'var(--text-secondary)',
}

function normalizeMagnitude(value: number, min: number, max: number): number {
  if (max <= min) return 0.5
  return Math.max(0.15, Math.min(1, (value - min) / (max - min)))
}

function sphericalToCartesian(r: number, theta: number, phi: number) {
  return {
    x: r * Math.sin(phi) * Math.cos(theta),
    y: r * Math.cos(phi),
    z: r * Math.sin(phi) * Math.sin(theta),
  }
}

export function buildBodies(
  accounts: Account[],
  goals: Goal[],
  debts: DebtItem[],
): UniverseBody[] {
  const bodies: UniverseBody[] = []

  const accountValues = accounts.map((a) => Math.abs(a.current_balance))
  const accountMin = accountValues.length ? Math.min(...accountValues) : 0
  const accountMax = accountValues.length ? Math.max(...accountValues) : 1

  accounts.forEach((a, i) => {
    const theta = ((i * 137.5) * Math.PI) / 180
    const phi = Math.acos(1 - (2 * (i + 0.5)) / Math.max(1, accounts.length))
    const pos = sphericalToCartesian(280, theta, phi)
    bodies.push({
      id: `account-${a.id}`,
      type: 'account',
      name: a.account_name,
      value: a.current_balance,
      magnitude: normalizeMagnitude(Math.abs(a.current_balance), accountMin, accountMax),
      color: TYPE_COLORS[a.account_type] ?? 'var(--accent-electric)',
      meta: a.account_type,
      ...pos,
    })
  })

  goals.forEach((g, i) => {
    const theta = ((i * 137.5 + 90) * Math.PI) / 180
    const phi = Math.acos(1 - (2 * (i + 0.5)) / Math.max(1, goals.length))
    const pos = sphericalToCartesian(180, theta, phi)
    bodies.push({
      id: `goal-${g.id}`,
      type: 'goal',
      name: g.name,
      value: g.target_amount,
      magnitude: 0.35,
      color: 'var(--accent-gold, var(--warning-500))',
      meta: `Target: ${formatNumber(g.target_amount)}`, 
      ...pos,
    })
  })

  const debtValues = debts.map((d) => Math.abs(d.balance))
  const debtMin = debtValues.length ? Math.min(...debtValues) : 0
  const debtMax = debtValues.length ? Math.max(...debtValues) : 1

  debts.forEach((d, i) => {
    const theta = ((i * 137.5 + 180) * Math.PI) / 180
    const phi = Math.acos(1 - (2 * (i + 0.5)) / Math.max(1, debts.length))
    const pos = sphericalToCartesian(120, theta, phi)
    bodies.push({
      id: `debt-${d.account_id}`,
      type: 'debt',
      name: d.account_name,
      value: d.balance,
      magnitude: normalizeMagnitude(Math.abs(d.balance), debtMin, debtMax),
      color: 'var(--negative-500)',
      meta: `Balance: ${formatNumber(Math.abs(d.balance))}`,
      ...pos,
    })
  })

  return bodies
}

export default function FinancialUniverse({ accounts, goals, debts, className }: FinancialUniverseProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<HTMLDivElement>(null)
    const [zoom, setZoom] = useState(1)
  const [dragging, setDragging] = useState(false)
  const [focused, setFocused] = useState<string | null>(null)
  const dragStart = useRef({ x: 0, y: 0, rotX: 0, rotY: 0 })
  const reducedMotion = useReducedMotion()

  const bodies = useMemo(() => buildBodies(accounts, goals, debts), [accounts, goals, debts])

  // Deterministic starfield so server/client and re-renders match.
  const stars = useMemo(() => {
    return Array.from({ length: 60 }, (_, i) => ({
      id: i,
      size: (i % 3) + 1,
      top: ((i * 37) % 100),
      left: ((i * 73) % 100),
      opacity: ((i % 7) + 3) / 10,
    }))
  }, [])

  const autoRot = useRef({ x: -15, y: 25, zoom: 1 })
  const isDraggingRef = useRef(false)
  const focusedRef = useRef<string | null>(null)

  useEffect(() => {
    isDraggingRef.current = dragging
  }, [dragging])

  useEffect(() => {
    focusedRef.current = focused
  }, [focused])

  const applyTransform = useCallback(() => {
    const el = sceneRef.current
    if (!el) return
    el.style.transform = `scale(${autoRot.current.zoom}) rotateX(${autoRot.current.x}deg) rotateY(${autoRot.current.y}deg)`
  }, [])

  useEffect(() => {
    if (reducedMotion) return
    let raf = 0
    let active = true
    const loop = () => {
      if (!active) return
      if (!isDraggingRef.current && !focusedRef.current) {
        autoRot.current.y += 0.05
        applyTransform()
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => {
      active = false
      cancelAnimationFrame(raf)
    }
  }, [reducedMotion, applyTransform])

  useEffect(() => {
    autoRot.current.zoom = zoom
    applyTransform()
  }, [zoom, applyTransform])

  useEffect(() => {
    applyTransform()
  }, [applyTransform])

  const handleMouseDown = (e: React.MouseEvent) => {
    setDragging(true)
    dragStart.current = { x: e.clientX, y: e.clientY, rotX: autoRot.current.x, rotY: autoRot.current.y }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragging) return
    const dx = e.clientX - dragStart.current.x
    const dy = e.clientY - dragStart.current.y
    autoRot.current = {
      ...autoRot.current,
      x: dragStart.current.rotX - dy * 0.2,
      y: dragStart.current.rotY + dx * 0.2,
    }
    applyTransform()
  }

  const handleMouseUp = () => setDragging(false)

  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    setDragging(true)
    dragStart.current = { x: touch.clientX, y: touch.clientY, rotX: autoRot.current.x, rotY: autoRot.current.y }
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!dragging) return
    const touch = e.touches[0]
    const dx = touch.clientX - dragStart.current.x
    const dy = touch.clientY - dragStart.current.y
    autoRot.current = {
      ...autoRot.current,
      x: dragStart.current.rotX - dy * 0.2,
      y: dragStart.current.rotY + dx * 0.2,
    }
    applyTransform()
  }

  const handleTouchEnd = () => setDragging(false)

  const handleWheel = (e: React.WheelEvent) => {
    setZoom((z) => Math.max(0.5, Math.min(2, z - e.deltaY * 0.001)))
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      setZoom((z) => Math.max(0.5, Math.min(2, z - e.deltaY * 0.001)))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  return (
    <div
      className={`relative w-full h-[600px] rounded-2xl overflow-hidden bg-[var(--space-950)] ${className ?? ''}`}
      ref={containerRef}
      data-testid="financial-universe"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      role="application"
      aria-label="Interactive 3D financial universe. Drag to rotate, scroll to zoom."
    >
      {/* Starfield background */}
      <div className="absolute inset-0 opacity-40 pointer-events-none">
        {stars.map((star) => (
          <div
            key={star.id}
            className="absolute rounded-full bg-white"
            style={{
              width: star.size,
              height: star.size,
              top: `${star.top}%`,
              left: `${star.left}%`,
              opacity: star.opacity,
            }}
          />
        ))}
      </div>

      {/* Scene */}
      <div
        ref={sceneRef}
        data-testid="universe-scene"
        className="absolute left-1/2 top-1/2 w-0 h-0"
        style={{
          transformStyle: 'preserve-3d',
          transition: dragging ? 'none' : 'transform 0.1s linear',
        }}
      >
        {/* Orbital rings */}
        {[120, 180, 280].map((r, i) => (
          <div
            key={r}
            data-testid="universe-orbit"
            className="absolute rounded-full border border-[var(--border-color)] opacity-30"
            style={{
              width: r * 2,
              height: r * 2,
              left: -r,
              top: -r,
              transform: `rotateX(90deg) translateZ(${i * 10}px)`,
            }}
          />
        ))}

        {/* Bodies */}
        {bodies.map((body) => {
          const isFocused = focused === body.id
          const size = 12 + body.magnitude * 28
          return (
            <button
              key={body.id}
              data-testid={`universe-node-${body.id}`}
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setFocused(isFocused ? null : body.id)
              }}
              className={`absolute flex items-center justify-center rounded-full transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-cyan)] ${
                isFocused ? 'z-10' : ''
              }`}
              style={{
                width: size,
                height: size,
                backgroundColor: body.color,
                boxShadow: `0 0 ${12 + body.magnitude * 24}px ${body.color}`,
                transform: `translate3d(${body.x}px, ${body.y}px, ${body.z}px)`,
                left: -size / 2,
                top: -size / 2,
              }}
              aria-label={`${body.type} ${body.name}${body.meta ? ` — ${body.meta}` : ''}`}
            >
              {body.type === 'account' && <Landmark className="w-3 h-3 text-white/90" aria-hidden="true" />}
              {body.type === 'goal' && <Target className="w-3 h-3 text-white/90" aria-hidden="true" />}
              {body.type === 'debt' && <CreditCard className="w-3 h-3 text-white/90" aria-hidden="true" />}
            </button>
          )
        })}
      </div>

      {/* Legend / HUD */}
      <div className="absolute bottom-4 left-4 right-4 flex flex-wrap items-end justify-between gap-4 pointer-events-none">
        <div className="glass-surface px-4 py-3 rounded-xl pointer-events-auto">
        <h3 className="headline-md text-primary flex items-center gap-2">
          <Orbit className="w-5 h-5 text-[var(--accent-cyan)]" aria-hidden="true" />
          Financial Universe
        </h3>
        <p className="body-sm text-on-surface-variant mt-1">
          {bodies.length} celestial bodies · Drag to rotate · Scroll to zoom
        </p>
        </div>

        <div className="glass-surface px-4 py-3 rounded-xl space-y-2 pointer-events-auto">
          <div className="flex items-center gap-2 text-xs text-on-surface-variant">
            <span className="w-3 h-3 rounded-full bg-[var(--accent-electric)]" />
            Accounts
          </div>
          <div className="flex items-center gap-2 text-xs text-on-surface-variant">
            <span className="w-3 h-3 rounded-full bg-[var(--accent-gold, var(--warning-500))]" />
            Goals
          </div>
          <div className="flex items-center gap-2 text-xs text-on-surface-variant">
            <span className="w-3 h-3 rounded-full bg-[var(--negative-500)]" />
            Debts
          </div>
        </div>
      </div>

      {/* Focus panel */}
      {focused && (
        <div className="absolute top-4 right-4 w-64 glass-surface p-4 rounded-xl z-20">
          {(() => {
            const body = bodies.find((b) => b.id === focused)
            if (!body) return null
            return (
              <>
                <div className="flex items-center gap-2 mb-2">
                  {body.type === 'account' && <Landmark className="w-4 h-4 text-[var(--accent-electric)]" />}
                  {body.type === 'goal' && <Target className="w-4 h-4 text-[var(--accent-gold)]" />}
                  {body.type === 'debt' && <CreditCard className="w-4 h-4 text-[var(--negative-500)]" />}
                  <h4 className="font-semibold text-primary text-sm">{body.name}</h4>
                </div>
                <p className="text-xs text-on-surface-variant capitalize mb-1">{body.type}</p>
                <p className="text-lg font-bold tabular-nums text-primary">
                  {formatNumber(Math.abs(body.value))}
                </p>
                {body.meta && <p className="text-xs text-on-surface-variant mt-1">{body.meta}</p>}
              </>
            )
          })()}
        </div>
      )}
    </div>
  )
}
