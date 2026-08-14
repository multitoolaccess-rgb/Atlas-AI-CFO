'use client'

import { createContext, useContext, type ReactNode } from 'react'

const EmbeddedMoneyViewContext = createContext(false)

/** Reuse legacy page content in an activated Money destination without route chrome. */
export function EmbeddedMoneyView({ children }: { children: ReactNode }) {
  return <EmbeddedMoneyViewContext.Provider value>{children}</EmbeddedMoneyViewContext.Provider>
}

export function useEmbeddedMoneyView(): boolean {
  return useContext(EmbeddedMoneyViewContext)
}
