#!/usr/bin/env python3
"""Maintain Atlas project status without network, Git, or application changes."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ATLAS_STATUS_ROOT", Path(__file__).resolve().parents[1]))
STATUS_PATH = ROOT / "docs/10-roadmap/PROJECT_STATUS.json"
MARKDOWN_PATH = ROOT / "docs/10-roadmap/PROJECT_STATUS.md"
COMPLETED_PATH = ROOT / "docs/10-roadmap/COMPLETED_PHASES.md"
WORK_STATUSES = {"planned", "in_progress", "blocked", "in_review", "complete", "cancelled"}
PHASE_STATUSES = {"not_started", "in_progress", "blocked", "in_review", "complete"}
RISK_TIERS = {"low", "medium", "high"}
# Risk-tier enforcement summary. The canonical policy is:
#   docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md
# Low needs focused commit evidence only; medium needs commit + direct tests;
# high needs branch, focused tests, and local validation evidence (or a
# preserved historical hosted-CI record) plus fresh review evidence.
# This utility validates evidence shape and phase status; it does not impose a
# fixed correction-cycle limit or require unrelated full-suite evidence.
CI_RUN_URL = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/[0-9]+(?:/job/[0-9]+)?$")
GENERIC_CI_CHECK_NAMES = {"passed", "success", "successful", "green", "ok"}
GENERIC_LOCAL_COMMANDS = {"passed", "success", "successful", "green", "ok", "tests"}


class StatusError(ValueError):
    pass


def load(path: Path = STATUS_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatusError(f"cannot read status: {exc}") from exc


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def save(status: dict[str, Any], path: Path = STATUS_PATH) -> None:
    status["last_updated"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    atomic_write(path, json.dumps(status, indent=2, sort_keys=True) + "\n")


def ids(items: list[dict[str, Any]], label: str) -> None:
    values = [item.get("id") for item in items]
    if any(not isinstance(value, str) or not value for value in values) or len(values) != len(set(values)):
        raise StatusError(f"duplicate or missing {label} identifiers")


def work_risk_tier(item: dict[str, Any]) -> str | None:
    tier = item.get("risk_tier")
    if tier is None:
        return None
    if tier not in RISK_TIERS:
        raise StatusError(f"invalid risk tier for {item.get('id')}")
    return tier


def valid_ci_evidence(value: Any) -> bool:
    """Accept preserved historical successful GitHub Actions evidence."""
    if not isinstance(value, dict) or set(value) != {"run_url", "check", "conclusion"}:
        return False
    run_url = value["run_url"]
    check = value["check"]
    conclusion = value["conclusion"]
    return (
        isinstance(run_url, str)
        and bool(CI_RUN_URL.fullmatch(run_url))
        and isinstance(check, str)
        and bool(check.strip())
        and check.strip().lower() not in GENERIC_CI_CHECK_NAMES
        and len(check) <= 160
        and conclusion == "success"
    )


def valid_local_evidence(value: Any) -> bool:
    """Accept concrete structured local validation evidence for new work."""
    if not isinstance(value, dict):
        return False
    required = {"kind", "commit", "command", "result", "timestamp", "environment"}
    if not required.issubset(value) or value.get("kind") != "local":
        return False
    commit = value.get("commit")
    command = value.get("command")
    result = value.get("result")
    timestamp = value.get("timestamp")
    environment = value.get("environment")
    if not all(isinstance(item, str) and item.strip() for item in (commit, command, result, timestamp, environment)):
        return False
    if command.strip().lower() in GENERIC_LOCAL_COMMANDS or len(command) > 500:
        return False
    if len(result) > 160 or len(environment) > 300:
        return False
    try:
        dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    count = value.get("test_count")
    return count is None or (isinstance(count, int) and count >= 0)


def valid_validation_evidence(value: Any) -> bool:
    """Accept new local evidence or unchanged historical hosted evidence."""
    return valid_local_evidence(value) or valid_ci_evidence(value)


def validate(status: dict[str, Any]) -> None:
    required = {"schema_version", "last_updated", "current_phase_id", "overall_status", "current_objective", "active_work", "blockers", "risks", "phases", "completed_work", "commit_pr_evidence", "test_evidence", "next_bounded_task"}
    missing = required - set(status)
    if missing:
        raise StatusError(f"missing top-level keys: {', '.join(sorted(missing))}")
    if status["overall_status"] not in PHASE_STATUSES | {"planned"}:
        raise StatusError("invalid overall_status")
    for key in ("active_work", "blockers", "risks", "phases", "completed_work", "commit_pr_evidence", "test_evidence"):
        if not isinstance(status[key], list):
            raise StatusError(f"{key} must be a list")
    ids(status["risks"], "risk")
    ids(status["phases"], "phase")
    ids(status["completed_work"], "completed-work")
    phase_ids = {phase["id"] for phase in status["phases"]}
    if status["current_phase_id"] not in phase_ids:
        raise StatusError("current_phase_id is not a phase")
    criteria: list[dict[str, Any]] = []
    for phase in status["phases"]:
        if phase.get("status") not in PHASE_STATUSES:
            raise StatusError(f"invalid phase status: {phase.get('id')}")
        phase_criteria = phase.get("exit_criteria")
        if not isinstance(phase_criteria, list):
            raise StatusError(f"phase {phase['id']} has no exit_criteria list")
        criteria.extend(phase_criteria)
    ids(criteria, "exit-criterion")
    all_work = status["active_work"] + status["completed_work"]
    ids(all_work, "work")
    for work in all_work:
        if work.get("status") not in WORK_STATUSES or work.get("phase_id") not in phase_ids:
            raise StatusError(f"invalid work item: {work.get('id')}")
        tier = work_risk_tier(work)
        if work["status"] in {"blocked", "cancelled"} and not work.get("reason"):
            raise StatusError(f"{work['id']} requires a reason")
        if work["status"] == "in_review" and not work.get("pr"):
            raise StatusError(f"{work['id']} in_review requires a PR")
        if tier == "high" and (
            not isinstance(work.get("branch"), str) or not work["branch"].strip()
        ):
            raise StatusError(f"{work['id']} high-risk work requires a branch")
        if work["status"] == "complete":
            if tier == "low" and not work.get("commit"):
                raise StatusError(f"{work['id']} low-risk completion requires commit evidence")
            if tier == "medium" and (not work.get("commit") or not work.get("tests")):
                raise StatusError(f"{work['id']} medium-risk completion requires commit and test evidence")
            if tier == "high" and (
                not work.get("commit")
                or not work.get("pr")
                or not work.get("review_evidence")
                or not work.get("tests")
                or not valid_validation_evidence(work.get("validation_evidence") or work.get("ci_evidence"))
            ):
                raise StatusError(f"{work['id']} high-risk completion requires branch, commit, PR, review, tests, and concrete local or historical validation evidence")
            if tier is None and not (work.get("commit") or work.get("pr")):
                raise StatusError(f"{work['id']} complete requires commit or PR evidence")
    for phase in status["phases"]:
        if phase["status"] == "complete" and not all(item.get("complete") is True for item in phase["exit_criteria"]):
            raise StatusError(f"phase {phase['id']} is complete with incomplete exit criteria")


def path_overlap(left: str, right: str) -> bool:
    a, b = left.strip("/"), right.strip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def phase(status: dict[str, Any], phase_id: str) -> dict[str, Any]:
    for item in status["phases"]:
        if item["id"] == phase_id:
            return item
    raise StatusError(f"unknown phase: {phase_id}")


def render(status: dict[str, Any]) -> str:
    current = phase(status, status["current_phase_id"])
    lines = [
        "# Atlas Project Status",
        "",
        "> Generated from `PROJECT_STATUS.json`; regenerate with `python3 scripts/atlas_project_status.py render`.",
        "",
        f"- Current phase: **{current['id']} — {current['name']}** ({current['status']})",
        f"- Overall status: **{status['overall_status']}**",
        f"- Current objective: {status['current_objective']}",
        f"- Last updated: {status['last_updated']}",
        "",
        "## Active work",
    ]
    lines += [f"- {item['id']}: {item['title']} ({item['status']}{', ' + item['risk_tier'] if item.get('risk_tier') else ''})" for item in status["active_work"]] or ["- None"]
    lines += ["", "## Blockers"] + [f"- {item}" for item in status["blockers"] or ["None"]]
    lines += ["", "## Phase progress"]
    for item in status["phases"]:
        done = sum(criterion.get("complete") is True for criterion in item["exit_criteria"])
        lines.append(f"- {item['id']} — {item['name']}: {item['status']} ({done}/{len(item['exit_criteria'])} exit criteria)")
    lines += ["", "## Current risks"]
    lines += [f"- {risk['id']} [{risk['severity']}/{risk['likelihood']}, {risk['status']}]: {risk['description']}" for risk in status["risks"]] or ["- None"]
    lines += ["", "## Recently completed work"]
    lines += [f"- {item['id']}: {item['title']} — commit {item.get('commit', 'n/a')}, PR {item.get('pr', 'n/a')}" for item in status["completed_work"][-5:]] or ["- None"]
    lines += ["", "## Evidence"]
    lines += [f"- {item.get('commit', 'n/a')}: {item.get('description', '')} {item.get('pr', '')}".rstrip() for item in status["commit_pr_evidence"]]
    lines += [f"- Test {item['id']}: {item['scope']} — {item['result']}" for item in status["test_evidence"]]
    next_task = status["next_bounded_task"]
    lines += ["", "## Next bounded task", f"- {next_task['id']}: {next_task['description']}", "", "Do not begin the next phase or task automatically.", ""]
    return "\n".join(lines)


def write_render(status: dict[str, Any], check: bool = False) -> None:
    rendered = render(status)
    if check:
        actual = MARKDOWN_PATH.read_text(encoding="utf-8") if MARKDOWN_PATH.exists() else ""
        if actual != rendered:
            raise StatusError("PROJECT_STATUS.md is stale; run render")
    else:
        atomic_write(MARKDOWN_PATH, rendered)


def command_start(status: dict[str, Any], args: argparse.Namespace) -> None:
    if args.phase != status["current_phase_id"]:
        raise StatusError("work does not belong to the current phase")
    target_phase = phase(status, args.phase)
    if target_phase["status"] == "complete":
        raise StatusError("cannot start work in a completed phase")
    if any(item["id"] == args.id for item in status["active_work"] + status["completed_work"]):
        raise StatusError("duplicate work identifier")
    for item in status["active_work"]:
        if item["status"] not in {"complete", "cancelled"} and any(path_overlap(a, b) for a in args.path for b in item.get("paths", [])):
            raise StatusError(f"conflicting active work: {item['id']}")
    if target_phase["status"] == "not_started":
        target_phase["status"] = "in_progress"
        status["overall_status"] = "in_progress"
    if args.risk_tier == "high" and not args.branch:
        raise StatusError("high-risk work requires a branch")
    status["active_work"].append({"id": args.id, "title": args.title, "status": "in_progress", "phase_id": args.phase, "paths": args.path, "objective": args.objective, "risk_tier": args.risk_tier, "branch": args.branch, "issue": args.issue, "tests": args.test})


def work(status: dict[str, Any], work_id: str) -> dict[str, Any]:
    for item in status["active_work"]:
        if item["id"] == work_id:
            return item
    raise StatusError(f"unknown active work: {work_id}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("show", "check"):
        sub.add_parser(name)
    render_parser = sub.add_parser("render"); render_parser.add_argument("--check", action="store_true")
    start = sub.add_parser("start"); start.add_argument("--id", required=True); start.add_argument("--title", required=True); start.add_argument("--phase", required=True); start.add_argument("--path", action="append", required=True); start.add_argument("--objective", required=True); start.add_argument("--risk-tier", choices=sorted(RISK_TIERS), default="medium"); start.add_argument("--branch", default=""); start.add_argument("--issue", default=""); start.add_argument("--test", action="append", default=[])
    block = sub.add_parser("block"); block.add_argument("--id", required=True); block.add_argument("--reason", required=True)
    review = sub.add_parser("review"); review.add_argument("--id", required=True); review.add_argument("--pr", required=True)
    complete = sub.add_parser("complete-work"); complete.add_argument("--id", required=True); complete.add_argument("--commit"); complete.add_argument("--pr"); complete.add_argument("--review-evidence"); complete.add_argument("--test", action="append", default=[]); complete.add_argument("--ci-run-url"); complete.add_argument("--ci-check"); complete.add_argument("--local-command"); complete.add_argument("--local-result"); complete.add_argument("--local-environment", default="")
    complete_phase = sub.add_parser("complete-phase"); complete_phase.add_argument("--phase", required=True); complete_phase.add_argument("--commit", required=True); complete_phase.add_argument("--pr", action="append", default=[]); complete_phase.add_argument("--test", action="append", required=True); complete_phase.add_argument("--adr", action="append", required=True); complete_phase.add_argument("--limitation", action="append", required=True); complete_phase.add_argument("--next-task", required=True)
    add_risk = sub.add_parser("add-risk"); add_risk.add_argument("--id", required=True); add_risk.add_argument("--description", required=True); add_risk.add_argument("--severity", required=True); add_risk.add_argument("--likelihood", required=True); add_risk.add_argument("--mitigation", required=True); add_risk.add_argument("--owner", required=True); add_risk.add_argument("--related", default="")
    resolve = sub.add_parser("resolve-risk"); resolve.add_argument("--id", required=True); resolve.add_argument("--evidence", required=True)
    next_task = sub.add_parser("set-next"); next_task.add_argument("--id", required=True); next_task.add_argument("--description", required=True); next_task.add_argument("--phase", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        status = load(); validate(status)
        if args.command == "show": print(render(status)); return 0
        if args.command == "check": print("project status is valid"); return 0
        if args.command == "render": write_render(status, args.check); return 0
        if args.command == "start": command_start(status, args)
        elif args.command == "block": item = work(status, args.id); item.update(status="blocked", reason=args.reason)
        elif args.command == "review": item = work(status, args.id); item.update(status="in_review", pr=args.pr)
        elif args.command == "complete-work":
            item = work(status, args.id)
            tier = work_risk_tier(item) or "medium"
            if tier == "low" and not args.commit:
                raise StatusError("low-risk completion requires commit evidence")
            if tier == "medium" and (not args.commit or not args.test):
                raise StatusError("medium-risk completion requires commit and test evidence")
            if tier == "high" and (not args.commit or not args.pr or not args.review_evidence or not args.test):
                raise StatusError("high-risk completion requires commit, PR, review, and test evidence")
            ci_evidence = None
            if args.ci_run_url is not None or args.ci_check is not None:
                ci_evidence = {"run_url": args.ci_run_url, "check": args.ci_check, "conclusion": "success"}
            local_evidence = None
            if args.local_command is not None or args.local_result is not None or args.local_environment:
                local_evidence = {
                    "kind": "local",
                    "commit": args.commit,
                    "command": args.local_command,
                    "result": args.local_result,
                    "timestamp": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "environment": args.local_environment,
                }
            if tier == "high":
                if ci_evidence is not None and local_evidence is not None:
                    raise StatusError("provide either historical CI evidence or local validation evidence, not both")
                if not valid_validation_evidence(local_evidence or ci_evidence):
                    raise StatusError("high-risk completion requires concrete local validation evidence or preserved historical CI evidence")
            completion = {
                "status": "complete",
                "commit": args.commit,
                "pr": args.pr,
                "review_evidence": args.review_evidence,
                "tests": args.test,
            }
            if tier == "high":
                if local_evidence is not None:
                    completion["validation_evidence"] = local_evidence
                else:
                    completion["ci_evidence"] = ci_evidence
            item.update(completion); status["active_work"].remove(item); status["completed_work"].append(item)
        elif args.command == "complete-phase":
            target = phase(status, args.phase)
            if target["status"] == "complete":
                raise StatusError("phase is already complete")
            if not all(item.get("complete") is True for item in target["exit_criteria"]): raise StatusError("cannot complete phase with incomplete exit criteria")
            target["status"] = "complete"
            entry = (
                f"\n## {target['id']} — {target['name']}\n\n"
                f"- Completion date: {dt.date.today().isoformat()}\n"
                f"- Final commit: `{args.commit}`\n"
                f"- Merged PRs: {', '.join(args.pr) or 'None recorded'}\n"
                f"- Test evidence: {'; '.join(args.test)}\n"
                f"- ADRs: {', '.join(args.adr)}\n"
                f"- Known limitations: {'; '.join(args.limitation)}\n"
                f"- Authorized next phase: {args.next_task}\n"
            )
            with COMPLETED_PATH.open("a", encoding="utf-8") as handle: handle.write(entry)
        elif args.command == "add-risk":
            status["risks"].append({"id": args.id, "description": args.description, "severity": args.severity, "likelihood": args.likelihood, "mitigation": args.mitigation, "owner": args.owner, "status": "open", "related": args.related})
        elif args.command == "resolve-risk":
            risk = next((item for item in status["risks"] if item["id"] == args.id), None)
            if not risk: raise StatusError("unknown risk")
            risk.update(status="resolved", related=(risk.get("related", "") + "; " + args.evidence).strip("; "))
        elif args.command == "set-next":
            phase(status, args.phase); status["next_bounded_task"] = {"id": args.id, "description": args.description, "phase_id": args.phase}
        validate(status); save(status); write_render(status)
        return 0
    except StatusError as exc:
        print(f"error: {exc}", file=os.sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
