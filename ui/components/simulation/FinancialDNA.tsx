'use client'

import { useMemo } from 'react'
import { Fingerprint, Award } from 'lucide-react'
import type { DashboardSummary } from '@/lib/api'

/**
 * Phase 5 — FinancialDNA.
 *
 * Five-axis radar chart (a.k.a. spider chart) that visualises the user's
 * "financial DNA" — a behavioural fingerprint of saving, investing,
 * liquidity and goal-pursuit. Each axis is 0–100, where 100 is "ideal
 * behaviour" per the Atlas scoring rubric:
 *   - Savings Rate:  monthly savings / monthly income × 100
 *                    (capped at 60; >60% is usually transient).
 *   - Investment Diversity:  account count normalised  (1 acct=20, 5+=100).
 *   - Cash Buffer:  months of expenses covered  (3-mo=60, 6-mo=100).
 *   - Debt Discipline:  100 − debt/asset ratio (0 debt → 100; max 0).
 *   - Goal Velocity:  average progress across all goals (0–100).
 *
 * The radar polygon is drawn as an SVG `<polygon>`. Each axis label sits
 * around the perimeter. The center is a single composite DNA score
 * (mean of the 5 axes), color-coded by tier (Excellent/Good/Fair/Building).
 *
 * data-testid surface:
 *   - ``dna-card`` — root container
 *   - ``dna-axis-{name}`` — each axis label
 *   - ``dna-polygon`` — the filled radar shape
 *   - ``dna-score`` — center composite number
 */

export interface DNAAxisValues {
  savingsRate: number
  investmentDiversity: number
  cashBuffer: number
  debtDiscipline: number
  goalVelocity: number
}

export interface FinancialDNAProps {
  summary: DashboardSummary | null
  /** Total debt across all accounts in USD (optional). */
  totalDebt?: number
  /** Total assets/balance (defaults to summary.total_balance). */
  totalAssets?: number
  className?: string
}

function clamp(n: number, min = 0, max = 100): number {
  if (!Number.isFinite(n)) return 0
  return Math.max(min, Math.min(max, n))
}

export function computeDNA(
  summary: DashboardSummary | null,
  totalDebt = 0,
  totalAssetsOverride?: number,
): DNAAxisValues {
  const income = Math.max(0, summary?.total_income_month ?? 0)
  const expenses = Math.max(0, summary?.total_expenses_month ?? 0)
  const savings = Math.max(0, income - expenses)
  const savingsRate = income > 0 ? clamp((savings / income) * 100 * (100 / 60)) : 0

  const accountCount = summary?.accounts_count ?? 0
  const investmentDiversity = clamp(20 + accountCount * 16)

  const buffer = expenses > 0 ? savings / expenses : 0
  const cashBuffer = clamp((buffer / 6) * 100)

  const assets = totalAssetsOverride ?? summary?.total_balance ?? 0
  const debtDiscipline = assets > 0 ? clamp(100 - Math.min(100, (totalDebt / assets) * 100)) : clamp(100 - Math.min(100, totalDebt > 0 ? 100 : 0), 0, 100)

  // Goal velocity: average progress of user_goals from 0..1 → 0..100
  const goals = summary?.user_goals ?? []
  const goalVelocity =
    goals.length === 0
      ? 0
      : clamp(
          (goals.reduce((s, g) => s + Math.min(1, assets / Math.max(1, g.target_amount)), 0) /
            goals.length) *
            100,
        )

  return {
    savingsRate: Math.round(savingsRate),
    investmentDiversity: Math.round(investmentDiversity),
    cashBuffer: Math.round(cashBuffer),
    debtDiscipline: Math.round(debtDiscipline),
    goalVelocity: Math.round(goalVelocity),
  }
}

const AXES = [
  { key: 'savingsRate', label: 'Savings' },
  { key: 'investmentDiversity', label: 'Diversity' },
  { key: 'cashBuffer', label: 'Cash Buffer' },
  { key: 'debtDiscipline', label: 'Debt' },
  { key: 'goalVelocity', label: 'Goals' },
] as const

const VIEW = 280
const CENTER = VIEW / 2
const RADIUS = 95

function tierFromScore(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Excellent', color: 'var(--success-600)' }
  if (score >= 60) return { label: 'Good', color: 'var(--accent-electric)' }
  if (score >= 40) return { label: 'Fair', color: 'var(--warning-600)' }
  return { label: 'Building', color: 'var(--text-secondary)' }
}

export default function FinancialDNA({ summary, totalDebt = 0, totalAssets, className }: FinancialDNAProps) {
  const values = useMemo(() => computeDNA(summary, totalDebt, totalAssets), [summary, totalDebt, totalAssets])

  // 5 axes evenly distributed. Angle measured clockwise from top (i.e. -π/2).
  const points = useMemo(() => {
    return AXES.map((_, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / AXES.length
      return {
        angle,
        x: CENTER + Math.cos(angle) * RADIUS,
        y: CENTER + Math.sin(angle) * RADIUS,
        labelX: CENTER + Math.cos(angle) * (RADIUS + 22),
        labelY: CENTER + Math.sin(angle) * (RADIUS + 22),
      }
    })
  }, [])

  const composite = Math.round(AXES.reduce((s, a) => s + (values[a.key as keyof DNAAxisValues] ?? 0), 0) / AXES.length)
  const tier = tierFromScore(composite)

  // Polygon points scaled by axis value (0-100 maps to 0-RADIUS).
  const polygonPoints = AXES.map((axis, i) => {
    const v = values[axis.key as keyof DNAAxisValues] / 100
    const angle = points[i].angle
    const x = CENTER + Math.cos(angle) * RADIUS * v
    const y = CENTER + Math.sin(angle) * RADIUS * v
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')

  return (
    <div className={`card p-6 ${className ?? ''}`} data-testid="dna-card">
      <div className="flex-between mb-3">
        <div className="flex items-center gap-3">
          <span
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'color-mix(in srgb, var(--accent-violet, var(--accent-electric)) 12%, transparent)' }}
          >
            <Fingerprint className="w-4 h-4 text-[var(--accent-violet, var(--accent-electric))]" aria-hidden="true" />
          </span>
          <div>
            <h3 className="headline-md text-primary">Financial DNA</h3>
            <p className="body-sm text-on-surface-variant">Your behavior fingerprint.</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: tier.color }}>
            <Award className="w-3.5 h-3.5 inline mr-1" aria-hidden="true" />
            {tier.label}
          </div>
          <div className="text-xl font-bold tabular-nums" style={{ color: tier.color }} data-testid="dna-score">
            {composite}
          </div>
        </div>
      </div>

      <div className="flex justify-center">
        <svg
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          width="280"
          height="280"
          aria-label="Financial DNA radar chart with five axes"
        >
          <defs>
            <radialGradient id="dna-fill" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="var(--accent-electric)" stopOpacity="0.35" />
              <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity="0.15" />
            </radialGradient>
          </defs>

          {/* Concentric rings — 25%, 50%, 75%, 100% */}
          {[0.25, 0.5, 0.75, 1].map((r) => (
            <circle
              key={r}
              cx={CENTER}
              cy={CENTER}
              r={RADIUS * r}
              fill="none"
              stroke="var(--border-color)"
              strokeOpacity="0.4"
              strokeDasharray={r === 1 ? '0' : '3 3'}
            />
          ))}

          {/* Axis lines */}
          {points.map((p, i) => (
            <line
              key={`axis-${i}`}
              x1={CENTER}
              y1={CENTER}
              x2={p.x}
              y2={p.y}
              stroke="var(--border-color)"
              strokeOpacity="0.4"
            />
          ))}

          {/* Data polygon */}
          <polygon
            points={polygonPoints}
            fill="url(#dna-fill)"
            stroke="var(--accent-cyan)"
            strokeWidth="2"
            strokeLinejoin="round"
            data-testid="dna-polygon"
          />

          {/* Axis labels */}
          {AXES.map((axis, i) => {
            const p = points[i]
            const v = values[axis.key as keyof DNAAxisValues]
            return (
              <g key={`lbl-${axis.key}`}>
                <text
                  x={p.labelX}
                  y={p.labelY}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize="11"
                  fontWeight="600"
                  fill="var(--text-primary)"
                  data-testid={`dna-axis-${axis.key}`}
                >
                  {axis.label}
                </text>
                <text
                  x={p.labelX}
                  y={p.labelY + 14}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize="10"
                  fontWeight="700"
                  fill="var(--accent-cyan)"
                  className="tabular-nums"
                >
                  {v}
                </text>
              </g>
            )
          })}

          {/* Center tier marker */}
          <circle cx={CENTER} cy={CENTER} r={6} fill={tier.color} />
        </svg>
      </div>
    </div>
  )
}
