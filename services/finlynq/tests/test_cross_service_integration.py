"""DEPRECATED shim — the real cross-service integration test moved to
``services/tests/test_cross_db_roundtrip.py`` so it can build a SECOND
``create_engine`` from the same SQLite URL WITHOUT side-effect-binding
either service's conftest-bound engine at import time.

This file is kept so pytest auto-discovery stays clean (pytest logs
a "no tests ran" warning for empty files in some reporters). The
substantive invariants live in
``services/tests/test_cross_db_roundtrip.py`` which PROVES Phase-F2:
two engines, one file, one row observable across engine boundaries.
"""

# Intentionally minimal — a single placeholder test so the pytest
# collection walker logs zero warnings for this file path. The real
# coverage is in services/tests/test_cross_db_roundtrip.py.
def test_placeholder_moved_to_services_tests_test_cross_db_roundtrip() -> None:
    """Placeholder test — the actual Phase-F2 cross-engine invariant
    test lives at services/tests/test_cross_db_roundtrip.py because
    building a SECOND ``create_engine`` at test time cannot happen
    inside either service's own tests/ directory (the conftest
    auto-discovery would side-effect-bind that service's engine FIRST,
    polluting the F2 invariant experiment).
    """
    assert True, "this is a placeholder; see services/tests/test_cross_db_roundtrip.py"
