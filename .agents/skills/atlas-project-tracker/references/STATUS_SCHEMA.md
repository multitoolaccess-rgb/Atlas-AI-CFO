# Atlas Project Status Schema

`PROJECT_STATUS.json` is the source of truth. Use stable IDs prefixed with
`phase-`, `work-`, `risk-`, and `ec-`.

Required top-level keys: `schema_version`, `last_updated`, `current_phase_id`,
`overall_status`, `current_objective`, `active_work`, `blockers`, `risks`,
`phases`, `completed_work`, `commit_pr_evidence`, `test_evidence`, and
`next_bounded_task`.

Work statuses: `planned`, `in_progress`, `blocked`, `in_review`, `complete`,
`cancelled`. Phase statuses: `not_started`, `in_progress`, `blocked`,
`in_review`, `complete`. Material work items may include `risk_tier`: `low`,
`medium`, or `high`.

The authoritative risk, evidence, review, CI, merge, and full-certification
requirements are defined in
`docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`.

## Evidence rules for tiered completed work

- **Low:** `commit` evidence (a hash or short SHA from the local repo).
  `pr`, `review_evidence`, and `ci_evidence` are not required.
- **Medium:** `commit` and `tests` evidence. `pr` and `review_evidence` are
  optional. Relevant local validation evidence is recorded when the changed
  behavior affects shared application behavior.
- **High:** `commit`, `tests`, and concrete validation evidence. A branch is
  recommended; `pr` and `review_evidence` are recorded when applicable or when
  an independent reviewer is available. New work should use structured
  `validation_evidence`:

  ```json
  {
    "kind": "local",
    "commit": "abc123",
    "command": "python3 -m pytest tests/test_contract.py -q",
    "result": "3 passed",
    "timestamp": "2026-08-15T12:00:00Z",
    "environment": "Python 3.12 isolated Rules Service environment"
  }
  ```

  The command or bounded suite and commit are mandatory; generic claims without
  them are invalid. Historical `ci_evidence` records with a concrete successful
  GitHub Actions URL remain valid and unchanged for provenance, but no hosted
  workflow URL is required for new work. Findings that block a high-risk merge
  are defined by the canonical policy; do not infer a fixed correction-cycle
  limit from this schema.

An `in_review` work item requires a `pr` because that status represents an
open PR. Completed solo work may omit `pr` and review evidence when no
independent reviewer is available. `blocked` or `cancelled` work
requires a `reason`. Each phase has `exit_criteria`, with stable IDs and a
`complete` boolean. Phase completion remains forbidden until every criterion
is complete.

## Tracking policy

- Update project status only for material work starts, completions, phase
  changes, genuine blockers, significant risks, or next-task changes.
- Do not create tracker-evidence commits after every implementation correction.
- Do not require issues for routine work.
- Preserve historical evidence and existing internally consistent records.

Run `python3 scripts/atlas_project_status.py check` after every mutation.
Local evidence is authoritative because GitHub Actions is intentionally
disabled; stored workflow files and historical CI records are not completion
gates.
