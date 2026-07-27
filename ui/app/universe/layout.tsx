import { ReactNode } from 'react'
import { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Financial Universe — Atlas',
}

export default function UniverseLayout({
  children,
}: {
  children: ReactNode
}) {
  return <>{children}</>
}
