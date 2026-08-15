# Claude Skills

Read `CLAUDE.md` first. Use `docs/master-plan.md` for full-system context.
Keep finance logic deterministic in Rules Service.

## Risk-tier summary

Use the canonical policy at
`docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md` and the tracker skill at
`.agents/skills/atlas-project-tracker/SKILL.md`. The policy defines focused
validation, review, CI, merge, autonomy, and stop requirements for low,
medium, and high work. Do not add fixed correction-cycle limits or enterprise
ceremony in this file.

## Tracking

Update project status only for material milestones, blockers, significant
risks, or next-task changes. Do not create tracker-evidence commits after every
implementation correction. Preserve historical evidence in
`PROJECT_STATUS.json`.
