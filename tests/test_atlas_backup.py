"""Synthetic-only tests for Atlas's local SQLite recovery tools."""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from atlas_backup_common import (  # noqa: E402
    BackupToolError,
    check_backup,
    create_backup,
    prepare_backup_directory,
    restore_to_new_database,
    _backup_into,
)


class AtlasBackupTests(unittest.TestCase):
    def make_database(self, directory: str, *, revision: str = "X7a1b2c3d4e5") -> Path:
        path = Path(directory) / "source.sqlite"
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=1000000")
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            CREATE TABLE synthetic_records (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        connection.execute("INSERT INTO alembic_version(version_num) VALUES (?)", (revision,))
        connection.execute("INSERT INTO synthetic_records(value) VALUES ('wal-only synthetic record')")
        connection.commit()
        connection.close()
        writer = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sqlite3,sys,time; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=1000000'); c.execute(\"INSERT INTO synthetic_records(value) VALUES ('committed in WAL')\"); c.commit(); print('ready', flush=True); time.sleep(20)",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(writer.stdout.readline().strip(), "ready")
            os.kill(writer.pid, signal.SIGKILL)
            writer.wait(timeout=5)
        finally:
            if writer.poll() is None:
                writer.kill()
                writer.wait(timeout=5)
            writer.stdout.close()
            writer.stderr.close()
        self.assertTrue(Path(f"{path}-wal").exists())
        return path

    def test_wal_backup_contains_committed_state_and_has_restrictive_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            source = self.make_database(directory)
            output = Path(directory) / "backup"
            manifest = create_backup(source, output, database_id="rules-finlynq-shared")
            self.assertEqual(manifest["format_version"], "atlas-sqlite-backup/v1")
            self.assertEqual(manifest["integrity_check"], "ok")
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "database.sqlite").stat().st_mode & 0o777, 0o600)
            self.assertEqual((output / "manifest.json").stat().st_mode & 0o777, 0o600)
            restored = sqlite3.connect(output / "database.sqlite")
            try:
                values = [row[0] for row in restored.execute("SELECT value FROM synthetic_records ORDER BY id")]
            finally:
                restored.close()
            self.assertEqual(values, ["wal-only synthetic record", "committed in WAL"])
            self.assertEqual(check_backup(output)["status"], "verified")
            manifest_text = (output / "manifest.json").read_text()
            self.assertNotIn("DATABASE_URL", manifest_text)
            self.assertNotIn(str(source), manifest_text)

    def test_online_backup_remains_read_safe_with_a_concurrent_reader(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            source = self.make_database(directory)
            target = Path(directory) / "reader-safe.sqlite"
            reader = sqlite3.connect(source)
            try:
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM synthetic_records").fetchone()[0], 2)
                _backup_into(source, target)
            finally:
                reader.close()
            with sqlite3.connect(target) as copied:
                self.assertEqual(copied.execute("SELECT COUNT(*) FROM synthetic_records").fetchone()[0], 2)

    def test_checksum_corruption_and_truncation_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            source = self.make_database(directory)
            output = Path(directory) / "backup"
            create_backup(source, output, database_id="rules-finlynq-shared")
            database = output / "database.sqlite"
            original = database.read_bytes()
            database.write_bytes(original[:-10])
            with self.assertRaisesRegex(BackupToolError, "checksum_mismatch"):
                check_backup(output)

    def test_existing_destination_symlink_and_traversal_are_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            root = Path(directory)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(BackupToolError, "destination_already_exists"):
                prepare_backup_directory(existing)
            link = root / "link"
            link.symlink_to(existing, target_is_directory=True)
            with self.assertRaisesRegex(BackupToolError, "symlink_path_rejected"):
                prepare_backup_directory(link)
            with self.assertRaisesRegex(BackupToolError, "path_traversal_rejected"):
                prepare_backup_directory(root / ".." / "unsafe")

    def test_unsupported_schema_and_wrong_identity_are_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            source = self.make_database(directory)
            output = Path(directory) / "backup"
            create_backup(source, output, database_id="rules-finlynq-shared")
            with self.assertRaisesRegex(BackupToolError, "backup_database_identity_mismatch"):
                check_backup(output, database_id="other-database")
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["schema_revision"] = "not-a-repository-revision"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(BackupToolError, "backup_metadata_mismatch"):
                check_backup(output)

    def test_disposable_restore_is_equivalent_and_existing_target_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            root = Path(directory)
            source = self.make_database(directory)
            output = root / "backup"
            create_backup(source, output, database_id="rules-finlynq-shared")
            target = root / "disposable-restore.sqlite"
            result = restore_to_new_database(output, target, database_id="rules-finlynq-shared")
            self.assertEqual(result["status"], "restored_to_new_database")
            restored = sqlite3.connect(target)
            try:
                self.assertEqual(restored.execute("SELECT COUNT(*) FROM synthetic_records").fetchone()[0], 2)
            finally:
                restored.close()
            with self.assertRaisesRegex(BackupToolError, "destination_already_exists"):
                restore_to_new_database(output, target, database_id="rules-finlynq-shared")

    def test_active_database_holder_is_refused_without_killing_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-backup-test-") as directory:
            source = self.make_database(directory)
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import sqlite3,sys,time; c=sqlite3.connect(sys.argv[1]); print('ready', flush=True); time.sleep(20)",
                    str(source),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                time.sleep(0.2)
                with self.assertRaisesRegex(BackupToolError, "active_database_writer_or_reader_present"):
                    create_backup(source, Path(directory) / "backup", database_id="rules-finlynq-shared")
                self.assertIsNone(child.poll())
            finally:
                child.terminate()
                child.wait(timeout=5)
                child.stdout.close()
                child.stderr.close()


if __name__ == "__main__":
    unittest.main()
