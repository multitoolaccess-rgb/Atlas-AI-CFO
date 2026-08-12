'use client'

import { Check, Monitor, Moon, Palette, Sun } from 'lucide-react'
import { useAppearance } from '@/components/providers/AppearanceProvider'
import type { AccentProfile, ThemeMode } from '@/lib/appearance'
import Card from '@/components/ui/Card'

const MODES: Array<{ value: ThemeMode; label: string; description: string; Icon: typeof Sun }> = [
  { value: 'light', label: 'Light', description: 'Bright canvas for daytime review', Icon: Sun },
  { value: 'dark', label: 'Dark', description: 'Low-light command center', Icon: Moon },
  { value: 'system', label: 'System', description: 'Follow your operating system', Icon: Monitor },
]

const ACCENTS: Array<{ value: AccentProfile; name: string; description: string; signal: string }> = [
  { value: 'indigo', name: 'Indigo Intelligence', description: 'Balanced, precise, and unmistakably Atlas.', signal: 'Default' },
  { value: 'vermilion', name: 'Vermilion Energy', description: 'Decisive warmth for a more active command center.', signal: 'Decisive' },
  { value: 'ion', name: 'Ion Future', description: 'Experimental chartreuse with disciplined contrast.', signal: 'Experimental' },
]

export default function AppearanceSection() {
  const { mode, accent, setMode, setAccent, resolvedTheme } = useAppearance()

  return (
    <section aria-labelledby="appearance-title" className="mt-8 max-w-4xl" data-testid="appearance-section">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-accent-subtle text-accent-primary" aria-hidden="true">
          <Palette className="h-5 w-5" />
        </div>
        <div>
          <h2 id="appearance-title" className="headline-md text-primary">Appearance</h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-secondary">
            Set the working light level and Atlas accent independently. These choices change presentation only. Gains, losses, warnings, and critical states keep their financial meaning.
          </p>
        </div>
      </div>

      <Card className="overflow-hidden border-[var(--border-subtle)] shadow-none" padding="default">
        <fieldset>
          <legend className="text-sm font-semibold text-primary">Mode</legend>
          <p className="mt-1 text-sm text-secondary">Currently rendered in {resolvedTheme} mode.</p>
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Color mode">
            {MODES.map(({ value, label, description, Icon }) => {
              const selected = mode === value
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setMode(value)}
                  className={`min-h-14 rounded-[var(--radius-md)] border px-4 py-3 text-left transition-[border-color,background-color,transform] duration-200 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-focus)] active:scale-[0.99] ${selected ? 'border-accent-primary bg-accent-subtle' : 'border-[var(--border-subtle)] bg-surface-base hover:border-accent-border hover:bg-surface-selected'}`}
                  data-testid={`appearance-mode-${value}`}
                >
                  <span className="flex items-center gap-3">
                    <Icon className="h-4 w-4 shrink-0 text-accent-primary" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-primary">{label}</span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-secondary">{description}</span>
                    </span>
                    {selected && <Check className="ml-auto h-4 w-4 shrink-0 text-accent-primary" aria-hidden="true" />}
                  </span>
                </button>
              )
            })}
          </div>
        </fieldset>

        <fieldset className="mt-8 border-t border-[var(--border-subtle)] pt-7">
          <legend className="text-sm font-semibold text-primary">Accent profile</legend>
          <p className="mt-1 text-sm text-secondary">Choose Atlas identity. Financial semantics remain profile-independent.</p>
          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3" role="radiogroup" aria-label="Accent profile">
            {ACCENTS.map(({ value, name, description, signal }) => {
              const selected = accent === value
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setAccent(value)}
                  className={`appearance-preview appearance-preview-${value} min-h-40 rounded-[var(--radius-md)] border p-4 text-left transition-[border-color,transform,box-shadow] duration-200 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-focus)] active:scale-[0.99] ${selected ? 'border-accent-primary shadow-[0_0_0_3px_var(--accent-selection)]' : 'border-[var(--border-subtle)] hover:-translate-y-0.5 hover:border-accent-border'}`}
                  data-preview-accent={value}
                  data-testid={`appearance-accent-${value}`}
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full border-2 border-white/60 bg-[var(--preview-accent)] shadow-[0_0_0_2px_var(--preview-ring)]" aria-hidden="true" />
                      <span className="text-xs font-semibold text-[var(--preview-ink)]">{signal}</span>
                    </span>
                    {selected && <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--preview-accent)] text-[var(--preview-on-accent)]" aria-label="Selected"><Check className="h-4 w-4" aria-hidden="true" /></span>}
                  </span>
                  <span className="mt-10 block text-sm font-semibold text-[var(--preview-ink)]">{name}</span>
                  <span className="mt-1 block text-xs leading-relaxed text-[var(--preview-muted)]">{description}</span>
                  <span className="mt-4 flex gap-1.5" aria-hidden="true">
                    <span className="h-1.5 flex-1 rounded-full bg-[var(--preview-accent)]" />
                    <span className="h-1.5 w-1/4 rounded-full bg-[var(--preview-track)]" />
                    <span className="h-1.5 w-1/6 rounded-full bg-[var(--preview-track)]" />
                  </span>
                </button>
              )
            })}
          </div>
        </fieldset>
      </Card>
    </section>
  )
}
