'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, HelpCircle, Mail, BookOpen } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'

const FAQ = [
  {
    q: 'How do I add a new account?',
    a: 'Go to the Accounts tab and click "Add Account" in the top-right. Fill in the name, type, institution, and opening balance. Saved accounts immediately show up in your dashboard totals.',
  },
  {
    q: 'Where do my transactions come from?',
    a: 'Transactions are created in two ways: (1) manual entry via the API, or (2) uploaded statement files (CSV / OFX / PDF) via the /api/imports/upload endpoint. Plaid linking is also supported in the backend and will surface here as a future "Connect with Plaid" option.',
  },
  {
    q: 'Why does the Overview show "Network Error"?',
    a: 'The frontend cannot reach the rules-service backend on :8000. Start it with: cd services/rules-service && .venv/bin/python -m uvicorn app.main:app. Once /health returns 200, the dashboard auto-recovers on the next page load (or click the Retry button on the error banner).',
  },
  {
    q: 'How is the 20-year projection calculated?',
    a: 'It uses a standard future-value-of-annuity formula: FV = PV * (1+r)^n + PMT * (((1+r)^n - 1) / r), where r is the annual return (7% by default), n is the number of years (20 for the goal), and PMT is your monthly net contribution (income minus expenses). Negative PMT values are NOT floored at 0 — the engine lets the principal draw down so you see the real cost of a spending deficit.',
  },
  {
    q: 'Is my data safe?',
    a: 'In dev mode, all data is stored in a local SQLite database at services/rules-service/finance.db. Authentication is a JWT issued by /api/auth/devlogin (non-production only). For real deployment, swap the SQLite URL for a managed Postgres and replace devlogin with your real auth provider.',
  },
  {
    q: 'How do I run the tests?',
    a: 'From the project root: bash scripts/test.sh (full suite including Playwright) or bash scripts/test-e2e.sh (with auto-started backend). The pre-push hook runs a smart subset based on what files changed.',
  },
]

export default function HelpPage() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  return (
    <PageLayout>
      <h1 className="headline-xl text-primary mb-2">Help Center</h1>
      <p className="body-md text-secondary mb-6">
        Common questions, troubleshooting tips, and pointers to the docs.
      </p>

      <div className="card p-6 mb-6" data-testid="help-faq">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-primary" aria-hidden="true" />
          <h2 className="headline-md text-primary">Frequently asked questions</h2>
        </div>
        <ul className="space-y-2">
          {FAQ.map((item, i) => {
            const open = openIndex === i
            return (
              <li key={i} className="border-b border-outline-variant/20 last:border-b-0">
                <button
                  type="button"
                  onClick={() => setOpenIndex(open ? null : i)}
                  className="w-full flex items-center justify-between py-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  aria-expanded={open}
                  aria-controls={`faq-panel-${i}`}
                >
                  <span className="body-md font-semibold text-primary">
                    {item.q}
                  </span>
                  {open ? (
                    <ChevronDown
                      className="w-4 h-4 text-on-surface-variant shrink-0"
                      aria-hidden="true"
                    />
                  ) : (
                    <ChevronRight
                      className="w-4 h-4 text-on-surface-variant shrink-0"
                      aria-hidden="true"
                    />
                  )}
                </button>
                {open && (
                  <p
                    id={`faq-panel-${i}`}
                    className="body-md text-secondary pb-3"
                  >
                    {item.a}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      </div>

      <div className="card p-6">
        <div className="flex items-center gap-2 mb-2">
          <HelpCircle className="w-5 h-5 text-primary" aria-hidden="true" />
          <h2 className="headline-md text-primary">Still need help?</h2>
        </div>
        <p className="body-md text-secondary mb-4">
          The project docs in <code className="font-mono text-primary">docs/</code>{' '}
          cover the architecture, master plan, and rules-service API. The README
          has a Getting Started section.
        </p>
        <div className="flex items-center gap-2 text-sm text-secondary">
          <Mail className="w-4 h-4" aria-hidden="true" />
          <span>
            Open an issue or reach out via the project&apos;s normal channels.
          </span>
        </div>
      </div>
    </PageLayout>
  )
}
