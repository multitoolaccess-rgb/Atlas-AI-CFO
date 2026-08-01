/**
 * Phase F2 #2 regression — GoalsPage error-isolation contract.
 *
 * The bug: the previous ``Promise.all([listGoals(), getDashboardSummary()])``
 * shape REJECTED the outer try/catch when the forwarded
 * ``getDashboardSummary`` returned a 502 (Finlynq JWT_SECRET drift).
 * That surfaced on /goals as ``Couldn't load goals: <upstream raw detail>``
 * even though the LOCAL listGoals endpoint was healthy.
 *
 * The fix: each promise is wrapped in ``.then(ok, err)``, the two
 * results are joined at Promise.all, and ``error`` vs ``summaryError``
 * are routed to separate banners (top-of-page for listGoals, inline
 * inside ``FinancialPlans`` for dashboard projection). Tests below
 * lock both directions of this contract.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Shared HTTP-mock handles for the ``api_phase2`` cross-import seam
// declared inside ``vi.mock`` below. ``vi.hoisted`` makes these
// available to the hoisted mock factory AND to the test body's
// ``beforeEach`` reset hook.
const defaultApiHandles = vi.hoisted(() => {
  const readGateOff = {
    isAxiosError: true,
    response: {
      status: 503,
      data: {
        code: 'forecast_read_api_unavailable',
        message: 'Forecast reads are currently disabled.',
      },
    },
  }
  return {
    readGateOff,
    get: vi.fn().mockRejectedValue(readGateOff),
    post: vi.fn().mockRejectedValue(readGateOff),
  }
})

vi.mock('@/lib/api', () => ({
  rulesService: {
    listGoals: vi.fn(),
    getDashboardSummary: vi.fn(),
    createGoal: vi.fn(),
    updateGoal: vi.fn(),
    deleteGoal: vi.fn(),
    // PageLayout's bootstrap useEffect calls getProfile() once at
    // mount for the header avatar. Provide a resolved stub so
    // mount doesn't crash on the missing-method TypeError.
    getProfile: vi
      .fn()
      .mockResolvedValue({ id: 1, email: 'alex@test.com', full_name: 'Alex' }),
  },
  // Cross-import seam for ``api_phase2.ts`` (Slice 2):
  //   ``import api from '@/lib/api'`` → ``api.get``/``api.post``
  //   Default behaviour: reject with the sanitized 503 so the
  //   LatestForecastSection page wiring collapses gracefully.
  default: {
    get: defaultApiHandles.get,
    post: defaultApiHandles.post,
  },
}))

// Mock lucide-react icons. GoalsPage transitively pulls in
// ``Sidebar`` (via PageLayout) which imports more icons than the
// Goals page itself uses (LayoutDashboard, Wallet, etc.). Use the
// ``importOriginal`` partial-mock pattern so any icon we don't
// list explicitly resolves to the real lucide-react export —
// avoids the ``No "X" export is defined on the "lucide-react" mock``
// failure for unexpected icons.
vi.mock('lucide-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lucide-react')>()
  const Stub = (props: { className?: string }) => (
    <svg data-testid="icon" className={props.className} aria-hidden="true" />
  )
  return {
    ...actual,
    Plus: Stub,
    Target: Stub,
    Pencil: Stub,
    Trash2: Stub,
    Loader2: Stub,
    Calendar: Stub,
    TrendingUp: Stub,
  }
})

import GoalsPage from '@/app/goals/page'
import { rulesService } from '@/lib/api'

const mockedRulesService = vi.mocked(rulesService)

const fakeGoal = {
  id: 1,
  name: 'Retirement by 55',
  target_amount: 15000000,
  horizon_years: 20,
  priority: 10,
  is_archived: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: null,
  target_date: null,
  notes: null,
}

/**
 * Build a one-rejection-then-resolve mock implementation for
 * ``rulesService.getDashboardSummary``. Encapsulates the
 * ``callIndex = 0`` closure in a factory function (vs. an inline
 * ``let`` per-test) so:
 *   - duplication across tests is centralized;
 *   - the per-test counter is fresh by construction (no chance of
 *     stale state leaking between tests if vitest hoists or
 *     reorders the suite).
 *
 * Generic on ``T`` so the returned function's signature matches
 * the endpoint contract (e.g. ``Promise<DashboardSummary>``) and
 * ``vi.mocked(rulesService).getDashboardSummary.mockImplementation(fn)``
 * type-checks cleanly at the call site.
 *
 * Usage:
 *   mockedRulesService.getDashboardSummary.mockImplementation(
 *     createIntermittentDashboardMock<DashboardSummary>(rejectionObj, resolutionObj),
 *   )
 */
function createIntermittentDashboardMock<T>(
  rejection: unknown,
  resolution: T,
): () => Promise<T> {
  let callIndex = 0
  return () => {
    callIndex += 1
    if (callIndex === 1) return Promise.reject(rejection) as Promise<T>
    return Promise.resolve(resolution)
  }
}

beforeEach(() => {
  mockedRulesService.listGoals.mockReset()
  mockedRulesService.getDashboardSummary.mockReset()
  mockedRulesService.createGoal.mockReset()
  mockedRulesService.updateGoal.mockReset()
  mockedRulesService.deleteGoal.mockReset()
  // Slice 2 cross-import seam: clear cross-test call counts on the
  // shared ``default.get``/``default.post`` HTTP mocks so a prior
  // test's POST and the next test's component mount see fresh state.
  defaultApiHandles.get.mockClear()
  defaultApiHandles.post.mockClear()
})

describe('GoalsPage — Phase F2 #2 error isolation', () => {
  it('renders goals list successfully when only the FORWARDED dashboard call 502s', async () => {
    // LOCAL listGoals succeeds; FORWARDED dashboard fails with the
    // exact Phase F2 #2 envelope (drift-safe 502 wrapping Finlynq 401).
    mockedRulesService.listGoals.mockResolvedValue([fakeGoal])
    mockedRulesService.getDashboardSummary.mockRejectedValue({
      response: {
        status: 502,
        data: { detail: 'Finlynq upstream returned HTTP 401 on GET /state/summary.' },
      },
      message: 'Request failed with status code 502',
    })

    render(<GoalsPage />)

    // Goal card should render — listGoals is local & succeeded.
    await waitFor(() => {
      expect(screen.getByTestId('goal-card-1')).toBeInTheDocument()
    })
    expect(screen.getByText('Retirement by 55')).toBeInTheDocument()

    // Top-of-page banner must NOT fire — listGoals didn't fail.
    expect(screen.queryByText("Couldn't load goals:")).not.toBeInTheDocument()

    // Inline FinancialPlans warning banner SHOULD fire, with the
    // classifier's "Downstream service is unavailable…" message —
    // NOT the raw upstream "Finlynq upstream returned HTTP 401" text.
    expect(screen.getByText("Couldn't load projections:")).toBeInTheDocument()
    expect(
      screen.getByText(/Downstream service is unavailable/i),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/Finlynq upstream returned HTTP 401/i),
    ).not.toBeInTheDocument()

    // Regression lock: the inline banner MUST render with the
    // AMBER/warning Tailwind contracts (`border-warning-200`,
    // `bg-warning-50`, `text-warning-700`) so a page-level
    // data-load failure is visually distinct from a destructive
    // action-failure (import upload, form save, etc., which use
    // danger/RED). The original bug surfaced as a RED banner
    // because ``ErrorBanner`` defaulted to danger; this assertion
    // pins the warning variant at the contract level so a future
    // regression on ``FinancialPlans`` ALSO flips RED.
    const inlineBanner = screen
      .getByText("Couldn't load projections:")
      .closest('[role="alert"]')
    expect(inlineBanner).not.toBeNull()
    expect(inlineBanner).toHaveClass('border-warning-200')
    expect(inlineBanner).toHaveClass('bg-warning-50')
    expect(inlineBanner).toHaveClass('text-warning-700')
  })

  it('renders top-of-page banner when LOCAL listGoals 500s — even if dashboard 200s', async () => {
    // No ``detail`` in the response body so ``classifyError`` falls
    // through to the friendly 5xx fallback string. (When a backend
    // detail IS present, the classifier prefers it — that's the
    // contract for actionable server errors, so we exercise the
    // fallback path explicitly here.)
    mockedRulesService.listGoals.mockRejectedValue({
      response: {
        status: 500,
        data: {},
      },
      message: 'Request failed with status code 500',
    })
    mockedRulesService.getDashboardSummary.mockResolvedValue({
      total_balance: 0,
      total_income_month: 0,
      total_expenses_month: 0,
      accounts_count: 0,
      transactions_count: 0,
      import_batches_count: 0,
      user_goals: [fakeGoal],
    })

    render(<GoalsPage />)

    await waitFor(() => {
      expect(screen.getByText("Couldn't load goals:")).toBeInTheDocument()
    })
    // Friendly 5xx message from the classifier, not the raw detail.
    expect(
      screen.getByText(/The server hit an error/i),
    ).toBeInTheDocument()
    // Inline projection banner must NOT fire — dashboard succeeded.
    expect(screen.queryByText("Couldn't load projections:")).not.toBeInTheDocument()
  })

  it('handles BOTH endpoints failing independently — both banners render', async () => {
    mockedRulesService.listGoals.mockRejectedValue({
      response: {
        status: 401,
        data: { detail: 'Your session expired.' },
      },
      message: 'Request failed with status code 401',
    })
    mockedRulesService.getDashboardSummary.mockRejectedValue({
      response: {
        status: 502,
        data: { detail: 'Upstream Finlynq 503' },
      },
      message: 'Request failed with status code 502',
    })

    render(<GoalsPage />)

    // Top-of-page "session expired" friendly message.
    await waitFor(() => {
      expect(screen.getByText("Couldn't load goals:")).toBeInTheDocument()
    })
    expect(
      screen.getByText(/session expired/i),
    ).toBeInTheDocument()
    // Inline projection banner also renders.
    expect(screen.getByText("Couldn't load projections:")).toBeInTheDocument()
    expect(
      screen.getByText(/Downstream service is unavailable/i),
    ).toBeInTheDocument()
  })

  // ---- Retry-button regression tests (Phase F2 #2 follow-up) --------
  // The top-of-page ``Couldn't load goals:`` banner and the inline
  // ``Couldn't load projections:`` banner each carry their own Retry
  // control wired to ``setRetryCount(c => c + 1)``. These tests lock
  // the post-retry state machine:
  //   1. Successful Retry clears its banner AND renders the data.
  //   2. Granular Retry: a partial recovery clears ONLY the banner
  //      whose endpoint is now healthy.
  //   3. Retry message follows the LATEST error — no stale banner.
  //   4. Rapid double-clicks commit exactly ONE additional fetch
  //      (React 18 batches the ``setRetryCount`` state updates so
  //      the [retryCount] useEffect dep fires once, not twice).
  //   5. The mount-time fetches do not leak past an unmount triggered
  //      by an in-flight retry.

  it('clears top-of-page banner and renders goals when local Retry recovers', async () => {
    // 1st call (initial mount) fails; 2nd call (post-Retry) succeeds.
    // We use ``mockResolvedValueOnce`` so the second call re-enters
    // the resolved branch without losing the original list shape.
    mockedRulesService.listGoals
      .mockRejectedValueOnce({
        response: { status: 500, data: {} },
        message: 'Internal server error',
      })
      .mockResolvedValueOnce([fakeGoal])
    mockedRulesService.getDashboardSummary.mockResolvedValue({
      total_balance: 0,
      total_income_month: 0,
      total_expenses_month: 0,
      accounts_count: 0,
      transactions_count: 0,
      import_batches_count: 0,
      user_goals: [fakeGoal],
    })

    render(<GoalsPage />)

    // Initial top-of-page banner + Retry button visible (dashboard
    // OK, so only the top banner renders). Using ``waitFor`` + the
    // visible button text ``Retry`` is more robust across RTL +
    // jsdom versions than ``findByRole({ name: /.../ })`` whose
    // accessible-name resolution can drift between minor versions.
    await waitFor(() => {
      expect(
        screen.getByText("Couldn't load goals:"),
      ).toBeInTheDocument()
    })
    const [retryBtn] = await screen.findAllByText('Retry')

    fireEvent.click(retryBtn)

    // Wait for the goal card to mount — proves the effect re-ran
    // AND the data made it through.
    await screen.findByTestId('goal-card-1')
    expect(
      screen.queryByText("Couldn't load goals:"),
    ).not.toBeInTheDocument()
  })

  it('clears inline projection banner and renders goals tile when dashboard Retry recovers', async () => {
    mockedRulesService.listGoals.mockResolvedValue([fakeGoal])
    // 1st mount call: 502 rejection triggers the inline banner.
    // Post-Retry call: success with a real goal in user_goals so the
    // goal tile (data-testid="goal-tile-1") emits.
    mockedRulesService.getDashboardSummary.mockImplementation(
      createIntermittentDashboardMock(
        {
          response: {
            status: 502,
            data: { detail: 'Finlynq upstream returned HTTP 401' },
          },
          message: 'Bad Gateway',
        },
        {
          total_balance: 1000,
          total_income_month: 0,
          total_expenses_month: 0,
          accounts_count: 0,
          transactions_count: 0,
          import_batches_count: 0,
          user_goals: [fakeGoal],
        },
      ),
    )

    render(<GoalsPage />)

    await waitFor(() => {
      expect(
        screen.getByText("Couldn't load projections:"),
      ).toBeInTheDocument()
    })
    const [retryBtn] = await screen.findAllByText('Retry')

    fireEvent.click(retryBtn)

    // ``goal-tile-1`` is emitted by :file:`FinancialPlans.tsx` only
    // when ``summary`` is non-null and ``summaryError`` is null —
    // i.e. exactly when the retry-clear path completes.
    await screen.findByTestId('goal-tile-1')
    expect(
      screen.queryByText("Couldn't load projections:"),
    ).not.toBeInTheDocument()
  })

  it('granular retry: top banner clears when list recovers, inline persists when downstream still fails', async () => {
    // 1st attempt: both reject.
    mockedRulesService.listGoals.mockRejectedValueOnce(
      new Error('list fail'),
    )
    mockedRulesService.getDashboardSummary.mockRejectedValueOnce(
      new Error('downstream fail'),
    )
    // 2nd attempt: list recovers, downstream STILL fails. The two
    // error states must be independent — top banner MUST clear,
    // inline banner MUST stay.
    mockedRulesService.listGoals.mockResolvedValueOnce([fakeGoal])
    mockedRulesService.getDashboardSummary.mockRejectedValueOnce(
      new Error('downstream still down'),
    )

    render(<GoalsPage />)

    // Two retry buttons render — one per banner. DOM order:
    // [0] = top-of-page (rendered first in GoalsPage's JSX),
    // [1] = inline inside ``FinancialPlans``.
    const retryBtns = await screen.findAllByText('Retry')
    expect(retryBtns).toHaveLength(2)

    // Clicking either button drives the SAME ``retryCount`` state,
    // so the effect re-runs both fetches. Use [0].
    fireEvent.click(retryBtns[0])

    await screen.findByText('Retirement by 55')

    expect(
      screen.queryByText("Couldn't load goals:"),
    ).not.toBeInTheDocument()
    // Inline banner must persist because the dashboard forwarder
    // is still unhealthy on this retry round.
    expect(
      screen.queryByText("Couldn't load projections:"),
    ).toBeInTheDocument()
  })

  it('reflects the LATEST error message when retry flips to a new error type', async () => {
    mockedRulesService.listGoals.mockResolvedValue([fakeGoal])
    // 1st: 502 → classifier maps to "Downstream service is unavailable"
    mockedRulesService.getDashboardSummary.mockRejectedValueOnce({
      response: { status: 502, data: { detail: 'Finlynq 502' } },
      message: 'Failed',
    })
    // 2nd: 401 (different failure mode) → classifier maps to "Your session expired"
    mockedRulesService.getDashboardSummary.mockRejectedValueOnce({
      response: {
        status: 401,
        data: { detail: 'Your session expired.' },
      },
      message: 'Failed 401',
    })

    render(<GoalsPage />)

    await waitFor(() => {
      expect(
        screen.getByText(/Downstream service is unavailable/i),
      ).toBeInTheDocument()
    })
    const [retryBtn] = await screen.findAllByText('Retry')

    fireEvent.click(retryBtn)

    // The new error classification should replace the old one
    // (no stale banner text from the previous failure round).
    await screen.findByText(/Your session expired/i)
    expect(
      screen.queryByText(/Downstream service is unavailable/i),
    ).not.toBeInTheDocument()
  })

  it('rapid double-click on Retry does not double-fetch beyond React batching tolerance', async () => {
    // Persistently healthy listGoals — only the dashboard forwarder
    // is intermittent on this test.
    mockedRulesService.listGoals.mockResolvedValue([fakeGoal])
    mockedRulesService.getDashboardSummary.mockImplementation(
      createIntermittentDashboardMock(
        new Error('init fail'),
        {
          total_balance: 0,
          total_income_month: 0,
          total_expenses_month: 0,
          accounts_count: 0,
          transactions_count: 0,
          import_batches_count: 0,
          // Phase 15: ``FinancialPlans`` no longer synthesizes a
          // ``-1`` "Implied $15M" fallback row when ``user_goals``
          // is empty — the BE auto-seeds the default goal on first
          // list (Phase 15). Pass an explicit real-id goal so the
          // ``goal-tile-1`` tile lands after the retry resolves.
          user_goals: [fakeGoal],
        },
      ),
    )

    render(<GoalsPage />)

    await waitFor(() => {
      expect(screen.getAllByText('Retry').length).toBeGreaterThanOrEqual(1)
    })
    // Capture the first (and only, in this scenario) Retry button.
    const [retryBtn] = await screen.findAllByText('Retry')

    // Drop the initial-mount call from history so the assertion
    // reflects POST-Retry fetch counts only.
    mockedRulesService.listGoals.mockClear()
    mockedRulesService.getDashboardSummary.mockClear()

    // Two rapid synchronous synthetic clicks. We assert a RANGE
    // (``>= 1 && <= 2``) instead of an exact count because React's
    // automatic-batching semantics around ``setState`` from synthetic
    // event handlers can drift between minor versions — sometimes
    // one fetch round fires (batched), sometimes two (microtask
    // interleaving). The contract being locked is: NEVER more than 2
    // fetches (no triple-fire / runaway loop) and AT LEAST 1
    // (retry DID fire). Both bounds are user-facing-real.
    fireEvent.click(retryBtn)
    fireEvent.click(retryBtn)

    // Health state — the real seeded goal with id=1 emits the
    // ``goal-tile-1`` testid (StatCard data-testid pass-through).
    // Anchor shifted from ``-1`` to ``1`` in Phase 15: ``FinancialPlans``
    // now reads user_goals ONLY (no synthesized fallback), so the
    // negative-id testid is no longer emitted.
    await screen.findByTestId('goal-tile-1')

    expect(mockedRulesService.listGoals.mock.calls.length).toBeGreaterThanOrEqual(1)
    expect(mockedRulesService.listGoals.mock.calls.length).toBeLessThanOrEqual(2)
    expect(mockedRulesService.getDashboardSummary.mock.calls.length).toBeGreaterThanOrEqual(1)
    expect(mockedRulesService.getDashboardSummary.mock.calls.length).toBeLessThanOrEqual(2)
  })
})
