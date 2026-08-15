#!/usr/bin/env python3
"""Create or verify a local Atlas SQLite backup.

Examples:
  python3 scripts/atlas_backup.py --database rules-finlynq-shared --output /absolute/backup/path
  python3 scripts/atlas_backup.py --check /absolute/backup/path

The command is local-only, refuses active database holders, never overwrites
an existing destination, and never starts or stops services.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from atlas_backup_common import (
    BackupToolError,
    DEFAULT_DATABASE_ID,
    check_backup,
    create_backup,
    resolve_database_identity,
    safe_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE_ID, help="Explicit supported Atlas database identity.")
    parser.add_argument("--output", type=Path, help="New absolute backup directory; it must not already exist.")
    parser.add_argument("--check", type=Path, metavar="BACKUP_DIRECTORY", help="Verify an existing backup without touching its source.")
    parser.add_argument("--json", action="store_true", help="Emit safe machine-readable output.")
    args = parser.parse_args(argv)
    if bool(args.output) == bool(args.check):
        parser.error("provide exactly one of --output or --check")
    try:
        if args.check:
            result = check_backup(args.check, database_id=args.database if args.database != DEFAULT_DATABASE_ID else None)
        else:
            identity = resolve_database_identity(args.database)
            result = create_backup(identity.path, args.output, database_id=identity.name)
            result = {
                "status": "created_and_verified",
                "format_version": result["format_version"],
                "database_id": result["database_id"],
                "schema_revision": result["schema_revision"],
                "integrity_check": result["integrity_check"],
                "sha256": result["sha256"],
            }
    except BackupToolError as exc:
        print(f"atlas_backup: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(safe_json(result))
    else:
        print("Atlas backup: " + result["status"])
        print(f"  database: {result['database_id']}")
        print(f"  schema: {result.get('schema_revision', 'unknown')}")
        print(f"  integrity: {result.get('integrity_check', 'unknown')}")
        print(f"  sha256: {result.get('sha256', 'unknown')}")
        print("  sensitive database contents and source paths are omitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
