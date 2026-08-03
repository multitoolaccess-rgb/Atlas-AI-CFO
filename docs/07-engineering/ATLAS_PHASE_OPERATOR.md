# Atlas Phase Operator

Opt-in developer tooling for a separately authorized phase. Start with:

```bash
python3 scripts/atlas_phase_operator.py start --phase phase-3
```

It uses `workspace-write`, approval policy `never`, JSONL, and one persistent
Codex session. State and logs live in ignored `.atlas-operator-state/`.
Resume with `resume --phase phase-3`. It stops between iterations on any
non-`continue` status, limits, quota/rate errors, unsafe Git, or recovery.
The agent result must contain `status`, `summary`, `completed_work`,
`validation`, `git_state`, `tracker_state`, `next_bounded_task`, `next_prompt`,
and `handoff_updated`. Phase completion is accepted only after tracker exit
criteria and certification checks are recorded.
