'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Edit2, LogIn, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import Button from '@/components/ui/Button'

interface QuickActionsProps {
  onAddExpense?: () => void
  onAddBudget?: () => void
  onLogIncome?: () => void
  className?: string
}

/**
 * Floating action button with quick action menu.
 * Keyboard shortcut: Cmd+K (or Ctrl+K)
 * Bottom-right fixed position with spring animation.
 */
export default function QuickActions({
  onAddExpense,
  onAddBudget,
  onLogIncome,
  className = '',
}: QuickActionsProps) {
  const [open, setOpen] = useState(false)

  const actions = [
    {
      id: 'expense',
      icon: Plus,
      label: 'Add Expense',
      color: 'bg-[var(--danger-500)] hover:bg-[var(--danger-600)]',
      onClick: () => {
        setOpen(false)
        onAddExpense?.()
      },
    },
    {
      id: 'budget',
      icon: Edit2,
      label: 'Add Budget',
      color: 'bg-[var(--primary-500)] hover:bg-[var(--primary-600)]',
      onClick: () => {
        setOpen(false)
        onAddBudget?.()
      },
    },
    {
      id: 'income',
      icon: LogIn,
      label: 'Log Income',
      color: 'bg-[var(--success-500)] hover:bg-[var(--success-600)]',
      onClick: () => {
        setOpen(false)
        onLogIncome?.()
      },
    },
  ]

  // Keyboard shortcut handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === 'Escape') {
        setOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className={`fixed bottom-6 right-6 z-40 ${className}`}>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.2 }}
            className="absolute bottom-20 right-0 space-y-2"
          >
            {actions.map((action) => {
              const Icon = action.icon
              return (
                <motion.button
                  key={action.id}
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: 0.05 }}
                  onClick={action.onClick}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white font-medium text-sm ${action.color} transition-all shadow-lg hover:shadow-xl`}
                  title={`${action.label} (Cmd+K to toggle menu)`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{action.label}</span>
                </motion.button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main FAB */}
      <motion.button
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setOpen(!open)}
        className={`w-14 h-14 rounded-full flex items-center justify-center text-white font-semibold shadow-lg hover:shadow-xl transition-all ${
          open
            ? 'bg-[var(--slate-600)] hover:bg-[var(--slate-700)]'
            : 'bg-[var(--primary-500)] hover:bg-[var(--primary-600)]'
        }`}
        title="Quick actions (Cmd+K)"
      >
        {open ? (
          <X className="w-6 h-6" />
        ) : (
          <Plus className="w-6 h-6" />
        )}
      </motion.button>

      {/* Keyboard shortcut hint */}
      {!open && (
        <div className="absolute bottom-20 right-0 px-2 py-1 rounded bg-[var(--slate-900)] text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none">
          Cmd+K
        </div>
      )}
    </div>
  )
}
