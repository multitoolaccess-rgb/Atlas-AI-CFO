# Atlas Delivery Phase Plan

This plan translates the 12-month roadmap and delivery milestones into bounded
implementation phases. `PROJECT_STATUS.json` is the current-state authority.

| Phase | Outcome | Entry condition | Exit criteria |
| --- | --- | --- | --- |
| Phase 0 | Validated Atlas foundation | Imported foundation under review | Decimal projection authority, parity fixtures/docs, safe import, isolated service environments, synthetic fixture coverage and CI evidence complete. |
| Phase 1 | Forecast persistence | Phase 0 complete and explicitly authorized | Versioned forecast records, migrations, authorization, audit evidence, tests, and rollback path. |
| Phase 2 | Forecast UI migration | Phase 1 complete and explicitly authorized | UI uses persisted forecasts, preserves explainability, has accessibility and parity coverage. |
| Phase 3 | Goal-linked recommendations | Phase 2 complete and explicitly authorized | Recommendations link goals, evidence, risks, confidence, approvals, and evaluation. |
| Phase 4 | Decision journal | Phase 3 complete and explicitly authorized | Decisions, alternatives, outcomes, permissions, audit history, and recovery are tested. |

No phase starts automatically. Review the active phase, dependencies, and exit
criteria before authorizing the next bounded task.

Project-status consistency is enforced in pull-request CI, not by a blocking
local hook, so agents can record legitimate work in progress without bypasses
or duplicated checks.
