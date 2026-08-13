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
`medium`, or `high`. Existing historical work without a tier remains valid.

## Evidence rules for tiered completed work

- **Low:** `commit` evidence (a hash or short SHA from the local repo).
  `pr`, `review_evidence`, and `ci_evidence` are not required.
- **Medium:** `commit` and `tests` evidence. `pr` and `review_evidence`
  are optional. `ci_evidence` is required only when the change affects
  shared application behavior (then it follows the High format below).
- **High:** `branch`, `commit`, `pr`, independent `review_evidence` (the
  review-approval string records the cycle count used, capped at two),
  `tests`, and structured `ci_evidence`. `ci_evidence` is exactly:

  ```json
  {
    "run_url": "https://github.com/OWNER/REPOSITORY/actions/runs/RUN_ID",
    "check": "concrete check name (not a generic claim)",
    "conclusion": "success"
  }
  ```

  The run URL must identify a GitHub Actions run and the conclusion must be
  `success`; empty or generic check claims such as `passed` are invalid.
  After two correction-and-review cycles, if a material finding remains
  the work MUST stop with the exact unresolved decision recorded in
  `review_evidence`.

An `in_review` work item requires a `pr`. `blocked` or `cancelled` work
requires a `reason`. Each phase has `exit_criteria`, with stable IDs and a
`complete` boolean. Phase completion remains forbidden until every
criterion is complete.

## Tracking policy

- Update project status only when material work starts, completes, changes
  phase, or becomes genuinely blocked.
- Do not create tracker-evidence commits after every implementation
  correction. Fold final tracker evidence into the implementation commit
  when practical, or use one final evidence commit.
- Do not require issues for routine work.
- Do not require PR comments duplicating tracker evidence.
- Existing historical evidence must remain intact (records produced under
  any prior policy remain valid as long as the data they carry is
  internally consistent).

Run `python3 scripts/atlas_project_status.py check` after every mutation.
