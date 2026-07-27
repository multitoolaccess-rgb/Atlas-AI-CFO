'use client'

import { useEffect, useState } from 'react'
import Sidebar from './Sidebar'
import Header from './Header'
import { SidebarProvider, useSidebar } from './SidebarContext'
import CopilotRoot from '@/components/copilot/CopilotRoot'
import { rulesService, type Profile } from '@/lib/api'

/**
 * Shared page chrome for the 7 non-Overview routes. Each page is a
 * `'use client'` component that fetches its own domain data, then
 * renders its body inside <PageLayout>. The layout itself handles
 * devLogin + getProfile (the same bootstrap that app/page.tsx does)
 * so the Sidebar avatar + Header profile work consistently, and
 * every page is one consistent DOM tree.
 *
 * Why a shared layout vs. inlining Sidebar+Header in every page:
 *   - Single source of truth for the bootstrap side effect
 *   - Pages don't each need to remember to import devLogin
 *   - Visual consistency is enforced
 *   - A future "Settings changes the layout" PR only edits one file
 */
function PageLayoutInner({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const { collapsed } = useSidebar()

  useEffect(() => {
    // AuthBootstrapProvider (mounted in the root layout) is the single
    // source of truth for the devLogin handshake — it centralises the
    // cold-start JWT mint and gates the tree behind a splash. By the
    // time this useEffect runs, either (a) splash has succeeded and
    // a token exists in localStorage so getProfile will authorise, or
    // (b) the user clicked Skip and there is no token; getProfile
    // will 401 and we silently render without a profile.
    //
    // Do NOT call devLogin from here. Doing so races the
    // AuthBootstrapProvider's own devLogin AND re-triggers the
    // axios 401 interceptor's deadlock when the handshake is
    // already in flight elsewhere — the very failure mode that
    // stranded users on the splash.
    let cancelled = false
    rulesService
      .getProfile()
      .then((p) => {
        if (!cancelled) {
          setProfile(p)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <Sidebar />
      <Header profile={profile} loading={loading} />
      <main
        className="p-8 pt-4 transition-all duration-300 ease-in-out ml-[var(--layout-ml)]"
        style={{ '--layout-ml': collapsed ? '4.5rem' : '16rem' } as React.CSSProperties}
      >{children}</main>
      {/* Phase 4 — Persistent AI Copilot (orb + dock).
          On non-dashboard pages we render with empty insights; the user
          can still open Scout via the orb and ask questions, just without
          the proactive insight feed (which only the dashboard populates). */}
      <CopilotRoot />
    </>
  )
}

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <PageLayoutInner>{children}</PageLayoutInner>
    </SidebarProvider>
  )
}
