#!/usr/bin/env python3
"""Render a safe, repository-authoritative Atlas handoff."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


HANDOFF_RELATIVE_PATH = Path("docs/10-roadmap/CURRENT_HANDOFF.md")
STATUS_RELATIVE_PATH = Path("docs/10-roadmap/PROJECT_STATUS.json")
GENERATED_PATH = HANDOFF_RELATIVE_PATH.as_posix()


class HandoffError(RuntimeError):
    """A safe, caller-facing handoff error."""


def run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise HandoffError("Git metadata is unavailable for the Atlas repository")
    return result.stdout.strip()


def discover_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("ATLAS_REPO_ROOT"):
        candidates.append(Path(os.environ["ATLAS_REPO_ROOT"]).expanduser())
    candidates.append(Path.cwd())
    try:
        candidates.append(Path(__file__).resolve().parents[4])
    except IndexError:
        pass

    for candidate in candidates:
        candidate = candidate.resolve()
        top = run_git(candidate, "rev-parse", "--show-toplevel", check=False)
        root = Path(top).resolve() if top else candidate
        if (root / STATUS_RELATIVE_PATH).is_file():
            return root
    raise HandoffError("Run from Atlas or pass --repo / set ATLAS_REPO_ROOT")


def load_status(root: Path) -> dict[str, Any]:
    path = root / STATUS_RELATIVE_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError("Canonical Atlas project status is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise HandoffError("Canonical Atlas project status must be an object")
    return value


def phase(status: dict[str, Any]) -> dict[str, Any]:
    phase_id = status.get("current_phase_id")
    for item in status.get("phases", []):
        if item.get("id") == phase_id:
            return item
    raise HandoffError("Current phase is missing from canonical project status")


def text(value: Any, fallback: str = "None") -> str:
    if value is None or value == "":
        return fallback
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def render_canonical(status: dict[str, Any]) -> str:
    current = phase(status)
    criteria = current.get("exit_criteria", [])
    complete = sum(item.get("complete") is True for item in criteria)
    lines = [
        "# Atlas Current Handoff",
        "",
        "> Generated from canonical project status. Verify live Git state before editing.",
        "",
        "## Current objective",
        "",
        f"- Phase: {text(current.get('id'))} — {text(current.get('name'))}",
        f"- Phase status: {text(current.get('status'))}",
        f"- Overall status: {text(status.get('overall_status'))}",
        f"- Objective: {text(status.get('current_objective'))}",
        f"- Phase exit criteria: {complete}/{len(criteria)} complete",
        f"- Tracker updated: {text(status.get('last_updated'))}",
        "",
        "## Active work",
        "",
    ]
    active = status.get("active_work", [])
    if active:
        for item in active:
            lines.append(
                f"- {text(item.get('id'))}: {text(item.get('title'))} "
                f"[{text(item.get('status'))}/{text(item.get('risk_tier'), 'unclassified')}]"
            )
            lines.append(f"  - Objective: {text(item.get('objective'))}")
            lines.append(f"  - Branch: {text(item.get('branch'))}")
            paths = item.get("paths") or []
            lines.append(f"  - Paths: {', '.join(text(path) for path in paths) or 'None'}")
    else:
        lines.append("- None")

    lines += ["", "## Blockers", ""]
    blockers = status.get("blockers", [])
    if blockers:
        for item in blockers:
            if isinstance(item, dict):
                lines.append(
                    f"- {text(item.get('id'))} [{text(item.get('status'))}]: "
                    f"{text(item.get('description'))}"
                )
            else:
                lines.append(f"- {text(item)}")
    else:
        lines.append("- None")

    lines += ["", "## Open risks", ""]
    risks = [item for item in status.get("risks", []) if item.get("status") != "resolved"]
    if risks:
        for item in risks:
            lines.append(
                f"- {text(item.get('id'))} "
                f"[{text(item.get('severity'))}/{text(item.get('likelihood'))}]: "
                f"{text(item.get('description'))}"
            )
    else:
        lines.append("- None")

    lines += ["", "## Recently completed", ""]
    completed = status.get("completed_work", [])[-5:]
    if completed:
        for item in completed:
            lines.append(
                f"- {text(item.get('id'))}: {text(item.get('title'))} — "
                f"commit {text(item.get('commit'), 'not recorded')}, "
                f"PR {text(item.get('pr'), 'not recorded')}"
            )
    else:
        lines.append("- None")

    next_task = status.get("next_bounded_task") or {}
    lines += [
        "",
        "## Next bounded task",
        "",
        f"- {text(next_task.get('id'))}: {text(next_task.get('description'))}",
        "",
        "Do not begin the next task automatically.",
        "",
    ]
    return "\n".join(lines)


def live_git_summary(root: Path) -> str:
    branch = run_git(root, "branch", "--show-current") or "detached"
    head = run_git(root, "rev-parse", "HEAD")
    upstream = run_git(root, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    sync = "no upstream"
    if upstream:
        counts = run_git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        behind, ahead = counts.split() if counts else ("?", "?")
        sync = f"{ahead} ahead / {behind} behind {upstream}"

    porcelain = run_git(root, "status", "--porcelain", "--untracked-files=all", check=False)
    changed = []
    for line in porcelain.splitlines():
        path = line[3:].split(" -> ")[-1] if len(line) > 3 else ""
        if path and path != GENERATED_PATH:
            changed.append(path)
    state = "clean" if not changed else f"dirty ({len(changed)} path(s))"
    return "\n".join(
        [
            "## Live Git state (read-only)",
            "",
            f"- Branch: {branch}",
            f"- HEAD: {head}",
            f"- Synchronization: {sync}",
            f"- Working tree: {state}",
            "",
        ]
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("start", "status", "close", "check"))
    result.add_argument("--repo", help="Atlas repository root")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        root = discover_root(args.repo)
        status = load_status(root)
        canonical = render_canonical(status)
        target = root / HANDOFF_RELATIVE_PATH

        if args.mode in {"start", "status"}:
            print(canonical)
            print(live_git_summary(root))
            return 0
        if args.mode == "close":
            atomic_write(target, canonical)
            print(f"updated {HANDOFF_RELATIVE_PATH.as_posix()}")
            return 0

        actual = target.read_text(encoding="utf-8") if target.exists() else ""
        if actual != canonical:
            raise HandoffError("CURRENT_HANDOFF.md is stale; run atlas_handoff.py close")
        print("Atlas handoff is current")
        return 0
    except HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
