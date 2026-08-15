# Atlas Coding-Agent Instructions

Read `docs/00-product-vision/ATLAS_MASTER_PRODUCT_SPEC.md` first, then the
relevant strategy, architecture, domain, experience, and engineering
specifications.

## Rules

1. Preserve financial correctness, provenance, explainability, and user control.
2. Keep deterministic calculations separate from model-generated reasoning.
3. Never invent financial facts or silently fill missing data.
4. No material financial action without explicit permission and an audit record.
5. Link each recommendation to goals, evidence, assumptions, risks, and confidence.
6. Prefer incremental migration over rewriting the existing product.
7. Add tests for calculations, policies, permissions, and failure paths.
8. Update documentation when an accepted implementation changes a contract.
9. For local Python work, use `.venv-rules` for Rules Service and
   `.venv-finlynq` for Finlynq. Never combine their manifests or use the old
   Finance Copilot `.venv`; see `docs/07-engineering/LOCAL_PYTHON_ENVIRONMENTS.md`.

## Delivery governance

Apply `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md` as the canonical
risk-based policy. Use the project-local tracker skill for commands and status
operations, but do not impose enterprise-style ceremony or fixed
correction-cycle caps beyond the canonical policy.

Authorized implementation work runs under the canonical Autonomous completion
mode by default. Outcome-level authorization includes bounded subordinate
corrections and review loops. Stop only at the policy’s mandatory stop
conditions or when the user explicitly requests a narrower workflow. Explicit
task restrictions still apply, so future prompts should describe the permitted
outcome and safety boundaries without imposing artificial correction-cycle
limits.

Before implementation, identify affected documents and acceptance criteria.
After implementation, report the exact focused tests, assumptions, risks, and
unresolved decisions. Local validation is authoritative because GitHub Actions
is intentionally disabled; PRs and workflow URLs are optional history only.
Do not claim skipped checks passed and do not rerun unrelated green suites.

Use `$atlas-handoff` when starting, resuming, transferring, closing, or
checking material Atlas work, or for project-status and next-task requests.
Skip it for routine builds, tests, linting, inspection, and small edits within
an uninterrupted task.

Current phase status lives in `docs/10-roadmap/PROJECT_STATUS.json`. External
multi-user production enablement remains blocked pending the approved
retention and user-deletion policy; personal single-user development may
proceed under the canonical policy.
