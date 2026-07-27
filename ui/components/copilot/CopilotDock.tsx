'use client'

import { useState, useCallback, useEffect } from 'react'
import { Sparkles, MessageSquare, Lightbulb, X } from 'lucide-react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import ChatPanel from '@/components/assistant/ChatPanel'
import ProactiveInsights, { type ProactiveInsight, deriveProactiveInsights } from './ProactiveInsights'
import type { InsightItem } from '@/lib/api'

/**
 * Phase 4 — CopilotDock.
 *
 * A slide-in side panel that hosts the Scout chat, proactive insight
 * cards, and quick-query chips. The panel has two tabs:
 *   - "Chat" — the full ChatPanel (conversation + streaming + tool cards)
 *   - "Insights" — proactive AI cards derived from the dashboard data
 *
 * The dock is rendered fixed on the right side, ~420px wide on desktop,
 * full-width on mobile. It slides in/out via a CSS transform transition.
 *
 * The parent (PageLayout) controls ``open`` and renders the CopilotOrb
 * separately; this component just renders the panel content.
 *
 * Quick-query chips: tapping one forwards the text to the ChatPanel.
 * We use a simple ref bridge — the ChatPanel reads from a shared
 * ``pendingQuery`` prop and consumes it on mount/update.
 *
 * data-testid surface:
 * - ``copilot-dock`` — the panel root
 * - ``copilot-dock-tab-chat`` — the Chat tab button
 * - ``copilot-dock-tab-insights`` — the Insights tab button
 * - ``copilot-dock-close`` — the close button
 * - ``copilot-query-chip-{i}`` — each quick-query chip
 */

interface CopilotDockProps {
  open: boolean
  onClose: () => void
  /** Raw dashboard insights to derive proactive cards from. */
  insights: InsightItem[]
}

const QUICK_QUERIES = [
  'Can I afford a Tesla?',
  'When will I be a millionaire?',
  'Where am I wasting money?',
  'How much should I invest monthly?',
]

type Tab = 'chat' | 'insights'

export default function CopilotDock({ open, onClose, insights }: CopilotDockProps) {
  const [tab, setTab] = useState<Tab>('chat')
  const [pendingQuery, setPendingQuery] = useState<string | null>(null)

  const proactiveInsights: ProactiveInsight[] = deriveProactiveInsights(insights)

  const handleQuickQuery = useCallback((query: string) => {
    setPendingQuery(query)
    setTab('chat')
  }, [])

  const handleAskFromInsight = useCallback((query: string) => {
    setPendingQuery(query)
    setTab('chat')
  }, [])

  const reduced = useReducedMotion()

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  const panelVariants = reduced
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : { hidden: { x: '100%' }, visible: { x: 0 }, exit: { x: '100%' } }

  const backdropVariants = { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            key="copilot-backdrop"
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={{ duration: reduced ? 0 : 0.25 }}
            className="fixed inset-0 z-[var(--z-modal-backdrop, 90)] bg-black/30 backdrop-blur-sm md:hidden"
            onClick={onClose}
            aria-hidden="true"
            data-testid="copilot-dock-backdrop"
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.aside
            key="copilot-panel"
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={
              reduced
                ? { duration: 0 }
                : { type: 'spring', stiffness: 260, damping: 28 }
            }
            className="
              fixed top-0 right-0 z-[var(--z-modal, 100)]
              h-full w-full md:w-[420px]
              bg-[var(--bg-primary)] border-l border-[var(--border-color)]
              shadow-[var(--shadow-4)]
              flex flex-col
            "
            role="dialog"
            aria-modal="true"
            aria-labelledby="copilot-title"
            data-testid="copilot-dock"
          >
        {/* Header — title + tabs + close */}
        <div className="flex items-center gap-2 p-3 border-b border-[var(--border-color)]">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span
              className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: 'radial-gradient(circle at 30% 30%, var(--accent-cyan) 0%, var(--accent-electric) 100%)',
              }}
            >
              <Sparkles className="w-4 h-4 text-white" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2 id="copilot-title" className="text-sm font-semibold text-[var(--text-primary)] truncate">Scout Copilot</h2>
              <p className="text-[10px] text-[var(--text-tertiary)]">Your AI financial companion</p>
            </div>
          </div>

          {/* Tab switcher */}
          <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--surface-container-low)]">
            <button
              type="button"
              onClick={() => setTab('chat')}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                tab === 'chat'
                  ? 'bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
              }`}
              data-testid="copilot-dock-tab-chat"
            >
              <MessageSquare className="w-3.5 h-3.5" aria-hidden="true" />
              Chat
            </button>
            <button
              type="button"
              onClick={() => setTab('insights')}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                tab === 'insights'
                  ? 'bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
              }`}
              data-testid="copilot-dock-tab-insights"
            >
              <Lightbulb className="w-3.5 h-3.5" aria-hidden="true" />
              Insights
              {proactiveInsights.length > 0 && (
                <span className="ml-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-[var(--accent-cyan)] text-white">
                  {proactiveInsights.length}
                </span>
              )}
            </button>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="flex-shrink-0 p-1.5 rounded-lg text-[var(--text-tertiary)]
                       hover:text-[var(--text-primary)] hover:bg-[var(--surface-container)]
                       transition-colors duration-150"
            data-testid="copilot-dock-close"
            aria-label="Close copilot panel"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Quick-query chips (always visible above the tab content) */}
        <div className="px-3 py-2 border-b border-[var(--border-color)] flex flex-wrap gap-1.5">
          {QUICK_QUERIES.map((q, i) => (
            <button
              key={q}
              type="button"
              onClick={() => handleQuickQuery(q)}
              className="px-2.5 py-1 rounded-full text-[11px] font-medium
                         bg-[var(--surface-container-low)] text-[var(--text-secondary)]
                         border border-[var(--border-color)]
                         hover:bg-[var(--surface-container)] hover:text-[var(--text-primary)]
                         hover:border-[var(--accent-cyan)]
                         transition-all duration-150"
              data-testid={`copilot-query-chip-${i}`}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {tab === 'chat' ? (
            <div className="h-full">
              <ChatPanel key={pendingQuery ?? 'default'} pendingQuery={pendingQuery} />
            </div>
          ) : (
            <div className="h-full overflow-y-auto p-3">
              <ProactiveInsights
                insights={proactiveInsights}
                onAsk={handleAskFromInsight}
                maxItems={10}
              />
            </div>
          )}
        </div>
      </motion.aside>
        )}
    </AnimatePresence>
  </>
  )
}
