#!/usr/bin/env python3
"""Confirm USD currency + balance evidence for every active account lacking it.

Dry-run is the default.  The command reports only counts and a bounded intent
hash — never balances, account identifiers, account names, transactions,
holdings, credentials, or provider payloads.

  python3 scripts/atlas_confirm_new_accounts.py --database-path /absolute/path/finance.db
  python3 scripts/atlas_confirm_new_accounts.py --database-path /absolute/path/finance.db \
      --apply --confirm --observed-at <timestamp-from-dry-run> --intent-hash <hash-from-dry-run>

Writes are append-only and idempotent; no stored balance is ever changed.
This command runs no startup hooks, no migrations, and no feature-flag mutation.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _validate_database_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("database_path_must_be_absolute_and_normalized")
    if path.is_symlink() or not path.is_file():
        raise ValueError("database_path_unavailable")
    current = Path(path.anchor)
    trusted_aliases = {Path("/tmp"), Path("/var")}
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink() and current not in trusted_aliases:
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
    parser.add_argument("--apply", action="store_true", help="Permit the append-only evidence writes.")
    parser.add_argument("--confirm", action="store_true", help="Required together with --apply for an explicit write confirmation.")
    parser.add_argument("--intent-hash", help="Intent hash returned by the matching dry-run.")
    parser.add_argument("--json", action="store_true", help="Emit bounded machine-readable output.")
    args = parser.parse_args(argv)
    if args.confirm and not args.apply:
        parser.error("--confirm requires --apply")
    if args.apply and not args.confirm:
        parser.error("--apply requires --confirm")
    try:
        path = _validate_database_path(args.database_path)
        os.environ["DATABASE_URL"] = f"sqlite:///{path}"
        service_dir = Path(__file__).resolve().parents[1] / "services" / "finlynq"
        sys.path.insert(0, str(service_dir))
        from app.config import settings  # noqa: E402
        from app.database import SessionLocal, engine  # noqa: E402
        from app.projection_state.confirm_new_accounts import (  # noqa: E402
            BatchConfirmationError,
            confirm_new_active_accounts,
        )

        engine.echo = False
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        if args.observed_at:
            observed_at = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
        with SessionLocal() as db:
            result = confirm_new_active_accounts(
                db,
                user_sub=settings.local_user,
                observed_at=observed_at,
                apply=args.apply,
                confirm=args.confirm,
                expected_intent_hash=args.intent_hash,
            )
    except BatchConfirmationError as exc:
        reason = exc.args[0] if exc.args and isinstance(exc.args[0], str) else "batch_confirmation_failed"
        if not reason.replace("_", "").isalnum() or len(reason) > 80:
            reason = "batch_confirmation_failed"
        if args.json:
            print(json.dumps({"status": "blocked", "reason_code": reason}, sort_keys=True, separators=(",", ":")))
        else:
            print(f"Atlas account confirmation: blocked ({reason})")
            print("  no database write was performed; sensitive records and paths are omitted")
        return 2
    except Exception:
        if args.json:
            print(json.dumps({"status": "blocked", "reason_code": "batch_confirmation_failed"}, sort_keys=True, separators=(",", ":")))
        else:
            print("Atlas account confirmation: blocked (batch_confirmation_failed)")
            print("  no database write was performed; sensitive records and paths are omitted")
        return 2

    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        if result["status"] == "no_pending_accounts":
            print("Atlas account confirmation: no pending accounts")
            print(f"  active accounts with full evidence: {result['eligible_active_accounts']}")
        else:
            print(f"Atlas account confirmation: {result['mode']} ({result['status']})")
            print(f"  active accounts: {result['eligible_active_accounts']}")
            print(f"  currency pending: {result['currency_pending']}")
            print(f"  balance pending: {result['balance_pending']}")
            if result.get("intent_hash"):
                print(f"  intent hash: {result['intent_hash']}")
            if result.get("currency_recorded") is not None:
                print(f"  currency recorded: {result['currency_recorded']}")
            if result.get("balance_confirmed") is not None:
                print(f"  balance confirmed: {result['balance_confirmed']}")
            print("  balances, account identifiers, paths, and sensitive records are omitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
