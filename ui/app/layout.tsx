import './globals.css'
import { spaceGrotesk, jetbrainsMono } from '@/lib/fonts'
import AuthBootstrapProvider from '@/components/providers/AuthBootstrapProvider'
import { NotificationProvider } from '@/components/providers/NotificationContext'
import ToastContainer from '@/components/ui/ToastContainer'
import { BackendUnavailableError } from '@/lib/backendError'

/**
 * Pre-hydration warm-flag bootstrap. Runs SYNCHRONOUSLY in <head>
 * before React loads. If the user already has a session token or a
 * prior warm-flag timestamp, re-arm the warm flag now so the next
 * page mount can skip the splash without waiting for React to call
 * `markBootstrapWarm` during hydration. Self-cleans: never writes
 * a warm flag for a fresh user. Wrapped in try/catch so Safari
 * private mode (localStorage throws) is silently non-fatal.
 *
 * Why this exists: when Next.js dev chunks 404 (stale .next cache),
 * React never hydrates, so no onClick fires and the splash UI is
 * effectively frozen. This script gives the NEXT healthy load the
 * warm data it needs to skip the splash even if THIS load's chunks
 * were served stale. Keys must stay in lockstep with the
 * production `isBootstrapWarm` reads (ui/lib/api.ts).
 */
const PRE_HYDRATION_WARM_KEY = 'fc_bootstrap_warm_at'
const PRE_HYDRATION_TOKEN_KEY = 'fc_session_token'
const PRE_HYDRATION_WARM_SCRIPT = `(function(){try{var w=${JSON.stringify(PRE_HYDRATION_WARM_KEY)};var t=${JSON.stringify(PRE_HYDRATION_TOKEN_KEY)};var oldDm='darkMode';var newDm='atlas_theme';var tok=window.localStorage.getItem(t);var warm=window.localStorage.getItem(w);if(tok||warm){window.localStorage.setItem(w,String(Date.now()));}if(window.localStorage.getItem(oldDm)!==null){window.localStorage.removeItem(oldDm);}var stored=window.localStorage.getItem(newDm);var wantDark=stored==='enabled';if(wantDark){document.documentElement.classList.add('dark');}}catch(e){}
/* Auth splash escape hatches — run BEFORE React hydrates.
   These handle the case where stale .next chunks cause 404s on
   JS bundles, preventing React from ever hydrating. Without these
   raw-JS fallbacks, the user is permanently stuck on the splash
   screen because all existing escape mechanisms require React
   useEffect / onClick to execute. */
try{
  /* 1. ?skip-splash= query param — immediate escape.
     Mark warm so the NEXT reload (without the query) also skips
     the splash. Hide the splash DOM element directly so the user
     sees content even if React never mounts. */
  if(window.location.search.indexOf('skip-splash=')!==-1){
    window.localStorage.setItem(w,String(Date.now()));
    var s=document.querySelector('[aria-label="Securing your session"]');
    if(s)s.style.display='none';
  }
  /* 2. Auto-skip after 8 seconds — the nuclear option.
     If React hasn't hydrated after 8s, something is broken.
     Rather than leave the user stuck forever, force-navigate
     to the current URL with ?skip-splash=1 appended.
     The warm flag is set so future reloads skip the splash
     entirely. */
  var _splashTimer=setTimeout(function(){
    var s=document.querySelector('[aria-label="Securing your session"]');
    if(!s)return;/* Already gone — React hydrated successfully. */
    window.localStorage.setItem(w,String(Date.now()));
    var u=new URL(window.location.href);
    u.searchParams.set('skip-splash',String(Date.now()));
    window.location.assign(u.toString());
  },8000);
  /* 3. Native onclick on the Continue button — works without React.
     If React hydrates, its onClick handler takes over. If it doesn't,
     this raw onclick fires and navigates to ?skip-splash=1. */
  document.addEventListener('DOMContentLoaded',function(){
    var btn=document.querySelector('[data-continue-app]');
    if(btn){
      btn.addEventListener('click',function(){
        clearTimeout(_splashTimer);
        window.localStorage.setItem(w,String(Date.now()));
        var u=new URL(window.location.href);
        u.searchParams.set('skip-splash',String(Date.now()));
        window.location.assign(u.toString());
      });
    }
  });
}catch(e){}})();`

export const metadata = {
  title: 'Atlas - Financial Copilot',
  description: 'Your AI-powered financial advisor',
}

/**
 * SSR-side health probe for the rules-service.
 *
 * We hit ``/health`` directly from the SSR Node process so a backend
 * outage surfaces as a **visible server-rendered alert** instead of a
 * blank loading skeleton. Three deliberate choices:
 *
 *  - **1.5 s timeout** (``clearTimeout`` is in ``finally`` so the timer
 *    is released on every path): cheap-and-fast. A cold-restart BE
 *    with alembic + DB bootstrap will transiently show "unavailable"
 *    while alembic runs — the user refreshes.
 *  - ````cache: 'no-store'````: dev restarts happen often; cached
 *    health results from a previous boot would lie.
 *  - ````.replace('localhost', '127.0.0.1')````: Node 18+ resolves
 *    ``localhost`` to ``::1`` (IPv6) on macOS by default, while
 *    FastAPI binds ``127.0.0.1`` (IPv4). That drift causes a phantom
 *    ``ECONNREFUSED`` during SSR. The replace is a no-op on machines
 *    without the dual-stack issue (and matches the same fix in
 *    ``lib/api.ts`` so client and server agree).
 */
async function checkBackend(): Promise<boolean> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 1500)
  try {
    const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000')
      .replace('localhost', '127.0.0.1')
    const res = await fetch(`${baseUrl}/health`, {
      cache: 'no-store',
      signal: controller.signal,
    })
    return res.ok
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Root Layout (server component).
 *
 * ``<head>`` is rendered ONCE as a direct sibling of ``<body>`` so the
 * Material Symbols font stylesheet is loaded from a valid HTML5
 * position. Putting the ``<link>`` as a direct child of ``<html>``
 * (the prior shape) is invalid HTML — the browser's parser silently
 * auto-corrects it by hoisting the ``<link>`` into an implicit
 * ``<head>``, which then fails React hydration with
 * "Expected server HTML to contain a matching <link> in <html>".
 * Wrapping it in an explicit ``<head>`` keeps the SSR DOM and the
 * browser DOM byte-identical so hydration succeeds.
 *
 * When the BE is unreachable we throw ``BackendUnavailable``. The root
 * ``error.tsx`` boundary catches it and renders the offline shell
 * (Sidebar + Header + ErrorBanner). The layout itself always renders
 * ``{children}`` because Next.js App Router requires it.
 */
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const isUp = await checkBackend()

  // Next.js App Router requires layouts to always render {children}.
  // If the backend is down we throw here and let the nearest error
  // boundary (ui/app/error.tsx) render the offline shell.
  if (!isUp) {
    throw new BackendUnavailableError()
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* next/font injects @font-face + preloads automatically via the
            className on <body>. No additional <link> needed for text fonts. */}
        {/* Pre-hydration warm-flag — see constant above the JSX. */}
        <script dangerouslySetInnerHTML={{ __html: PRE_HYDRATION_WARM_SCRIPT }} />
      </head>
      <body className={`bg-background text-foreground ${spaceGrotesk.variable} ${jetbrainsMono.variable}`}>
        {/* Skip navigation link — accessible keyboard shortcut to main content */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[9999] focus:px-4 focus:py-2 focus:bg-[var(--primary-500)] focus:text-white focus:rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--primary-500)]"
        >
          Skip to main content
        </a>
        <AuthBootstrapProvider>
          <NotificationProvider>
            {children}
            <ToastContainer />
          </NotificationProvider>
        </AuthBootstrapProvider>
      </body>
    </html>
  )
}