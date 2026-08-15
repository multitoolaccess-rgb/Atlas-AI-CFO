"""Finlynq SQLAlchemy models — Phase-F5 canonical-store surface.

Re-exports every SQLAlchemy model Finlynq owns so:

- ``from app.models import User, Account, Goal, ...`` works (rules-service pattern).
- ``app.main`` + ``app.database`` charge ``Base.metadata`` once with all
  8 tables, enabling ``Base.metadata.create_all(engine)`` on a fresh DB
  to populate the full canonical-store surface.
- ``alembic/env.py``'s ``target_metadata = Base.metadata`` sees all 8
  tables for auto-diff operations.

Mirrors ``services/rules-service/app/models/__init__.py`` re-export
pattern; the models are lifted VERBATIM from rules-service so both
services bind the same ORM class to the same DB table per Phase-F2
shared-DB wiring (no cross-service Python import — each service keeps
its own copy in lockstep).

Phase-F5 surface (canonical portfolio + transactions + state):

- ``Account``       — checking/savings/investment rows; aggregator sums
                      ``current_balance`` for ``total_balance``.
- ``Budget``        — spending-limit per (category, period); aggregator
                      does NOT surface budgets today (F5+ follow-up).
- ``Category``      — Phase-F4 categorizer lookup table (already lifted).
- ``Goal``          — multi-goal financial planning; aggregator emits
                      non-archived goals ordered by priority DESC.
- ``ImportBatch``   — one CSV/PDF/OCR statement upload's envelope;
                      aggregator's ``last_import_at`` derives from
                      ``ImportBatch.processed_at``.
- ``Institution``   — banks/brokers/exchanges (FK by Account only).
- ``Transaction``   — financial movements ledger; aggregator sums
                      positive amounts for ``total_income_month`` and
                      abs(negative) for ``total_expenses_month``.
- ``User``          — identity anchor; aggregator scopes every inner
                      query by ``User.id`` via
                      ``get_or_create_local_user``.
"""
# Phase-F5 lifted models (verbatim from rules-service). Alphabetical.
from app.models.account import Account
from app.models.account_balance_observation import AccountBalanceObservation
from app.models.account_balance_evidence import AccountBalanceEvidence
from app.models.account_currency_evidence import AccountCurrencyEvidence
from app.models.budget import Budget
from app.models.category import Category
from app.models.goal import Goal
from app.models.goal_projection_config import GoalProjectionConfig
from app.models.import_batch import ImportBatch
from app.models.institution import Institution
from app.models.transaction import Transaction
from app.models.user import User

__all__ = [
    "Account",
    "AccountBalanceObservation",
    "AccountBalanceEvidence",
    "AccountCurrencyEvidence",
    "Budget",
    "Category",
    "Goal",
    "GoalProjectionConfig",
    "ImportBatch",
    "Institution",
    "Transaction",
    "User",
]
