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
  optional. Relevant CI evidence is recorded when the changed behavior affects
  shared application behavior.
- **High:** `branch`, `commit`, `pr`, fresh independent `review_evidence`,
  `tests`, and relevant successful `ci_evidence`. The CI record is exactly:

  ```json
  {
    "run_url": "https://github.com/OWNER/REPOSITORY/actions/runs/RUN_ID",
    "check": "concrete check name (not a generic claim)",
    "conclusion": "success"
  }
  ```

  The run URL must identify a GitHub Actions run and the conclusion must be
  `success`; empty or generic check claims such as `passed` are invalid.
  Findings that block a high-risk merge are defined by the canonical policy;
  do not infer a fixed correction-cycle limit from this schema.

An `in_review` work item requires a `pr`. `blocked` or `cancelled` work
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
