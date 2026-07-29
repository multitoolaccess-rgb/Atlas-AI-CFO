"""Dedicated Finlynq projection-state provider for Phase 1 B0.

The provider deliberately emits only the bounded atlas-projection-state/v1
envelope.  It never serializes Account names/numbers, transactions, uploads,
or user profile data.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.models import Account, Goal, GoalProjectionConfig, User
from app.projection_state.currency import CurrencyEvidenceError, validate_currency_evidence, validate_stable_reference


PROJECTION_STATE_SCHEMA_VERSION = "atlas-projection-state/v1"
CANONICAL_JSON_VERSION = "atlas-canonical-json/v1"
HASH_SCHEMA_VERSION = "atlas-input-state-hash/v1"
MAX_COMPONENTS = 32
MAX_PROVENANCE = 32
MAX_FRESHNESS_DAYS = 7
LIABILITY_ACCOUNT_TYPES = frozenset({"credit_card", "loan", "mortgage"})
ASSET_ACCOUNT_TYPES = frozenset({"checking", "savings", "debit_card", "investment", "hsa", "529", "401k", "ira", "crypto", "other"})


class ProjectionStateUnavailable(ValueError):
    """Stable safe code; no source row values belong in this exception."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ProjectionStateUnavailable("projection_state_unavailable")
    # SQLite does not retain tzinfo for SQLAlchemy DateTime values.  The
    # established Atlas storage convention is UTC, so recover UTC only for a
    # timestamp already accepted at the evidence boundary; never apply local
    # time or a user preference.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    value = _utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_decimal(value: Any) -> str:
    """Convert legacy Float only through Decimal(str(value)); never restore precision."""
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProjectionStateUnavailable("projection_state_unavailable") from exc
    if not parsed.is_finite() or parsed.copy_abs() > Decimal("1E+24"):
        raise ProjectionStateUnavailable("projection_state_unavailable")
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-0"}:
        return "0"
    return rendered


def _source_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _component_kind(account_type: str) -> str:
    if account_type in LIABILITY_ACCOUNT_TYPES:
        return "debt"
    if account_type in {"investment", "hsa", "529", "401k", "ira", "crypto"}:
        return "investment"
    if account_type in {"checking", "savings", "debit_card"}:
        return "cash"
    return "other_asset"


def _safe_user(db: Session, user_sub: str) -> User:
    user = db.query(User).filter(User.local_user_sub == user_sub).first()
    if user is None:
        raise ProjectionStateUnavailable("projection_state_unavailable")
    return user


def build_projection_state(
    db: Session, *, user_sub: str, goal_id: int, now: datetime | None = None
) -> dict[str, Any]:
    """Build one authorized, deterministic v1 envelope or fail closed."""
    current_time = _utc(now or datetime.now(timezone.utc))
    user = _safe_user(db, user_sub)
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if goal is None:
        # Same safe result for missing and cross-user goals.
        raise ProjectionStateUnavailable("projection_state_not_found")
    config = (
        db.query(GoalProjectionConfig)
        .filter(GoalProjectionConfig.goal_id == goal.id, GoalProjectionConfig.user_id == user.id)
        .first()
    )
    if (
        goal.is_archived
        or config is None
        or config.projection_kind != "net_worth"
        or config.currency_code != "USD"
        or config.monthly_contribution is None
    ):
        raise ProjectionStateUnavailable("projection_state_unavailable")
    config_observed = _utc(config.contribution_observed_at)
    try:
        validate_stable_reference(config.contribution_source_reference)
    except CurrencyEvidenceError as exc:
        raise ProjectionStateUnavailable("projection_state_unavailable") from exc
    if config_observed > current_time:
        raise ProjectionStateUnavailable("projection_state_unavailable")
    if (current_time - config_observed).total_seconds() > MAX_FRESHNESS_DAYS * 86400:
        raise ProjectionStateUnavailable("projection_state_unavailable")
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.is_active.is_(True))
        .order_by(Account.id.asc())
        .all()
    )
    if not accounts or len(accounts) > MAX_COMPONENTS:
        raise ProjectionStateUnavailable("projection_state_unavailable")
    components: list[dict[str, str]] = []
    source_rows: list[dict[str, Any]] = []
    observation_times: list[datetime] = [config_observed]
    for account in accounts:
        if (
            account.currency_code is None
            or account.currency_source is None
            or account.currency_observed_at is None
            or account.currency_source_reference is None
            or account.currency_code != "USD"
        ):
            raise ProjectionStateUnavailable("projection_state_unavailable")
        if account.account_type not in LIABILITY_ACCOUNT_TYPES | ASSET_ACCOUNT_TYPES:
            raise ProjectionStateUnavailable("projection_state_unavailable")
        balance_observed = _utc(account.last_sync)
        currency_observed = _utc(account.currency_observed_at)
        try:
            validate_currency_evidence(
                code=account.currency_code, source=account.currency_source,
                observed_at=currency_observed, source_reference=account.currency_source_reference,
            )
        except CurrencyEvidenceError as exc:
            raise ProjectionStateUnavailable("projection_state_unavailable") from exc
        included_observed = min(balance_observed, currency_observed)
        if included_observed > current_time:
            raise ProjectionStateUnavailable("projection_state_unavailable")
        if (current_time - included_observed).total_seconds() > MAX_FRESHNESS_DAYS * 86400:
            raise ProjectionStateUnavailable("projection_state_unavailable")
        amount = _canonical_decimal(account.current_balance)
        if account.account_type in LIABILITY_ACCOUNT_TYPES:
            if amount.startswith("-"):
                raise ProjectionStateUnavailable("projection_state_unavailable")
            amount = "-" + amount
        component = {
            "kind": _component_kind(account.account_type),
            "amount": amount,
            "source_reference": f"finlynq-account-{account.id}",
            "observed_at": _timestamp(included_observed),
        }
        components.append(component)
        source_rows.append(
            {
                "account_id": account.id,
                "account_type": account.account_type,
                "amount": amount,
                "balance_observed_at": _timestamp(balance_observed),
                "currency_code": account.currency_code,
                "currency_source": account.currency_source,
                "currency_observed_at": _timestamp(currency_observed),
                "currency_source_reference": account.currency_source_reference,
                "float_source_representation": True,
                "precision_restored": False,
            }
        )
        observation_times.append(included_observed)
    components.sort(key=lambda item: (item["kind"], item["source_reference"], item["observed_at"]))
    contribution_amount = _canonical_decimal(config.monthly_contribution)
    as_of = min(observation_times)
    age_days = int((current_time - as_of).total_seconds() // 86400)
    source_payload = {
        "accounts": source_rows,
        "goal_id": goal.id,
        "projection_kind": config.projection_kind,
        "currency": config.currency_code,
        "contribution": {
            "amount": contribution_amount,
            "source_reference": config.contribution_source_reference,
            "observed_at": _timestamp(config_observed),
        },
    }
    digest = _source_hash(source_payload)
    provenance = [{
        "source_system": "finlynq",
        "reference_id": f"finlynq-projection-goal-{goal.id}",
        "observed_at": _timestamp(as_of),
        "record_count": len(components) + 1,
        "source_state_hash": digest,
    }]
    if len(provenance) > MAX_PROVENANCE:
        raise ProjectionStateUnavailable("projection_state_unavailable")
    return {
        "schema_version": PROJECTION_STATE_SCHEMA_VERSION,
        "canonicalization": {
            "canonical_json_version": CANONICAL_JSON_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "hash_algorithm": "sha256",
        },
        "user_id": user.local_user_sub,
        "goal_id": goal.id,
        "as_of_timestamp": _timestamp(as_of),
        "currency": "USD",
        "current_value_components": components,
        "contribution_inputs": [{
            "kind": "monthly_investable_cash_flow",
            "amount": contribution_amount,
            "source_reference": f"finlynq-config-{config.id}",
            "observed_at": _timestamp(config_observed),
        }],
        "freshness": {
            "max_data_age_days": MAX_FRESHNESS_DAYS,
            "observed_age_days": age_days,
            "source_updated_at": _timestamp(as_of),
        },
        "provenance": provenance,
        "missing_data_codes": ["legacy_float_balance_representation"],
        "reconciliation_state": "partial",
    }
