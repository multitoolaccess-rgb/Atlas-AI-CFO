# Phase 5 Market Intelligence Brief: Operational-Readiness Audit

> **Status:** Evidence-based documentation audit only. No application code,
> configuration, data, provider, delivery, or feature-flag change was made.
>
> **Audit date:** 2026-08-11
>
> **Baseline:** clean `main` / `origin/main` at `ecaeaa2` with annotated
> `phase-5-complete` resolving to that same commit. Phase 5 certification
> hosted run `31505665961` passed at `7832d60` (cheap and heavy CI passed;
> Playwright: 86 passed, 1 skipped).

## Scope and method

This audit answers whether the certified Phase 5 implementation is operable
for a local personal portfolio under its deliberately strict zero-dollar and
privacy boundaries. It traces the checked-in UI, route, application startup,
composer, flags, tests, and certification evidence. It does not start Atlas:
`start.sh` normally targets the local `finance.db`, and Rules Service startup
hooks may seed legacy demo recommendations. Starting it would violate this
documentation-only, no-local-data-change audit.

## Findings

| Question | Evidence | Result | Operational impact |
| --- | --- | --- | --- |
| Is `/market-briefs` discoverable in navigation? | Direct route `ui/app/market-briefs/page.tsx` renders `MarketBriefArchive`, but `ui/components/layout/Sidebar.tsx` has no Market Brief entry; repository-wide UI use outside the page/component/client finds none. | **No.** It is directly addressable but not discoverable through normal navigation. | A local user cannot reasonably find the certified archive surface. |
| Are read, generation, and external-provider gates default off? | `services/rules-service/app/config.py` sets `atlas_market_brief_generation_enabled`, `atlas_market_brief_read_api_enabled`, and `atlas_market_brief_external_provider_enabled` to `False`. Route guards in `app/routes/market_briefs.py` return the same 503 unavailable envelope when required gates are off. | **Yes, default off.** | Correct safety posture, but no checked-in deployment can read or generate briefs until a reviewed server-side configuration enables the applicable gates. |
| Is the trusted composer wired at application startup? | `app/routes/market_briefs.py` declares module-global `_composer = None`; `configure_market_brief_composer` has no production caller. The only call sites are `services/rules-service/tests/test_market_briefing.py`, which injects a hermetic `TrustedMarketBriefComposer` and clears it after tests. `app/main.py` registers the router but does not configure it. | **No. Test-only composition.** | Even with generation/provider flags enabled, the route remains 503 in a normal local process because `_composer is None`. |
| Can a real local portfolio generate and persist a brief? | The route can persist through `MarketBriefRepository.get_or_create` only after all gates are on and a composer is injected. `TrustedMarketBriefComposer.assemble` safely selects active, owned, non-cash holdings and uses provider interfaces, but no startup composition assembles real Finnhub/SEC adapters or local secrets. | **No, not from the checked-in local lifecycle.** Persistence is tested only through injected synthetic providers. | Certification proves contract correctness, not an operator-usable local generation path. No real external provider or personal database was exercised. |
| Does the archive have a usable empty state and a Generate Brief action? | `MarketBriefArchive.tsx` loads an array, renders a `<nav><ul>` of items, and has unavailable/loading states. When the API returns `[]`, it renders an empty list with no explanatory empty state. It imports only `listMarketBriefs` and `getMarketBrief`; `ui/lib/marketBriefs.ts` exposes no generate client and the component has no button/form. Component tests cover empty data only implicitly and detail request races, not an actionable empty state/generation. | **No.** | A user who reaches the route sees no way to understand an empty archive or generate the first brief. |
| Did certification use synthetic data and leave the personal database empty? | `PROJECT_STATUS.json` records Phase 5 synthetic/fake provider and delivery coverage and hosted run `31505665961`; tests use injected fake providers and `FakeEmailAdapter`. `tests/fixtures/atlas_forecast_snapshots_v1.json` explicitly says synthetic test data only. The Phase 5 completion evidence states no real email, paid endpoint, or cloud LLM was used. The audit did not open or modify local `finance.db`; no repository evidence can prove its pre-existing personal rows are empty. | **Synthetic/fake certification: yes. Personal database empty: not established and not required by certification.** | Do not claim that certification emptied or inspected a personal database. Any future local smoke test needs an isolated synthetic database. |

## What is already safe and reusable

- Provider-neutral, bounded contracts, cache/rate controls, paid-endpoint
  rejection, and untrusted-content handling remain appropriate.
- The server-only route refuses client-provided positions, owner IDs, hashes,
  and provider payloads; it assembles from owned active holdings only once a
  trusted composer exists.
- Brief persistence is owner-scoped and immutable, and the archive detail
  renderer includes source links, freshness, warnings, and race-safe detail
  selection.
- Delivery remains default-off, fake-testable, and preview/fail-closed; no
  real recipient, credential, or email delivery is necessary for the
  operationalization correction.

## Decision

**A bounded Phase 5 operationalization correction must precede Phase 6.**

This is not a Phase 5 financial-calculation or provider-contract defect; it
is a material operability gap between certified components and a safe local
personal-use workflow. Proceeding to Scenario Lab would otherwise build on an
undiscoverable archive whose generation path cannot be composed by the
application.

The correction must remain narrow and preserve Phase 5 boundaries:

1. Add a server-owned, explicitly configured composition factory that is
   absent unless reviewed local provider credentials and the two provider/
   generation flags are enabled. It must retain timeouts, free endpoints,
   rate limits, cache, fail-closed behavior, and no client financial payload.
2. Provide a discoverable Market Brief navigation entry and an accessible
   archive empty state with a Generate Brief affordance. The affordance must
   accurately explain disabled/unavailable state and must never expose a
   client flag override.
3. Add an isolated synthetic-database browser/operator journey proving a
   user can discover, generate, persist, list, and view one synthetic brief;
   prove disabled configuration remains unavailable and no real network,
   email, or personal database is used.
4. Do not activate production-like flags in checked-in configuration, install
   the scheduler, send email, add a paid endpoint, or alter Phase 5’s
   `phase-5-complete` evidence tag. This is a governed post-certification
   correction with a new exact evidence commit/tag relationship recorded
   truthfully.

## Recommended execution order

1. Authorize and complete the bounded Phase 5 operationalization correction
   as one high-risk cohesive PR (composition/configuration, archive UX, and
   isolated synthetic journey together).
2. Re-certify the affected Phase 5 provider, privacy, archive, and browser
   boundaries on the corrected clean main; preserve the original certified
   tag and create only a documented post-certification evidence record if
   governance requires it.
3. Re-run the Phase 6 capability audit’s focused assumptions against that
   merged state, then seek separate Phase 6 implementation authorization.

## Exact next authorization prompt

> Authorize one high-risk, bounded **Phase 5 operationalization correction**
> only: wire a reviewed server-owned local market-brief composer behind the
> existing default-off flags; add discoverable accessible archive navigation,
> empty state, and Generate Brief UX; and prove the complete flow only with
> isolated synthetic data/fake providers. Preserve all Phase 5 zero-dollar,
> privacy, no-email, no-LLM, and no-autonomous-execution boundaries. Do not
> begin Phase 6 or enable real provider/email credentials.
