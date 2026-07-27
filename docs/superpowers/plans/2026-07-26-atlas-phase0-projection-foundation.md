# Atlas Phase 0 Projection Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the Atlas projection contract, shared golden fixtures, and
a pure authoritative backend Decimal calculation without persistence or UI
changes.

**Architecture:** JSON fixtures define cross-language inputs and expected
behavior. A pure Python calculations module validates inputs, compounds monthly
with end-of-month contributions, and returns three deterministic scenarios.
TypeScript tests compare only the legacy-compatible subset and explicitly
record intentional differences.

**Tech Stack:** Python 3.12, `decimal`, pytest, TypeScript 5.3, Vitest, JSON.

## Global Constraints

- Preserve existing user changes and unrelated behavior.
- Do not add or change database schema.
- Do not change production UI or recommendation behavior.
- Do not add Monte Carlo calculations or probability labels.
- Do not upgrade dependencies.
- Use USD with an explicit currency field.
- Use monthly periods and end-of-month contributions.
- Round external monetary outputs with round-half-even.

---

### Task 1: Architecture contract

**Files:**
- Create: `docs/adr/ADR-005-ATLAS-VERTICAL-SLICE-FOUNDATION.md`

**Interfaces:**
- Consumes: Atlas product, architecture, domain, intelligence, security, and
  migration requirements.
- Produces: the accepted Phase 0 calculation and migration boundaries.

- [x] Record projection authority, Decimal arithmetic, USD handling, timing,
  rounding, scenario, versioning, recommendation, decision, tenancy, and
  service-boundary decisions.

### Task 2: Shared golden fixtures and failing backend tests

**Files:**
- Create: `tests/fixtures/atlas_projection_cases.json`
- Create: `services/rules-service/tests/test_atlas_projection.py`

**Interfaces:**
- Produces: fixture schema version `atlas-projection-fixtures/v1`.
- Consumes: `project_scenarios(ProjectionRequest) -> ProjectionResult`.

- [ ] Add valid, invalid, stale, rounding, and large-value fixture cases.
- [ ] Add fixture-schema and backend behavioral tests.
- [ ] Run the backend test and verify it fails because
  `app.calculations.projection` does not exist.

### Task 3: Pure Decimal projection module

**Files:**
- Create: `services/rules-service/app/calculations/__init__.py`
- Create: `services/rules-service/app/calculations/projection.py`

**Interfaces:**
- Produces: `ProjectionRequest`, `ProjectionAssumptions`,
  `ProjectionValidationError`, and `project_scenarios`.
- Consumes: strings and integers from the shared JSON fixture.

- [ ] Validate currency, dates, freshness, finite Decimal inputs, and horizon.
- [ ] Compound each scenario monthly with end-of-month contributions.
- [ ] Preserve unrounded internals and quantize output money to USD cents with
  `ROUND_HALF_EVEN`.
- [ ] Return structured assumptions, drivers, and scenario results.
- [ ] Run focused backend tests to green.

### Task 4: TypeScript parity contract

**Files:**
- Create: `ui/lib/math/__tests__/atlasProjectionParity.test.ts`
- Create: `docs/atlas-projection-parity.md`

**Interfaces:**
- Consumes: shared JSON fixtures and existing
  `projectDashboardTrajectory`.
- Produces: evidence for compatible cases and a documented difference matrix.

- [ ] Compare exact compatible cases using tolerance only for JavaScript
  representation.
- [ ] Assert monthly timing cases are intentionally excluded from exact legacy
  parity.
- [ ] Document Decimal, timing, rounding, and scenario differences.
- [ ] Run focused frontend tests to green.

### Task 5: Verification

**Files:**
- Modify only files listed above if verification finds a scoped defect.

- [ ] Run focused backend projection tests.
- [ ] Run the complete rules-service pytest suite.
- [ ] Run focused frontend projection and parity tests.
- [ ] Run the complete Vitest suite and TypeScript typecheck.
- [ ] Review `git diff` and confirm no schema, production UI, recommendation,
  or unrelated changes.
- [ ] Commit only Phase 0 files.

