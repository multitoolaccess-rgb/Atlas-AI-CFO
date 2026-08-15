'use client'

import PageLayout from '@/components/layout/PageLayout'
import AnimatedPageSection from '@/components/ui/AnimatedPageSection'
import { GlobalFilterProvider } from '@/components/ui/GlobalFilterContext'
import DebtsContent from '@/components/debts/DebtsContent'

export default function DebtsPage() {
  return <PageLayout><GlobalFilterProvider><AnimatedPageSection><DebtsContent /></AnimatedPageSection></GlobalFilterProvider></PageLayout>
}
