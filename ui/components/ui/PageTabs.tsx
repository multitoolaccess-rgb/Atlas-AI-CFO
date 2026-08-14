'use client'

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

export interface PageTab {
  id: string
  label: string
  disabled?: boolean
  panel?: ReactNode
}

export interface PageTabsProps {
  tabs: readonly PageTab[]
  activeId?: string
  defaultActiveId?: string
  queryKey?: string
  onChange?: (id: string) => void
  className?: string
}

export function withTabQuery(search: string, queryKey: string, id: string): string {
  const params = new URLSearchParams(search)
  params.set(queryKey, id)
  return `?${params.toString()}`
}

/** Accessible, horizontally scrollable sibling-view tabs. It is intentionally inactive until a page opts in. */
export default function PageTabs({ tabs, activeId, defaultActiveId, queryKey, onChange, className = '' }: PageTabsProps) {
  const searchParams = useSearchParams()
  const router = useRouter()
  const baseId = useId()
  const initialId = useMemo(() => defaultActiveId ?? tabs.find((tab) => !tab.disabled)?.id ?? '', [defaultActiveId, tabs])
  const [internalId, setInternalId] = useState(initialId)
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  const urlId = queryKey ? searchParams.get(queryKey) : null
  const validUrlId = urlId && tabs.some((tab) => tab.id === urlId && !tab.disabled) ? urlId : null
  const selectedId = activeId ?? validUrlId ?? internalId
  const ownsPanels = tabs.every((tab) => tab.panel !== undefined)

  useEffect(() => { if (!activeId && validUrlId) setInternalId(validUrlId) }, [activeId, validUrlId])

  const select = (id: string) => {
    const target = tabs.find((tab) => tab.id === id)
    if (!target || target.disabled) return
    if (activeId === undefined) setInternalId(id)
    if (queryKey) {
      router.replace(withTabQuery(searchParams.toString(), queryKey, id), { scroll: false })
    }
    onChange?.(id)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const enabled = tabs.filter((tab) => !tab.disabled)
    const current = enabled.findIndex((tab) => tab.id === tabs[index].id)
    let next: PageTab | undefined
    if (event.key === 'ArrowRight') next = enabled[(current + 1) % enabled.length]
    if (event.key === 'ArrowLeft') next = enabled[(current - 1 + enabled.length) % enabled.length]
    if (event.key === 'Home') next = enabled[0]
    if (event.key === 'End') next = enabled[enabled.length - 1]
    if (!next) return
    event.preventDefault()
    select(next.id)
    refs.current[next.id]?.focus()
  }

  return <div className={`min-w-0 overflow-x-auto ${className}`} data-testid="page-tabs" data-mobile-overflow="horizontal">
    <div role={ownsPanels ? 'tablist' : 'navigation'} aria-label="Page views" className="flex min-w-max border-b border-[var(--border-color)]">
      {tabs.map((tab, index) => {
        const active = selectedId === tab.id
        return <button key={tab.id} ref={(node) => { refs.current[tab.id] = node }} id={`${baseId}-${tab.id}`} type="button" role={ownsPanels ? 'tab' : undefined} disabled={tab.disabled} aria-selected={ownsPanels ? active : undefined} aria-current={!ownsPanels && active ? 'page' : undefined} aria-controls={ownsPanels ? `${baseId}-${tab.id}-panel` : undefined} tabIndex={active ? 0 : -1} onClick={() => select(tab.id)} onKeyDown={(event) => onKeyDown(event, index)} className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-[color,border-color] duration-[var(--duration-fast)] motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--primary-500)] disabled:cursor-not-allowed disabled:opacity-50 ${active ? 'border-[var(--primary-500)] text-[var(--primary-600)]' : 'border-transparent text-[var(--text-secondary)] hover:border-[var(--border-color)] hover:text-[var(--text-primary)]'}`}>{tab.label}</button>
      })}
    </div>
    {ownsPanels && tabs.map((tab) => <div key={tab.id} id={`${baseId}-${tab.id}-panel`} role="tabpanel" aria-labelledby={`${baseId}-${tab.id}`} hidden={selectedId !== tab.id} tabIndex={0}>{tab.panel}</div>)}
  </div>
}
