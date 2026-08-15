#!/usr/bin/env python3
"""Run Atlas's bounded synthetic personal-use acceptance.

The runner creates one disposable SQLite database, scopes all feature flags to
child test processes, uses existing fake/stub providers, and runs no service
or browser process. It never reads the repository's personal database and
removes its temporary database when complete.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "services" / "rules-service"
PYTHON = ROOT / ".venv-rules" / "bin" / "python"
CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("readiness_and_currency_authority", ("tests/test_readiness.py",)),
    ("forecast", ("tests/test_routes_forecast_generation.py",)),
    ("recommendation_and_decision", ("tests/test_routes_recommendations_derived.py",)),
    ("decision_history", ("tests/test_routes_decision_history.py",)),
    ("outcome_lifecycle", ("tests/test_outcome_evaluation_service.py",)),
    ("scenario_generation_comparison_archive", ("tests/test_scenario_routes.py", "tests/test_scenario_repository.py", "tests/test_scenario_engine.py")),
    ("market_fake_provider", ("tests/test_market_brief_operational_wiring.py", "tests/test_market_delivery.py")),
)


def child_environment(db_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Do not inherit any operator database or provider credential into the
    # acceptance subprocess. Every value below is synthetic/local-only.
    for key in ("DATABASE_URL", "TEST_DATABASE_URL", "FINNHUB_API_KEY", "SEC_USER_AGENT", "PLAID_CLIENT_ID", "PLAID_SECRET", "OPENAI_API_KEY", "OLLAMA_BASE_URL"):
        env.pop(key, None)
    env.update({
        "TEST_DATABASE_URL": f"sqlite:///{db_path}",
        "DATABASE_URL": f"sqlite:///{db_path}",
        "JWT_SECRET": "atlas-synthetic-acceptance-secret",
        "LOCAL_USER": "synthetic-owner",
        "ENVIRONMENT": "development",
        "ATLAS_FORECAST_PERSISTENCE_ENABLED": "true",
        "ATLAS_FORECAST_READ_API_ENABLED": "true",
        "ATLAS_DECISION_HISTORY_API_ENABLED": "true",
        "ATLAS_SCENARIO_LAB_ENABLED": "true",
        "ATLAS_MARKET_BRIEF_GENERATION_ENABLED": "false",
        "ATLAS_MARKET_BRIEF_READ_API_ENABLED": "false",
        "ATLAS_MARKET_BRIEF_EXTERNAL_PROVIDER_ENABLED": "false",
        "ATLAS_MARKET_BRIEF_EMAIL_DELIVERY_ENABLED": "false",
        "ATLAS_MARKET_BRIEF_SCHEDULER_ENABLED": "false",
        "ATLAS_MARKET_BRIEF_LOCAL_SUMMARIZATION_ENABLED": "false",
        "FINLYNQ_BASE_URL": "http://127.0.0.1:9",
        "ATLAS_SYNTHETIC_ACCEPTANCE": "1",
    })
    return env


def run_case(name: str, paths: tuple[str, ...], env: dict[str, str]) -> dict[str, Any]:
    command = [str(PYTHON), "-m", "pytest", "-q", "--disable-warnings", *paths]
    try:
        completed = subprocess.run(command, cwd=RULES, env=env, capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "result": "failed", "reason": type(exc).__name__, "tests": 0}
    output = completed.stdout + completed.stderr
    match = re.search(r"(?:(\d+) passed).*", output)
    passed = int(match.group(1)) if match else 0
    return {
        "name": name,
        "result": "passed" if completed.returncode == 0 else "failed",
        "tests": passed,
        "command": " ".join(command[0:4] + list(paths)),
        "summary": output[-500:] if completed.returncode != 0 else f"{passed} passed",
    }


def run_acceptance() -> dict[str, Any]:
    if not PYTHON.exists():
        return {"schema_version": "atlas-synthetic-acceptance/v1", "result": "blocked", "reason_code": "rules_environment_missing", "recovery_action": "Run the documented isolated-environment bootstrap.", "journeys": []}
    with tempfile.TemporaryDirectory(prefix="atlas-synthetic-acceptance-") as directory:
        db_path = Path(directory) / "acceptance.sqlite"
        env = child_environment(db_path)
        journeys = []
        for name, paths in CASES:
            # The readiness contract also proves the server's default-off
            # posture. Run that diagnostic suite with its optional flags
            # explicitly false; the mutation journeys below enable only the
            # flags their focused fixtures require.
            case_env = env.copy()
            if name == "readiness_and_currency_authority":
                for key in (
                    "ATLAS_FORECAST_READ_API_ENABLED",
                    "ATLAS_DECISION_HISTORY_API_ENABLED",
                    "ATLAS_SCENARIO_LAB_ENABLED",
                ):
                    case_env[key] = "false"
            journeys.append(run_case(name, paths, case_env))
        failed = [journey for journey in journeys if journey["result"] != "passed"]
        return {
            "schema_version": "atlas-synthetic-acceptance/v1",
            "result": "passed" if not failed else "failed",
            "database": "disposable temporary SQLite (removed after run)",
            "currency_authority": "explicit synthetic USD account evidence only; no operator currency is read",
            "provider_mode": "fake/stub providers only; external credentials removed",
            "flags": {
                "forecast_persistence": True,
                "forecast_read_api": True,
                "decision_history": True,
                "scenario_lab": True,
                "market_intelligence_external_provider": False,
                "email": False,
                "scheduler": False,
                "local_llm_summarization": False,
            },
            "processes": "in-process focused pytest only; no Atlas service or unrelated process started",
            "cleanup": "temporary database and child process environment removed",
            "journeys": journeys,
            "restart_persistence": "covered by immutable archive/history contract suites; a full service restart remains a documented acceptance gap until the local activation profile is approved",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = run_acceptance()
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print("Atlas synthetic personal-use acceptance")
        print(f"Result: {report['result']}")
        for journey in report.get("journeys", []):
            print(f"{journey['name']}: {journey['result']} ({journey.get('tests', 0)} passed)")
        print("No personal database, real credentials, external provider, email, scheduler, or execution path was used.")
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
