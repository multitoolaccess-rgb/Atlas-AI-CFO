#!/usr/bin/env python3
"""Atlas Doctor: bounded, read-only local readiness diagnostics.

The command intentionally uses only standard-library probes. It never imports
application startup hooks, opens a database for writing, starts/stops a
process, changes feature flags, runs migrations, or prints sensitive values.

Exit codes:
  0 ready
  1 ready with blocked optional capabilities
  2 configuration failure
  3 unsafe state
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "services" / "rules-service"
FINLYNQ_DIR = ROOT / "services" / "finlynq"
KNOWN_FLAGS = (
    "ATLAS_FORECAST_PERSISTENCE_ENABLED",
    "ATLAS_FORECAST_READ_API_ENABLED",
    "ATLAS_DECISION_HISTORY_API_ENABLED",
    "ATLAS_MARKET_BRIEF_GENERATION_ENABLED",
    "ATLAS_MARKET_BRIEF_READ_API_ENABLED",
    "ATLAS_MARKET_BRIEF_EXTERNAL_PROVIDER_ENABLED",
    "ATLAS_MARKET_BRIEF_EMAIL_DELIVERY_ENABLED",
    "ATLAS_MARKET_BRIEF_SCHEDULER_ENABLED",
    "ATLAS_MARKET_BRIEF_LOCAL_SUMMARIZATION_ENABLED",
    "ATLAS_SCENARIO_LAB_ENABLED",
)
BOOL_TRUE = {"1", "true", "yes", "on"}
BOOL_FALSE = {"0", "false", "no", "off", ""}
APPROVED_CURRENCY_SOURCES = {"structured_provider", "structured_statement", "operator_confirmed"}
APPROVED_EVENT_TYPES = {"assertion", "correction", "revocation"}
MAX_CURRENCY_AGE_DAYS = 7


def env_file_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def git_state() -> tuple[str | None, bool | None]:
    try:
        sha_result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=2, check=False)
        status_result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None, None
    value = sha_result.stdout.strip()
    sha = value if sha_result.returncode == 0 and re.fullmatch(r"[0-9a-f]{4,40}", value) else None
    return sha, status_result.returncode == 0 and not status_result.stdout


def safe_sha() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{4,40}", value) else None


def command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    line = (result.stdout or result.stderr).strip().splitlines()
    return line[0] if line else None


def port_probe(port: int) -> dict[str, Any]:
    try:
        result = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN"], capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "reason_code": "port_probe_unavailable", "recovery_action": "Install or restore the local port-inspection command, then rerun Atlas Doctor."}
    lines = [line for line in result.stdout.splitlines()[1:] if line.strip()]
    if not lines:
        return {"state": "ready", "reason_code": "port_available", "recovery_action": "No action required.", "listening": False, "atlas_owned": False}
    pids: set[str] = set()
    for line in lines:
        fields = line.split()
        if len(fields) > 1 and fields[1].isdigit():
            pids.add(fields[1])
    owned = False
    for pid in pids:
        try:
            cwd_result = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=2, check=False)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        cwd = next((line[1:] for line in cwd_result.stdout.splitlines() if line.startswith("n")), "")
        if cwd == str(ROOT) or cwd.startswith(str(ROOT) + os.sep):
            owned = True
            break
    if owned:
        return {"state": "ready", "reason_code": "atlas_process_listening", "recovery_action": "No action required.", "listening": True, "atlas_owned": True}
    return {"state": "blocked", "reason_code": "port_owned_by_other_process", "recovery_action": "Choose an unused local port with ATLAS_*_PORT; do not stop an unrelated process.", "listening": True, "atlas_owned": False}


def health_probe(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = json.loads(response.read().decode("utf-8"))
        healthy = response.status == 200 and body.get("status") == "healthy"
        return {"state": "ready" if healthy else "degraded", "reason_code": "service_healthy" if healthy else "service_health_unconfirmed", "recovery_action": "No action required." if healthy else "Inspect the service log and rerun Atlas Doctor.", "healthy": healthy, "reported_sha": body.get("git_sha") if isinstance(body.get("git_sha"), str) else None}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return {"state": "unavailable", "reason_code": "service_unreachable", "recovery_action": "Start the affected Atlas-owned service with the documented local lifecycle, then rerun Atlas Doctor.", "healthy": False, "reported_sha": None}


def database_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw = database_url[len("sqlite:///"):]
    if raw.startswith("/"):
        return Path("/" + raw.lstrip("/"))
    return (RULES_DIR / raw).resolve()


def migration_heads() -> tuple[str, ...]:
    revisions: dict[str, str | None] = {}
    referenced: set[str] = set()
    pattern = re.compile(r"^revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    down_pattern = re.compile(r"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*(.+)$", re.MULTILINE)
    for path in sorted((RULES_DIR / "alembic" / "versions").glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = pattern.search(text)
        if not match:
            continue
        revision = match.group(1)
        revisions[revision] = revision
        down = down_pattern.search(text)
        if down:
            for value in re.findall(r"['\"]([^'\"]+)['\"]", down.group(1)):
                if value != "None":
                    referenced.add(value)
    return tuple(sorted(set(revisions) - referenced))


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _currency_authority_snapshot(conn: sqlite3.Connection) -> dict[str, str]:
    """Derive aggregate authority from immutable events without exposing IDs."""
    try:
        accounts = conn.execute("SELECT id FROM accounts WHERE is_active = 1 ORDER BY id").fetchall()
        events = conn.execute(
            """SELECT id, account_id, event_type, source_kind, currency_code,
                      observed_at, supersedes_event_id
               FROM account_currency_evidence
               ORDER BY recorded_at ASC, id ASC"""
        ).fetchall()
    except sqlite3.OperationalError:
        return {
            "state": "blocked",
            "reason_code": "currency_evidence_incomplete",
            "recovery_action": "Apply the approved account-currency evidence migration; Atlas Doctor never migrates from this screen.",
        }
    if not accounts:
        return {"state": "blocked", "reason_code": "currency_evidence_incomplete", "recovery_action": "Add or import an account with explicit currency evidence; a preference is not evidence."}
    events_by_account: dict[int, list[tuple[Any, ...]]] = {}
    for event in events:
        events_by_account.setdefault(int(event[1]), []).append(event)
    current_time = datetime.now(timezone.utc)
    states: list[tuple[str, str | None]] = []
    for account_row in accounts:
        account_id = int(account_row[0])
        active: tuple[str, str, datetime] | None = None
        revoked = False
        reason = "currency_unknown"
        for event_id, event_account_id, event_type, source_kind, code, observed_raw, supersedes_id in events_by_account.get(account_id, []):
            if event_type not in APPROVED_EVENT_TYPES:
                reason, active = "currency_evidence_incomplete", None
                break
            observed = _parse_utc(observed_raw)
            if event_type == "assertion":
                if source_kind not in APPROVED_CURRENCY_SOURCES or not code or active is not None and active[1] != code:
                    reason, active = "currency_conflict" if active is not None else "currency_evidence_incomplete", None
                    break
                active, revoked, reason = (str(event_id), str(code), observed) if observed else None, False, "currency_authority_ready"
                if active is None:
                    reason = "currency_evidence_incomplete"
                    break
            elif event_type == "correction":
                if source_kind != "correction" or not code or active is None or supersedes_id != active[0] or observed is None:
                    reason, active = "currency_conflict", None
                    break
                active, revoked, reason = (str(event_id), str(code), observed), False, "currency_authority_ready"
            elif event_type == "revocation":
                if source_kind != "revocation" or code is not None or active is None or supersedes_id != active[0]:
                    reason, active = "currency_conflict", None
                    break
                active, revoked, reason = None, True, "currency_revoked"
        if active is None:
            reason = "currency_revoked" if revoked else reason
        elif active[1] != "USD":
            states.append(("currency_unsupported", active[1]))
            continue
        elif current_time - active[2] > timedelta(days=MAX_CURRENCY_AGE_DAYS) or active[2] > current_time:
            states.append(("currency_stale", active[1]))
            continue
        else:
            states.append(("currency_authority_ready", "USD"))
            continue
        states.append((reason, None))
    codes = {code for reason, code in states if code is not None}
    if len(codes) > 1:
        return {"state": "blocked", "reason_code": "currency_mixed", "recovery_action": "Resolve mixed active-account currencies before enabling projection capabilities."}
    for reason in ("currency_conflict", "currency_revoked", "currency_stale", "currency_unsupported", "currency_unknown", "currency_evidence_incomplete"):
        if any(item[0] == reason for item in states):
            return {"state": "blocked", "reason_code": reason, "recovery_action": "Resolve authoritative USD evidence for every active account; a preference is not evidence."}
    return {"state": "ready", "reason_code": "currency_authority_ready", "recovery_action": "No action required."}


def _canonical_balance(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("balance_invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("balance_invalid") from exc
    if not parsed.is_finite() or parsed.copy_abs() > Decimal("1E+24"):
        raise ValueError("balance_invalid")
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _balance_hash_from_row(row: tuple[Any, ...]) -> str:
    account_id, user_id, account_type, current_balance, is_active = row
    payload = {
        "account_id": int(account_id),
        "account_type": account_type,
        "balance_representation": _canonical_balance(current_balance),
        "is_active": bool(is_active),
        "user_id": int(user_id),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _balance_observation_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        accounts = conn.execute(
            "SELECT id, user_id, account_type, current_balance, is_active, last_sync FROM accounts WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        events = conn.execute(
            """SELECT id, user_id, account_id, source_kind, actor_category, observed_at,
                      precondition_hash, recorded_at
               FROM account_balance_observations
               ORDER BY recorded_at DESC, id DESC"""
        ).fetchall()
    except sqlite3.OperationalError:
        return {"state": "blocked", "reason_code": "balance_observation_incomplete", "recovery_action": "Run the explicit local balance-observation operator after reviewing the stored balances."}
    if not accounts:
        return {"state": "blocked", "reason_code": "balance_observation_incomplete", "recovery_action": "No active account observation scope is available."}
    latest: dict[int, tuple[Any, ...]] = {}
    for event in events:
        latest.setdefault(int(event[2]), event)
    now = datetime.now(timezone.utc)
    reasons: list[str] = []
    for account in accounts:
        event = latest.get(int(account[0]))
        if event is None:
            reasons.append("balance_observation_unknown")
            continue
        if event[1] != account[1] or event[3] != "operator_confirmed" or event[4] != "local_operator":
            reasons.append("balance_observation_incomplete")
            continue
        observed = _parse_utc(event[5])
        last_sync = _parse_utc(account[5])
        try:
            state_hash = _balance_hash_from_row(account)
        except ValueError as exc:
            reasons.append(str(exc))
            continue
        if observed is None or last_sync is None:
            reasons.append("balance_observation_incomplete")
        elif observed > now:
            reasons.append("balance_observation_future")
        elif event[6] != state_hash:
            reasons.append("balance_observation_changed")
        elif last_sync != observed:
            reasons.append("balance_observation_conflict")
        elif now - observed > timedelta(days=7):
            reasons.append("balance_observation_stale")
        elif now - observed > timedelta(days=6):
            reasons.append("balance_observation_nearing_expiry")
        else:
            reasons.append("balance_observation_current")
    for reason in (
        "balance_invalid", "balance_observation_changed", "balance_observation_conflict",
        "balance_observation_future", "balance_observation_stale", "balance_observation_unknown",
        "balance_observation_incomplete",
    ):
        if reason in reasons:
            return {"state": "blocked", "reason_code": reason, "recovery_action": "Review the stored balances, then rerun the explicit local balance-observation operator; no timestamp is refreshed automatically."}
    if "balance_observation_nearing_expiry" in reasons:
        return {"state": "ready", "reason_code": "balance_observation_nearing_expiry", "recovery_action": "Reconfirm the stored balances before the seven-day freshness window expires."}
    return {"state": "ready", "reason_code": "balance_observation_current", "recovery_action": "No action required."}


def sqlite_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"state": "unavailable", "reason_code": "non_sqlite_database", "recovery_action": "Use the selected database operator check; Atlas Doctor does not print or expose connection details."}
    if not path.exists():
        return {"state": "blocked", "reason_code": "database_not_found", "recovery_action": "Create or select the approved local database through the documented lifecycle; Atlas Doctor does not create it."}
    uri = f"file:{path}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=1) as conn:
            current = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            wal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            currency_authority = _currency_authority_snapshot(conn)
            balance_observation = _balance_observation_snapshot(conn)
    except sqlite3.Error:
        return {"state": "blocked", "reason_code": "database_readiness_unavailable", "recovery_action": "Run the approved read-only database and migration check against the selected local database."}
    heads = migration_heads()
    migration_ready = bool(current and heads and current in heads)
    return {
        "state": "ready" if migration_ready else "blocked",
        "reason_code": "migration_ready" if migration_ready else "migration_mismatch",
        "recovery_action": "No action required." if migration_ready else "Run the approved Alembic migration check; Atlas Doctor never upgrades the database.",
        "migration_current": current,
        "migration_heads": heads,
        "wal_state": "enabled" if str(wal).lower() == "wal" else str(wal),
        "currency_authority": currency_authority,
        "balance_observation": balance_observation,
    }


def bool_value(values: dict[str, str], key: str) -> bool:
    raw = os.environ.get(key, values.get(key, "false")).strip().lower()
    return raw in BOOL_TRUE


def build_report() -> dict[str, Any]:
    rules_values = env_file_values(RULES_DIR / ".env")
    database_url = os.environ.get("DATABASE_URL", rules_values.get("DATABASE_URL", "postgresql://configured-server/database"))
    sha, clean = git_state()
    ui_port = int(os.environ.get("ATLAS_UI_PORT", "3333"))
    rules_port = int(os.environ.get("ATLAS_RULES_PORT", "8888"))
    finlynq_port = int(os.environ.get("ATLAS_FINLYNQ_PORT", "8889"))
    flags = {key.removeprefix("ATLAS_").lower(): bool_value(rules_values, key) for key in KNOWN_FLAGS}
    credentials = {
        "jwt_secret_configured": bool(os.environ.get("JWT_SECRET", rules_values.get("JWT_SECRET", ""))),
        "finnhub_api_key_present": bool(os.environ.get("FINNHUB_API_KEY", rules_values.get("FINNHUB_API_KEY", ""))),
        "sec_user_agent_present": bool(os.environ.get("SEC_USER_AGENT", rules_values.get("SEC_USER_AGENT", ""))),
        "plaid_client_id_present": bool(os.environ.get("PLAID_CLIENT_ID", rules_values.get("PLAID_CLIENT_ID", ""))),
        "plaid_secret_present": bool(os.environ.get("PLAID_SECRET", rules_values.get("PLAID_SECRET", ""))),
    }
    database = sqlite_snapshot(database_path(database_url))
    checks = {
        "repository": {"state": "ready" if sha and clean else "blocked", "reason_code": "clean_checkout" if sha and clean else "dirty_checkout" if sha else "git_unavailable", "recovery_action": "Review and commit or safely revert only known changes before continuing." if sha and not clean else "Confirm this directory is a clean Git checkout." if not sha else "No action required.", "sha": sha, "clean_state": clean},
        "python": {"state": "ready" if sys.version_info[:2] == (3, 12) else "degraded", "reason_code": "python_version_checked", "recovery_action": "Use the documented Python 3.12 environment." if sys.version_info[:2] != (3, 12) else "No action required.", "version": "%d.%d.%d" % sys.version_info[:3]},
        "node": {"state": "ready" if command_version(["node", "--version"]) else "blocked", "reason_code": "node_available" if command_version(["node", "--version"]) else "node_unavailable", "recovery_action": "Install or restore the repository's supported Node runtime."},
        "rules_environment": {"state": "ready" if (ROOT / ".venv-rules" / "bin" / "python").exists() else "blocked", "reason_code": "rules_environment_available" if (ROOT / ".venv-rules" / "bin" / "python").exists() else "rules_environment_missing", "recovery_action": "Run the documented isolated-environment bootstrap."},
        "finlynq_environment": {"state": "ready" if (ROOT / ".venv-finlynq" / "bin" / "python").exists() else "blocked", "reason_code": "finlynq_environment_available" if (ROOT / ".venv-finlynq" / "bin" / "python").exists() else "finlynq_environment_missing", "recovery_action": "Run the documented isolated-environment bootstrap."},
        "ui_port": port_probe(ui_port),
        "rules_port": port_probe(rules_port),
        "finlynq_port": port_probe(finlynq_port),
        "rules_health": health_probe(f"http://127.0.0.1:{rules_port}/health"),
        "finlynq_health": health_probe(f"http://127.0.0.1:{finlynq_port}/health"),
        "ui_health": health_probe(f"http://127.0.0.1:{ui_port}/"),
        "storage": database,
        "database_mode": {"state": "ready", "mode": "sqlite" if database_url.startswith("sqlite:") else "server", "recovery_action": "No action required."},
        "account_currency_authority": database.get("currency_authority", {"state": "unavailable", "reason_code": "database_probe_unavailable", "recovery_action": "Run the isolated database readiness check."}),
        "balance_observation": database.get("balance_observation", {"state": "unavailable", "reason_code": "database_probe_unavailable", "recovery_action": "Run the isolated database readiness check."}),
        "forecast_baseline_prerequisites": {"state": "disabled" if not flags["forecast_persistence_enabled"] else "blocked", "reason_code": "forecast_flags_disabled" if not flags["forecast_persistence_enabled"] else "currency_and_baseline_must_be_proven", "recovery_action": "Keep forecast flags disabled until explicit currency authority and synthetic acceptance pass."},
        "decision_history_readiness": {"state": "disabled" if not flags["decision_history_api_enabled"] else "blocked", "reason_code": "decision_history_disabled" if not flags["decision_history_api_enabled"] else "baseline_required", "recovery_action": "Keep the server-owned decision-history flag disabled until its dependencies pass."},
        "scenario_lab_readiness": {"state": "disabled" if not flags["scenario_lab_enabled"] else "blocked", "reason_code": "scenario_lab_disabled" if not flags["scenario_lab_enabled"] else "baseline_required", "recovery_action": "Keep Scenario Lab disabled until a compatible immutable baseline passes synthetic acceptance."},
        "market_intelligence_readiness": {"state": "disabled" if not flags["market_brief_read_api_enabled"] else "blocked", "reason_code": "market_intelligence_disabled" if not flags["market_brief_read_api_enabled"] else "provider_readiness_required", "recovery_action": "Keep Market Intelligence disabled unless approved server-side provider configuration is reviewed."},
        "privacy_safety": {"state": "ready" if not any(flags[key] for key in ("market_brief_email_delivery_enabled", "market_brief_scheduler_enabled", "market_brief_local_summarization_enabled")) else "unsafe", "reason_code": "prohibited_capabilities_disabled" if not any(flags[key] for key in ("market_brief_email_delivery_enabled", "market_brief_scheduler_enabled", "market_brief_local_summarization_enabled")) else "optional_unsafe_capability_enabled", "recovery_action": "Disable email, scheduler, and summarization flags; never use Doctor to change them."},
    }
    critical = (not sha) or clean is not True or checks["python"]["state"] == "blocked" or checks["storage"]["state"] == "blocked" or checks["account_currency_authority"]["state"] == "blocked" or checks["balance_observation"]["state"] == "blocked"
    unsafe = checks["privacy_safety"]["state"] == "unsafe"
    optional_blocked = any(item.get("state") in {"blocked", "unavailable", "degraded", "disabled"} for name, item in checks.items() if name not in {"repository", "python", "storage", "account_currency_authority", "privacy_safety"})
    overall = "unsafe_state" if unsafe else "configuration_failure" if critical else "ready_with_blocked_optional_capabilities" if optional_blocked else "ready"
    return {
        "schema_version": "atlas-doctor/v1",
        "overall_state": overall,
        "repository": checks["repository"],
        "runtime": {"python": checks["python"], "node": checks["node"], "rules_environment": checks["rules_environment"], "finlynq_environment": checks["finlynq_environment"]},
        "ports": {"ui": checks["ui_port"], "rules": checks["rules_port"], "finlynq": checks["finlynq_port"]},
        "health": {"ui": checks["ui_health"], "rules": checks["rules_health"], "finlynq": checks["finlynq_health"]},
        "storage": checks["storage"],
        "database_mode": checks["database_mode"],
        "feature_flags": flags,
        "credentials": credentials,
        "readiness": {key: checks[key] for key in ("account_currency_authority", "balance_observation", "forecast_baseline_prerequisites", "decision_history_readiness", "market_intelligence_readiness", "scenario_lab_readiness", "privacy_safety")},
        "prohibited_capabilities": {"email": "disabled", "scheduler": "disabled", "llm": "disabled", "execution": "disabled", "trading": "disabled", "money_movement": "disabled"},
    }


def print_summary(report: dict[str, Any]) -> None:
    print("Atlas Doctor — read-only local readiness")
    print(f"Overall: {report['overall_state'].replace('_', ' ')}")
    print(f"Repository SHA: {report['repository'].get('sha') or 'unavailable'}")
    for name, item in report["readiness"].items():
        print(f"{name}: {item.get('state', 'unknown')} ({item.get('reason_code', 'unknown')}) — {item.get('recovery_action', '')}")
    print("Feature flags: " + ", ".join(f"{key}={value}" for key, value in sorted(report["feature_flags"].items())))
    print("Credentials: " + ", ".join(f"{key}={value}" for key, value in sorted(report["credentials"].items())))
    print("Financial values, tokens, connection strings, raw paths, account identifiers, and provider payloads are omitted.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit stable machine-readable JSON only")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_summary(report)
    return {"ready": 0, "ready_with_blocked_optional_capabilities": 1, "configuration_failure": 2, "unsafe_state": 3}[report["overall_state"]]


if __name__ == "__main__":
    raise SystemExit(main())
