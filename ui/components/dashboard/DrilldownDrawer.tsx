'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'

interface DrilldownDrawerProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  breadcrumbs?: string[]
  onBreadcrumbClick?: (index: number) => void
  children: ReactNode
  width?: 'md' | 'lg' | 'xl'
}

const widthClasses = { md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl' }

export default function DrilldownDrawer({
  open,
  onClose,
  title,
  subtitle,
  breadcrumbs,
  onBreadcrumbClick,
  children,
  width = 'lg',
}: DrilldownDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!mounted || typeof document === 'undefined') return null

  const variants = reduced
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        hidden: { opacity: 0, x: '100%' },
        visible: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: '100%' },
      }

  const backdropVariants = reduced
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }

  return createPortal(
    <AnimatePresence mode="wait">
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end" aria-modal="true" role="dialog">
          <motion.div
            key="backdrop"
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={{ duration: reduced ? 0 : 0.25 }}
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            ref={drawerRef}
            key="panel"
            variants={variants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={
              reduced
                ? { duration: 0 }
                : { type: 'spring', stiffness: 260, damping: 28 }
            }
            className={`relative w-full ${widthClasses[width]} bg-[var(--bg-primary)] border-l border-[var(--border-color)] shadow-2xl flex flex-col`}
          >
            {/* Header */}
            <div className="flex items-center gap-3 p-5 border-b border-[var(--border-color)] flex-shrink-0">
              <button
                type="button"
                onClick={onClose}
                className="p-2 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--slate-100)] transition-colors focus-visible:outline-2 focus-visible:outline-[var(--primary-500)]"
                aria-label="Close drawer"
              >
                <X className="w-4 h-4" />
              </button>
              <div className="min-w-0 flex-1">
                {breadcrumbs && breadcrumbs.length > 0 && (
                  <div className="flex items-center gap-1 text-xs text-[var(--text-tertiary)] mb-0.5 font-semibold">
                    {breadcrumbs.map((crumb, i) => (
                      <span key={i} className="flex items-center gap-1">
                        {i > 0 && <span>/</span>}
                        <button
                          type="button"
                          onClick={() => onBreadcrumbClick?.(i)}
                          className="hover:text-[var(--text-primary)] transition-colors"
                        >
                          {crumb}
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <h2 className="headline-md text-primary truncate">{title}</h2>
                {subtitle && <p className="text-xs text-tertiary truncate">{subtitle}</p>}
              </div>
            </div>
            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto p-5">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
