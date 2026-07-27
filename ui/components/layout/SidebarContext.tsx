'use client'

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

interface SidebarContextValue {
  collapsed: boolean
  toggleCollapsed: () => void
  /** Per-group expand/collapse state. True = expanded (default). */
  groupStates: Record<string, boolean>
  toggleGroup: (groupKey: string) => void
}

const SidebarContext = createContext<SidebarContextValue>({
  collapsed: false,
  toggleCollapsed: () => {},
  groupStates: {},
  toggleGroup: () => {},
})

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [groupStates, setGroupStates] = useState<Record<string, boolean>>({
    money: true,
    wealth: true,
    tools: true,
    system: true,
  })

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), [])

  const toggleGroup = useCallback((groupKey: string) => {
    setGroupStates((prev) => ({ ...prev, [groupKey]: !prev[groupKey] }))
  }, [])

  return (
    <SidebarContext.Provider value={{ collapsed, toggleCollapsed, groupStates, toggleGroup }}>
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  return useContext(SidebarContext)
}

/** Width constants shared across Sidebar, Header, and main content. */
export const SIDEBAR_WIDTH_EXPANDED = '16rem'   // w-64 = 256px
export const SIDEBAR_WIDTH_COLLAPSED = '4.5rem'  // 72px — icon-only
