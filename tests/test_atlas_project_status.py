import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/atlas_project_status.py"


class ProjectStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "docs/10-roadmap").mkdir(parents=True)
        self.status = self.root / "docs/10-roadmap/PROJECT_STATUS.json"
        self.markdown = self.root / "docs/10-roadmap/PROJECT_STATUS.md"
        self.completed = self.root / "docs/10-roadmap/COMPLETED_PHASES.md"
        self.completed.write_text("# Completed\n", encoding="utf-8")
        self.status.write_text(json.dumps({
            "schema_version": "1.0.0", "last_updated": "2026-01-01T00:00:00Z",
            "current_phase_id": "phase-1", "overall_status": "in_progress", "current_objective": "test",
            "active_work": [], "blockers": [], "risks": [],
            "phases": [{"id": "phase-1", "name": "One", "status": "in_progress", "exit_criteria": [{"id": "ec-1", "description": "done", "complete": True}]}],
            "completed_work": [], "commit_pr_evidence": [], "test_evidence": [],
            "next_bounded_task": {"id": "next-1", "description": "stop", "phase_id": "phase-1"}
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args, expect=0):
        result = subprocess.run(["python3", str(SCRIPT), *args], cwd=self.root, text=True, capture_output=True, env={**__import__("os").environ, "ATLAS_STATUS_ROOT": str(self.root)})
        self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def test_check_and_render_are_deterministic(self):
        self.invoke("check")
        self.invoke("render")
        self.invoke("render", "--check")

    def test_start_rejects_overlapping_work(self):
        args = ("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test")
        self.invoke(*args)
        self.assertEqual(json.loads(self.status.read_text())["phases"][0]["status"], "in_progress")
        self.invoke("start", "--id", "work-2", "--title", "Two", "--phase", "phase-1", "--path", "services/rules-service/app", "--objective", "test", expect=1)

    def test_low_risk_completion_requires_only_a_commit(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "docs", "--objective", "test", "--risk-tier", "low")
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123")
        completed = json.loads(self.status.read_text())["completed_work"][0]
        self.assertEqual(completed["risk_tier"], "low")
        self.assertFalse(completed["pr"])
        self.assertNotIn("ci_evidence", completed)
        # Low risk requires NO branch (the tracker always emits the ``branch`` key on
        # the work dict; for low risk it stays empty), NO pr, NO review_evidence,
        # NO ci_evidence.
        self.assertEqual(completed.get("branch"), "")

    def test_medium_risk_completion_allows_no_pr(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "docs", "--objective", "test", "--risk-tier", "medium")
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--test", "1 passed")
        completed = json.loads(self.status.read_text())["completed_work"][0]
        self.assertEqual(completed["risk_tier"], "medium")
        self.assertFalse(completed["pr"])
        self.assertNotIn("ci_evidence", completed)
        # Medium risk requires NO branch (consistent with optional PR + optional CI
        # under the new "shared-behavior-affected" gate).
        self.assertEqual(completed.get("branch"), "")

    def test_medium_risk_start_does_not_require_a_branch(self):
        # Mirror the new simplified medium-risk policy: medium-risk work can start
        # without an explicit --branch flag (a branch may still be created locally
        # by the workflow, but the tracker does not require it).
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "ui/components/dashboard", "--objective", "test", "--risk-tier", "medium")
        active = json.loads(self.status.read_text())["active_work"][0]
        self.assertEqual(active["risk_tier"], "medium")
        self.assertFalse(active["branch"])

    def test_high_risk_review_evidence_has_no_fixed_cycle_marker_requirement(self):
        # Review evidence remains required for high-risk work, but the tracker
        # does not impose an arbitrary correction-cycle format or cap.
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        review_text = "Fresh independent review approved the exact head; no critical or high findings remain."
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", review_text, "--test", "1 passed", "--ci-run-url", "https://github.com/atlas/test/actions/runs/123", "--ci-check", "status")
        completed = json.loads(self.status.read_text())["completed_work"][0]
        self.assertEqual(completed["risk_tier"], "high")
        self.assertEqual(completed["review_evidence"], review_text)
        self.assertEqual(completed["ci_evidence"]["conclusion"], "success")

    def test_high_risk_completion_accepts_structured_local_validation_evidence(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        self.invoke(
            "complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7",
            "--review-evidence", "local review approved", "--test", "focused contract: 3 passed",
            "--local-command", "python3 -m pytest services/rules-service/tests/test_contract.py -q",
            "--local-result", "3 passed", "--local-environment", "Python 3.12 isolated Rules Service environment",
        )
        completed = json.loads(self.status.read_text())["completed_work"][0]
        self.assertEqual(completed["validation_evidence"]["kind"], "local")
        self.assertEqual(completed["validation_evidence"]["commit"], "abc123")
        self.assertEqual(completed["validation_evidence"]["result"], "3 passed")
        self.assertNotIn("ci_evidence", completed)

    def test_high_risk_completion_rejects_missing_or_generic_local_evidence(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        common = ("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "approved", "--test", "1 passed")
        self.invoke(*common, "--local-result", "1 passed", "--local-environment", "Python 3.12", expect=1)
        self.invoke(*common, "--local-command", "passed", "--local-result", "1 passed", "--local-environment", "Python 3.12", expect=1)
        self.invoke(*common, "--local-command", "python3 -m pytest tests/test.py -q", "--local-result", "1 passed", expect=1)

    def test_high_risk_completion_rejects_local_evidence_with_missing_commit(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        self.invoke(
            "complete-work", "--id", "work-1", "--pr", "#7", "--review-evidence", "approved", "--test", "1 passed",
            "--local-command", "python3 -m pytest tests/test.py -q", "--local-result", "1 passed", "--local-environment", "Python 3.12", expect=1,
        )

    def test_high_risk_historical_hosted_evidence_remains_accepted(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "historical review approved", "--test", "1 passed", "--ci-run-url", "https://github.com/atlas/test/actions/runs/123", "--ci-check", "status")
        completed = json.loads(self.status.read_text())["completed_work"][0]
        self.assertEqual(completed["ci_evidence"]["run_url"], "https://github.com/atlas/test/actions/runs/123")
        self.assertNotIn("validation_evidence", completed)

    def test_high_risk_work_still_requires_a_branch_on_completion(self):
        # Backward-compat: high-risk work requires a branch even after the
        # simplified policy. This catches regressions in command_start / validate.
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "approved", "--test", "1 passed", "--ci-run-url", "https://github.com/atlas/test/actions/runs/123", "--ci-check", "status")
        payload = json.loads(self.status.read_text())
        payload["completed_work"][0].pop("branch")
        self.status.write_text(json.dumps(payload), encoding="utf-8")
        self.invoke("check", expect=1)

    def test_high_risk_completion_requires_branch_pr_review_and_ci_evidence(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--test", "1 passed", expect=1)
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--test", "1 passed", expect=1)
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "independent review approved", "--test", "1 passed", expect=1)
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "independent review approved", "--test", "1 passed", "--ci-run-url", "https://github.com/atlas/test/actions/runs/123", "--ci-check", "passed", expect=1)
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "independent review approved", "--test", "1 passed", "--ci-run-url", "https://github.com/atlas/test/actions/runs/123", "--ci-check", "status")
        completed = json.loads(self.status.read_text())["completed_work"][0]
        self.assertEqual(completed["ci_evidence"]["conclusion"], "success")

    def test_completed_high_risk_work_without_branch_is_rejected(self):
        self.invoke("start", "--id", "work-1", "--title", "One", "--phase", "phase-1", "--path", "services/rules-service", "--objective", "test", "--risk-tier", "high", "--branch", "codex/high-risk")
        self.invoke("complete-work", "--id", "work-1", "--commit", "abc123", "--pr", "#7", "--review-evidence", "independent review approved", "--test", "1 passed", "--ci-run-url", "https://github.com/atlas/test/actions/runs/123", "--ci-check", "status")
        payload = json.loads(self.status.read_text())
        payload["completed_work"][0].pop("branch")
        self.status.write_text(json.dumps(payload), encoding="utf-8")
        self.invoke("check", expect=1)

    def test_check_workflow_does_not_mutate_status(self):
        self.invoke("render")
        before = self.status.read_bytes()
        self.invoke("check")
        self.invoke("render", "--check")
        self.assertEqual(before, self.status.read_bytes())

    def test_phase_completion_rejects_incomplete_criteria(self):
        payload = json.loads(self.status.read_text())
        payload["phases"][0]["exit_criteria"][0]["complete"] = False
        self.status.write_text(json.dumps(payload), encoding="utf-8")
        self.invoke(
            "complete-phase", "--phase", "phase-1", "--commit", "abc123",
            "--test", "1 passed", "--adr", "ADR-test", "--limitation", "none",
            "--next-task", "review phase 2", expect=1,
        )

    def test_phase_completion_creates_a_complete_append_only_record(self):
        args = (
            "complete-phase", "--phase", "phase-1", "--commit", "abc123",
            "--pr", "#7", "--test", "1 passed", "--adr", "ADR-test",
            "--limitation", "none", "--next-task", "review phase 2",
        )
        self.invoke(*args)
        record = self.completed.read_text(encoding="utf-8")
        self.assertIn("Test evidence: 1 passed", record)
        self.assertIn("Authorized next phase: review phase 2", record)
        self.invoke(*args, expect=1)


if __name__ == "__main__":
    unittest.main()
