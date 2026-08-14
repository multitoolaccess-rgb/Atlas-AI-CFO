export const LEGACY_MONEY_REDIRECTS = {
  '/income': { pathname: '/cash-flow', view: 'income' },
  '/expenses': { pathname: '/cash-flow', view: 'spending' },
  '/activity': { pathname: '/cash-flow', view: 'transactions' },
  '/budgeting': { pathname: '/plan', view: 'budget' },
} as const

export type MoneyDestination = 'cash-flow' | 'plan'

const MONEY_VIEWS: Record<MoneyDestination, readonly string[]> = {
  'cash-flow': ['overview', 'income', 'spending', 'transactions'],
  plan: ['budget', 'commitments', 'calendar'],
}

export function getLegacyMoneyRedirect(pathname: string) {
  return LEGACY_MONEY_REDIRECTS[pathname as keyof typeof LEGACY_MONEY_REDIRECTS]
}

export function getMoneyView(destination: MoneyDestination, view: string | null): string {
  return view && MONEY_VIEWS[destination].includes(view) ? view : MONEY_VIEWS[destination][0]
}
