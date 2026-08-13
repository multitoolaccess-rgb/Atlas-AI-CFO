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

- **Low:** documentation, comments, formatting, styling-only changes, test
  cleanup, generated documentation. Process: direct commit to `main`; run
  focused validation; no branch, PR, independent review, CI evidence, or
  active tracker item required.
- **Medium:** UI features, read-only API composition, mappers, schemas,
  explanations, non-financial application logic. Process: one cohesive
  feature branch; focused + relevant regression tests; PR and independent
  review optional; squash-merge after validation; CI required only when the
  change affects shared application behavior. Do not split one vertical
  slice into mapper / schema / route micro-PRs without a concrete dependency
  or safety reason.
- **High:** financial mathematics, persisted financial state, database
  migrations, authentication / authorization, write APIs, privacy / security
  boundaries, external execution. Process: one cohesive branch and PR;
  required relevant CI; one fresh independent review; maximum two
  correction-and-review cycles. If material findings remain after two
  cycles, stop with the exact unresolved decision. Record test, CI, review,
  and commit evidence before completion.

## Tracking policy

- Update project status only when material work starts, completes, changes
  phase, or becomes genuinely blocked.
- Do not create tracker-evidence commits after every implementation
  correction. Fold final tracker evidence into the implementation commit
  when practical, or use one final evidence commit.
- Do not require issues for routine work.
- Do not require PR comments duplicating tracker evidence.
- Phase exit criteria remain enforced.
- Existing historical evidence must remain intact.

## Personal-use boundary

- Phase 2 personal single-user development may proceed.
- Open retention / user-deletion risks block external multi-user production
  rollout only.
- Currency uncertainty must continue to fail closed.
- Advisor access, household tenancy, and autonomous financial execution
  remain out of scope.

## Phase 2 packaging

Use two cohesive implementation slices unless a real safety boundary requires
otherwise:

1. Backend recommendation plus decision-journal substrate.
2. Complete user-visible UI vertical slice using that substrate.

Do not create separate PRs for mappers, schemas, routes, tests, or
documentation belonging to the same slice.

## Start workflow

1. Classify risk and identify whether the work materially affects a phase.
2. For low-risk or documentation cleanup work, commit directly to `main`
   after focused validation; do not create status work solely for the
   prompt.
3. For tracked medium or high work, run `show` and `check`, read the phase
   plan, confirm scope and dependencies, then run `start --risk-tier`.
4. High-risk work requires a branch; medium- and low-risk work do not.
   Issues are not required for any tier.
5. Identify required validation and exit criteria. Stop if another active
   work item overlaps affected paths.

## Completion workflow

1. Run scoped validation and review the diff.
2. For tracked work, record evidence with `complete-work` consistent with
   the tier. Low requires a commit. Medium requires commit and test
   evidence; PR is optional. High requires branch, commit, PR, independent
   `review_evidence` (the review records the cycle count used, capped at
   two), test evidence, and structured `ci_evidence`.
3. Update risks, exit criteria, and next task only when they materially
   change.
4. Run `render`, then `check` and `render --check` after a status
   mutation.
5. Report the next bounded task. Do not begin it automatically.

## Check workflow

For read-only reviews, status questions, and low-risk documentation fixes,
run relevant checks; use `check`, `show`, and `render --check` when status
is in scope. Do not mutate status unless explicitly asked or a material
phase fact changed.
