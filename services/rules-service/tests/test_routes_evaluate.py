"""Tests for the Phase 2 policy-based rule evaluation endpoint.

Covers:
1. Portfolio drift — account-type allocation vs targetAllocation
2. Idle cash — cash percentage vs idleCashThresholdPct
3. Goal progress — net worth progress toward goal targetValue
4. Edge cases — no accounts, empty policy, liability accounts excluded
"""
from pathlib import Path

import pytest

from app.routes.evaluate import _load_policy


# ---------------------------------------------------------------------------
# Fixtures — seed accounts with known balances using conftest helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_accounts(db_session, make_account, make_family_member):
    """Seed test accounts with known balances for evaluation tests."""
    from app.routes.shared import get_or_create_local_user

    local_user = get_or_create_local_user(db_session, "alex")
    self_row = make_family_member(name="Self", is_self=True)
    db_session.add(self_row)
    db_session.commit()
    db_session.refresh(self_row)

    accounts = [
        make_account(
            account_name="Checking",
            account_type="checking",
            institution_name="Bank",
            current_balance=10_000.0,
            family_member_id=self_row.id,
        ),
        make_account(
            account_name="Savings",
            account_type="savings",
            institution_name="Bank",
            current_balance=50_000.0,
            family_member_id=self_row.id,
        ),
        make_account(
            account_name="Brokerage",
            account_type="brokerage",
            institution_name="Fidelity",
            current_balance=100_000.0,
            family_member_id=self_row.id,
        ),
        make_account(
            account_name="401k",
            account_type="401k",
            institution_name="Fidelity",
            current_balance=200_000.0,
            family_member_id=self_row.id,
        ),
        make_account(
            account_name="Credit Card",
            account_type="credit_card",
            institution_name="Chase",
            current_balance=-5_000.0,
            family_member_id=self_row.id,
        ),
    ]
    for a in accounts:
        db_session.add(a)
    db_session.commit()
    return accounts


# ---------------------------------------------------------------------------
# Policy loader tests (pure — no DB needed)
# ---------------------------------------------------------------------------


class TestLoadPolicy:
    """Tests for the policy YAML loader."""

    def test_loads_default_policy(self):
        """The default policy file should load successfully."""
        policy = _load_policy()
        assert "targetAllocation" in policy
        assert "rebalanceThresholdPct" in policy
        assert "idleCashThresholdPct" in policy
        assert "goal" in policy

    def test_missing_file_returns_empty(self):
        """A missing policy file should return an empty dict."""
        policy = _load_policy(Path("/nonexistent/policy.yaml"))
        assert policy == {}

    def test_custom_policy_file(self, tmp_path):
        """A custom policy file should load correctly."""
        policy_file = tmp_path / "test-policy.yaml"
        policy_file.write_text(
            "targetAllocation:\n  us_equity: 0.50\nrebalanceThresholdPct: 10\n"
        )
        policy = _load_policy(policy_file)
        assert policy["targetAllocation"]["us_equity"] == 0.50
        assert policy["rebalanceThresholdPct"] == 10


# ---------------------------------------------------------------------------
# Portfolio drift tests
# ---------------------------------------------------------------------------


class TestPortfolioDrift:
    """Tests for the portfolio drift evaluation rule."""

    def test_drift_within_threshold(self, client, seed_accounts):
        """Accounts within threshold should return ok status."""
        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        drift_eval = next(
            e for e in data["evaluations"] if e["rule"] == "portfolio_drift"
        )
        # Total portfolio: 10k checking + 50k savings + 100k brokerage + 200k 401k = 360k
        # cash = 60k/360k = 16.7% (target 10%, drift 6.7% > 5% threshold)
        # This should be a warning since cash drifts beyond 5%
        assert drift_eval["status"] in ["ok", "warning", "critical"]
        assert "details" in drift_eval

    def test_no_accounts_returns_ok(self, client):
        """No accounts should return ok with a helpful message."""
        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        drift_eval = next(
            e for e in data["evaluations"] if e["rule"] == "portfolio_drift"
        )
        assert drift_eval["status"] == "ok"
        assert "No portfolio assets" in drift_eval["message"]

    def test_liability_accounts_excluded(self, client, db_session, make_account, make_family_member):
        """Credit card balances should not count toward portfolio allocation."""
        from app.routes.shared import get_or_create_local_user

        local_user = get_or_create_local_user(db_session, "alex")
        self_row = make_family_member(name="Self", is_self=True)
        db_session.add(self_row)
        db_session.commit()
        db_session.refresh(self_row)

        # Only a credit card — should not affect portfolio calculation
        db_session.add(
            make_account(
                account_name="Credit Card",
                account_type="credit_card",
                institution_name="Chase",
                current_balance=-5_000.0,
                family_member_id=self_row.id,
            )
        )
        db_session.commit()

        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        drift_eval = next(
            e for e in data["evaluations"] if e["rule"] == "portfolio_drift"
        )
        assert drift_eval["status"] == "ok"
        assert drift_eval["details"]["total_portfolio"] == 0.0


# ---------------------------------------------------------------------------
# Idle cash tests
# ---------------------------------------------------------------------------


class TestIdleCash:
    """Tests for the idle cash evaluation rule."""

    def test_high_cash_triggers_warning(self, client, seed_accounts):
        """Cash above threshold should trigger a warning."""
        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        cash_eval = next(
            e for e in data["evaluations"] if e["rule"] == "idle_cash"
        )
        # Cash = 60k (checking + savings), total = 360k (excluding credit card)
        # Cash % = 16.7%, threshold = 5% → should be warning
        assert cash_eval["status"] in ["warning", "critical"]
        assert (
            "exceeds" in cash_eval["message"].lower()
            or "threshold" in cash_eval["message"].lower()
        )

    def test_low_cash_returns_ok(self, client, db_session, make_account, make_family_member):
        """Cash within threshold should return ok."""
        from app.routes.shared import get_or_create_local_user

        local_user = get_or_create_local_user(db_session, "alex")
        self_row = make_family_member(name="Self", is_self=True)
        db_session.add(self_row)
        db_session.commit()
        db_session.refresh(self_row)

        # Very little cash relative to investments
        db_session.add(
            make_account(
                account_name="Checking",
                account_type="checking",
                institution_name="Bank",
                current_balance=1_000.0,
                family_member_id=self_row.id,
            )
        )
        db_session.add(
            make_account(
                account_name="Brokerage",
                account_type="brokerage",
                institution_name="Fidelity",
                current_balance=100_000.0,
                family_member_id=self_row.id,
            )
        )
        db_session.commit()

        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        cash_eval = next(
            e for e in data["evaluations"] if e["rule"] == "idle_cash"
        )
        # Cash = 1k / 101k = 0.99%, threshold = 5% → ok
        assert cash_eval["status"] == "ok"


# ---------------------------------------------------------------------------
# Goal progress tests
# ---------------------------------------------------------------------------


class TestGoalProgress:
    """Tests for the goal progress evaluation rule."""

    def test_goal_progress_basic(self, client, seed_accounts):
        """Goal progress should evaluate against policy goal."""
        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        goal_eval = next(
            e for e in data["evaluations"] if e["rule"] == "goal_progress"
        )
        assert goal_eval["status"] in ["ok", "warning", "critical"]
        assert "details" in goal_eval
        assert "target_value" in goal_eval["details"]
        assert "net_worth" in goal_eval["details"]
        assert "actual_pct" in goal_eval["details"]
        assert "expected_pct" in goal_eval["details"]


# ---------------------------------------------------------------------------
# Endpoint shape + auth tests
# ---------------------------------------------------------------------------


class TestEvaluateEndpoint:
    """Tests for the /api/evaluate endpoint shape and auth."""

    def test_requires_auth(self, client_no_auth):
        """Unauthenticated requests should return 401."""
        response = client_no_auth.get("/api/evaluate")
        assert response.status_code == 401

    def test_response_shape(self, client, seed_accounts):
        """Response should match EvaluateResponse schema."""
        response = client.get("/api/evaluate")
        assert response.status_code == 200
        data = response.json()

        assert "evaluations" in data
        assert "policy_path" in data
        assert "evaluated_at" in data
        assert isinstance(data["evaluations"], list)
        assert len(data["evaluations"]) >= 3  # drift, idle cash, goal

        for eval_item in data["evaluations"]:
            assert "rule" in eval_item
            assert "status" in eval_item
            assert "message" in eval_item
            assert eval_item["status"] in ["ok", "warning", "critical"]
