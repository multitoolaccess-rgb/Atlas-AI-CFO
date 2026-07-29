"""Rules adapter contracts for the dedicated B0 provider only."""
from __future__ import annotations

from app.forecast_provider.finlynq import HttpFinlynqProjectionStateAdapter


class _Response:
    status_code = 200
    def json(self):
        return {
            "schema_version": "atlas-projection-state/v1",
            "canonicalization": {"canonical_json_version": "atlas-canonical-json/v1", "hash_schema_version": "atlas-input-state-hash/v1", "hash_algorithm": "sha256"},
            "user_id": "atlas-test-user", "goal_id": 7, "as_of_timestamp": "2026-07-29T12:00:00Z", "currency": "USD",
            "current_value_components": [{"kind": "cash", "amount": "123.45", "source_reference": "finlynq-account-1", "observed_at": "2026-07-29T12:00:00Z"}],
            "contribution_inputs": [{"kind": "monthly_investable_cash_flow", "amount": "4.56", "source_reference": "finlynq-config-1", "observed_at": "2026-07-29T12:00:00Z"}],
            "freshness": {"max_data_age_days": 7, "observed_age_days": 0, "source_updated_at": "2026-07-29T12:00:00Z"},
            "provenance": [{"source_system": "finlynq", "reference_id": "finlynq-projection-goal-7", "observed_at": "2026-07-29T12:00:00Z", "record_count": 2, "source_state_hash": "a" * 64}],
            "missing_data_codes": ["legacy_float_balance_representation"], "reconciliation_state": "partial",
        }


class _Client:
    def __init__(self): self.calls = []
    def get(self, url, *, headers, timeout):
        self.calls.append((url, headers, timeout)); return _Response()


def test_adapter_calls_only_dedicated_provider_once_and_validates_scope():
    client = _Client()
    adapter = HttpFinlynqProjectionStateAdapter(base_url="http://finlynq", authorization="Bearer test", client=client)
    state = adapter.load_projection_state(user_id="atlas-test-user", goal_id=7)
    assert state.goal_id == 7
    assert client.calls == [("http://finlynq/projection-state/goals/7", {"Authorization": "Bearer test"}, 5.0)]
    assert all("/state" not in call[0] for call in client.calls)
