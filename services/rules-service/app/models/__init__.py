"""Lift of wealthiq backend/app/models/__init__.py plus Phase 8 Goal +
Phase 18 MerchantAlias + Phase 24 MerchantRule.

Re-exports every SQLAlchemy model lifted in Phase 3 (and Phase 8's
``Goal`` + Phase 18's ``MerchantAlias`` + Phase 24's
``MerchantRule``) so that:

- ``from app.models import User, Goal, MerchantAlias, MerchantRule`` works
  (wealthiq's pattern).
- ``app.main`` can import the full set, which forces the metadata to register
  all tables before ``alembic revision --autogenerate`` inspects it.
- ``alembic/env.py``'s ``target_metadata = Base.metadata`` sees ALL 10 tables.
"""
# Phase 3 lift — see ``docs/wealthiq-merge-plan.md`` §4 Reuse Map items 5–11.
from app.models.budget import Budget
from app.models.category import Category
from app.models.account import Account
from app.models.institution import Institution
from app.models.transaction import Transaction
from app.models.import_batch import ImportBatch
from app.models.user import User
from app.models.goal import Goal
# Phase 16 — Family Members (per-account grouping).
# Models module-level import so ``Base.metadata.create_all`` (used by
# the test conftest) registers the ``family_members`` table. The
# upline routes (accounts.py + family_members.py + plaid.py) already
# import FamilyMember directly via their route module, so this is
# the second site that needs the table registered for ``create_all``.
from app.models.family_member import FamilyMember
# Phase 18 — categorizer v2 per-user alias learning table. The categorizer's
# Pass 1 SELECTs from this table to skip past substring + fuzzy for known
# merchant text. See ``app.models.merchant_alias`` for the full schema docstring.
from app.models.merchant_alias import MerchantAlias
# Phase 24 — categorizer v3 DB-backed substring rules. The categorizer's
# Pass 2 SELECTs from this table once per bulk run so the user can
# add/remove/disable keywords via the Settings UI without redeploying
# the BE. See ``app.models.merchant_rule`` for the full schema docstring.
from app.models.merchant_rule import MerchantRule
# Phase 30c — conversation persistence for the AI Finance Assistant.
# Both tables are registered so ``Base.metadata.create_all`` (used by
# the test conftest) + ``alembic revision --autogenerate`` see them.
from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_message import AssistantMessage
# Phase 39 — portfolio positions import.
from app.models.holding import Holding
# Phase 4 — recommendation approval workflow audit trail.
from app.models.recommendation_log import RecommendationLog
from app.models.forecast import Forecast, ForecastVersion
# Phase 2 Slice 1 — deterministic, derived-from-forecast-version
# recommendation ledger (append-only; one row per derivation) and the
# user's append-only decision journal. The two models are distinct from
# the Phase-4 mutable ``RecommendationLog`` workflow audit trail.
from app.models.recommendation import Recommendation
from app.models.decision_journal_entry import DecisionJournalEntry
# Phase 3 Slice 1 — append-only outcome evaluation records for accepted
# decisions. Privacy-safe: allowlisted evidence_source_kind + hash-only
# evidence_reference_hash (no raw URLs, filenames, or identifiers).
from app.models.outcome_evaluation import OutcomeEvaluation
from app.models.decision_history import DecisionAuditEvent, DecisionHistoryEntry
from app.models.market_brief import MarketBrief
from app.models.market_brief_delivery import MarketBriefDeliveryAttempt, MarketBriefDeliveryPreference
# Phase 6 Slice 1 — owner-scoped immutable Scenario Lab identity/version history.
from app.models.scenario import Scenario, ScenarioVersion

__all__ = [
    "Budget",
    "Category",
    "Account",
    "Institution",
    "Transaction",
    "ImportBatch",
    "User",
    "Goal",
    "FamilyMember",
    "MerchantAlias",
    "MerchantRule",
    "AssistantConversation",
    "AssistantMessage",
    "Holding",
    "RecommendationLog",
    "Forecast",
    "ForecastVersion",
    "Recommendation",
    "DecisionJournalEntry",
    "OutcomeEvaluation",
    "DecisionHistoryEntry",
    "DecisionAuditEvent",
    "MarketBrief",
    "MarketBriefDeliveryAttempt",
    "MarketBriefDeliveryPreference",
    "Scenario",
    "ScenarioVersion",
]
