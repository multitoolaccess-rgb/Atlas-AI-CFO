#!/usr/bin/env python3
"""Scheduled merchant-rule backup: export rules CSV to git, push only on change.

Reads the ``merchant_rules`` table directly from the local SQLite database
(no server or API dependency — safe to run at 3am while the app is idle) and
writes the Phase 27 locked CSV contract used by
``POST /api/merchant-rules/import``:

    category_name,keyword,priority,is_archived,source

The snapshot is stored at ``backups/merchant-rules.csv`` inside the repo and
committed + pushed to GitHub ONLY when the rules actually changed (a content
diff against the committed copy). An identical export is a no-op: nothing is
committed, nothing is pushed.

Only the RULES table is exported. The database itself contains personal
financial data (transactions, balances, account details) and is intentionally
NEVER pushed to git; local full-DB backups are handled by
``scripts/atlas_backup.py``.

Examples:
  python3 scripts/backup_merchant_rules.py            # commit+push if changed
  python3 scripts/backup_merchant_rules.py --dry-run  # report without writing
"""
from __future__ import annotations

import argparse
import csv
import io
import sqlite3
import subprocess
import sys
from pathlib import Path

from atlas_backup_common import ROOT, resolve_database_identity

SNAPSHOT_PATH = ROOT / "backups" / "merchant-rules.csv"

# Locked Phase 27 CSV header — mirrors app/routes/merchant_rules.py.
CSV_HEADER = ("category_name", "keyword", "priority", "is_archived", "source")

_SELECT_RULES = """
    SELECT c.name, r.keyword, r.priority, r.is_archived, r.source
    FROM merchant_rules AS r
    JOIN categories AS c ON c.id = r.category_id
    ORDER BY c.name, r.priority, r.keyword
"""


class BackupError(RuntimeError):
    pass


def export_rules_csv(database_path: Path) -> str:
    """Return the Phase 27 CSV payload for the current merchant_rules rows."""
    if not database_path.exists():
        raise BackupError(f"database not found: {database_path}")
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        raise BackupError(f"could not open database read-only: {exc}") from exc
    try:
        rows = connection.execute(_SELECT_RULES).fetchall()
    except sqlite3.Error as exc:
        raise BackupError(f"could not read merchant_rules: {exc}") from exc
    finally:
        connection.close()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for name, keyword, priority, is_archived, source in rows:
        writer.writerow((name, keyword, priority, "true" if is_archived else "false", source))
    return buffer.getvalue()


def git_run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=check,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupError(f"git {' '.join(args)} failed: {exc}") from exc
    return result


def current_committed_snapshot() -> str | None:
    """Return the committed CSV contents, or None when never committed."""
    result = git_run("show", f"HEAD:{SNAPSHOT_PATH.relative_to(ROOT).as_posix()}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report whether rules changed without writing or committing.")
    args = parser.parse_args(argv)

    try:
        identity = resolve_database_identity()
        snapshot = export_rules_csv(identity.path)
    except BackupError as exc:
        print(f"backup_merchant_rules: {exc}", file=sys.stderr)
        return 2

    committed = current_committed_snapshot()
    if committed is not None and committed == snapshot:
        print(f"backup_merchant_rules: no change ({len(snapshot.splitlines())} lines); nothing to commit")
        return 0

    if args.dry_run:
        print(f"backup_merchant_rules: rules CHANGED since last commit (dry-run; no write)")
        return 0

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(snapshot, encoding="utf-8")

    git_run("add", str(SNAPSHOT_PATH))
    commit = git_run("commit", "-m", "chore(backup): merchant rules snapshot", "--", str(SNAPSHOT_PATH), check=False)
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr):
            print("backup_merchant_rules: rules written but already committed; skipping push")
            return 0
        raise BackupError(f"git commit failed: {commit.stderr.strip()}")

    push = git_run("push", check=False)
    if push.returncode != 0:
        print(f"backup_merchant_rules: committed locally but push failed: {push.stderr.strip()}", file=sys.stderr)
        return 1

    print(f"backup_merchant_rules: committed and pushed snapshot ({len(snapshot.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())