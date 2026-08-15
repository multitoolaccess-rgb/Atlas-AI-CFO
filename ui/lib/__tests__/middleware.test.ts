import { describe, expect, it } from 'vitest'
import { NextRequest } from 'next/server'
import { middleware } from '@/middleware'

describe('information architecture compatibility middleware', () => {
  it('redirects legacy Decisions routes while preserving query state', () => {
    const response = middleware(new NextRequest('http://localhost/recommendations?goal=7&cursor=next'))
    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('http://localhost/decisions?goal=7&cursor=next&view=recommendations')
  })

  it('redirects legacy Market Briefs without discarding archive context', () => {
    const response = middleware(new NextRequest('http://localhost/market-briefs?brief=abc'))
    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('http://localhost/market-intelligence?brief=abc')
  })

  it('does not activate the Accounts compatibility redirect before System migration', () => {
    const response = middleware(new NextRequest('http://localhost/accounts?tab=all'))
    expect(response.status).toBe(200)
    expect(response.headers.get('location')).toBeNull()
  })
})
