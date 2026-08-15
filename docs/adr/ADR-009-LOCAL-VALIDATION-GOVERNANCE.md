# ADR-009: Local-only validation governance

- **Status:** Accepted
- **Date:** 2026-08-15
- **Decision owners:** Atlas solo development

## Decision

Atlas is a private, single-user, pre-production application. GitHub remains the
private source repository, backup, and history system, but GitHub Actions is
intentionally disabled to avoid unnecessary paid hosted execution. Local
validation is authoritative for normal changes, phase completion, releases, and
tags; no workflow URL is required as completion evidence.

Full local regression and canonical Playwright validation remain mandatory at
phase boundaries, release certification, repository-wide infrastructure
changes, or when concrete evidence indicates broad regression risk. Low- and
medium-risk work uses the focused local validation selected by the diff. High-
risk work preserves focused contract and integration tests, structured local
evidence, and local review when a reviewer is available.

Pull requests and stored workflow files remain optional records for history or
collaboration. Historical hosted-CI evidence is preserved and remains valid;
it is not required for new work.

## Safety impact

This decision changes delivery evidence and hosting cost only. It does not
weaken financial-authority, Decimal/calculation, privacy, authorization,
ownership-isolation, migration, immutable-history, credential, or execution
boundaries. Those boundaries continue to require their directly affected local
contract and integration tests.

## Consequences

- Agents and developers must record concrete local commands or bounded suite
  names, results, commit SHAs, timestamps, and material environment details.
- Generic claims and evidence without a concrete command/suite and commit are
  rejected by the tracker.
- GitHub Actions workflow definitions are retained but inactive.
- A future change to hosted validation requires a new governance decision.
