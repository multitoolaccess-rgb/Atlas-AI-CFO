"""Shared safety primitives for Atlas's local SQLite recovery tools.

This module deliberately has no Atlas application imports.  It resolves only
an explicitly named local database, uses SQLite's online backup API, and emits
safe metadata without exposing database contents or connection secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "services" / "rules-service"
BACKUP_FORMAT_VERSION = "atlas-sqlite-backup/v1"
DATABASE_FILENAME = "database.sqlite"
MANIFEST_FILENAME = "manifest.json"
DEFAULT_DATABASE_ID = "rules-finlynq-shared"
REVISION_PATTERN = re.compile(r"^revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
DOWN_REVISION_PATTERN = re.compile(r"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*(.+)$", re.MULTILINE)


class BackupToolError(RuntimeError):
    """A safe, user-actionable backup/recovery failure."""


@dataclass(frozen=True)
class DatabaseIdentity:
    name: str
    path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else "unknown"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise BackupToolError("database_is_not_sqlite")
    raw = database_url[len("sqlite:///") :].split("?", 1)[0]
    if not raw or raw == ":memory:":
        raise BackupToolError("database_path_is_not_file_backed")
    if raw.startswith("/"):
        return Path("/") / raw.lstrip("/")
    return RULES_DIR / raw


def resolve_database_identity(name: str = DEFAULT_DATABASE_ID) -> DatabaseIdentity:
    """Resolve one supported Atlas database identity without printing its path."""
    if name != DEFAULT_DATABASE_ID:
        raise BackupToolError("unsupported_database_identity")
    values = _read_env_file(RULES_DIR / ".env")
    database_url = os.environ.get("DATABASE_URL") or values.get("DATABASE_URL")
    if database_url:
        path = _sqlite_path_from_url(database_url)
    else:
        # This is the one documented shared-stack fallback: start.sh exports
        # this exact path for both services. No directory search or alternate
        # database guessing is permitted.
        path = RULES_DIR / "finance.db"
    path = path.expanduser().resolve(strict=False)
    return DatabaseIdentity(name=name, path=path)


def _reject_path_traversal(path: Path) -> None:
    if any(part == ".." for part in path.parts):
        raise BackupToolError("path_traversal_rejected")


def _reject_symlink_components(path: Path) -> None:
    """Reject operator-selected symlink components while allowing system aliases."""
    _reject_path_traversal(path)
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    # macOS commonly exposes /var and /tmp as aliases under /private. Those
    # system aliases are allowed; every other selected component is checked.
    trusted_aliases = {Path("/var"), Path("/tmp")}
    for part in parts:
        current /= part
        if current.is_symlink() and current not in trusted_aliases:
            raise BackupToolError("symlink_path_rejected")


def require_source_database(path: Path) -> Path:
    path = path.expanduser()
    _reject_symlink_components(path)
    if not path.is_absolute():
        raise BackupToolError("database_path_must_be_absolute")
    if not path.exists() or not path.is_file():
        raise BackupToolError("database_not_found")
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        connection.execute("SELECT 1").fetchone()
    except (sqlite3.Error, OSError) as exc:
        raise BackupToolError("database_is_not_readable_sqlite") from exc
    finally:
        if connection is not None:
            connection.close()
    return path


def prepare_new_path(path: Path, *, allow_directory_creation: bool = True) -> Path:
    path = path.expanduser()
    _reject_symlink_components(path)
    if not path.is_absolute():
        raise BackupToolError("destination_path_must_be_absolute")
    if path.exists() or path.is_symlink():
        raise BackupToolError("destination_already_exists")
    parent = path.parent
    if allow_directory_creation:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise BackupToolError("destination_parent_unavailable")
    _reject_symlink_components(parent)
    return path


def prepare_backup_directory(path: Path) -> Path:
    path = path.expanduser()
    _reject_symlink_components(path)
    if not path.is_absolute():
        raise BackupToolError("backup_destination_must_be_absolute")
    if path.exists() or path.is_symlink():
        raise BackupToolError("backup_destination_already_exists")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _reject_symlink_components(path.parent)
    return path


def _database_holders(path: Path) -> set[int]:
    """Return PIDs holding the DB or WAL/SHM siblings; fail closed if lsof is absent."""
    if shutil.which("lsof") is None:
        raise BackupToolError("writer_ownership_probe_unavailable")
    holders: set[int] = set()
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        result = subprocess.run(
            ["lsof", "-nP", "-t", "--", str(candidate)],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for value in result.stdout.split():
            if value.isdigit():
                holders.add(int(value))
    return holders


def require_quiescent_database(path: Path) -> None:
    holders = _database_holders(path)
    if holders:
        raise BackupToolError("active_database_writer_or_reader_present")


def _single_value(connection: sqlite3.Connection, sql: str) -> Any:
    row = connection.execute(sql).fetchone()
    if not row:
        raise BackupToolError("database_metadata_missing")
    return row[0]


def schema_revision(connection: sqlite3.Connection) -> str:
    try:
        value = _single_value(connection, "SELECT version_num FROM alembic_version")
    except sqlite3.Error as exc:
        raise BackupToolError("migration_revision_unavailable") from exc
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9]+", value):
        raise BackupToolError("migration_revision_invalid")
    return value


def migration_revisions() -> set[str]:
    revisions: set[str] = set()
    versions = RULES_DIR / "alembic" / "versions"
    for path in sorted(versions.glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = REVISION_PATTERN.search(text)
        if match:
            revisions.add(match.group(1))
    return revisions


def current_heads() -> tuple[str, ...]:
    revisions: set[str] = set()
    referenced: set[str] = set()
    versions = RULES_DIR / "alembic" / "versions"
    for path in sorted(versions.glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = REVISION_PATTERN.search(text)
        if not match:
            continue
        revision = match.group(1)
        revisions.add(revision)
        down = DOWN_REVISION_PATTERN.search(text)
        if down:
            referenced.update(re.findall(r"['\"]([A-Za-z0-9]+)['\"]", down.group(1)))
    return tuple(sorted(revisions - referenced))


def sqlite_metadata(path: Path) -> dict[str, str]:
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        journal_mode = str(_single_value(connection, "PRAGMA journal_mode")).lower()
        integrity = str(_single_value(connection, "PRAGMA integrity_check"))
        quick_check = str(_single_value(connection, "PRAGMA quick_check"))
        revision = schema_revision(connection)
        sqlite_version = sqlite3.sqlite_version
    except (sqlite3.Error, BackupToolError) as exc:
        if isinstance(exc, BackupToolError):
            raise
        raise BackupToolError("sqlite_metadata_unavailable") from exc
    finally:
        if connection is not None:
            connection.close()
    if integrity.lower() != "ok" or quick_check.lower() != "ok":
        raise BackupToolError("sqlite_integrity_check_failed")
    return {
        "sqlite_version": sqlite_version,
        "journal_mode": journal_mode,
        "integrity_check": integrity,
        "quick_check": quick_check,
        "schema_revision": revision,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_sqlite_sidecars(path: Path) -> None:
    """Remove only sidecars created beside a tool-owned standalone copy."""
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.is_symlink():
            raise BackupToolError("backup_sidecar_symlink_rejected")
        try:
            sidecar.unlink()
        except FileNotFoundError:
            pass


def _write_json_restrictive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    os.chmod(path, 0o600)


def _backup_into(source: Path, target: Path) -> None:
    source_connection = None
    target_connection = None
    try:
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=2)
        target_connection = sqlite3.connect(target)
        source_connection.backup(target_connection, pages=128, sleep=0.05)
        target_connection.commit()
    except sqlite3.Error as exc:
        raise BackupToolError("sqlite_online_backup_failed") from exc
    finally:
        if source_connection is not None:
            source_connection.close()
        if target_connection is not None:
            target_connection.close()


def create_backup(source_path: Path, destination: Path, *, database_id: str) -> dict[str, Any]:
    source = require_source_database(source_path)
    require_quiescent_database(source)
    destination = prepare_backup_directory(destination)
    temporary_root = Path(tempfile.mkdtemp(prefix=".atlas-backup-", dir=destination.parent))
    os.chmod(temporary_root, 0o700)
    temporary_database = temporary_root / DATABASE_FILENAME
    temporary_manifest = temporary_root / MANIFEST_FILENAME
    try:
        source_metadata = sqlite_metadata(source)
        _backup_into(source, temporary_database)
        os.chmod(temporary_database, 0o600)
        copied_metadata = sqlite_metadata(temporary_database)
        _remove_sqlite_sidecars(temporary_database)
        if copied_metadata["schema_revision"] != source_metadata["schema_revision"]:
            raise BackupToolError("backup_schema_revision_changed")
        checksum = sha256_file(temporary_database)
        manifest: dict[str, Any] = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": utc_now(),
            "atlas_git_sha": safe_git_sha(),
            "database_id": database_id,
            "database_kind": "sqlite",
            "schema_revision": copied_metadata["schema_revision"],
            "schema_heads": list(current_heads()),
            "sqlite_version": copied_metadata["sqlite_version"],
            "journal_mode": copied_metadata["journal_mode"],
            "integrity_check": copied_metadata["integrity_check"],
            "quick_check": copied_metadata["quick_check"],
            "file_size": temporary_database.stat().st_size,
            "sha256": checksum,
            "recovery": "Verify this manifest, then restore only to a new disposable path with atlas_restore.py --to.",
        }
        _write_json_restrictive(temporary_manifest, manifest)
        # Directory rename via os.replace could overwrite an operator-created
        # empty destination in a race. Create the final directory exclusively,
        # then move only the two tool-owned files into it.
        try:
            os.mkdir(destination, 0o700)
        except FileExistsError as exc:
            raise BackupToolError("backup_destination_created_during_operation") from exc
        os.replace(temporary_database, destination / DATABASE_FILENAME)
        os.replace(temporary_manifest, destination / MANIFEST_FILENAME)
        shutil.rmtree(temporary_root, ignore_errors=True)
        return manifest
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        if destination.exists() and destination.is_dir() and not destination.is_symlink():
            try:
                if {item.name for item in destination.iterdir()} <= {DATABASE_FILENAME, MANIFEST_FILENAME}:
                    shutil.rmtree(destination)
            except OSError:
                pass
        raise


def _read_manifest(backup_directory: Path) -> tuple[dict[str, Any], Path]:
    backup_directory = backup_directory.expanduser()
    _reject_symlink_components(backup_directory)
    if not backup_directory.is_absolute():
        raise BackupToolError("backup_path_must_be_absolute")
    if not backup_directory.is_dir():
        raise BackupToolError("backup_directory_not_found")
    manifest_path = backup_directory / MANIFEST_FILENAME
    database_path = backup_directory / DATABASE_FILENAME
    for path in (manifest_path, database_path):
        if path.is_symlink() or not path.is_file():
            raise BackupToolError("backup_artifact_missing_or_symlinked")
    # A read-only SQLite consumer may create transient WAL/SHM siblings beside
    # a standalone backup. They are not backup contents: remove only these
    # known sidecars after confirming no process still holds the backup file.
    sidecars = [Path(f"{database_path}-wal"), Path(f"{database_path}-shm")]
    for sidecar in sidecars:
        if sidecar.is_symlink():
            raise BackupToolError("backup_sidecar_symlink_rejected")
    if any(sidecar.exists() for sidecar in sidecars):
        if _database_holders(database_path):
            raise BackupToolError("active_backup_reader_or_writer_present")
        _remove_sqlite_sidecars(database_path)
    allowed = {MANIFEST_FILENAME, DATABASE_FILENAME}
    if {item.name for item in backup_directory.iterdir()} != allowed:
        raise BackupToolError("backup_contains_unexpected_files")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupToolError("backup_manifest_invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupToolError("backup_format_unsupported")
    required = {"database_id", "schema_revision", "sqlite_version", "journal_mode", "integrity_check", "quick_check", "file_size", "sha256"}
    if not required.issubset(manifest):
        raise BackupToolError("backup_manifest_incomplete")
    if not isinstance(manifest["database_id"], str) or not isinstance(manifest["schema_revision"], str):
        raise BackupToolError("backup_manifest_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["sha256"])):
        raise BackupToolError("backup_checksum_invalid")
    if manifest["file_size"] != database_path.stat().st_size or sha256_file(database_path) != manifest["sha256"]:
        raise BackupToolError("backup_checksum_mismatch")
    try:
        metadata = sqlite_metadata(database_path)
    finally:
        _remove_sqlite_sidecars(database_path)
    for field in ("schema_revision", "journal_mode", "integrity_check", "quick_check"):
        if str(manifest[field]) != str(metadata[field]):
            raise BackupToolError("backup_metadata_mismatch")
    if metadata["schema_revision"] not in migration_revisions():
        raise BackupToolError("backup_schema_revision_unsupported")
    return manifest, database_path


def check_backup(backup_directory: Path, *, database_id: str | None = None) -> dict[str, Any]:
    manifest, _ = _read_manifest(backup_directory)
    if database_id is not None and manifest["database_id"] != database_id:
        raise BackupToolError("backup_database_identity_mismatch")
    return {
        "status": "verified",
        "format_version": manifest["format_version"],
        "database_id": manifest["database_id"],
        "schema_revision": manifest["schema_revision"],
        "integrity_check": manifest["integrity_check"],
        "sha256": manifest["sha256"],
    }


def restore_to_new_database(backup_directory: Path, target: Path, *, database_id: str) -> dict[str, Any]:
    manifest, source = _read_manifest(backup_directory)
    if manifest["database_id"] != database_id:
        raise BackupToolError("backup_database_identity_mismatch")
    target = prepare_new_path(target)
    temporary = target.parent / f".{target.name}.atlas-restore-{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        raise BackupToolError("restore_temporary_target_exists")
    try:
        _backup_into(source, temporary)
        os.chmod(temporary, 0o600)
        metadata = sqlite_metadata(temporary)
        _remove_sqlite_sidecars(temporary)
        if metadata["schema_revision"] != manifest["schema_revision"]:
            raise BackupToolError("restore_schema_revision_mismatch")
        if metadata["integrity_check"] != "ok":
            raise BackupToolError("restore_integrity_check_failed")
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise BackupToolError("restore_target_created_during_operation") from exc
        temporary.unlink()
        return {
            "status": "restored_to_new_database",
            "database_id": database_id,
            "schema_revision": metadata["schema_revision"],
            "integrity_check": metadata["integrity_check"],
            "sha256": sha256_file(target),
        }
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def safe_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
