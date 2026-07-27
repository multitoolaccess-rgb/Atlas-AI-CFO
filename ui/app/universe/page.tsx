'use client'

import { Suspense } from 'react'
import dynamic from 'next/dynamic'
import Sidebar from '@/components/layout/Sidebar'
import Header from '@/components/layout/Header'
import { SidebarProvider, useSidebar } from '@/components/layout/SidebarContext'
import { useCachedFetch } from '@/lib/cache'
import { rulesService, type Account, type Goal, type DebtItem } from '@/lib/api'
import ErrorBanner from '@/components/ui/ErrorBanner'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'

const FinancialUniverse = dynamic(() => import('@/components/universe/FinancialUniverse'), {
  ssr: false,
  loading: () => (
    <div className="card h-[600px] flex items-center justify-center" aria-busy="true">
      <div className="skeleton h-full w-full" />
    </div>
  ),
})

function UniverseInner() {
  const { collapsed } = useSidebar()
  const { data: accounts, error: accountsError } = useCachedFetch<Account[]>(
    'universe-accounts',
    () => rulesService.listAccounts().catch(() => []),
    [],
    { group: 'universe' },
  )
  const { data: goals, error: goalsError } = useCachedFetch<Goal[]>(
    'universe-goals',
    () => rulesService.listGoals().catch(() => []),
    [],
    { group: 'universe' },
  )
  const { data: debts, error: debtsError } = useCachedFetch<DebtItem[]>(
    'universe-debts',
    () => rulesService.getDebtsSummary().then((r) => r.debts).catch(() => []),
    [],
    { group: 'universe' },
  )

  const error = accountsError ?? goalsError ?? debtsError

  return (
    <>
      <Sidebar />
      <Header />
      <main
        id="main-content"
        className="p-8 pt-4 transition-all duration-300 ease-in-out ml-[var(--layout-ml)]"
        style={{ '--layout-ml': collapsed ? '4.5rem' : '16rem' } as React.CSSProperties}
      >
        <div className="mb-6">
          <h1 className="headline-xl text-primary mb-1">Financial Universe</h1>
          <p className="body-md text-secondary">
            Explore your accounts, goals, and debts as a 3D galaxy. Drag to rotate, scroll to zoom.
          </p>
        </div>

        {/* Floating bar — URL-synced via ?range=… (page-default YTD).
            Visual-only today: universe data is not range-aware yet. */}
        <FloatingTimeRangeBar />

        {error && (
          <ErrorBanner
            title="Couldn't load universe data:"
            message={error}
            variant="warning"
          />
        )}

        <FinancialUniverse
          accounts={accounts ?? []}
          goals={goals ?? []}
          debts={debts ?? []}
        />
      </main>
    </>
  )
}

export default function UniversePage() {
  return (
    <SidebarProvider>
      <Suspense fallback={<div className="card h-[600px] flex items-center justify-center" aria-busy="true"><div className="skeleton h-full w-full" /></div>}>
        <AtlasFilterProvider>
        <UniverseInner />
        </AtlasFilterProvider>
      </Suspense>
    </SidebarProvider>
  )
}
