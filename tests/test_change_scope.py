import unittest

from scripts.classify_change_scope import classify_paths


class ChangeScopeTests(unittest.TestCase):
    def test_governance_only_uses_governance_scope(self):
        result = classify_paths([
            "docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md",
            "AGENTS.md",
            ".github/workflows/test.yml",
            ".husky/pre-push",
            "scripts/classify_change_scope.py",
            "tests/test_change_scope.py",
        ])
        self.assertEqual(result["scope"], "governance")
        self.assertTrue(result["governance"])
        self.assertFalse(result["frontend"])
        self.assertFalse(result["full"])

    def test_root_documentation_uses_governance_scope(self):
        result = classify_paths(["README.md"])
        self.assertEqual(result["scope"], "governance")
        self.assertTrue(result["governance"])

    def test_frontend_scope_enables_only_frontend_by_default(self):
        result = classify_paths(["ui/components/Widget.tsx", "ui/lib/widget.test.ts"])
        self.assertEqual(result["scope"], "frontend")
        self.assertTrue(result["frontend"])
        self.assertFalse(result["rules"])
        self.assertFalse(result["finlynq"])
        self.assertFalse(result["full"])

    def test_browser_marker_is_preserved_for_interaction_changes(self):
        result = classify_paths(["ui/__tests__/e2e/navigation.spec.ts"])
        self.assertTrue(result["frontend"])
        self.assertTrue(result["browser"])
        self.assertTrue(result["live_stack"])

    def test_route_mocked_browser_scope_does_not_enable_service_validation(self):
        result = classify_paths(["ui/__tests__/e2e/navigation-route-mocked.spec.ts"])
        self.assertEqual(result["scope"], "frontend")
        self.assertTrue(result["frontend"])
        self.assertTrue(result["browser"])
        self.assertFalse(result["rules"])
        self.assertFalse(result["finlynq"])
        self.assertFalse(result["live_stack"])

    def test_backend_ui_or_auth_scope_requires_live_stack(self):
        integrated = classify_paths(["ui/lib/api.ts", "services/rules-service/app/routes/example.py"])
        auth = classify_paths(["ui/components/providers/AuthBootstrapProvider.tsx"])
        self.assertTrue(integrated["live_stack"])
        self.assertTrue(auth["live_stack"])

    def test_service_scopes_are_independent(self):
        rules = classify_paths(["services/rules-service/app/routes/example.py"])
        finlynq = classify_paths(["services/finlynq/app/main.py"])
        self.assertEqual(rules["scope"], "rules")
        self.assertTrue(rules["rules"])
        self.assertFalse(rules["finlynq"])
        self.assertEqual(finlynq["scope"], "finlynq")
        self.assertTrue(finlynq["finlynq"])
        self.assertFalse(finlynq["rules"])

    def test_mixed_application_scope_enables_direct_services(self):
        result = classify_paths(["ui/lib/api.ts", "services/rules-service/app/routes/example.py"])
        self.assertEqual(result["scope"], "mixed")
        self.assertTrue(result["frontend"])
        self.assertTrue(result["rules"])
        self.assertFalse(result["full"])

    def test_runner_changes_request_full_matrix_scope(self):
        result = classify_paths(["scripts/test.sh"])
        self.assertEqual(result["scope"], "full")
        self.assertTrue(result["full"])
        self.assertTrue(result["live_stack"])
        self.assertTrue(result["frontend"])
        self.assertTrue(result["rules"])
        self.assertTrue(result["finlynq"])

    def test_unrelated_root_script_is_not_misclassified_as_governance(self):
        result = classify_paths(["scripts/check-build.sh"])
        self.assertEqual(result["scope"], "full")
        self.assertFalse(result["governance"])


if __name__ == "__main__":
    unittest.main()
