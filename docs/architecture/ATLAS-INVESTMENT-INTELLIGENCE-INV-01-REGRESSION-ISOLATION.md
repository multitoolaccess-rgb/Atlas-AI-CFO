# INV-01 Regression Isolation Analysis

**Date:** 2026-08-30  
**Task:** Determine whether two Rules Service dashboard failures were introduced by INV-01.

## 1. Current Git status

The worktree contains unrelated dirty work across the dashboard, budgeting,
schema, and UI areas, plus the uncommitted INV-01 files. The dashboard files
are modified independently of the INV-01 package:

- `services/rules-service/app/routes/dashboard.py`
- `services/rules-service/tests/test_routes_dashboard_phase35.py`

The INV-01 files are:

- `docs/09-decisions/ADR-INVESTMENT-001-CANONICAL-INVESTMENT-AUTHORITY.md`
- `services/rules-service/app/investments/__init__.py`
- `services/rules-service/app/investments/contracts.py`
- `services/rules-service/app/investments/context.py`
- `services/rules-service/app/investments/errors.py`
- `services/rules-service/app/config.py`
- `services/rules-service/tests/test_investment_foundation_contracts.py`

No dashboard file was changed by the INV-01 work.

## 2. Evidence of pre-existing unrelated work

`git diff` shows the dashboard changes remove the legacy `period` query
parameter and replace it with `from_date`/`to_date` validation. The two failing
tests still call `?period=not-a-date` and assert a 400 response. Because the
route no longer declares or reads `period`, FastAPI ignores that unknown query
parameter and the request follows the default current-month path, returning
200. The test then fails its expected status assertion.

The dashboard diff also contains unrelated Sankey grouping, trend-range,
breakdown, category, and test changes. This is direct repository evidence that
the failures are associated with the dirty dashboard change set rather than
with the INV-01 foundation.

## 3. Failing tests and exact causes

- `test_dashboard_flows_rejects_malformed_period_query`
- `test_dashboard_breakdown_rejects_malformed_period_query`

Both tests send `period=not-a-date`. The current route signatures no longer
accept a `period` parameter and no longer validate it. Unknown query parameters
are ignored, so both routes return their normal successful response instead of
400. This is a contract mismatch between the modified dashboard implementation
and its still-expecting legacy tests.

## 4. Dependency analysis

The failing routes import dashboard, account, transaction, classification,
and existing schema modules. They do not import `app.investments` or any INV-01
contract. INV-01's configuration additions are independent boolean settings
with false defaults; they are not read by dashboard routes, dashboard tests, or
the dashboard calculation path.

The new investment tests and package do not alter the dashboard router, route
registration, SQL models, migrations, or test fixtures. There is no dependency
path from `app/investments/*` to either failing test. The only shared file is
`app/config.py`, and the added settings have no dashboard behavior or import
side effects.

Therefore the causal path:

```text
INV-01 → dashboard regression
```

is not supported by the repository evidence.

## 5. INV-01 isolated validation

Using the repository-prescribed Python 3.12 Rules Service environment:

```bash
../../.venv-rules/bin/python -m pytest -q \
  tests/test_investment_foundation_contracts.py \
  tests/test_market_intelligence_foundation.py \
  tests/test_routes_assistant.py \
  tests/test_assistant_conversations.py \
  tests/test_assistant_models.py \
  tests/test_assistant_streaming.py
```

Result:

```text
75 passed
```

Static import/bytecode validation also passed:

```bash
../../.venv-rules/bin/python -m compileall -q app/investments app/config.py
```

The full Rules Service suite remains:

```text
1384 passed, 10 skipped, 1 xfailed, 2 failed
```

The only failures are the two dashboard tests listed above.

## 6. Classification

### B — Pre-existing unrelated regression

The unrelated dashboard regression remains an existing repository baseline
issue and was not introduced by INV-01.

The failure is explained by the dirty dashboard route/test change set, and the
isolated INV-01 plus relevant assistant/Market Intelligence tests pass. No
INV-01 import, contract, configuration behavior, provider, migration, or
execution path is involved.

## 7. Governance interpretation

`docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md` states that documented
non-critical bugs are acceptable during pre-production development and that
local validation is authoritative. It also requires focused evidence and
protects financial correctness, authorization, ownership, privacy, migration,
credential, and execution boundaries.

The policy does not provide a literal rule saying that every unrelated
pre-existing failure must block an otherwise isolated phase. It does support
risk-based focused validation and documenting non-critical baseline failures.
Accordingly, this analysis does not silently waive the full-suite failures:
they remain recorded repository baseline debt, while INV-01 health is reported
separately from repository baseline health.

## 8. Recommendation

INV-01 is technically healthy and independently validated. The two dashboard
failures should be handled in the dashboard workstream without modifying or
including those dirty files in an INV-01 commit.

Do not weaken, skip, or xfail the dashboard tests. Subject to `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md` and its mandatory
stop conditions, INV-01 may be closed and the already-authorized program may
proceed to INV-02. No dashboard files were changed by this analysis.
