# Phase 2 Repository-Health Stabilization

> **Status:** In progress on `codex/repository-health-stabilization`.
> **Baseline:** `main` / `origin/main` / GitHub `main` at `e758631046da698f74edc0a67671e68a0c1dd5ee`.
> **Boundary:** Repository-health prerequisite only. No Phase 2 financial behavior, forecast mathematics, backend contracts, migrations, tenancy, retention/deletion, execution, or Phase 3 work.

## Purpose

Restore reproducible clean-runner lint behavior and classify the pre-existing browser-suite debt before the final Phase 2 certification attempt. The dedicated Phase 2 forecast → recommendation → explanation → decision journey remains protected and must stay green.

## Baseline evidence

The clean pre-Phase-2 baseline at certified Phase 1 tag `08f6f811da7c325da8a3d60adae9f2d9c2d210e8` reproduced the legacy browser debt:

- 66 passed
- 17 failed
- 1 skipped

The 17 failures were recorded before the Phase 2 UI correction work and are therefore repository-health debt, not a Phase 2 regression. A later current-main run varied to 19 failures because the browser/dev-server environment is not fully deterministic; that run is retained as diagnostic evidence and is not substituted for the 17-test baseline.

## Hosted lint diagnosis

`ui/.eslintrc.json` enables `local-rules/no-semantic-dark-overrides`, but the configured plugin is source-local under `ui/eslint-plugin-local-rules/` and was absent from `ui/package.json` and `ui/package-lock.json`. A clean `npm ci` therefore could not resolve the configured ESLint plugin.

The bounded correction packages the existing local implementation as:

- `ui/eslint-plugin-local-rules/package.json` (`private`, version `0.0.0`, `main: index.js`)
- `ui/package.json` dev dependency `eslint-plugin-local-rules: file:eslint-plugin-local-rules`
- corresponding lockfile link
- direct compatible `@typescript-eslint/eslint-plugin: 6.21.0` for the existing rule suppression

No lint rule was disabled, skipped, globally installed, or made unpinned.

## Browser failure groups

### 1. Stale or ambiguous selectors — medium risk, test-only

Affected journeys include Budgeting, Income, Debts, and sidebar navigation. Several assertions use broad text or OR locators that match multiple valid elements (for example `Add Budget`, `Income Sources`, `Total Debt`, and debt category labels). The smallest correction is to use existing test IDs, semantic headings, or `.first()` only where the contract is presence rather than uniqueness. No application behavior is changed.

### 2. Dark-mode storage contract drift — low risk, test-only

`DarkModeToggle` intentionally migrated storage from `darkMode` to `atlas_theme` and removes the old key. Existing E2E tests asserted the retired key. The smallest correction is to assert `atlas_theme` and use the updated `Switch to light mode` accessible name for the second click. Production behavior is unchanged.

### 3. Auth/error-fixture setup — high risk until proven, not yet classified as test-only

The downstream 502, 500 detail, and dashboard warning-banner tests fail to observe their mocked error state. The application root layout and `AuthBootstrapProvider` perform health/auth bootstrap before page content mounts. These failures require route/interception-order and rendered-DOM diagnosis. No production auth or error behavior is changed in this stabilization branch without a separate demonstrated correction boundary.

### 4. Import workflow setup — high risk until proven

CSV upload tests time out while interacting with `import-submit`. The submit control is disabled until a file is selected, and the page also loads import history on mount. The smallest safe correction must prove whether the fixture selects a file, whether the account fixture is available, and whether the backend upload route is reachable. No upload or financial behavior is changed speculatively.

### 5. Merchant-rule/activity synchronization — medium risk, unresolved

Settings and Activity tests time out waiting for merchant-rule or transaction responses. The tests must establish that the response listener is registered before the action and that the route pattern matches the actual request. Production changes require separate authorization if diagnosis identifies an API defect.

### 6. Assistant/sidebar/dashboard legacy coverage — unresolved

The assistant and legacy dashboard failures are retained as pre-existing coverage evidence. The dedicated Phase 2 journey passes; these failures must not be masked, skipped, or attributed to Phase 2 without a reproducer.

## Current diagnostic disposition

The following bounded test/infrastructure corrections are now evidenced and applied:

- Local ESLint plugin packaging and its direct TypeScript ESLint companion resolve under clean `npm ci`; strict lint is green.
- Dark-mode assertions use the current `atlas_theme` storage key and post-toggle accessible name.
- Enhanced-page selectors use stable test IDs or exact semantic locators instead of ambiguous broad text/OR matches.
- Account-import E2E flows select the `Statement` tab explicitly, complete the deterministic synthetic account-type prompt, and assert the actual warning-bearing success contract: preview plus saved-transaction count.
- The activity upload flow selects the same `Statement` tab before interacting with the file input.

The following failures remain blockers and are not silently changed in this stabilization scope:

- Dashboard/auth 500/502 tests: the route mock is reached, but the shared dashboard cache surfaces raw Axios text instead of the existing classifier contract. This is a demonstrated production UI defect and requires a separate bounded product-correction authorization.
- Activity merchant-rule/transaction synchronization and assistant chat failures remain legacy live-stack failures pending independent route/fixture diagnosis; no skips or weakened assertions are allowed.

## Latest verification evidence

The latest focused correction run passed all five affected import/activity tests. The complete canonical Playwright run remains failing:

- 85 total tests
- 74 passed
- 2 skipped (pre-existing conditional coverage)
- 9 failed

Remaining failures are grouped as follows:

- **Separate production-correction blocker:** two auth-flow error-banner tests and one dashboard-banner variant test. The dashboard-summary mock is reached, but the application renders raw Axios text instead of the established `classifyError` downstream/server contract. No production correction is included here.
- **Legacy live-stack synchronization:** two merchant-rule/transaction response-wait tests. They require route/fixture diagnosis before any production edit.
- **Legacy assistant/navigation:** two assistant tests (Scout sidebar visibility and tool-card chat startup). They remain outside this stabilization correction boundary.
- **Legacy enhanced-page startup:** one Budgeting page load test failed in the complete shared-stack run, despite the corrected enhanced-page selector subset passing; this requires an isolated reproducer before attribution.
- **No new financial, authorization, migration, tenancy, retention/deletion, or Phase 2 recommendation behavior was introduced by these corrections.**

Because the complete browser matrix is not green, this branch is not ready for PR/merge or Phase 2 certification. Hosted CI and certification tagging must wait for the separate production correction and remaining legacy diagnosis.

## Correction rules

- Do not add sleeps, raise global timeouts, skip tests, weaken assertions, or bypass lint.
- Keep Phase 2 financial behavior and API contracts unchanged.
- Correct test infrastructure, stale selectors, and deterministic fixture setup in one cohesive stabilization change only when the shared root cause is proven.
- Stop and request a separate bounded product-correction authorization if authentication, import, dashboard, or navigation production defects are demonstrated.

## Required completion gates

- Clean `npm ci` resolves the local ESLint plugin and TypeScript ESLint companion.
- `npm run lint -- --max-warnings 0` passes.
- Complete Playwright matrix passes without adding skips.
- Dedicated Phase 2 browser journey remains green.
- Frontend Vitest and `npm run typecheck` pass.
- Rules Service, Finlynq, and cross-service suites remain green.
- Canonical `scripts/test.sh` passes.
- Hosted status, cheap, and heavy CI pass.
- Tracker check and deterministic render check pass.
- Scope and sensitive-data review pass.

Phase 2 remains uncertified and `phase-2-complete` must not be created until all gates pass.
