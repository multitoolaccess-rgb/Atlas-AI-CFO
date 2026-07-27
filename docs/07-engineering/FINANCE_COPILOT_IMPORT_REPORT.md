# Finance Copilot Implementation Import Report

## Purpose and source of truth

Atlas-AI-CFO is the permanent product and documentation authority. This import
uses only the committed Git tree from Finance Copilot commit
`c73fbcdb672a136cfc8f4d71b20f0265cf2464ba` on
`codex/atlas-phase0-projections`. The source working tree was not switched or
modified.

## Pre-import manifest

| Category | Decision |
| --- | --- |
| Application import | `ui/`, `services/`, `tests/`, `scripts/`, `agents/`, `policies/`, `designs/`, Docker/startup files, dependency manifests, CI, and safe example environment templates. |
| Phase 0 documentation | Import only ADR-005, the projection parity document, and the Phase 0 projection plan. |
| Atlas-authoritative files | Preserve `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/`, `agent-context/`, and `templates/`. |
| Root/document conflicts | Preserve Atlas `README.md` and `CLAUDE.md`; do not copy legacy source documentation broadly. Add only the three new, non-conflicting Phase 0 documents above. |
| Exclusions | Git metadata; `.env` and local env files; credentials; runtime databases and WAL/SHM files; logs/PIDs; caches; dependencies; build/coverage output; backups; editor metadata; temporary files; source agent/tool state; and uncommitted source changes. |
| Expected path changes | None. Application scripts and configuration use repository-relative paths and are imported at the Atlas repository root. |

## Status

### Imported application content

- Frontend: `ui/`, including source, tests, dependency manifests, and local
  ESLint rules.
- Backend: `services/rules-service/`, `services/finlynq/`, and
  `services/telegram-gateway/`, including schemas and Alembic migrations.
- Supporting content: `tests/`, `scripts/`, `agents/`, `policies/`,
  `designs/`, `.github/`, `.husky/`, Docker Compose, startup scripts, Python
  version pin, and safe `.env.example` templates.
- Phase 0: ADR-005, the Phase 0 plan, projection parity documentation,
  Decimal calculations, backend tests, shared golden fixtures, TypeScript
  projection math, and parity tests.

### Exclusions and security review

- Excluded from the committed source tree: `finance.db`, Finlynq
  `finance.db`, WAL/SHM files, `ui/.env.local`, its backup, temporary script
  output, `node_modules`, source agent/tool state, and all legacy source
  documentation outside the three Phase 0 documents.
- Excluded by construction: source `.git`, all uncommitted source changes,
  including `.agents/skills/verify-ui/`, source `AGENTS.md`, and
  `ui/app/layout.tsx.backup`.
- Removed after destination inspection: test-generated SQLite and Next output,
  OS metadata, and both services' statement/transaction fixture directories.
  The fixture payloads included PDFs/CSVs and paths labelled
  `sample_statements_real`; their safety could not be established. The test
  code remains, but parser fixture tests need approved synthetic fixtures
  before they can run in Atlas.
- The final destination scan found no populated environment files, databases,
  WAL/SHM files, private-key files, logs, caches, dependency directories,
  build output, or financial-statement/transaction-export files. Example env
  files contain only documented development placeholders.

### Conflicts and configuration

`README.md`, `CLAUDE.md`, and the existing `docs/` hierarchy conflicted with
the source root/documentation hierarchy. Atlas versions are authoritative and
were preserved; only the three non-conflicting Phase 0 documents were added.
`AGENTS.md`, `agent-context/`, and `templates/` were not touched. No path or
product-name changes were required for the imported application to resolve
repository-relative paths. `.gitignore` was added to prevent recurrence of
secrets, runtime data, generated output, dependencies, backups, and tool state.

### Validation

All commands were executed with Atlas as the working tree. Existing local
Python and Node dependency environments were used read-only because dependency
directories are intentionally excluded from Atlas; no dependency was installed
or upgraded.

| Check | Result |
| --- | --- |
| Phase 0 backend projections | 13 passed |
| Shared golden-fixture subset | 2 passed |
| Complete Rules Service suite | 578 passed, 10 skipped, 1 xfailed, 1 failed |
| Finlynq suite | 93 passed |
| Cross-service suite | 4 passed |
| Focused frontend projection/parity | 17 passed |
| Complete frontend suite | 496 passed |
| TypeScript `tsc --noEmit` | passed |
| Targeted parity-test ESLint | passed |
| Python in-memory compilation | passed (two pre-existing invalid-escape warnings) |

The 13 Phase 0 backend projection tests were rerun after sensitive fixture
exclusion and still passed.

The sole complete Rules Service failure is
`tests/test_health.py::test_health_extended_contract`. It requires
`git rev-parse --short HEAD` inside Atlas; Atlas is deliberately not a Git
repository and this migration must not initialize it. This explains the
difference from the source baseline (579 passed, 10 skipped, 1 xfailed).

Repository-wide `next lint` also has pre-existing failures unrelated to Phase
0: 16 errors (unescaped entities, missing `@typescript-eslint` rule, hook-rule
violations, and missing test component display names) plus hook/export
warnings. This migration does not alter them. `black` and `ruff` were absent
from the environment and were not installed.

### Legacy names and remaining risk

Legacy names remain intentionally: Finance Copilot (22 files), WealthIQ (35),
CashFlix (19), and Finlynq (68). No broad rename was performed. Remaining
risks are the deferred approved-synthetic-fixture replacement, Git-dependent
health-test behavior until the next reviewed Git-initialization step, and the
pre-existing repository-wide frontend lint debt.

### Recommended next step

Review this import, then approve a separate Git-initialization and baseline
commit step for Atlas; after that, replace excluded statement fixtures with
approved synthetic data in a bounded test-fixture task. Do not begin Phase 1
as part of this migration.
