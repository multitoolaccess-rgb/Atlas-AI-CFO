#!/usr/bin/env python3
"""Classify changed repository paths for the smallest applicable CI scope."""
from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
from typing import Iterable

GOVERNANCE_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".husky/pre-push",
    "scripts/atlas_project_status.py",
    "scripts/classify_change_scope.py",
    "tests/test_atlas_project_status.py",
    "tests/test_change_scope.py",
}
GOVERNANCE_PREFIXES = (
    "docs/",
    ".agents/",
    "agents/",
    ".github/",
)
FULL_PREFIXES = (
    ".husky/",
    "scripts/",
    "tests/",
)


def _is_root_documentation(path: str) -> bool:
    return "/" not in path and path.lower().endswith((".md", ".markdown"))

FULL_FILES = {
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "docker-compose.yml",
    "docker-compose.yaml",
}
FRONTEND_PREFIX = "ui/"
RULES_PREFIX = "services/rules-service/"
FINLYNQ_PREFIX = "services/finlynq/"
BROWSER_MARKERS = (
    "ui/__tests__/e2e/",
    "ui/e2e/",
)
ROUTE_MOCKED_BROWSER_MARKERS = (
    "navigation-route-mocked.spec.ts",
    "route-mocked.spec.ts",
)


def _is_route_mocked_browser_path(path: str) -> bool:
    return any(path.endswith(marker) for marker in ROUTE_MOCKED_BROWSER_MARKERS)


def _requires_live_stack(paths: list[str], *, full: bool, frontend: bool, rules: bool, finlynq: bool, browser: bool) -> bool:
    if full:
        return True
    auth = any("auth" in path.lower() for path in paths)
    cross_service = rules and finlynq
    backend_ui = frontend and (rules or finlynq)
    browser_paths = [
        path for path in paths
        if path.startswith(BROWSER_MARKERS) or path.endswith('.spec.ts') or path.endswith('.spec.tsx')
    ]
    live_browser = browser and any(not _is_route_mocked_browser_path(path) for path in browser_paths)
    return auth or cross_service or backend_ui or live_browser


def _is_governance_path(path: str) -> bool:
    return path in GOVERNANCE_FILES or path.startswith(GOVERNANCE_PREFIXES) or _is_root_documentation(path)


def _is_full_path(path: str) -> bool:
    if path in GOVERNANCE_FILES or _is_root_documentation(path):
        return False
    return path in FULL_FILES or path.startswith(FULL_PREFIXES) or path in {
        "ui/package.json",
        "ui/package-lock.json",
        "ui/tsconfig.json",
        "ui/next.config.js",
        "ui/playwright.config.ts",
        "ui/vitest.config.ts",
        "ui/postcss.config.js",
        "ui/tailwind.config.ts",
    }


def classify_paths(paths: Iterable[str]) -> dict[str, object]:
    normalized = sorted({str(PurePosixPath(path)) for path in paths if path.strip()})
    if not normalized:
        return {
            "scope": "governance",
            "governance": True,
            "frontend": False,
            "rules": False,
            "finlynq": False,
            "browser": False,
            "live_stack": False,
            "full": False,
            "paths": [],
        }

    full = any(_is_full_path(path) for path in normalized)
    frontend = any(path.startswith(FRONTEND_PREFIX) for path in normalized)
    rules = any(path.startswith(RULES_PREFIX) for path in normalized)
    finlynq = any(path.startswith(FINLYNQ_PREFIX) for path in normalized)
    browser = any(
        path.startswith(BROWSER_MARKERS)
        or path.endswith(".spec.ts")
        or path.endswith(".spec.tsx")
        for path in normalized
    )
    live_stack = _requires_live_stack(
        normalized,
        full=full,
        frontend=frontend,
        rules=rules,
        finlynq=finlynq,
        browser=browser,
    )
    governance_only = all(_is_governance_path(path) for path in normalized)

    if governance_only:
        scope = "governance"
    elif full:
        scope = "full"
    elif frontend and not (rules or finlynq):
        scope = "frontend"
    elif rules and not (frontend or finlynq):
        scope = "rules"
    elif finlynq and not (frontend or rules):
        scope = "finlynq"
    else:
        scope = "mixed"

    return {
        "scope": scope,
        "governance": governance_only,
        "frontend": frontend or full,
        "rules": rules or full,
        "finlynq": finlynq or full,
        "browser": browser,
        "live_stack": live_stack,
        "full": full,
        "paths": normalized,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()
    result = classify_paths(args.paths)
    if args.github_output:
        for key, value in result.items():
            if key == "paths":
                continue
            print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
