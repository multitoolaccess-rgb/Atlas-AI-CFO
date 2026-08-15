'use client'

import AccountsPage from '@/app/accounts/page'

/**
 * Data Connections is the authoritative System destination for account
 * management and statement imports. The workspace remains shared with the
 * legacy module so account/import behavior has one implementation and the
 * /accounts compatibility redirect cannot drift from it.
 */
export default function DataConnectionsPage() {
  return <AccountsPage />
}
