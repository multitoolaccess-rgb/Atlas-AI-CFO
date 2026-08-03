---
name: atlas-phase-operator
description: Explicitly operate a bounded Atlas phase through one persistent Codex session. Use only when a user explicitly requests phase operation; never for ordinary builds or autonomous phase starts.
---

# Atlas Phase Operator

Run `python3 scripts/atlas_phase_operator.py start --phase <phase-id>`. The
operator persists state under ignored `.atlas-operator-state/`, starts one
`codex exec --json` session, captures its exact session id, and resumes only
that id. It never uses `--last` or bypasses approvals/sandboxing.

Each agent iteration must emit one JSON object matching the documented result
schema. The operator advances only on `continue`; all other states stop with
safe Git, tracker, handoff, and exact resume instructions. Recovery is
read-only before a crashed session can continue.
