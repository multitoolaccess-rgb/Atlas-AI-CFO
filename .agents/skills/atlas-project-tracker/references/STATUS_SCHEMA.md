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

Evidence rules for tiered completed work:

- Low: commit evidence; PR is optional.
- Medium: commit and test evidence; PR is optional.
- High: branch, commit, PR, independent `review_evidence`, test evidence, and
  structured `ci_evidence`. `ci_evidence` is exactly:

  ```json
  {
    "run_url": "https://github.com/OWNER/REPOSITORY/actions/runs/RUN_ID",
    "check": "concrete check name (not a generic claim)",
    "conclusion": "success"
  }
  ```

  The run URL must identify a GitHub Actions run and the conclusion must be
  `success`; empty or generic check claims such as `passed` are invalid.

An in-review work item requires a PR; blocked or cancelled work requires a
reason. Each phase has `exit_criteria`, with stable IDs and a `complete`
boolean. Phase completion remains forbidden until every criterion is complete.

Run `python3 scripts/atlas_project_status.py check` after every mutation.
