/**
 * Information-architecture contract for the staged migration.
 * Destinations are activated only when their complete route surface exists.
 */

export type NavigationIcon =
  | 'home' | 'cash-flow' | 'plan' | 'wealth' | 'portfolio' | 'goals'
  | 'decisions' | 'market-intelligence' | 'scenario-lab' | 'data-connections'
  | 'settings' | 'help'

export interface ProposedDestination {
  id: string
  label: string
  path: string
  icon: NavigationIcon
  activeMatch: readonly string[]
  /** True only after the migration wave that creates the destination is activated. */
  activated: boolean
  tabs?: readonly ProposedTabDestination[]
}

export interface ProposedTabDestination {
  id: string
  label: string
  query: Readonly<Record<string, string>>
}

export interface ProposedNavigationGroup {
  id: string
  label: string
  destinations: readonly ProposedDestination[]
}

const tab = (id: string, label: string): ProposedTabDestination => ({ id, label, query: { view: id } })

export const PROPOSED_NAVIGATION: readonly ProposedNavigationGroup[] = [
  { id: 'home', label: 'Home', destinations: [{ id: 'mission-control', label: 'Mission Control', path: '/', icon: 'home', activeMatch: ['/'], activated: true }] },
  { id: 'money', label: 'Money', destinations: [
    { id: 'cash-flow', label: 'Cash Flow', path: '/cash-flow', icon: 'cash-flow', activeMatch: ['/cash-flow'], activated: true, tabs: [tab('overview', 'Overview'), tab('income', 'Income'), tab('spending', 'Spending'), tab('transactions', 'Transactions')] },
    { id: 'plan', label: 'Plan', path: '/plan', icon: 'plan', activeMatch: ['/plan'], activated: true, tabs: [tab('budget', 'Budget'), tab('commitments', 'Commitments'), tab('calendar', 'Calendar')] },
  ] },
  { id: 'wealth', label: 'Wealth', destinations: [
    { id: 'wealth', label: 'Wealth', path: '/wealth', icon: 'wealth', activeMatch: ['/wealth'], activated: true, tabs: [tab('overview', 'Overview'), tab('assets', 'Assets'), tab('debts', 'Debts'), tab('universe', 'Universe view')] },
    { id: 'portfolio', label: 'Portfolio', path: '/portfolio', icon: 'portfolio', activeMatch: ['/portfolio'], activated: true, tabs: [tab('holdings', 'Holdings'), tab('allocation', 'Allocation'), tab('performance', 'Performance'), tab('risk', 'Risk')] },
    { id: 'goals', label: 'Goals', path: '/goals', icon: 'goals', activeMatch: ['/goals'], activated: true, tabs: [tab('goals', 'Goals'), tab('forecasts', 'Forecasts'), tab('progress', 'Progress')] },
  ] },
  { id: 'intelligence', label: 'Intelligence', destinations: [
    { id: 'decisions', label: 'Decisions', path: '/decisions', icon: 'decisions', activeMatch: ['/decisions'], activated: true, tabs: [tab('recommendations', 'Recommendations'), tab('journal', 'Decision journal'), tab('outcomes', 'Outcomes')] },
    { id: 'market-intelligence', label: 'Market Intelligence', path: '/market-intelligence', icon: 'market-intelligence', activeMatch: ['/market-intelligence'], activated: true, tabs: [tab('portfolio', 'My Portfolio'), tab('pulse', 'Market Pulse'), tab('earnings', 'Earnings & Events'), tab('scanner', 'S&P 500 Scanner'), tab('archive', 'Archive')] },
    { id: 'scenario-lab', label: 'Scenario Lab', path: '/scenario-lab', icon: 'scenario-lab', activeMatch: ['/scenario-lab'], activated: true, tabs: [tab('scenarios', 'Scenarios'), tab('comparisons', 'Comparisons'), tab('archive', 'Archive')] },
  ] },
  { id: 'system', label: 'System', destinations: [
    { id: 'data-connections', label: 'Data Connections', path: '/data-connections', icon: 'data-connections', activeMatch: ['/data-connections'], activated: false, tabs: [tab('accounts', 'Accounts'), tab('imports', 'Imports'), tab('synchronization', 'Synchronization'), tab('data-quality', 'Data quality')] },
    { id: 'settings', label: 'Settings', path: '/settings', icon: 'settings', activeMatch: ['/settings'], activated: false },
    { id: 'help', label: 'Help', path: '/help', icon: 'help', activeMatch: ['/help'], activated: false },
  ] },
] as const

export const COMPATIBILITY_REDIRECTS = [
  { from: '/income', to: '/cash-flow', view: 'income' },
  { from: '/expenses', to: '/cash-flow', view: 'spending' },
  { from: '/activity', to: '/cash-flow', view: 'transactions' },
  { from: '/budgeting', to: '/plan', view: 'budget' },
  { from: '/debts', to: '/wealth', view: 'debts' },
  { from: '/universe', to: '/wealth', view: 'universe' },
  { from: '/recommendations', to: '/decisions', view: 'recommendations' },
  { from: '/market-briefs', to: '/market-intelligence' },
  { from: '/accounts', to: '/data-connections', view: 'accounts' },
] as const

export const ACTIVE_COMPATIBILITY_REDIRECTS = COMPATIBILITY_REDIRECTS.filter(({ from }) => ['/income', '/expenses', '/activity', '/budgeting', '/debts', '/universe', '/recommendations', '/market-briefs'].includes(from))

export const SCOUT_PLACEMENT_CONTRACT = {
  futureLocation: 'global-header',
  fallbackRoute: '/assistant',
  activation: 'Activated in Step 2: Scout is exposed in the global header while /assistant remains the accessible fallback route.',
} as const

export function isProposedDestinationActive(destination: ProposedDestination, pathname: string): boolean {
  return destination.activeMatch.some((path) => pathname === path || pathname.startsWith(`${path}/`))
}

export function validateInformationArchitecture(): string[] {
  const destinations = PROPOSED_NAVIGATION.flatMap((group) => group.destinations)
  const ids = destinations.map(({ id }) => id)
  const paths = destinations.map(({ path }) => path)
  const duplicate = (values: readonly string[]) => values.filter((value, index) => values.indexOf(value) !== index)
  return [...duplicate(ids).map((id) => `duplicate destination id: ${id}`), ...duplicate(paths).map((path) => `duplicate destination path: ${path}`)]
}
