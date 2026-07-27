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

Use the project-local `atlas-project-tracker` skill for governed delivery work; see `docs/10-roadmap/PROJECT_STATUS.json` for current status.
