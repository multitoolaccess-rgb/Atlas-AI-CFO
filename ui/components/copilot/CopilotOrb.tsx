'use client'

import { useEffect, useState, forwardRef } from 'react'
import { Sparkles, X } from 'lucide-react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'

/**
 * Phase 4 — CopilotOrb.
 *
 * A persistent floating AI companion orb that sits in the bottom-right
 * corner of every page. It has a gentle "breathing" animation that signals
 * the AI is present and listening. Click to expand into the CopilotDock
 * side panel; click again to collapse.
 *
 * The orb uses the cyan-glow accent (the "AI intelligence" color from the
 * Atlas design system) and respects `prefers-reduced-motion`.
 *
 * data-testid surface:
 * - ``copilot-orb`` — the orb button
 * - ``copilot-orb-icon`` — the icon inside the orb
 */

interface CopilotOrbProps {
  /** Whether the dock is currently open. */
  open: boolean
  /** Toggle the dock open/closed. */
  onToggle: () => void
  /** Number of unread proactive insights (shows a badge when > 0). */
  insightCount?: number
}

const CopilotOrb = forwardRef<HTMLButtonElement, CopilotOrbProps>(function CopilotOrb(
  { open, onToggle, insightCount = 0 },
  ref,
) {
  const [mounted, setMounted] = useState(false)
  const reduced = useReducedMotion()

  // Avoid SSR hydration flash — the orb only appears after mount.
  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null

  return (
    <motion.button
      ref={ref}
      type="button"
      onClick={onToggle}
      aria-label={open ? 'Close AI copilot panel' : 'Open AI copilot panel'}
      aria-expanded={open}
      whileHover={reduced ? undefined : { scale: 1.05 }}
      whileTap={reduced ? undefined : { scale: 0.95 }}
      className="
        fixed bottom-6 right-6 z-[var(--z-tooltip, 100)]
        w-14 h-14 rounded-full
        flex items-center justify-center
        transition-colors duration-300 ease-out
        focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-cyan)] focus-visible:ring-offset-2
        focus-visible:ring-offset-[var(--bg-primary)]
      "
      style={{
        background: open
          ? 'var(--surface-container-high)'
          : 'radial-gradient(circle at 30% 30%, var(--accent-cyan) 0%, var(--accent-electric) 100%)',
        boxShadow: open
          ? 'none'
          : '0 4px 24px rgba(34, 211, 238, 0.35), 0 0 0 1px rgba(34, 211, 238, 0.2)',
      }}
      data-testid="copilot-orb"
    >
      {/* Ambient aura ring — only when closed (breathing effect) */}
      {!open && (
        <span
          className="absolute inset-0 rounded-full animate-aura pointer-events-none"
          style={{
            background: 'radial-gradient(circle, transparent 60%, var(--accent-cyan) 100%)',
            opacity: 0.3,
          }}
          aria-hidden="true"
        />
      )}

      {/* Icon — Sparkles when closed, X when open */}
      {open ? (
        <X
          className="w-5 h-5 text-[var(--text-primary)] relative z-10"
          aria-hidden="true"
          data-testid="copilot-orb-icon"
        />
      ) : (
        <Sparkles
          className="w-6 h-6 text-white relative z-10"
          aria-hidden="true"
          data-testid="copilot-orb-icon"
        />
      )}

      {/* Unread insights badge */}
      <AnimatePresence>
        {!open && insightCount > 0 && (
          <motion.span
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.5 }}
            animate={reduced ? { opacity: 1 } : { opacity: 1, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.5 }}
            transition={{ duration: reduced ? 0 : 0.25 }}
            className="absolute -top-1 -right-1 w-5 h-5 rounded-full
                       bg-[var(--danger-500)] text-white
                       text-[10px] font-bold
                       flex items-center justify-center
                       ring-2 ring-[var(--bg-primary)]"
            aria-label={`${insightCount} new insights`}
            data-testid="copilot-orb-badge"
          >
            {insightCount > 9 ? '9+' : insightCount}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  )
})

export default CopilotOrb
