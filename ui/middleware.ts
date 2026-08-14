import { NextResponse, type NextRequest } from 'next/server'
import { getLegacyMoneyRedirect } from '@/lib/moneyRoutes'

/** Compatibility redirects preserve the full old query string and add only the authoritative tab. */
export function middleware(request: NextRequest) {
  const redirect = getLegacyMoneyRedirect(request.nextUrl.pathname)
  if (!redirect) return NextResponse.next()
  const url = request.nextUrl.clone()
  url.pathname = redirect.pathname
  url.searchParams.set('view', redirect.view)
  return NextResponse.redirect(url)
}

export const config = { matcher: ['/income', '/expenses', '/activity', '/budgeting'] }
