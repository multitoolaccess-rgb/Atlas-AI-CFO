---
name: atlas-project-tracker
description: Apply Atlas risk-based delivery governance for implementation, migrations, security, architecture, phase planning or completion, and project-status requests. Use to classify work as low, medium, or high risk and record only material phase evidence.
---

# Atlas Project Tracker

Use `docs/10-roadmap/PROJECT_STATUS.json` only for phase milestones, material
deliverables, blockers, significant risks, and next-task changes. Read
`references/STATUS_SCHEMA.md` and run `python3 scripts/atlas_project_status.py
--help` when a command or field is unclear. Do not put secrets, financial data,
or lengthy logs in status files.

## Classify risk first

- **Low:** documentation corrections, comments, formatting, naming cleanup, or
  test-only improvements that preserve coverage. Commit directly to `main` when
  appropriate; no issue, branch, PR, or status mutation is required. Run
  relevant checks and review the diff.
- **Medium:** UI work, internal refactoring, developer scripts, read-only
  endpoints, observability, or non-sensitive integrations. Prefer a branch;
  PR and independent review are optional. Require validation. Record status
  only for a tracked phase deliverable.
- **High:** financial calculations, forecasting, migrations, authorization,
  privacy, recommendations, banking/brokerage integrations, money movement,
  autonomous execution, or destructive behavior. Require a branch, PR, CI,
  independent review, status/risk updates, and explicit approval before the
  next phase. Add an ADR only for a durable architecture decision.

## Start workflow

1. Classify risk and identify whether the work materially affects a phase.
2. For low-risk or documentation typo work, use the lightweight check workflow;
   do not create status work solely for the prompt.
3. For tracked medium/high work, run `show` and `check`, read the phase plan,
   confirm scope and dependencies, then run `start --risk-tier`.
4. Require a branch for high-risk work; do not require an issue for low or
   medium work.
5. Identify required validation and exit criteria. Stop if another active work
   item overlaps affected paths.

## Completion workflow

1. Run scoped validation and review the diff.
2. For tracked work, record evidence with `complete-work`: low requires a
   commit; medium requires a commit and tests; high requires branch, commit,
   PR, independent review, tests, and a concrete successful CI run/check.
3. Update risks, exit criteria, and next task only when they materially change.
4. Run `render`, then `check` and `render --check` after a status mutation.
5. Report the next bounded task. Do not begin it automatically.

## Check workflow

For read-only reviews, status questions, and low-risk documentation typo fixes,
run relevant checks; use `check`, `show`, and `render --check` when status is
in scope. Do not mutate status unless explicitly asked or a material phase
fact changed.
