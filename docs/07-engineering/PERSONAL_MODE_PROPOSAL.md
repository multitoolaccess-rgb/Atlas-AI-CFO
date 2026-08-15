# Atlas Personal Mode Proposal

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Status:** Wave 1A implementation complete for read-only diagnostics, readiness observation, synthetic contract acceptance, and activation/recovery guidance. Personal Mode still sets no financial or provider flags automatically.
- **Related:** [Personal-Use Readiness Report](./PERSONAL_USE_READINESS_REPORT.md), [System Health Audit](./SYSTEM_HEALTH_AUDIT.md), [Remediation Backlog](../10-roadmap/REMEDIATION_BACKLOG.md), [Scenario Lab Contract](./SCENARIO_LAB_CONTRACT.md).

## Design principles

Atlas is a private, single-user, pre-production application. Personal Mode must improve local activation without turning client configuration into financial authority. It must preserve server-owned flags, fail closed on currency/freshness/ownership uncertainty, and never make external execution or delivery capabilities implicit.

Personal Mode is a supported local profile, not a production mode. It must use isolated or explicitly operator-selected local storage, synthetic fixtures for acceptance, no committed credentials, and an observable readiness report.

## Proposed startup profile

1. Verify the checkout, Node dependencies, `.venv-rules`, and `.venv-finlynq` use the documented Python 3.12 environments.
2. Resolve an explicit local database path; never silently use a personal database for acceptance tests.
3. Verify Rules Service and Finlynq health, migration head, shared JWT contract, and local port ownership.
4. Verify server-owned flags and show their effective state without exposing secret values.
5. Verify authoritative account currency and forecast baseline prerequisites before offering forecast/scenario actions.
6. Start the UI with the final five-group IA and link to System → Readiness/Help.
7. Keep external provider, email, scheduler, cloud LLM, execution and money-movement capabilities disabled unless separately configured and authorized.

## Existing flags and proposed behavior

All checked-in defaults remain unchanged: `false` unless noted. Personal Mode must not be a client-side override.

| Existing server setting | Current default | Personal Mode proposal | Dependencies / safety gate |
|---|---:|---|---|
| `atlas_forecast_persistence_enabled` | false | **Never auto-enable.** Allow an explicit local operator override only after currency authority, migration head, retention acknowledgement, and synthetic acceptance pass. | Immutable forecast history and retention risk |
| `atlas_forecast_read_api_enabled` | false | **Never auto-enable.** May be enabled only with forecast persistence and the same authority checks. | Trusted baseline and read contract |
| `atlas_decision_history_api_enabled` | false | **Never auto-enable.** Optional explicit local override after append-only/history checks. | Immutable history and retention acknowledgement |
| `atlas_market_brief_read_api_enabled` | false | **Never auto-enable.** Allow explicit local enablement for synthetic/fake data or reviewed local provider configuration. | Provider readiness, citations, freshness, privacy |
| `atlas_market_brief_generation_enabled` | false | **Never auto-enable.** Enable only when a trusted server composer is configured and the operator understands provider boundaries. | Read flag, external provider contract, holdings coverage |
| `atlas_market_brief_external_provider_enabled` | false | **Never auto-enable.** Enable only with a valid local Finnhub key and SEC User-Agent; show readiness, never the secret. | Credentials, rate limits, source citations |
| `atlas_market_brief_email_delivery_enabled` | false | **Never set automatically; must remain false.** | Real delivery is out of personal audit scope |
| `atlas_market_brief_scheduler_enabled` | false | **Never set automatically; must remain false.** | Background delivery and operational side effects |
| `atlas_market_brief_local_summarization_enabled` | false | **Never set automatically; must remain false.** | No cloud/local LLM summarization authority in this boundary |
| `atlas_scenario_lab_enabled` | false | **Never auto-enable.** Explicit local override only after forecast/read/currency/baseline checks pass. | Server-authoritative scenario contract |

**Exact automatic behavior:** Personal Mode sets none of the existing financial or provider flags to `true`. It may report them and provide a bounded operator command for explicit, audited local overrides. It must always force or verify email, scheduler, local summarization, execution, trading, brokerage, money movement, and cloud LLM behavior off. Any future execution flag must be placed on the never-enable list by default.

## Proposed Atlas Doctor command

Implemented command: `python3 scripts/atlas_doctor.py` (readable summary) or `python3 scripts/atlas_doctor.py --json` (stable machine-readable output). It is read-only and returns exit code 0 for ready, 1 for ready with blocked optional capabilities, 2 for configuration failure, and 3 for unsafe state.

The command reports:

- Git SHA and clean/dirty state.
- Python/Node versions and required environment paths.
- UI, Rules Service, and Finlynq port ownership.
- Health response and service git SHA.
- Alembic head/current and whether the selected local DB is isolated.
- Effective non-secret flags and dependencies.
- Currency authority, forecast baseline, provider readiness, and migration safety.
- A redacted recovery action for each failed check.

It must never print JWT secrets, provider keys, raw credentials, personal financial values, raw provider payloads, or immutable evidence payloads.

## Proposed System → Readiness screen

Implemented surface: Settings includes a read-only Readiness section backed by the authenticated `GET /api/system/readiness` contract. It is an operational surface, not a new financial dashboard. Sections:

1. **Runtime:** UI/API/Finlynq health, SHA, ports, environment.
2. **Storage:** selected DB mode, migration head, backup freshness, WAL state.
3. **Financial authority:** currency proof, baseline freshness, forecast/readiness.
4. **Intelligence:** decision-history, market provider readiness, Scenario Lab readiness.
5. **Privacy and boundaries:** local-only status, credentials absent/present (boolean only), email/scheduler/execution disabled.
6. **Recovery:** copyable bounded next steps linking to Help; no raw errors.

## Supported local commands

```bash
# Redacted local diagnostics; never mutates flags, databases, migrations, or processes.
python3 scripts/atlas_doctor.py --json

# Disposable synthetic contract acceptance; uses a temporary SQLite database and fake/stub providers.
python3 scripts/synthetic_personal_acceptance.py
```

The acceptance command scopes forecast, recommendation, decision-history, and Scenario Lab flags only to child test processes. It deliberately leaves external Market Intelligence, email, scheduler, and local summarization disabled. Its focused suites cover immutable generation, decisions, history, outcomes, comparisons, archive behavior, and persistence across a reopened database session; a full service restart remains a separate release-boundary evidence item.

## Safe activation tiers

- **Tier 0 — default personal shell:** Money, Wealth source views, Settings, Help, and disabled/recovery Intelligence surfaces. No financial server flags enabled automatically.
- **Tier 1 — synthetic acceptance:** isolated database and fake providers; explicit test overrides may be applied by the test harness only, never by the browser.
- **Tier 2 — reviewed local financial analysis:** only after currency authority and retention acknowledgement; explicitly enable forecast/read/history/scenario flags as a bounded operator action.
- **Tier 3 — external provider context:** only after valid local credentials, provider readiness, citations/freshness tests, and explicit operator confirmation; no email/scheduler/execution.

Tier 3 does not imply multi-user production readiness or external rollout.

## Recovery and rollback

- If a readiness check fails, keep the affected flag off and render the sanitized recovery state.
- If a migration or provider check fails, stop activation; do not downgrade immutable history or delete records.
- Remove an explicit local override by restoring the flag to `false`; never mutate persisted financial history as a rollback mechanism.
- Keep acceptance databases disposable and separate from any personal database.

## Remaining evidence gaps

- Authoritative currency source and operator acceptance wording require a high-risk product/data decision.
- Backup freshness and restore semantics need an approved local storage policy.
- A supported local provider credential flow is not yet documented end-to-end.
- A full service restart/personal database recovery drill remains unproven and belongs to the release-boundary acceptance wave.

## Recommendation

Implement Wave 1 of [REMEDIATION_BACKLOG.md](../10-roadmap/REMEDIATION_BACKLOG.md) before enabling any financial intelligence flags. This proposal is not authorization to change flags or begin Phase 7.
