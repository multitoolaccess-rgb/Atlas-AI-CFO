---
name: atlas-project-tracker
description: Apply Atlas Solo Development Policy v2 for risk classification, focused evidence, phase tracking, and completion status.
---

# Atlas Project Tracker

The canonical human-readable policy is
`docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`. Read it before classifying
material work. This skill contains only tracker-specific enforcement and
command guidance; it must not duplicate or strengthen the delivery policy.

Use `docs/10-roadmap/PROJECT_STATUS.json` only for phase milestones, material
deliverables, blockers, significant risks, and next-task changes. Read
`references/STATUS_SCHEMA.md` and run `python3 scripts/atlas_project_status.py
--help` when a command or field is unclear. Never put secrets, financial data,
or lengthy logs in status files.

## Risk classification

- **Low:** documentation, copy, styling, visual tokens, generated tracker or
  handoff updates, isolated test corrections, and non-behavioral refactors.
  Focused validation is enough; direct main commit is allowed and no PR,
  review, hosted CI, or active tracker item is required unless part of a phase
  exit.
- **Medium:** UI pages, navigation, redirects, client state, shared visual
  components, non-financial clients, accessibility/responsive corrections, and
  normal tooling. Add directly affected tests; use TypeScript/lint for
  frontend changes and focused browser journeys for interaction/navigation/URL
  changes. Branch and cohesive PR are recommended; independent review is
  optional. Only critical/high findings block merging.
- **High:** financial calculations, forecast/recommendation authority,
  authentication/authorization, ownership isolation, immutable history,
  migrations, privacy, credentials/external delivery, and execution boundaries.
  Use a branch and PR, focused contract/integration tests, relevant CI, and a
  fresh independent review. Only critical/high findings block merging unless a
  medium/low finding threatens integrity, privacy, ownership, or authorization.
  Hosted CI is optional for medium-risk work when equivalent focused local
  validation has passed. Frontend-owned route-mocked browser tests do not
  require Rules Service, Finlynq, OCR, or the live-stack harness; reserve the
  live stack for genuine backend/UI integration, authentication,
  cross-service behavior, certification, or explicit manual validation.

## Tracking policy

- Update project status only when material work starts, completes, changes
  phase, becomes genuinely blocked, or changes the next bounded task.
- Do not create tracker-evidence commits after every implementation correction;
  fold final evidence into the implementation commit when practical or make
  one final evidence commit.
- Do not require issues for routine work or PR comments duplicating tracker
  evidence.
- Preserve historical evidence and phase exit criteria.

## Start workflow

1. Classify risk and identify whether the work materially affects a phase.
2. For low-risk or documentation cleanup, run focused validation and avoid
   creating status work solely for the prompt.
3. For tracked work, run `show` and `check`, read the phase plan, confirm scope
   and dependencies, then use `start --risk-tier`.
4. A high-risk item requires a branch; a medium branch is recommended; low
   work may proceed directly on main. Issues are not required.
5. Identify the smallest validation set that proves the changed behavior.

## Completion workflow

1. Run scoped validation and review the diff.
2. For tracked work, use `complete-work` consistent with the risk tier:
   low requires commit evidence; medium requires commit and tests; high
   requires branch, commit, PR, fresh review evidence, relevant tests, and
   successful relevant CI evidence.
3. Update risks, exit criteria, and next task only when they materially change.
4. Run `render`, then `check` and `render --check` after a status mutation.
5. Report exactly what ran, including skipped checks, and report the next
   bounded task without beginning it automatically.

## Check workflow

For read-only reviews, status questions, and low-risk documentation fixes, run
relevant checks and use `check`, `show`, and `render --check` when status is in
scope. Do not mutate status unless explicitly asked or a material phase fact
changed.
