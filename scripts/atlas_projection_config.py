#!/usr/bin/env python3
"""Configure one explicit, server-owned personal goal projection input.

The command is dry-run by default.  It must run with the Finlynq Python 3.12
environment because Finlynq owns the shared GoalProjectionConfig table:

  ./.venv-finlynq/bin/python scripts/atlas_projection_config.py \
    --monthly-contribution 500.00
  ./.venv-finlynq/bin/python scripts/atlas_projection_config.py \
    --monthly-contribution 500.00 --apply --confirm

It prints only bounded status metadata.  It never prints a goal name, balance,
transaction, holding, account identifier, credential, database path, or raw
configuration payload.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINLYNQ_DIR = ROOT / "services" / "finlynq"
if str(FINLYNQ_DIR) not in sys.path:
    sys.path.insert(0, str(FINLYNQ_DIR))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.projection_state.configuration import (  # noqa: E402
    ProjectionConfigurationError,
    apply_configuration,
    build_request,
    plan_configuration,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monthly-contribution", required=True, help="Canonical non-negative amount with at most two decimal places.")
    parser.add_argument("--goal-id", type=int, help="Optional bounded selection; exactly one active goal must still exist.")
    parser.add_argument("--apply", action="store_true", help="Permit the append-only configuration write.")
    parser.add_argument("--confirm", action="store_true", help="Required together with --apply for an explicit write confirmation.")
    args = parser.parse_args(argv)
    if args.confirm and not args.apply:
        parser.error("--confirm requires --apply")
    if args.apply and not args.confirm:
        parser.error("--apply requires --confirm")

    session = SessionLocal()
    try:
        if args.apply:
            result = apply_configuration(
                session,
                user_sub=settings.local_user,
                monthly_contribution=args.monthly_contribution,
                goal_id=args.goal_id,
            )
        else:
            _, _, request, existing = plan_configuration(
                session,
                user_sub=settings.local_user,
                monthly_contribution=args.monthly_contribution,
                goal_id=args.goal_id,
            )
            result = {
                "status": "already_configured" if existing is not None else "ready_to_apply",
                "projection": "ready",
                "projection_kind": request.projection_kind,
                "currency": request.currency_code,
                "monthly_contribution": format(request.monthly_contribution, "f"),
                "observed": "current_utc",
            }
    except ProjectionConfigurationError as exc:
        print(f"atlas_projection_config: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()

    print(
        "Atlas projection configuration: "
        + result["status"]
        + f" (projection={result['projection']}, currency={result.get('currency', 'USD')}, "
        f"monthly_contribution={result.get('monthly_contribution', 'configured')})"
    )
    print("  owner and goal scope were resolved server-side; sensitive financial records are omitted")
    print("  no browser authority, provider call, migration, or feature-flag mutation was performed by this command")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
