#!/usr/bin/env python3
"""Verify an Atlas backup or restore it to a new disposable SQLite path.

Examples:
  python3 scripts/atlas_restore.py --check /absolute/backup/path
  python3 scripts/atlas_restore.py --database rules-finlynq-shared --to /absolute/new.sqlite /absolute/backup/path

In-place restore is intentionally not implemented. This command never starts
services, never runs migrations, and refuses an existing target.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from atlas_backup_common import (
    BackupToolError,
    DEFAULT_DATABASE_ID,
    check_backup,
    resolve_database_identity,
    restore_to_new_database,
    safe_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, help="Absolute backup directory.")
    parser.add_argument("--database", default=DEFAULT_DATABASE_ID, help="Explicit supported Atlas database identity.")
    parser.add_argument("--check", action="store_true", help="Verify the backup without restoring it.")
    parser.add_argument("--to", type=Path, metavar="NEW_DATABASE", help="Restore only to this new, non-existent path.")
    parser.add_argument("--json", action="store_true", help="Emit safe machine-readable output.")
    args = parser.parse_args(argv)
    if args.check and args.to:
        parser.error("--check cannot be combined with --to")
    if not args.check and not args.to:
        parser.error("actual restore requires --to; in-place restore is not supported")
    try:
        if args.check:
            result = check_backup(args.backup, database_id=args.database)
        else:
            # Resolve the identity for the explicit supported-name check. This
            # does not open the database and is not used as a restore target.
            resolve_database_identity(args.database)
            result = restore_to_new_database(args.backup, args.to, database_id=args.database)
    except BackupToolError as exc:
        print(f"atlas_restore: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(safe_json(result))
    else:
        print("Atlas restore: " + result["status"])
        print(f"  database: {result['database_id']}")
        print(f"  schema: {result.get('schema_revision', 'unknown')}")
        print(f"  integrity: {result.get('integrity_check', 'unknown')}")
        print(f"  sha256: {result.get('sha256', 'unknown')}")
        print("  no service was started and no in-place restore was attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
