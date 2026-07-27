"""Top-level project tests conftest (start.sh behavior + project-level shell tests).

Provides:
- ``project_root``  : session-scoped Path to the project root (parent of tests/).
- ``start_sh_path`` : session-scoped Path to start.sh.

Skip behavior: when either service interpreter is missing (fresh clone, no
``bash scripts/bootstrap.sh`` run yet), ONLY the slow e2e cold-boot
test is skipped. The static-analysis unit tests in this directory are
pure ``bash -n`` + ``re`` over ``start.sh`` and run fine under system
Python 3.12 — skipping the entire suite would over-attribute the
bootstrap problem to tests that don't depend on it (round-7 reviewer #3).
"""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
START_SH = PROJECT_ROOT / "start.sh"


def pytest_collection_modifyitems(config, items: list[pytest.Item]) -> None:
    """Skip ONLY the slow e2e cold-boot when either service environment is missing.

    v1 of this conftest skipped every test in ``tests/`` when a shared
    environment was absent. But the unit tests in
    ``test_start_sh_unit.py`` are pure static-analysis (``bash -n``,
    ``re`` search over ``start.sh``) and run fine under system Python
    3.12. Only the cold-boot e2e legitimately needs the venv-resident
    uvicorn + next-dev code paths.
    """
    rules_python = PROJECT_ROOT / ".venv-rules" / "bin" / "python"
    finlynq_python = PROJECT_ROOT / ".venv-finlynq" / "bin" / "python"
    if rules_python.exists() and finlynq_python.exists():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "Atlas service environment missing — slow e2e cold-boot requires running "
            "`bash scripts/bootstrap.sh` first. Unit tests still run with "
            "system Python; they only need /bin/bash + stdlib re."
        )
    )
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_marker)


def pytest_configure(config: pytest.Config) -> None:
    """Register the custom ``slow`` marker to silence
    ``PytestUnknownMarkWarning`` from ``test_start_sh_e2e.py``.

    Without this hook, pytest warns on every invocation that
    ``pytest.mark.slow`` is an unknown marker — even when the test isn't
    selected. The warning is harmless but pollutes test output.
    """
    config.addinivalue_line(
        "markers",
        "slow: end-to-end cold-boot (~60-120s); opt out with -m 'not slow'.",
    )


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Absolute path to the project root (the directory containing start.sh)."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def start_sh_path() -> Path:
    """Absolute path to the start.sh script."""
    return START_SH
