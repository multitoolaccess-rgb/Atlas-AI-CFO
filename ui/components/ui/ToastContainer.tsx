'use client'

import { useEffect, useState } from 'react'
import {
  X,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  Info,
} from 'lucide-react'
import { useNotifications, type Toast } from '@/components/providers/NotificationContext'

function variantStyles(variant: Toast['variant']) {
  switch (variant) {
    case 'success':
      return {
        bg: 'bg-[var(--success-50)] border-[var(--success-200)] text-[var(--success-700)]',
        icon: CheckCircle2,
        progress: 'bg-[var(--success-400)]',
      }
    case 'warning':
      return {
        bg: 'bg-[var(--warning-50)] border-[var(--warning-200)] text-[var(--warning-700)]',
        icon: AlertTriangle,
        progress: 'bg-[var(--warning-400)]',
      }
    case 'danger':
      return {
        bg: 'bg-[var(--danger-50)] border-[var(--danger-200)] text-[var(--danger-700)]',
        icon: AlertOctagon,
        progress: 'bg-[var(--danger-400)]',
      }
    case 'info':
      return {
        bg: 'bg-[var(--primary-50)] border-[var(--primary-200)] text-[var(--primary-700)]',
        icon: Info,
        progress: 'bg-[var(--primary-400)]',
      }
  }
}

function SingleToast({
  toast,
  onDismiss,
}: {
  toast: Toast
  onDismiss: (id: string) => void
}) {
  const [entering, setEntering] = useState(true)
  const [exiting, setExiting] = useState(false)
  const { bg, icon: Icon, progress } = variantStyles(toast.variant)

  // Trigger enter animation
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntering(false))
    return () => cancelAnimationFrame(raf)
  }, [])

  const handleDismiss = () => {
    setExiting(true)
    // Wait for exit animation before removing from DOM
    setTimeout(() => onDismiss(toast.id), 300)
  }

  return (
    <div
      className={`
        relative overflow-hidden
        w-80 rounded-[var(--radius-lg)] border shadow-[var(--shadow-4)]
        transition-all duration-300 ease-out
        ${bg}
        ${entering ? 'translate-x-full opacity-0' : 'translate-x-0 opacity-100'}
        ${exiting ? 'translate-x-full opacity-0' : ''}
      `}
      role="alert"
      aria-live="assertive"
      data-testid={`toast-${toast.id}`}
    >
      <div className="flex items-start gap-3 p-3">
        <Icon className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold">{toast.title}</p>
          <p className="text-xs opacity-80 mt-0.5">{toast.message}</p>
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss"
          className="p-0.5 rounded opacity-60 hover:opacity-100 transition-opacity"
          data-testid={`toast-dismiss-${toast.id}`}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {/* Auto-dismiss progress bar */}
      {toast.duration > 0 && (
        <div className="h-0.5 w-full bg-black/5">
          <div
            className={`h-full ${progress} transition-all ease-linear`}
            style={{
              width: exiting ? '0%' : '100%',
              transitionDuration: exiting ? '300ms' : `${toast.duration}ms`,
            }}
          />
        </div>
      )}
    </div>
  )
}

/**
 * Toast container — renders in the bottom-right corner of the viewport.
 * Toasts auto-dismiss after their duration (3-8 seconds depending on variant).
 * Max 5 toasts visible at once.
 */
export default function ToastContainer() {
  const { toasts, dismissToast } = useNotifications()

  if (toasts.length === 0) return null

  return (
    <div
      className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2"
      aria-label="Toast notifications"
      data-testid="toast-container"
    >
      {toasts.map((t) => (
        <SingleToast key={t.id} toast={t} onDismiss={dismissToast} />
      ))}
    </div>
  )
}
