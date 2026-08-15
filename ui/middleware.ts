import { NextResponse, type NextRequest } from 'next/server'
import { ACTIVE_COMPATIBILITY_REDIRECTS } from '@/lib/informationArchitecture'
import { getLegacyMoneyRedirect } from '@/lib/moneyRoutes'

/** Compatibility redirects preserve the full old query string and add only the authoritative tab. */
export function middleware(request: NextRequest) {
  const moneyRedirect = getLegacyMoneyRedirect(request.nextUrl.pathname)
  const compatibilityRedirect = ACTIVE_COMPATIBILITY_REDIRECTS.find(({ from }) => from === request.nextUrl.pathname)
  const redirect = moneyRedirect ?? (compatibilityRedirect ? { pathname: compatibilityRedirect.to, view: 'view' in compatibilityRedirect ? compatibilityRedirect.view : undefined } : undefined)
  if (!redirect) return NextResponse.next()
  const url = request.nextUrl.clone()
  url.pathname = redirect.pathname
  if (redirect.view) url.searchParams.set('view', redirect.view)
  return NextResponse.redirect(url)
}

export const config = { matcher: ['/income', '/expenses', '/activity', '/budgeting', '/debts', '/universe', '/recommendations', '/market-briefs', '/accounts'] }
