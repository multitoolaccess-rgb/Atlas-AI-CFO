# Claude Skills

Read CLAUDE.md first. Use docs/master-plan.md for full-system context. Keep finance logic deterministic in rules-service.

## Risk-tier summary (governance)

Use the `atlas-project-tracker` skill (`.agents/skills/atlas-project-tracker/SKILL.md`) for risk classification:

- **Low** commits directly to `main` after focused validation. No branch, PR, review, CI evidence, or active tracker item is needed.
- **Medium** uses one cohesive feature branch with focused + relevant regression tests; PR and independent review are optional; CI is required only when the change affects shared application behavior. Do not split one vertical slice into mapper / schema / route micro-PRs without a concrete dependency or safety reason.
- **High** uses one cohesive branch and PR, required relevant CI, one fresh independent review, and a maximum of two correction-and-review cycles. Fold final tracker evidence into the implementation commit when practical.

## Tracking

- Update project status only on material work milestones, blockers, significant risks, or next-task changes.
- Do not create tracker-evidence commits after every implementation correction.
- Historical evidence in `PROJECT_STATUS.json` is preserved.
