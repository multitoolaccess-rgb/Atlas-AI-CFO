---
name: atlas-project-tracker
description: Track Atlas project phase status, scoped implementation, migrations, bug fixes, test restoration, security and architecture changes, phase planning or completion, and project-status or next-task requests. Use before changing a tracked task and when reporting its completion.
---

# Atlas Project Tracker

Use `docs/10-roadmap/PROJECT_STATUS.json` as the source of truth. Read
`references/STATUS_SCHEMA.md` and run `python3 scripts/atlas_project_status.py
--help` when a command or field is unclear. Do not put secrets, financial data,
or lengthy logs in status files.

## Start workflow

1. Run `show` and `check`; read the phase plan.
2. Confirm branch, issue, scope, paths, and dependencies.
3. Confirm the work belongs to the current phase; stop for approval if it does not.
4. Run `start` with the work-item ID and affected paths.
5. Identify required tests and phase exit criteria.
6. Stop if another active work item overlaps the paths or scope.

## Completion workflow

1. Run scoped validation.
2. Record exact test results and review evidence with `complete-work` or `review`.
3. Update risks and technical debt; do not mark unresolved items resolved.
4. Record branch, commit, and PR evidence.
5. Update completed and remaining exit criteria.
6. Run `render`, then `check` and `render --check`.
7. Report the next bounded task.
8. Do not begin that next task automatically.

## Check workflow

For read-only reviews and status questions, run `check`, `show`, and `render
--check`. Report the active phase, blockers, risks, evidence, and next action.
Do not mutate status unless explicitly asked.
