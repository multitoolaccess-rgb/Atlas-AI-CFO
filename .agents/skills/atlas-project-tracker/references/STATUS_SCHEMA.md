# Atlas Project Status Schema

`PROJECT_STATUS.json` is the source of truth. Use stable IDs prefixed with
`phase-`, `work-`, `risk-`, and `ec-`.

Required top-level keys: `schema_version`, `last_updated`, `current_phase_id`,
`overall_status`, `current_objective`, `active_work`, `blockers`, `risks`,
`phases`, `completed_work`, `commit_pr_evidence`, `test_evidence`, and
`next_bounded_task`.

Work statuses: `planned`, `in_progress`, `blocked`, `in_review`, `complete`,
`cancelled`. Phase statuses: `not_started`, `in_progress`, `blocked`,
`in_review`, `complete`. Each phase has `exit_criteria`, with stable IDs and a
`complete` boolean. A completed work item requires a commit or PR reference; an
in-review work item requires a PR; blocked or cancelled work requires a reason.

Run `python3 scripts/atlas_project_status.py check` after every mutation.
