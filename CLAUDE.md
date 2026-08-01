# Atlas Coding-Agent Instructions

Read `docs/00-product-vision/ATLAS_MASTER_PRODUCT_SPEC.md` first, then the relevant strategy, architecture, domain, experience, and engineering specifications.

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

Before implementation, identify affected documents and acceptance criteria. After implementation, report tests, assumptions, risks, and unresolved decisions.

Use the project-local `atlas-project-tracker` skill for risk tier classification
(see `.agents/skills/atlas-project-tracker/SKILL.md`):

- Low work commits directly to `main` after focused validation.
- Medium work uses one cohesive feature branch; PR and independent review
  are optional; CI required only when shared behavior is affected.
- High work uses one cohesive branch + PR, required relevant CI, one fresh
  independent review, and a maximum of two correction-and-review cycles.
  Fold final tracker evidence into the implementation commit when
  practical.

Current phase status lives in `docs/10-roadmap/PROJECT_STATUS.json`.
External multi-user production enablement remains blocked pending the
approved retention + user-deletion policy; Phase 2 personal single-user
development may proceed.
