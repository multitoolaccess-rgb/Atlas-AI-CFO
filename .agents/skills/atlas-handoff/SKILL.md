---
name: atlas-handoff
description: Load, report, validate, or close a repository-authoritative Atlas project handoff. Use for explicit $atlas-handoff requests and when starting, resuming, transferring, completing, or blocking material work in Atlas, or when asked for Atlas status or the next task. Do not use for routine builds, test reruns, linting, quick questions, read-only inspection, or small edits within an uninterrupted task.
---

# Atlas Handoff

Treat Git, `docs/10-roadmap/PROJECT_STATUS.json`, phase plans, ADRs, and tests
as authoritative. `CURRENT_HANDOFF.md` is a generated navigation aid, never a
replacement for those sources.

Do not copy conversations, tool logs, diffs, secrets, credentials, environment
values, financial records, or raw financial payloads into the handoff.

## Choose a workflow

- **start** — At the beginning of material Atlas work or after switching agents.
- **status** — For project progress, blockers, or next-task questions.
- **close** — After material work completes, becomes blocked, or is handed off.
- **check** — Verify the committed handoff matches canonical tracker state.

Run commands from the Atlas repository root:

```bash
python3 .agents/skills/atlas-handoff/scripts/atlas_handoff.py start
python3 .agents/skills/atlas-handoff/scripts/atlas_handoff.py status
python3 .agents/skills/atlas-handoff/scripts/atlas_handoff.py close
python3 .agents/skills/atlas-handoff/scripts/atlas_handoff.py check
```

`start` and `status` are read-only. `close` atomically regenerates
`docs/10-roadmap/CURRENT_HANDOFF.md`. `check` is read-only and fails on drift.

## Start workflow

1. Run `start` and read its output.
2. Run `python3 scripts/atlas_project_status.py check` and
   `python3 scripts/atlas_project_status.py render --check`.
3. Confirm the live Git branch and worktree reported by `start` agree with the
   requested task. Do not discard an existing dirty worktree.
4. Read the current phase plan and documents named by active work.
5. Apply the `atlas-project-tracker` skill when work needs risk classification
   or status mutation.
6. Report any mismatch before modifying code.

## Status workflow

1. Run `status`.
2. Report the current phase, objective, active work, blockers, open risks,
   recent completed work, and next bounded task.
3. Clearly distinguish live Git state from committed tracker state.
4. Do not mutate project status merely to answer a question.

## Close workflow

1. Update canonical project status through `atlas_project_status.py` only when
   a material milestone, blocker, significant risk, or next task changed.
2. Run tracker `check` and `render --check`.
3. Run `close` to regenerate the handoff.
4. Run `check` and review the handoff diff for bounded, non-sensitive content.
5. Report commit/PR/test/CI evidence only when it exists in authoritative
   sources. Never invent completion evidence.
6. Do not begin the next bounded task automatically.

## Trigger boundary

Automatic invocation means follow this workflow when the task itself is a
material Atlas handoff event. It does not mean run the skill for every shell
command, build, test, lint, or follow-up inside the same task.
