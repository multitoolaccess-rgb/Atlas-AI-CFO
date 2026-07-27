'use client'

import Sidebar from '@/components/layout/Sidebar'
import Header from '@/components/layout/Header'
import { SidebarProvider } from '@/components/layout/SidebarContext'
import ErrorBanner from '@/components/ui/ErrorBanner'
import { NotificationProvider } from '@/components/providers/NotificationContext'
import { BackendUnavailableError } from '@/lib/backendError'

/**
 * Global error boundary for the root layout.
 *
 * When the SSR health probe in layout.tsx fails, it throws
 * BackendUnavailableError. This boundary catches that error and renders
 * the offline shell so the user sees a server-rendered alert instead
 * of a blank page or a 404.
 */
export default function RootError({
  error,
}: {
  error: Error
}) {
  const isBackendUnavailable = error instanceof BackendUnavailableError

  return (
    <NotificationProvider>
      <SidebarProvider>
        <Sidebar />
        <Header />
        <main className="ml-64 p-8 pt-4 transition-all duration-300 ease-in-out">
          <ErrorBanner
            title={isBackendUnavailable ? 'Backend Unavailable:' : 'Something went wrong:'}
            message={
              isBackendUnavailable
                ? "The Atlas backend on :8000 isn't responding. Start it with: cd services/rules-service && ../../.venv-rules/bin/python -m uvicorn app.main:app. Then refresh this page."
                : error.message || 'An unexpected error occurred. Please refresh the page.'
            }
            retryHref="/"
          />
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-primary text-on-primary rounded-lg hover:bg-primary/90 transition-colors"
          >
            Retry
          </button>
        </main>
      </SidebarProvider>
    </NotificationProvider>
  )
}
