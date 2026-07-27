'use client'

import { useState, useEffect, useCallback } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import { GlobalFilterProvider, useGlobalFilters } from '@/components/ui/GlobalFilterContext'
import {
  rulesService,
  type BudgetStatusResponse,
  type Budget,
  type Category,
} from '@/lib/api'
import BudgetCategoryCard from '@/components/dashboard/BudgetCategoryCard'
import AnimatedKPICard from '@/components/cards/AnimatedKPICard'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import TiltCard from '@/components/ui/TiltCard'
import {
  DollarSign,
  TrendingDown,
  AlertTriangle,
  Plus,
  Check,
  X,
  Calendar,
} from 'lucide-react'
import { formatNumber } from '@/lib/format'
import { classifyErrorMessage } from '@/lib/errors'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'

const groupLabels: Record<string, string> = {
  fixed: 'Fixed Expenses',
  flexible: 'Flexible Expenses',
  debt: 'Debt Payments',
  savings: 'Savings & Investments',
  other: 'Other',
}

const groupOrder = ['fixed', 'flexible', 'debt', 'savings', 'other']

function BudgetingContent() {
  const [status, setStatus] = useState<BudgetStatusResponse | null>(null)
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newCategoryId, setNewCategoryId] = useState<number | ''>('')
  const [newAmount, setNewAmount] = useState('')

  // Global budgets are limited to one per user + period. Use this to
  // disable the option in the dropdown, switch the default category, and
  // surface a helpful hint.
  const globalBudgetForPeriod = budgets.find((b) => b.category_id === null)

  // When the add form opens and a Global budget already exists for this
  // period, default to the first available category so the user isn't
  // staring at a disabled Global selection and a Save that would 409.
  useEffect(() => {
    if (showAddForm && globalBudgetForPeriod && newCategoryId === '') {
      setNewCategoryId(categories[0]?.id ?? '')
    }
  }, [showAddForm, globalBudgetForPeriod, newCategoryId, categories])
  // SSR-safe default: an empty string keeps server and initial client
  // render identical. The real current period is set once after mount in
  // the effect below so the input never produces a hydration mismatch.
  const [newPeriod, setNewPeriod] = useState('')

  useEffect(() => {
    const now = new Date()
    setNewPeriod(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  }, [])

  const loadData = useCallback(async () => {
    if (!newPeriod) return
    try {
      setLoading(true)
      setError(null)
      const [statusData, budgetData, catData] = await Promise.all([
        rulesService.getBudgetStatus(newPeriod),
        rulesService.listBudgets({ period: newPeriod }),
        rulesService.listCategories(),
      ])
      setStatus(statusData)
      setBudgets(budgetData)
      setCategories(catData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load budget data')
    } finally {
      setLoading(false)
    }
  }, [newPeriod])

  useEffect(() => { loadData() }, [loadData])

  const handleAddBudget = async () => {
    if (!newAmount || Number(newAmount) <= 0) return
    try {
      await rulesService.createBudget({
        category_id: newCategoryId === '' ? null : Number(newCategoryId),
        amount: Number(newAmount),
        period: newPeriod,
      })
      setShowAddForm(false)
      setNewCategoryId('')
      setNewAmount('')
      loadData()
    } catch (err) {
      setError(classifyErrorMessage(err))
    }
  }

  const formatCurrency = (n: number) => formatNumber(n)

  const groupedCategories = status?.categories.reduce(
    (acc, cat) => {
      const group = cat.budget_group || 'other'
      if (!acc[group]) acc[group] = []
      acc[group].push(cat)
      return acc
    },
    {} as Record<string, typeof status.categories>,
  )

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-on-surface tracking-tight">Budgeting</h1>
        <p className="text-sm text-on-surface-variant">Track planned vs actual spending</p>
      </div>

      {/* Migrated from <FloatingFilterBar> children-pass-through (period input
          + Add Budget button). The floating bar's own range selector changes
          ?range=… (URL-only, no BE impact yet because budgeting keys by month);
          both controls render left-to-right inside the same bar. */}
      <FloatingTimeRangeBar>
        <div className="flex items-center gap-2 min-w-0">
          <Calendar className="w-4 h-4 text-[var(--text-tertiary)] flex-shrink-0" />
          <span className="text-xs font-semibold text-[var(--text-secondary)]">Period</span>
          <input
            type="month"
            value={newPeriod}
            onChange={(e) => setNewPeriod(e.target.value)}
            className="px-3 py-1.5 bg-surface-container border border-outline-variant/30 rounded-lg text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          data-testid="add-budget-button"
          className="flex items-center gap-2 px-4 py-2 bg-[var(--interactive-primary)] text-white rounded-lg text-sm font-semibold hover:bg-[var(--interactive-hover)] transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Budget
        </button>
      </FloatingTimeRangeBar>

      {/* Add Budget Form */}
      {showAddForm && (
        <div className="card p-6">
          <h3 className="text-sm font-bold uppercase tracking-wider text-on-surface mb-4">New Budget Entry</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-on-surface-variant mb-2">Category</label>
              <select
                value={newCategoryId}
                onChange={(e) => setNewCategoryId(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 bg-surface-container border border-outline-variant/30 rounded-lg text-sm"
              >
                <option value="" disabled={!!globalBudgetForPeriod}>
                  Global (no category) {globalBudgetForPeriod ? '— already added' : ''}
                </option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              {globalBudgetForPeriod && (
                <p className="text-xs text-warning-600 mt-1">
                  Only one Global budget is allowed per period.
                </p>
              )}
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-on-surface-variant mb-2">Amount</label>
              <input
                type="number"
                value={newAmount}
                onChange={(e) => setNewAmount(e.target.value)}
                placeholder="0.00"
                min="0"
                step="0.01"
                className="w-full px-3 py-2 bg-surface-container border border-outline-variant/30 rounded-lg text-sm"
              />
            </div>
            <div className="flex items-end gap-2">
              <button onClick={handleAddBudget} className="flex items-center gap-2 px-4 py-2 bg-[var(--interactive-success)] text-white rounded-lg text-sm font-semibold hover:bg-[var(--interactive-success-hover)] active:bg-[var(--interactive-success-active)] transition-colors">
                <Check className="w-4 h-4" /> Save
              </button>
              <button onClick={() => setShowAddForm(false)} className="flex items-center gap-2 px-4 py-2 bg-surface-container-high border border-outline-variant/30 rounded-lg text-sm">
                <X className="w-4 h-4" /> Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-3 p-4 bg-danger-50 border border-danger-200 rounded-lg" data-testid="budgeting-error">
          <AlertTriangle className="w-5 h-5 text-danger-500 shrink-0" />
          <p className="text-sm text-danger-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-danger-500 hover:text-danger-700"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4" data-testid="budgeting-loading">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-1/2 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-3/4" />
            </div>
          ))}
        </div>
      ) : status ? (
        groupedCategories && Object.keys(groupedCategories).length > 0 ? (
          <>
            {/* KPI Strip with 3D tilt */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4" data-testid="budgeting-kpi-strip">
              <TiltCard className="h-full">
                <AnimatedKPICard
                  icon={<DollarSign className="w-5 h-5 text-[var(--primary-500)]" />}
                  label="Total Budget"
                  value={formatCurrency(status.totals.planned)}
                  accentClass="bg-[var(--primary-500)]"
                  highlighted
                />
              </TiltCard>
              <TiltCard className="h-full">
                <AnimatedKPICard
                  icon={<TrendingDown className="w-5 h-5 text-[var(--danger-500)]" />}
                  label="Total Spent"
                  value={formatCurrency(status.totals.actual)}
                  subtext={`${status.totals.percent_used.toFixed(1)}% of budget`}
                  accentClass="bg-[var(--danger-500)]"
                />
              </TiltCard>
              <TiltCard className="h-full">
                <AnimatedKPICard
                  icon={<DollarSign className="w-5 h-5 text-[var(--success-500)]" />}
                  label="Remaining"
                  value={formatCurrency(status.totals.remaining)}
                  subtext={status.totals.remaining >= 0 ? 'Under budget' : 'Over budget'}
                  accentClass={status.totals.remaining >= 0 ? 'bg-[var(--success-500)]' : 'bg-[var(--danger-500)]'}
                  highlighted={status.totals.remaining < 0}
                />
              </TiltCard>
              <TiltCard className="h-full">
                <AnimatedKPICard
                  icon={<AlertTriangle className={`w-5 h-5 ${status.totals.percent_used > 100 ? 'text-[var(--danger-500)]' : status.totals.percent_used > 80 ? 'text-[var(--warning-500)]' : 'text-[var(--success-500)]'}`} />}
                  label="% Used"
                  value={`${status.totals.percent_used.toFixed(1)}%`}
                  subtext={status.totals.percent_used > 100 ? 'Overspent' : status.totals.percent_used > 80 ? 'Approaching limit' : 'On track'}
                  accentClass={status.totals.percent_used > 100 ? 'bg-[var(--danger-500)]' : status.totals.percent_used > 80 ? 'bg-[var(--warning-500)]' : 'bg-[var(--success-500)]'}
                  highlighted={status.totals.percent_used > 80}
                />
              </TiltCard>
            </div>

            {/* Budget by Group */}
            <div className="space-y-6">
              {groupOrder
                .filter((g) => groupedCategories[g])
                .map((group) => {
                  const groupTotal = groupedCategories[group].reduce((s, c) => s + c.planned, 0)
                  const groupActual = groupedCategories[group].reduce((s, c) => s + c.actual, 0)
                  const groupPct = groupTotal > 0 ? (groupActual / groupTotal) * 100 : 0
                  return (
                    <ExpandableCard
                      key={group}
                      title={groupLabels[group] || group}
                      subtitle={`${groupedCategories[group].length} categories · ${groupPct.toFixed(0)}% used`}
                      className="overflow-visible"
                    >
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {groupedCategories[group].map((cat) => (
                          <BudgetCategoryCard key={cat.category_id} category={cat} />
                        ))}
                      </div>
                    </ExpandableCard>
                  )
                })}
            </div>
          </>
        ) : (
          <div className="card p-12 text-center" data-testid="budgeting-empty-state">
            <DollarSign className="w-12 h-12 text-on-surface-variant/30 mx-auto mb-4" />
            <h3 className="text-lg font-bold text-on-surface mb-2">No budgets configured</h3>
            <p className="text-sm text-on-surface-variant mb-6 max-w-md mx-auto">
              Set up budgets for your categories to track planned vs actual spending for {newPeriod}.
            </p>
            <button onClick={() => setShowAddForm(true)} className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--interactive-primary)] text-white rounded-lg text-sm font-semibold hover:bg-[var(--interactive-hover)] transition-colors">
              <Plus className="w-4 h-4" /> Create Your First Budget
            </button>
          </div>
        )
      ) : null}
    </div>
  )
}

export default function BudgetingPage() {
  return (
    <PageLayout>
      <GlobalFilterProvider>
        <BudgetingContent />
      </GlobalFilterProvider>
    </PageLayout>
  )
}
