"""Focused regression tests for the read-only Atlas Doctor command."""
from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("atlas_doctor", ROOT / "scripts" / "atlas_doctor.py")
assert SPEC and SPEC.loader
atlas_doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(atlas_doctor)


def test_json_report_and_summary_never_echo_secret_values() -> None:
    secret = "JWT_SECRET=synthetic-secret-value"
    report = {
        "overall_state": "configuration_failure",
        "repository": {"sha": "abc1234"},
        "readiness": {
            "account_currency_authority": {
                "state": "blocked",
                "reason_code": "currency_evidence_missing",
                "recovery_action": "Resolve explicit USD evidence.",
            }
        },
        "feature_flags": {"scenario_lab_enabled": False},
        "credentials": {"jwt_secret_configured": True},
    }
    output = io.StringIO()
    with redirect_stdout(output):
        atlas_doctor.print_summary(report)
    assert secret not in output.getvalue()
    assert "jwt_secret_configured=True" in output.getvalue()
    serialized = json.dumps(report, sort_keys=True)
    assert secret not in serialized


def test_exit_codes_are_stable_and_json_is_machine_readable() -> None:
    expected = {
        "ready": 0,
        "ready_with_blocked_optional_capabilities": 1,
        "configuration_failure": 2,
        "unsafe_state": 3,
    }
    for state, code in expected.items():
        with patch.object(atlas_doctor, "build_report", return_value={"overall_state": state}), patch.object(
            sys, "argv", ["atlas_doctor.py", "--json"]
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                actual = atlas_doctor.main()
        assert actual == code
        assert json.loads(output.getvalue())["overall_state"] == state


def test_sqlite_snapshot_is_read_only_and_reports_currency_fail_closed() -> None:
    with TemporaryDirectory(prefix="atlas-doctor-test-") as directory:
        path = Path(directory) / "synthetic.sqlite"
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE alembic_version (version_num VARCHAR(32));
                INSERT INTO alembic_version(version_num) VALUES ('not-current');
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY,
                    is_active INTEGER NOT NULL,
                    currency_code VARCHAR(3),
                    currency_source VARCHAR(32),
                    currency_observed_at TEXT,
                    currency_source_reference VARCHAR(128)
                );
                CREATE TABLE account_currency_evidence (
                    id TEXT PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    currency_code TEXT,
                    observed_at TEXT,
                    supersedes_event_id TEXT,
                    recorded_at TEXT
                );
                INSERT INTO accounts VALUES (1, 1, 'USD', 'user_confirmed', '2026-08-01', 'legacy-cache-only');
                """
            )
        before = path.read_bytes()
        with patch.object(atlas_doctor, "migration_heads", return_value=("current-head",)):
            report = atlas_doctor.sqlite_snapshot(path)
        after = path.read_bytes()
        assert before == after
        assert report["state"] == "blocked"
        assert report["reason_code"] == "migration_mismatch"
        assert report["currency_authority"]["state"] == "blocked"
        assert report["currency_authority"]["reason_code"] == "currency_unknown"


def test_missing_database_fails_closed_without_creating_it() -> None:
    with TemporaryDirectory(prefix="atlas-doctor-test-") as directory:
        path = Path(directory) / "missing.sqlite"
        report = atlas_doctor.sqlite_snapshot(path)
        assert report["state"] == "blocked"
        assert report["reason_code"] == "database_not_found"
        assert not path.exists()
