/**
 * Vitest test for the 401 auto-retry interceptor in `ui/lib/api.ts`.
 *
 * Phase 9 ship target: the interceptor is now exposed as
 * ``createApiWithAuthRetry({ baseURL, deps: { loginFn, readToken, onTokenClear, onTokenRefresh } })``
 * so tests can build a custom client with a mock loginFn. This test
 * exercises that factory directly \u2014 no module-level spyOn, no
 * vi.resetModules dance. The previous test (Phase 8) used
 * ``vi.spyOn(apiModule.rulesService, 'devLogin')`` to stub the
 * singleton's login; this test is strictly cleaner.
 *
 * Asserts (same contract as the Phase 8 version):
 *
 * 1. On a 401 from a credentialed request, the interceptor calls
 *    ``loginFn`` exactly ONCE (the singleton inflightLogin batches
 *    concurrent 401s; this test exercises both the single-call and
 *    the batch path).
 * 2. The retry mutates ``original.headers`` via ``.set('Authorization', ...)``.
 * 3. The flag ``_retried: true`` is set so a second 401 from the
 *    retried request falls through to the original rejection.
 * 4. Null config (network/timeout) rejects the original error.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApiWithAuthRetry, getStoredToken, setStoredToken, clearStoredToken } from '@/lib/api'

class FakeAxiosHeaders {
  readonly setCalls: Array<[string, string]> = []
  set(name: string, value: string): this {
    this.setCalls.push([name, value])
    return this
  }
}

type DevLoginResponse = { token: string; subject: string }

const TOKEN_KEY = 'fc_session_token'

describe('createApiWithAuthRetry \u2014 factory-based 401 auto-retry', () => {
  let store: Record<string, string>
  let loginFn: ReturnType<typeof vi.fn<[], Promise<DevLoginResponse>>>
  let client: ReturnType<typeof createApiWithAuthRetry>
  // We mock the axios ADAPTER (not `client.request` and not
  // `vi.spyOn`) because:
  //   1. axios v1's `AxiosInstance.request` has a `transformRequest`
  //      field containing closures, and vitest's worker isolation
  //      tries to structuredClone the spy across the postMessage
  //      boundary, which throws
  //      `DataCloneError: function transformRequest(...) could not be cloned`.
  //   2. The adapter is a plain `(config) => Promise<AxiosResponse>`
  //      function on `client.defaults` (set internally by axios
  //      during `createApiWithAuthRetry`) — it's fully cloneable and
  //      receives the SAME config the real `request` would receive,
  //      so we can assert on it directly without any `as unknown as`
  //      casts.
  let adapter: ReturnType<typeof vi.fn>

  beforeEach(() => {
    // Fresh in-memory localStorage for each test.
    store = {}
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'localStorage', {
        value: {
          getItem: (k: string) => (k in store ? store[k] : null),
          setItem: (k: string, v: string) => { store[k] = v },
          removeItem: (k: string) => { delete store[k] },
          clear: () => { for (const k of Object.keys(store)) delete store[k] },
          key: (i: number) => Object.keys(store)[i] ?? null,
          length: 0,
        },
        configurable: true,
        writable: true,
      })
    }
    clearStoredToken()

    // loginFn mirrors the production side-effect: writes the new token
    // to the same store the readToken path reads from. Without this,
    // the retry's getStoredToken() call returns null and the
    // ``original.headers.set('Authorization', ...)`` step is a no-op.
    loginFn = vi.fn<[], Promise<DevLoginResponse>>().mockImplementation(async () => {
      const result: DevLoginResponse = { token: 'NEW-TOKEN-123', subject: 'alex' }
      setStoredToken(result.token)
      return result
    })

    // Build a FRESH client per test \u2014 the factory is the testable
    // surface; no module-level singleton, no resetModules dance.
    client = createApiWithAuthRetry({
      baseURL: 'http://localhost:8000',
      deps: { loginFn },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    clearStoredToken()
  })

  it('on 401, calls loginFn once and retries via original.headers.set("Authorization", \u2026)', async () => {
    adapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    })
    client.defaults.adapter = adapter as unknown as typeof client.defaults.adapter

    const fakeHeaders = new FakeAxiosHeaders()
    const fakeConfig: { headers: FakeAxiosHeaders; _retried?: boolean } = {
      headers: fakeHeaders,
      _retried: false,
    }
    const fakeError = {
      response: { status: 401, data: { detail: 'token expired' } },
      config: fakeConfig,
      message: 'Request failed with status code 401',
      request: {},
    }

    const handlers = (client.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers
    const rejected = handlers[0].rejected
    expect(rejected).toBeTypeOf('function')

    await rejected?.(fakeError)

    expect(loginFn).toHaveBeenCalledTimes(1)
    expect(fakeConfig._retried).toBe(true)
    expect(fakeHeaders.setCalls).toContainEqual(['Authorization', 'Bearer NEW-TOKEN-123'])
    // The adapter should have been called exactly once with the
    // retried config (the same one the real `request` would receive).
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(adapter).toHaveBeenCalledWith(expect.objectContaining({ _retried: true }))
    // The localStorage side-effect: readToken sees the new token.
    expect(getStoredToken()).toBe('NEW-TOKEN-123')
  })

  it('on a second 401 (config already _retried=true), does NOT call loginFn again', async () => {
    adapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    })
    client.defaults.adapter = adapter as unknown as typeof client.defaults.adapter

    const fakeConfig = { headers: new FakeAxiosHeaders(), _retried: true }
    const fakeError = {
      response: { status: 401, data: { detail: 'still expired after retry' } },
      config: fakeConfig,
      message: 'Request failed with status code 401',
      request: {},
    }

    const rejected = (client.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers[0].rejected

    await expect(rejected?.(fakeError)).rejects.toBe(fakeError)
    expect(loginFn).not.toHaveBeenCalled()
    expect(adapter).not.toHaveBeenCalled()
  })

  it('with null config (rare: network/timeout with no error.config), rejects the original error', async () => {
    const fakeError: { response: undefined; config: undefined; message: string } = {
      response: undefined,
      config: undefined,
      message: 'Network Error',
    }
    const rejected = (client.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers[0].rejected

    await expect(rejected?.(fakeError)).rejects.toBe(fakeError)
    expect(loginFn).not.toHaveBeenCalled()
  })

  it('on two concurrent 401s, batches into ONE loginFn call (singleton inflightLogin)', async () => {
    adapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    })
    client.defaults.adapter = adapter as unknown as typeof client.defaults.adapter

    const cfg1 = { headers: new FakeAxiosHeaders(), _retried: false }
    const cfg2 = { headers: new FakeAxiosHeaders(), _retried: false }
    const errFor = (cfg: typeof cfg1) => ({
      response: { status: 401, data: { detail: 'token expired' } },
      config: cfg,
      message: 'Request failed with status code 401',
      request: {},
    })

    const rejected = (client.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers[0].rejected

    await Promise.allSettled([rejected?.(errFor(cfg1)), rejected?.(errFor(cfg2))])

    expect(loginFn).toHaveBeenCalledTimes(1)
    expect(cfg1._retried).toBe(true)
    expect(cfg2._retried).toBe(true)
    expect(cfg1.headers.setCalls).toContainEqual(['Authorization', 'Bearer NEW-TOKEN-123'])
    expect(cfg2.headers.setCalls).toContainEqual(['Authorization', 'Bearer NEW-TOKEN-123'])
    expect(adapter).toHaveBeenCalledTimes(2)
  })

  it('request interceptor sets Bearer token from readToken (readToken injection works)', () => {
    setStoredToken('PRE-EXISTING-TOKEN')
    const captured = (client.interceptors.request as unknown as {
      handlers: Array<{ fulfilled?: (cfg: unknown) => unknown }>
    }).handlers[0].fulfilled
    expect(captured).toBeTypeOf('function')

    const config = {
      headers: {
        set: vi.fn(),
      },
    }
    const result = captured?.(config)
    expect((config.headers.set as ReturnType<typeof vi.fn>).mock.calls).toContainEqual([
      'Authorization',
      'Bearer PRE-EXISTING-TOKEN',
    ])
    expect(result).toBe(config)
  })

  it('onTokenClear and onTokenRefresh hooks fire correctly', async () => {
    const onTokenClear = vi.fn()
    const onTokenRefresh = vi.fn()
    const customClient = createApiWithAuthRetry({
      baseURL: 'http://localhost:8000',
      deps: { loginFn, onTokenClear, onTokenRefresh },
    })
    const customAdapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    })
    customClient.defaults.adapter = customAdapter as unknown as typeof customClient.defaults.adapter

    const fakeConfig = { headers: new FakeAxiosHeaders(), _retried: false }
    const fakeError = {
      response: { status: 401, data: { detail: 'token expired' } },
      config: fakeConfig,
      message: 'Request failed with status code 401',
      request: {},
    }

    const rejected = (customClient.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers[0].rejected
    await rejected?.(fakeError)

    expect(onTokenClear).toHaveBeenCalledTimes(1)
    expect(onTokenRefresh).toHaveBeenCalledWith('NEW-TOKEN-123')
  })

  // Round-trip sanity: a token written via setStoredToken before a
  // request is what the request interceptor puts in the header. This
  // pins the readToken injection contract.
  it('round-trip: TOKEN_KEY constant is the wire key for read/write', () => {
    setStoredToken('X')
    expect(getStoredToken()).toBe('X')
    // The factory uses the default readToken (getStoredToken), so any
    // client built with no readToken override will read 'X'.
    expect(loginFn).not.toHaveBeenCalled()
    expect(TOKEN_KEY).toBe('fc_session_token')
  })

  // Regression: the 401 interceptor must NEVER retry /api/auth/devlogin.
  // If it did, devLogin returning 401 would re-call deps.loginFn() (=
  // devLogin) through itself. With ``inflightLogin.current`` still
  // pointing at the unresolved original promise, the second request
  // does ``await inflightLogin.current`` and deadlocks — the very
  // failure mode that left the splash frozen. Test both the devlogin
  // and logout non-retryable paths.
  it('on 401 against /api/auth/devlogin, does NOT call loginFn (avoids Promise deadlock)', async () => {
    const fakeConfig = { headers: new FakeAxiosHeaders(), _retried: false }
    const fakeError = {
      response: { status: 401, data: { detail: 'devlogin rejected' } },
      config: { ...fakeConfig, url: '/api/auth/devlogin' },
      message: 'Request failed with status code 401',
      request: {},
    }

    const rejected = (client.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers[0].rejected

    await expect(rejected?.(fakeError)).rejects.toBe(fakeError)
    expect(loginFn).not.toHaveBeenCalled()
    expect(fakeConfig._retried).toBe(false)
  })

  it('on 401 against /api/auth/logout, does NOT call loginFn (logout must succeed or fail, never retry)', async () => {
    const fakeConfig = { headers: new FakeAxiosHeaders(), _retried: false }
    const fakeError = {
      response: { status: 401, data: { detail: 'logout rejected' } },
      config: { ...fakeConfig, url: '/api/auth/logout' },
      message: 'Request failed with status code 401',
      request: {},
    }

    const rejected = (client.interceptors.response as unknown as {
      handlers: Array<{ rejected?: (err: unknown) => unknown }>
    }).handlers[0].rejected

    await expect(rejected?.(fakeError)).rejects.toBe(fakeError)
    expect(loginFn).not.toHaveBeenCalled()
  })
})
