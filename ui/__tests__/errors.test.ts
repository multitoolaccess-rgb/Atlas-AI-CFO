/**
 * Vitest test for `ui/lib/errors.ts::classifyError` + `classifyErrorMessage`.
 *
 * Why this is a consolidated surface test:
 *   - The classifier is the FE's single source of truth for friendly
 *     error messages. Every page imports `classifyErrorMessage(err)`
 *     directly; if we lose a status (e.g. someone refactors and
 *     drops the 502 branch) every page silently reverts to the old
 *     "Your session expired" flash — exactly the bug we're fixing.
 *   - The matrix covers: 401 (session expired), 409 (validation),
 *     502 (downstream unavailable — Phase F2 #2), 5xx (server),
 *     503 (server), 4xx (other), no-response (network), non-object
 *     input.
 *
 * Round-trip contract: the friendly strings are pinned verbatim so
 * screenshots + Playwright text-matches stay stable. A drift in the
 * user-facing wording shows up here BEFORE it lands in the UI.
 */
import { describe, expect, it } from 'vitest'
import {
  classifyError,
  classifyErrorMessage,
  type ClassifiedError,
} from '@/lib/errors'

describe('classifyError — 401 (local auth failure)', () => {
  it('renders "Your session expired…" with category session-expired', () => {
    const axErr = {
      response: { status: 401, data: { detail: 'invalid token: expired' } },
      config: { headers: { set: () => undefined } },
      message: 'Request failed with status code 401',
    }
    const out: ClassifiedError = classifyError(axErr)
    expect(out.message).toMatch(/session expired/i)
    expect(out.category).toBe('session-expired')
    expect(out.cause).toBe(axErr)
  })
})

describe('classifyError — 409 (validation)', () => {
  it('surfaces the upstream detail verbatim', () => {
    const axErr = {
      response: {
        status: 409,
        data: { detail: 'A record with that value already exists.' },
      },
      message: 'Conflict',
    }
    const out = classifyError(axErr)
    expect(out.message).toBe('A record with that value already exists.')
    expect(out.category).toBe('validation')
  })

  it('falls back to friendly default when detail is missing', () => {
    const axErr = { response: { status: 409, data: {} }, message: 'Conflict' }
    const out = classifyError(axErr)
    expect(out.message).toMatch(/already taken/i)
    expect(out.category).toBe('validation')
  })
})

describe('classifyError — 502 (Phase F2 #2 downstream unavailable)', () => {
  it('renders "Downstream service is unavailable…" with category downstream-unavailable', () => {
    const axErr = {
      response: {
        status: 502,
        data: {
          detail:
            'Finlynq upstream returned HTTP 401 on GET /state/summary. ' +
            'Local auth succeeded; this is a downstream config drift...',
        },
      },
      message: 'Request failed with status code 502',
    }
    const out = classifyError(axErr)
    expect(out.message).toMatch(/Downstream service/i)
    expect(out.category).toBe('downstream-unavailable')
  })

  it('maps BOTH Finlynq-401-via-forwarder-4xx-verbatim AND Finlynq-refusal-502 to downstream-unavailable category', () => {
    // After Phase F2 #2 fix, Finlynq 4xx-via-forwarder maps to OUR 502;
    // and Finlynq-5xx-via-forwarder maps to OUR 502 as well. Both must
    // land in the same downstream-unavailable category so the FE
    // shows the same friendly "downstream" banner.
    const fourOhOneRelayed = {
      response: { status: 502, data: { detail: 'downstream JWT drift' } },
      message: '502',
    }
    const fiveOhThree = {
      response: { status: 502, data: { detail: 'Finlynq upstream 503' } },
      message: '502',
    }
    expect(classifyError(fourOhOneRelayed).category).toBe(
      'downstream-unavailable',
    )
    expect(classifyError(fiveOhThree).category).toBe('downstream-unavailable')
  })
})

describe('classifyError — 5xx (server)', () => {
  it('503 maps to category=server, message surfaces detail when present', () => {
    const axErr = {
      response: { status: 503, data: { detail: 'Database down.' } },
      message: 'Service Unavailable',
    }
    const out = classifyError(axErr)
    expect(out.message).toBe('Database down.')
    expect(out.category).toBe('server')
  })

  it('500 falls back to the friendly default', () => {
    const out = classifyError({
      response: { status: 500, data: {} },
      message: 'Internal Server Error',
    })
    expect(out.message).toMatch(/server hit an error/i)
    expect(out.category).toBe('server')
  })
})

describe('classifyError — other 4xx (unknown)', () => {
  it('404 with detail surfaces the detail verbatim and lands in `unknown`', () => {
    const axErr = {
      response: { status: 404, data: { detail: 'Goal not found' } },
      message: 'Not Found',
    }
    const out = classifyError(axErr)
    expect(out.message).toBe('Goal not found')
    expect(out.category).toBe('unknown')
  })

  it('422 without upstream detail surfaces the axios `message` so the dev sees the real cause', () => {
    // When the upstream detail is missing, classifyError falls back
    // to ``err.message`` -- the axios label like "Unprocessable
    // Entity" or "Bad Request" which is more useful than a generic
    // "The server rejected the request" placeholder. The last-resort
    // "rejected the request" string only fires for non-object input;
    // pinning this behavior so a future "always friendly default"
    // change doesn't accidentally drop the actionable label.
    const out = classifyError({
      response: { status: 422, data: {} },
      message: 'Unprocessable Entity',
    })
    expect(out.message).toBe('Unprocessable Entity')
    expect(out.category).toBe('unknown')
  })
})

describe('classifyError — network failure (no response)', () => {
  it('renders the BE-down message and lands in `network`', () => {
    const axErr = {
      request: {},
      // axios sets response=undefined when the request never completed
      response: undefined,
      message: 'Network Error',
    }
    const out = classifyError(axErr)
    expect(out.message).toMatch(/Can't reach the backend/i)
    expect(out.category).toBe('network')
  })
})

describe('classifyError — defensive null/non-object input', () => {
  it('null returns a friendly default message', () => {
    const out = classifyError(null)
    expect(out.message).toMatch(/server rejected the request/i)
    expect(out.category).toBe('unknown')
  })

  it('undefined returns the same default', () => {
    const out = classifyError(undefined)
    expect(out.category).toBe('unknown')
  })

  it('a thrown string still gracefully returns unknown', () => {
    const out = classifyError('Boom')
    expect(out.category).toBe('unknown')
    expect(out.cause).toBe('Boom')
  })
})

describe('classifyErrorMessage — string-only wrapper', () => {
  it('returns just the message string (the common case)', () => {
    const axErr = {
      response: { status: 401, data: { detail: 'token expired' } },
      message: '401',
    }
    expect(classifyErrorMessage(axErr)).toMatch(/session expired/i)
  })
})

describe('classifyError — happy-path invariants', () => {
  it('never returns an empty string', () => {
    const all: Array<unknown> = [
      null,
      undefined,
      'string',
      42,
      {},
      { response: undefined },
      { response: { status: 401 } },
      { response: { status: 502 } },
      { response: { status: 500 } },
      { response: { status: 999 } },
      { response: { status: 200, data: {} } },
    ]
    for (const input of all) {
      expect(classifyError(input).message.length).toBeGreaterThan(0)
    }
  })

  it('every category is one of the documented buckets', () => {
    const inputs = [
      { response: { status: 401 } },
      { response: { status: 409 } },
      { response: { status: 502 } },
      { response: { status: 500 } },
      { response: { status: 404 } },
      {},
      null,
    ]
    const allowed: Array<string> = [
      'session-expired',
      'downstream-unavailable',
      'validation',
      'server',
      'network',
      'unknown',
    ]
    for (const input of inputs) {
      expect(allowed).toContain(classifyError(input).category)
    }
  })
})
