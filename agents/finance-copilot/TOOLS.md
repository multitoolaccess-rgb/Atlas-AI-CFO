# FinanceCopilot TOOLS

## finlynq_get_state

Retrieves the full financial state from Finlynq's canonical store.

**Endpoint:** `GET /state` on Finlynq (port 8001)

**Auth:** Requires `fc_session` JWT cookie (minted by `POST /api/auth/devlogin` on rules-service).

**Query params:**
- `limit` (int, default 100, max 1000): caps the transactions list.

**Response shape (`StateOut`):**

```json
{
  "total_balance": 125000.00,
  "total_income_month": 8500.00,
  "total_expenses_month": 5200.00,
  "accounts_count": 4,
  "transactions_count": 47,
  "last_sync": "2026-07-12T10:00:00Z",
  "import_batches_count": 3,
  "last_import_at": "2026-07-10T14:30:00Z",
  "user_goals": [
    {
      "id": 1,
      "name": "$15M Goal",
      "target_amount": 15000000.00,
      "target_date": null,
      "horizon_years": 20,
      "priority": 100,
      "is_archived": false,
      "notes": null,
      "created_at": "2026-06-28T00:00:00Z",
      "updated_at": null
    }
  ],
  "accounts": [
    {
      "id": 1,
      "account_name": "Chase Checking",
      "account_type": "checking",
      "account_subtype": null,
      "current_balance": 15000.00,
      "is_active": true,
      "last_sync": "2026-07-12T10:00:00Z"
    }
  ],
  "transactions": [
    {
      "id": 42,
      "description": "PAYROLL DIRECT DEPOSIT",
      "amount": 4250.00,
      "transaction_date": "2026-07-11T00:00:00Z",
      "merchant_name": null,
      "is_pending": false,
      "account_id": 1,
      "account_name": "Chase Checking",
      "account_type": "checking",
      "category_id": 5,
      "category_name": "Base Salary"
    }
  ]
}
```

**Usage by agent persona:**
- Call `finlynq_get_state` to understand the user's current financial position before making recommendations.
- `total_balance` = net worth across all active accounts.
- `total_income_month` / `total_expenses_month` = rolling 60-day window.
- `user_goals` = non-archived goals ordered by priority DESC.
- `accounts` = all active accounts with current balances.
- `transactions` = most recent transactions (capped by `limit`).

**Companion tools:**
- `rules_evaluate` — deterministic rule evaluation against policy files.
- `telegram_notify` — send alerts to the user's Telegram chat.

---

## rules_evaluate

Evaluates financial rules against the current state. See `services/rules-service/app/routes/evaluate.py`.

## telegram_notify

Sends notifications to the user's configured Telegram chat. See `services/telegram-gateway/`.
