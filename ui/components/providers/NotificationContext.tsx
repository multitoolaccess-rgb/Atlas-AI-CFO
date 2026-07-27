'use client'

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react'

export interface Notification {
  id: string
  title: string
  message: string
  variant: 'danger' | 'warning' | 'success' | 'info'
  timestamp: number
  read: boolean
  /** When set, clicking the notification navigates here. */
  href?: string
}

export interface Toast {
  id: string
  title: string
  message: string
  variant: 'danger' | 'warning' | 'success' | 'info'
  /** Auto-dismiss duration in ms. Default: 4000 (4s). 0 = no auto-dismiss. */
  duration: number
}

interface NotificationContextValue {
  // Persistent notifications (bell icon)
  notifications: Notification[]
  unreadCount: number
  addNotification: (
    n: Omit<Notification, 'id' | 'timestamp' | 'read'>,
  ) => string
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  removeNotification: (id: string) => void
  clearAll: () => void
  // Toast notifications (auto-dismiss)
  toasts: Toast[]
  toast: (t: Omit<Toast, 'id'>) => void
  dismissToast: (id: string) => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

let _nextId = 1

// Default toast durations by variant
const TOAST_DURATIONS: Record<Toast['variant'], number> = {
  success: 3000,
  info: 4000,
  warning: 6000,
  danger: 8000,
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  // Clear all pending timers on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => clearTimeout(timer))
      timersRef.current.clear()
    }
  }, [])

  const addNotification = useCallback(
    (n: Omit<Notification, 'id' | 'timestamp' | 'read'>): string => {
      const id = `notif-${_nextId++}`
      setNotifications((prev) => [
        { ...n, id, timestamp: Date.now(), read: false },
        ...prev,
      ].slice(0, 50))
      return id
    },
    [],
  )

  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    )
  }, [])

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }, [])

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  const clearAll = useCallback(() => {
    setNotifications([])
  }, [])

  const dismissToast = useCallback((id: string) => {
    // Clear the auto-dismiss timer if it exists
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    (t: Omit<Toast, 'id'>) => {
      const id = `toast-${_nextId++}`
      const duration = t.duration ?? TOAST_DURATIONS[t.variant]
      const newToast: Toast = { ...t, id, duration }
      setToasts((prev) => [...prev, newToast].slice(-5)) // cap at 5 visible toasts

      // Auto-dismiss after duration
      if (duration > 0) {
        const timer = setTimeout(() => {
          dismissToast(id)
          timersRef.current.delete(id)
        }, duration)
        timersRef.current.set(id, timer)
      }
    },
    [dismissToast],
  )

  const unreadCount = notifications.filter((n) => !n.read).length

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        addNotification,
        markAsRead,
        markAllAsRead,
        removeNotification,
        clearAll,
        toasts,
        toast,
        dismissToast,
      }}
    >
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext)
  if (!ctx) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return ctx
}
