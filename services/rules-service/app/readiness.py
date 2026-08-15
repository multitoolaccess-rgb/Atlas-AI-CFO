"""Sanitized, authenticated local-readiness contract for Atlas.

This module deliberately reports operational state only. It never reads or
returns balances, transactions, holdings, forecast payloads, credentials,
connection strings, local paths, or provider responses. Feature flags remain
owned by the Rules Service settings object; the browser can only observe them.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Account, AccountBalanceEvidence, AccountBalanceObservation, AccountCurrencyEvidence, Forecast, User

ReadinessState = Literal["ready", "unavailable", "blocked", "degraded", "disabled"]
OverallReadinessState = Literal[
    "ready",
    "ready_with_blocked_optional_capabilities",
    "configuration_failure",
    "unsafe_state",
]


class ReadinessComponent(BaseModel):
    """One safe operational readiness result."""

    model_config = ConfigDict(extra="forbid")

    component: str = Field(min_length=1, max_length=64)
    state: ReadinessState
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    recovery_action: str = Field(min_length=1, max_length=240)
    last_checked: str
    dependencies: dict[str, bool]
    version: str | None = Field(default=None, max_length=64)


class ReadinessResponse(BaseModel):
    """The authenticated `/api/system/readiness` response."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["atlas-readiness/v1"] = "atlas-readiness/v1"
    overall_state: OverallReadinessState
    checked_at: str
    checks: tuple[ReadinessComponent, ...]
    feature_flags: dict[str, bool]
    credentials: dict[str, bool]
    prohibited_capabilities: dict[str, Literal["disabled", "not_configured"]]


_FLAG_NAMES = (
    "atlas_forecast_persistence_enabled",
    "atlas_forecast_read_api_enabled",
    "atlas_decision_history_api_enabled",
    "atlas_market_brief_generation_enabled",
    "atlas_market_brief_read_api_enabled",
    "atlas_market_brief_external_provider_enabled",
    "atlas_market_brief_email_delivery_enabled",
    "atlas_market_brief_scheduler_enabled",
    "atlas_market_brief_local_summarization_enabled",
    "atlas_scenario_lab_enabled",
)

def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _component(
    name: str,
    state: ReadinessState,
    reason: str,
    recovery: str,
    checked_at: str,
    dependencies: dict[str, bool],
    version: str | None = None,
) -> ReadinessComponent:
    return ReadinessComponent(
        component=name,
        state=state,
        reason_code=reason,
        recovery_action=recovery,
        last_checked=checked_at,
        dependencies=dependencies,
        version=version,
    )


def _repository_sha() -> str | None:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{4,40}", value) else None


def _migration_snapshot(db: Session) -> tuple[str | None, tuple[str, ...]]:
    """Read migration state and repository heads without changing anything."""
    current: str | None = None
    try:
        rows = db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if rows:
            current = str(rows[0])
    except Exception:
        current = None

    versions_dir = Path(__file__).resolve().parents[1] / "alembic"
    config = Config(str(versions_dir.parent / "alembic.ini"))
    config.set_main_option("script_location", str(versions_dir))
    try:
        heads = tuple(sorted(ScriptDirectory.from_config(config).get_heads()))
    except Exception:
        heads = ()
    return current, heads


def _currency_state(db: Session, user_id: int | None) -> tuple[ReadinessState, str, str, bool]:
    if user_id is None:
        return "blocked", "local_user_missing", "Open Settings once to initialize the local user, then retry.", False
    accounts = list(db.scalars(select(Account).where(Account.user_id == user_id, Account.is_active.is_(True))))
    if not accounts:
        return "blocked", "currency_evidence_incomplete", "Add or import an account with explicit currency evidence; a preference alone is not sufficient.", False
    now = datetime.now(timezone.utc)
    resolved: list[str] = []
    reasons: list[str] = []
    for account in accounts:
        events = list(
            db.scalars(
                select(AccountCurrencyEvidence)
                .where(AccountCurrencyEvidence.account_id == account.id, AccountCurrencyEvidence.user_id == user_id)
                .order_by(AccountCurrencyEvidence.recorded_at.asc(), AccountCurrencyEvidence.id.asc())
            )
        )
        active = None
        revoked = False
        reason = "currency_unknown"
        for event in events:
            if event.event_type == "assertion":
                if active is not None and active.currency_code != event.currency_code:
                    reason = "currency_conflict"
                    active = None
                    break
                active, revoked, reason = event, False, "currency_authority_ready"
            elif event.event_type == "correction" and active is not None and event.supersedes_event_id == active.id:
                active, revoked, reason = event, False, "currency_authority_ready"
            elif event.event_type == "revocation" and active is not None and event.supersedes_event_id == active.id:
                active, revoked, reason = None, True, "currency_revoked"
            else:
                reason = "currency_conflict"
                active = None
                break
        if active is None:
            reason = "currency_revoked" if revoked else reason
        elif active.currency_code != "USD":
            resolved.append(active.currency_code or "")
            reason = "currency_unsupported"
        else:
            observed_at = active.observed_at.replace(tzinfo=timezone.utc) if active.observed_at and active.observed_at.tzinfo is None else active.observed_at
            if observed_at is None or observed_at > now or now - observed_at > timedelta(days=7):
                reason = "currency_stale"
            else:
                resolved.append("USD")
        reasons.append(reason)
    if len(set(code for code in resolved if code)) > 1:
        return "blocked", "currency_mixed", "Resolve mixed active-account currencies before enabling projection capabilities.", False
    for reason in ("currency_conflict", "currency_revoked", "currency_stale", "currency_unsupported", "currency_unknown"):
        if reason in reasons:
            return "blocked", reason, "Resolve authoritative USD evidence for every active account; do not substitute the user preference.", False
    if all(reason == "currency_authority_ready" for reason in reasons):
        return "ready", "currency_authority_ready", "No action required.", True
    return "blocked", "currency_evidence_incomplete", "Resolve authoritative USD evidence for every active account; do not substitute the user preference.", False


def _canonical_balance(value: object) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("balance_amount_invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("balance_amount_invalid") from exc
    if not parsed.is_finite() or parsed.copy_abs() > Decimal("999999999999999999999999999999999999.99"):
        raise ValueError("balance_amount_precision_unavailable")
    rendered = format(parsed, "f")
    sign = "-" if rendered.startswith("-") else ""
    unsigned = rendered[1:] if sign else rendered
    integral, _, fractional = unsigned.partition(".")
    if len(fractional) > 2:
        raise ValueError("balance_amount_precision_unavailable")
    canonical = f"{sign}{integral}.{fractional.ljust(2, '0')}"
    return "0.00" if canonical == "-0.00" else canonical


def _balance_hash(account: Account, amount: str | None = None) -> str:
    payload = {
        "account_id": int(account.id),
        "account_type": account.account_type,
        "amount": amount if amount is not None else _canonical_balance(account.current_balance),
        "is_active": bool(account.is_active),
        "user_id": int(account.user_id),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _evidence_state_hash(account: Account, amount: str, observed_at: datetime) -> str:
    payload = {
        "account_id": int(account.id), "amount": amount, "currency_code": "USD",
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        "source_kind": "operator_confirmed", "user_id": int(account.user_id),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _balance_state(db: Session, user_id: int | None) -> tuple[ReadinessState, str, str, bool]:
    if user_id is None:
        return "blocked", "local_user_missing", "Open Settings once to initialize the local user, then retry.", False
    try:
        accounts = list(db.scalars(select(Account).where(Account.user_id == user_id, Account.is_active.is_(True))))
        events = list(db.scalars(select(AccountBalanceEvidence).where(
            AccountBalanceEvidence.user_id == user_id
        ).order_by(AccountBalanceEvidence.recorded_at.asc(), AccountBalanceEvidence.id.asc())))
    except Exception:
        return "blocked", "balance_evidence_incomplete", "Apply the approved exact-cent balance evidence migration; Atlas never migrates from this screen.", False
    if not accounts:
        return "blocked", "balance_evidence_incomplete", "No active account balance-authority scope is available.", False
    by_account: dict[int, list[AccountBalanceEvidence]] = {}
    for event in events:
        by_account.setdefault(int(event.account_id), []).append(event)
    now = datetime.now(timezone.utc)
    reasons: list[str] = []
    for account in accounts:
        account_events = by_account.get(int(account.id), [])
        assertions: dict[str, AccountBalanceEvidence] = {}
        revoked: set[str] = set()
        invalid = False
        for event in account_events:
            if event.account_id != account.id or event.source_kind != "operator_confirmed" or event.actor_category != "local_operator" or event.currency_code != "USD":
                invalid = True
                break
            if event.event_type == "assertion" and event.amount is not None and event.supersedes_event_id is None:
                assertions[event.id] = event
            elif event.event_type != "revocation":
                invalid = True
                break
        if invalid:
            reasons.append("balance_evidence_conflict")
            continue
        for event in account_events:
            if event.event_type == "revocation":
                if event.amount is not None or not event.supersedes_event_id or event.supersedes_event_id not in assertions:
                    invalid = True
                    break
                revoked.add(event.supersedes_event_id)
        if invalid:
            reasons.append("balance_evidence_conflict")
            continue
        valid = [event for event_id, event in assertions.items() if event_id not in revoked]
        if not valid:
            reasons.append("balance_evidence_revoked" if revoked else "balance_evidence_unknown")
            continue
        event = max(valid, key=lambda item: (item.observed_at, item.recorded_at, item.id))
        try:
            observed = event.observed_at.replace(tzinfo=timezone.utc) if event.observed_at.tzinfo is None else event.observed_at.astimezone(timezone.utc)
            amount = _canonical_balance(event.amount)
            current_amount = _canonical_balance(account.current_balance)
            current_hash = _balance_hash(account, current_amount)
        except (AttributeError, ValueError) as exc:
            reasons.append(str(exc))
            continue
        if event.precondition_hash != current_hash or amount != current_amount:
            reasons.append("balance_evidence_changed")
        elif event.state_hash != _evidence_state_hash(account, amount, observed):
            reasons.append("balance_evidence_conflict")
        elif observed > now:
            reasons.append("balance_evidence_future")
        elif now - observed > timedelta(days=7):
            reasons.append("balance_evidence_stale")
        elif now - observed > timedelta(days=6):
            reasons.append("balance_evidence_nearing_expiry")
        else:
            reasons.append("balance_evidence_current")
    for reason in (
        "balance_amount_invalid", "balance_amount_precision_unavailable", "balance_evidence_changed",
        "balance_evidence_conflict", "balance_evidence_future", "balance_evidence_stale",
        "balance_evidence_revoked", "balance_evidence_unknown", "balance_evidence_invalid",
        "balance_evidence_incomplete",
    ):
        if reason in reasons:
            return "blocked", reason, "Review the stored balances, then use the explicit local evidence operator; evidence never refreshes automatically.", False
    if "balance_evidence_nearing_expiry" in reasons:
        return "ready", "balance_evidence_nearing_expiry", "Reconfirm the stored balances before the seven-day freshness window expires.", True
    return "ready", "balance_evidence_current", "No action required.", True


def build_readiness(db: Session, user_sub: str) -> ReadinessResponse:
    """Build an owner-scoped, sanitized readiness snapshot."""
    checked_at = _checked_at()
    user = db.scalar(select(User).where(User.local_user_sub == user_sub, User.is_active.is_(True)))
    user_id = int(user.id) if user is not None else None
    flags = {name: bool(getattr(settings, name, False)) for name in _FLAG_NAMES}
    sha = _repository_sha()

    current, heads = _migration_snapshot(db)
    storage_ready = bool(current and heads and current in heads)
    checks: list[ReadinessComponent] = [
        _component(
            "runtime",
            "ready" if sha else "degraded",
            "runtime_ready" if sha else "runtime_version_unavailable",
            "Confirm the checkout is a Git repository and retry." if not sha else "No action required.",
            checked_at,
            {"rules_service": True, "repository_version": bool(sha)},
            sha or settings.app_version,
        ),
        _component(
            "storage",
            "ready" if storage_ready else "blocked",
            "migration_ready" if storage_ready else "migration_state_unavailable",
            "Run the approved Alembic migration check against the selected local database; Atlas never migrates from this screen." if not storage_ready else "No action required.",
            checked_at,
            {"database": current is not None, "migration_head": bool(heads)},
            current if storage_ready else None,
        ),
    ]

    try:
        currency_state, currency_reason, currency_recovery, currency_ready = _currency_state(db, user_id)
    except Exception:
        # A pre-X7 database has no evidence table yet. Readiness must report a
        # safe blocked contract rather than turn migration drift into a 500.
        currency_state, currency_reason, currency_recovery, currency_ready = (
            "blocked", "currency_evidence_incomplete",
            "Apply the approved account-currency evidence migration before reviewing currency readiness; Atlas never migrates from this screen.",
            False,
        )
    balance_state, balance_reason, balance_recovery, balance_ready = _balance_state(db, user_id)
    checks.append(_component(
        "balance_observations", balance_state, balance_reason, balance_recovery, checked_at,
        {"owner": user is not None, "observation_audit": balance_ready, "seven_day_window": True},
        "account-balance-evidence/v1" if balance_ready else None,
    ))
    financial_ready = currency_ready and balance_ready
    financial_state = currency_state if not currency_ready else balance_state
    financial_reason = currency_reason if not currency_ready else balance_reason
    financial_recovery = currency_recovery if not currency_ready else balance_recovery
    checks.append(_component(
        "financial_authority", financial_state, financial_reason, financial_recovery, checked_at,
        {"owner": user is not None, "account_currency_evidence": currency_ready, "balance_evidence": balance_ready, "usd_supported": True},
        "atlas-projection-state/v1" if financial_ready else None,
    ))

    forecast_exists = bool(user_id and db.scalar(select(Forecast.id).where(Forecast.user_id == user_id, Forecast.lifecycle_state == "active")))
    forecast_deps = financial_ready and storage_ready
    if not flags["atlas_forecast_persistence_enabled"] or not flags["atlas_forecast_read_api_enabled"]:
        forecast_state: ReadinessState = "disabled"
        forecast_reason = "forecast_flags_disabled"
        forecast_recovery = "Keep forecast flags disabled until currency, migration, retention, and synthetic acceptance gates are reviewed."
    elif not forecast_deps:
        forecast_state = "blocked"
        forecast_reason = "forecast_dependencies_unready"
        forecast_recovery = "Resolve financial authority and storage readiness before enabling forecast APIs."
    elif not forecast_exists:
        forecast_state = "blocked"
        forecast_reason = "baseline_forecast_missing"
        forecast_recovery = "Generate an approved immutable baseline forecast through the server-owned flow."
    else:
        forecast_state = "ready"
        forecast_reason = "baseline_forecast_ready"
        forecast_recovery = "No action required."
    checks.append(_component("forecasts", forecast_state, forecast_reason, forecast_recovery, checked_at, {"financial_authority": financial_ready, "storage": storage_ready, "baseline": forecast_exists}, "immutable-forecast/v1" if forecast_exists else None))

    history_enabled = flags["atlas_decision_history_api_enabled"]
    checks.append(_component(
        "decision_history",
        "ready" if history_enabled and forecast_exists else "disabled" if not history_enabled else "blocked",
        "decision_history_ready" if history_enabled and forecast_exists else "decision_history_disabled" if not history_enabled else "forecast_baseline_required",
        "No action required." if history_enabled and forecast_exists else "Enable the server-owned decision-history flag only after the forecast baseline and review gate pass." if not history_enabled else "Resolve forecast readiness first.",
        checked_at,
        {"server_flag": history_enabled, "forecast_baseline": forecast_exists},
        "atlas-decision-history/v1" if history_enabled else None,
    ))

    market_flags = flags["atlas_market_brief_generation_enabled"] or flags["atlas_market_brief_read_api_enabled"]
    market_credentials = bool(getattr(settings, "finnhub_api_key", None)) and bool(getattr(settings, "sec_user_agent", None))
    if not market_flags:
        market_state, market_reason, market_recovery = "disabled", "market_intelligence_disabled", "Keep Market Intelligence disabled until approved server-side provider configuration is present."
    elif not market_credentials:
        market_state, market_reason, market_recovery = "blocked", "market_provider_configuration_missing", "Configure approved server-side provider credentials or keep the feature disabled; never enter them in the browser."
    else:
        market_state, market_reason, market_recovery = "ready", "market_provider_configured", "No action required."
    checks.append(_component("market_intelligence", market_state, market_reason, market_recovery, checked_at, {"server_flag": market_flags, "provider_credentials": market_credentials}, "market-brief/v1" if market_state == "ready" else None))

    scenario_enabled = flags["atlas_scenario_lab_enabled"]
    if not scenario_enabled:
        scenario_state, scenario_reason, scenario_recovery = "disabled", "scenario_lab_disabled", "Keep Scenario Lab disabled until a reviewed local baseline and synthetic acceptance pass are recorded."
    elif not forecast_exists or not currency_ready:
        scenario_state, scenario_reason, scenario_recovery = "blocked", "scenario_baseline_unavailable", "Resolve authoritative currency and generate a compatible immutable baseline first."
    else:
        scenario_state, scenario_reason, scenario_recovery = "ready", "scenario_lab_ready", "No action required."
    checks.append(_component("scenario_lab", scenario_state, scenario_reason, scenario_recovery, checked_at, {"server_flag": scenario_enabled, "baseline": forecast_exists, "financial_authority": financial_ready}, "atlas-scenario/v1" if scenario_state == "ready" else None))

    unsafe_flags = flags["atlas_market_brief_email_delivery_enabled"] or flags["atlas_market_brief_scheduler_enabled"] or flags["atlas_market_brief_local_summarization_enabled"]
    checks.append(_component(
        "privacy_safety",
        "blocked" if unsafe_flags else "ready",
        "unsafe_optional_capability_enabled" if unsafe_flags else "execution_boundaries_disabled",
        "Disable email, scheduler, and local summarization flags and restart the service; this screen never changes them." if unsafe_flags else "No action required.",
        checked_at,
        {"email_disabled": not flags["atlas_market_brief_email_delivery_enabled"], "scheduler_disabled": not flags["atlas_market_brief_scheduler_enabled"], "llm_disabled": not flags["atlas_market_brief_local_summarization_enabled"], "execution_disabled": True, "money_movement_disabled": True},
        "local-single-user-boundary/v1",
    ))

    credentials = {
        "jwt_secret_configured": bool(getattr(settings, "jwt_secret", "")),
        "finnhub_api_key_present": bool(getattr(settings, "finnhub_api_key", None)),
        "sec_user_agent_present": bool(getattr(settings, "sec_user_agent", None)),
        "plaid_client_id_present": bool(getattr(settings, "plaid_client_id", None)),
        "plaid_secret_present": bool(getattr(settings, "plaid_secret", None)),
    }
    prohibited = {
        "email": "disabled" if not flags["atlas_market_brief_email_delivery_enabled"] else "not_configured",
        "scheduler": "disabled" if not flags["atlas_market_brief_scheduler_enabled"] else "not_configured",
        "llm": "disabled" if not flags["atlas_market_brief_local_summarization_enabled"] else "not_configured",
        "execution": "disabled",
        "trading": "disabled",
        "money_movement": "disabled",
    }
    if any(item.state == "unsafe_state" for item in checks):
        overall: OverallReadinessState = "unsafe_state"
    elif any(item.state == "blocked" for item in checks if item.component in {"storage", "financial_authority"}):
        overall = "configuration_failure"
    elif any(item.state in {"blocked", "unavailable", "degraded", "disabled"} for item in checks):
        overall = "ready_with_blocked_optional_capabilities"
    else:
        overall = "ready"
    return ReadinessResponse(
        overall_state=overall,
        checked_at=checked_at,
        checks=tuple(checks),
        feature_flags=flags,
        credentials=credentials,
        prohibited_capabilities=prohibited,
    )
