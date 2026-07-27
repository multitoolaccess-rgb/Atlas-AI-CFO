# FinanceCopilot AGENTS

Read SOUL.md, STYLE.md, and USER.md before every interaction.

## Tool Surface

| Tool | Source | When to Use |
|------|--------|-------------|
| `rules_evaluate` | rules-service `/evaluate` | First — deterministic rule evaluation (drift, idle cash, goal progress) |
| `finlynq_get_state` | Finlynq `GET /state` | Full financial state: summary + accounts[] + transactions[] + user_goals[] |
| `telegram_notify` | telegram-gateway | Important alerts that need human attention (**planned — not yet implemented**; Phase 3) |

## Architecture

- **Finlynq** (`localhost:8001`) is the canonical source of truth. Owns accounts, transactions, categories, imports, and the `/state` aggregator.
- **rules-service** (`localhost:8000`) is the API gateway. Its `/api/dashboard/summary`, `/api/categories/*`, and `/api/imports/upload` are thin httpx forwarders to Finlynq. Other endpoints (flows, trends, breakdown, insights, anomalies, upcoming-bills) query the shared DB directly.
- **Shared DB**: both services read/write the same `finance.db` (SQLite in dev, Postgres in prod). Phase F2 wiring ensures they resolve to the same DATABASE_URL.

## Decision Flow

1. `rules_evaluate` for rule-based recommendations
2. `finlynq_get_state` to verify current position before acting
3. `telegram_notify` for time-sensitive alerts only
