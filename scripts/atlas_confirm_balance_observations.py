#!/usr/bin/env python3
"""Confirm the currently stored balances are observed as current.

Dry-run is the default. The command requires an explicit absolute SQLite path,
never prints that path or any financial record, and writes only hash-bound
observation provenance plus the compatibility ``last_sync`` timestamp.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def _validate_database_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("database_path_must_be_absolute_and_normalized")
    if path.is_symlink() or not path.is_file():
        raise ValueError("database_path_unavailable")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError("database_path_symlink_rejected")
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        raise ValueError("database_is_not_readable_sqlite") from exc
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-path", required=True, help="Explicit absolute Atlas-owned SQLite path; never echoed.")
    parser.add_argument("--observed-at", help="UTC RFC3339 observation time; defaults to current UTC.")
    parser.add_argument("--apply", action="store_true", help="Permit the append-only observation write.")
    parser.add_argument("--confirm-all-active-balances-current", action="store_true", help="Required exact confirmation for writes.")
    parser.add_argument("--intent-hash", help="Intent hash returned by the matching dry-run.")
    parser.add_argument("--json", action="store_true", help="Emit bounded machine-readable output.")
    args = parser.parse_args(argv)
    try:
        path = _validate_database_path(args.database_path)
        os.environ["DATABASE_URL"] = f"sqlite:///{path}"
        # Import the service only after the explicit database selection has
        # been validated. This command does not run startup hooks or migrations.
        service_dir = Path(__file__).resolve().parents[1] / "services" / "finlynq"
        sys.path.insert(0, str(service_dir))
        from app.config import settings  # noqa: E402
        from app.database import SessionLocal, engine  # noqa: E402
        from app.projection_state.confirm_balance_observations import (  # noqa: E402
            BalanceObservationError,
            confirm_all_active_balances_current,
        )
        from datetime import datetime, timezone  # noqa: E402

        engine.echo = False
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        if args.observed_at:
            observed_at = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
        with SessionLocal() as db:
            result = confirm_all_active_balances_current(
                db,
                user_sub=settings.local_user,
                observed_at=observed_at,
                apply=args.apply,
                confirm_all_active=args.confirm_all_active_balances_current,
                expected_intent_hash=args.intent_hash,
            )
    except Exception as exc:
        reason = exc.args[0] if exc.args and isinstance(exc.args[0], str) else "balance_observation_operator_failed"
        if not reason.replace("_", "").isalnum() or len(reason) > 80:
            reason = "balance_observation_operator_failed"
        if args.json:
            print(json.dumps({"status": "blocked", "reason_code": reason}, sort_keys=True, separators=(",", ":")))
        else:
            print(f"Atlas balance observation: blocked ({reason})")
            print("  no database write was performed; sensitive records and paths are omitted")
        return 2

    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"Atlas balance observation: {result['mode']}")
        print(f"  eligible active accounts: {result['eligible_active_accounts']}")
        print(f"  observed at: {result['observed_at']}")
        print(f"  intent hash: {result['intent_hash']}")
        print("  balances, account identifiers, paths, and sensitive records are omitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
