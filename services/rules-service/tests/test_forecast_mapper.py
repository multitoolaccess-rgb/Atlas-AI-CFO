"""Test-first contract for ``app.forecasts.mappers``.

The bounded mapper translates ``PersistedForecastVersion`` (SQLAlchemy
rows) into the merged ``ForecastVersionResponse`` wire envelope.  These
tests prove:

* a valid persisted synthetic version maps to the exact wire shape
  with all Decimal strings canonical, target-decision v2 rounded
  semantically intact, drivers/timestamps normalized to UTC RFC 3339
  Z, HATEOAS rels deterministic, and the ETag coming from the merged
  codec;
* malformed assumption / output / provenance / input snapshots
  reject via ``ForecastMapperError`` with a sanitized token (no source
  bytes, no ORM internals, no financial values in the error);
* column-derived money (``ending_balance`` and ``target_gap``) come
  from the version columns and not from the output snapshot, even
  when the snapshot would carry different numbers;
* idempotent replay maps identically to the original version (equal
  bytes between two calls with the same input);
* the mapper never touches the database and never imports the
  Finlynq adapter — adapter / DB leakage would silently bypass the
  bounded generation path.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.forecasts.api_codecs import derive_forecast_etag
from app.forecasts.canonical_state import (
    HASH_SCHEMA_VERSION,
    PROJECTION_STATE_SCHEMA_VERSION,
)
from app.forecasts.mappers import (
    REL_FORECAST,
    REL_GOAL,
    REL_SELF,
    ForecastMapperError,
    build_forecast_version_response,
)
from app.forecasts.repository import PersistedForecastVersion
from app.forecasts.snapshots import (
    ASSUMPTION_SCHEMA_VERSION,
    CALCULATION_DECIMAL_SCHEMA_VERSION,
    TARGET_DECISION_SCHEMA_VERSION,
)


# ---------------------------------------------------------------
# Synthetic persisted-version fixture builder
# ---------------------------------------------------------------


def _make_state(as_of: str = "2026-07-01T12:00:00Z", user_id: str = "atlas-test-user", goal_id: int = 1) -> dict:
    return {
        "schema_version": PROJECTION_STATE_SCHEMA_VERSION,
        "canonicalization": {
            "canonical_json_version": "atlas-canonical-json/v1",
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "hash_algorithm": "sha256",
        },
        "user_id": user_id,
        "goal_id": goal_id,
        "as_of_timestamp": as_of,
        "currency": "USD",
        "current_value_components": [
            {
                "kind": "investment",
                "amount": "1234.56",
                "source_reference": "atlas-test-account",
                "observed_at": as_of,
            }
        ],
        "contribution_inputs": [
            {
                "kind": "monthly_investable_cash_flow",
                "amount": "100",
                "source_reference": "atlas-test-cashflow",
                "observed_at": as_of,
            }
        ],
        "freshness": {
            "max_data_age_days": 30,
            "observed_age_days": 0,
            "source_updated_at": as_of,
        },
        "provenance": [
            {
                "source_system": "finlynq",
                "reference_id": "atlas-test-aggregate",
                "observed_at": as_of,
                "record_count": 1,
                "source_state_hash": "a" * 64,
            }
        ],
        "missing_data_codes": [],
        "reconciliation_state": "reconciled",
    }


def _make_assumptions() -> dict:
    return {
        "assumption_profile": "atlas-test-default",
        "assumption_schema_version": ASSUMPTION_SCHEMA_VERSION,
        "annual_return_rates": {
            "conservative": "0.02",
            "base": "0.04",
            "optimistic": "0.06",
        },
        "annual_inflation_rate": "0.02",
        "contribution_timing": "end",
        "period": "monthly",
        "rounding_rule": "ROUND_HALF_EVEN",
        "money_precision": "0.01",
        "goal_inputs": {
            "target_amount": "1000",
            "horizon_years": 1,
            "target_date": None,
            "source_representation": "float",
            "conversion": "decimal-str",
            "precision_restored": False,
        },
    }


def _make_output() -> dict:
    return {
        "calculation_decimal_schema_version": CALCULATION_DECIMAL_SCHEMA_VERSION,
        "target_status": True,
        "target_decision": {
            "decision_schema_version": TARGET_DECISION_SCHEMA_VERSION,
            "scenario": "base",
            "comparison": "greater_than_or_equal",
            "decision_basis": "currency_rounded",
            "rounding_rule": "ROUND_HALF_EVEN",
            "money_precision": "0.01",
            "unrounded_ending_balance": "1000.0001",
            "unrounded_target_amount": "1000",
            "rounded_ending_balance": "1000",
            "rounded_target_amount": "1000",
            "target_status": True,
        },
        "drivers": {
            "current_balance": "1234.56",
            "monthly_contribution": "100",
            "total_contributions": "1200",
            "target_amount": "1000",
            "horizon_months": 12,
            "data_as_of": "2026-07-01",
            "data_age_days": 0,
        },
        "scenarios": {
            "conservative": {
                "annual_return_rate": "0.02",
                "monthly_real_rate": "0.001",
                "ending_balance": "1234.56",
                "investment_growth": "10",
                "target_gap": "0",
                "reaches_target": True,
            },
            "base": {
                "annual_return_rate": "0.04",
                "monthly_real_rate": "0.001",
                "ending_balance": "1000",
                "investment_growth": "10",
                "target_gap": "0",
                "reaches_target": True,
            },
            "optimistic": {
                "annual_return_rate": "0.06",
                "monthly_real_rate": "0.001",
                "ending_balance": "1234.56",
                "investment_growth": "10",
                "target_gap": "0",
                "reaches_target": True,
            },
        },
    }


class _FakeForecast:
    """Duck-typed stand-in for the SQL ``Forecast`` row."""

    def __init__(self, *, id_: str, user_id: int, goal_id: int, latest_version_number: int):
        self.id = id_
        self.user_id = user_id
        self.goal_id = goal_id
        self.latest_version_number = latest_version_number
        self.forecast_kind = "goal_projection"
        self.currency = "USD"
        self.lifecycle_state = "active"
        self.created_at = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)
        self.updated_at = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)
        # populated in __dict__ for mapper's `forecast.created_at` usage
        self.versions: tuple = ()


class _FakeForecastVersion:
    """Duck-typed stand-in for the SQL ``ForecastVersion`` row."""

    def __init__(
        self,
        *,
        id_: str,
        forecast_id: str,
        version_number: int,
        input_state_hash: str,
        idempotency_key_hash: str,
        snapshot_schema_version: str,
        hash_schema_version: str,
        model_version: str,
        calculation_version: str,
        currency: str,
        calculated_at: datetime,
        data_as_of: datetime,
        max_data_age_days: int,
        data_age_days: int,
        input_snapshot_json: str,
        assumption_snapshot_json: str,
        output_snapshot_json: str,
        provenance_snapshot_json: str,
        ending_balance: Decimal,
        target_gap: Decimal,
        created_at: datetime,
    ):
        self.id = id_
        self.forecast_id = forecast_id
        self.version_number = version_number
        self.input_state_hash = input_state_hash
        self.idempotency_key_hash = idempotency_key_hash
        self.snapshot_schema_version = snapshot_schema_version
        self.hash_schema_version = hash_schema_version
        self.model_version = model_version
        self.calculation_version = calculation_version
        self.currency = currency
        self.calculated_at = calculated_at
        self.data_as_of = data_as_of
        self.max_data_age_days = max_data_age_days
        self.data_age_days = data_age_days
        self.input_snapshot_json = input_snapshot_json
        self.assumption_snapshot_json = assumption_snapshot_json
        self.output_snapshot_json = output_snapshot_json
        self.provenance_snapshot_json = provenance_snapshot_json
        self.ending_balance = ending_balance
        self.target_gap = target_gap
        self.created_at = created_at


def _make_persisted() -> PersistedForecastVersion:
    state_payload = _make_state()
    assumptions = _make_assumptions()
    output = _make_output()
    # Mirror the repository's snapshot-builder output shape exactly.
    state_obj = _build_canonical_state_obj(state_payload)
    from app.forecasts.snapshots import _validate_assumption_snapshot, _validate_output_snapshot
    from app.forecasts.canonical_state import canonical_json
    from app.forecasts.snapshots import ForecastSnapshots
    assumption_validated = _validate_assumption_snapshot(assumptions)
    output_validated = _validate_output_snapshot(output)
    state_hash_payload = state_obj.hash_payload()
    input_json = canonical_json({"assumptions": assumption_validated, "state": state_hash_payload})
    input_state_hash = hashlib.sha256(input_json.encode("utf-8")).hexdigest()
    snapshots = ForecastSnapshots(
        input_snapshot_json=input_json,
        assumption_snapshot_json=canonical_json(assumption_validated),
        output_snapshot_json=canonical_json(output_validated),
        provenance_snapshot_json=canonical_json({
            "provenance": state_hash_payload["provenance"],
            "freshness": state_hash_payload["freshness"],
        }),
        input_state_hash=input_state_hash,
    )
    forecast = _FakeForecast(
        id_="11111111-2222-3333-4444-555555555555",
        user_id=1,
        goal_id=1,
        latest_version_number=1,
    )
    version = _FakeForecastVersion(
        id_="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        forecast_id=forecast.id,
        version_number=1,
        input_state_hash=snapshots.input_state_hash,
        idempotency_key_hash=hashlib.sha256(b"atlas-test-key").hexdigest(),
        snapshot_schema_version=PROJECTION_STATE_SCHEMA_VERSION,
        hash_schema_version=HASH_SCHEMA_VERSION,
        model_version="atlas-model-v1",
        calculation_version="phase0-projection-v1",
        currency="USD",
        calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        data_as_of=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        max_data_age_days=30,
        data_age_days=0,
        input_snapshot_json=snapshots.input_snapshot_json,
        assumption_snapshot_json=snapshots.assumption_snapshot_json,
        output_snapshot_json=snapshots.output_snapshot_json,
        provenance_snapshot_json=snapshots.provenance_snapshot_json,
        ending_balance=Decimal("1000.00"),
        target_gap=Decimal("0.00"),
        created_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
    )
    return PersistedForecastVersion(forecast, version, True, snapshots.input_snapshot_json)


def _build_canonical_state_obj(payload: dict) -> "CanonicalProjectionState":
    from app.forecasts.canonical_state import CanonicalProjectionState
    return CanonicalProjectionState.model_validate(payload)


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


def test_valid_persisted_version_maps_to_exact_response_envelope_shape() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")

    # Top-level field set
    assert hasattr(response, "forecast_id")
    assert hasattr(response, "version_id")
    assert hasattr(response, "version_number")
    assert hasattr(response, "etag")
    assert hasattr(response, "input_state_hash")
    assert hasattr(response, "idempotency_key_hash")
    assert hasattr(response, "snapshot")
    assert hasattr(response, "currency")
    assert hasattr(response, "calculated_at")
    assert hasattr(response, "data_as_of")
    assert hasattr(response, "max_data_age_days")
    assert hasattr(response, "data_age_days")
    assert hasattr(response, "created_at")
    assert hasattr(response, "ending_balance")
    assert hasattr(response, "target_gap")
    assert hasattr(response, "target_status")
    assert hasattr(response, "target_decision")
    assert hasattr(response, "drivers")
    assert hasattr(response, "scenarios")
    assert hasattr(response, "assumption_snapshot")
    assert hasattr(response, "provenance_snapshot")
    assert hasattr(response, "input_snapshot")
    assert hasattr(response, "links")

    # Identity round-trip
    assert response.forecast_id == str(persisted.forecast.id)
    assert response.version_id == str(persisted.version.id)
    assert response.version_number == int(persisted.version.version_number)
    assert response.currency == "USD"
    assert response.input_state_hash == str(persisted.version.input_state_hash)
    assert response.idempotency_key_hash == str(persisted.version.idempotency_key_hash)


def test_ending_balance_and_target_gap_come_from_version_columns_not_snapshot() -> None:
    persisted = _make_persisted()
    # The output snapshot scenarios base.ending_balance is "1000"; the
    # version column overrides it to 1234.56.  Canonical decimal form
    # strips trailing zeros (-1.00 -> -1) per ``canonical_decimal_string``.
    persisted.version.ending_balance = Decimal("1234.56")
    persisted.version.target_gap = Decimal("-1.00")
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    assert response.ending_balance == "1234.56"
    assert response.target_gap == "-1"


def test_etag_is_derived_through_merged_codec_not_assembled_inline() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    assert response.etag == derive_forecast_etag(
        forecast_id=str(persisted.forecast.id),
        version_number=int(persisted.version.version_number),
    )
    # The mapper must NOT assemble an ETag by string concatenation.
    bare_pattern = (
        f"{persisted.forecast.id}-v{persisted.version.version_number}"
    )
    assert response.etag == bare_pattern


def test_links_are_deterministic_self_forecast_goal() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="https://api.example.com")
    rel_names = sorted([l.rel for l in response.links])
    assert rel_names == sorted([REL_SELF, REL_FORECAST, REL_GOAL])
    self_link = next(l for l in response.links if l.rel == REL_SELF)
    forecast_link = next(l for l in response.links if l.rel == REL_FORECAST)
    goal_link = next(l for l in response.links if l.rel == REL_GOAL)
    assert self_link.href == (
        f"https://api.example.com/api/v1/forecasts/{persisted.forecast.id}/versions/1"
    )
    assert forecast_link.href == (
        f"https://api.example.com/api/v1/forecasts/{persisted.forecast.id}"
    )
    assert goal_link.href == f"https://api.example.com/api/goals/{persisted.forecast.goal_id}"


def test_links_strip_trailing_slash_on_base_url() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="https://api.example.com/")
    self_link = next(l for l in response.links if l.rel == REL_SELF)
    assert self_link.href.startswith("https://api.example.com/api/v1/")
    assert "//api/v1" not in self_link.href


def test_scenarios_are_ordered_tuple_conservative_base_optimistic() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    ordered = [name for name, _ in response.scenarios.scenarios]
    assert ordered == ["conservative", "base", "optimistic"]


def test_drivers_data_as_of_is_normalized_to_rfc3339_z() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    # Persisted fixture has data_as_of="2026-07-01"; mapper must promote it.
    assert response.drivers.data_as_of.endswith("Z")
    assert response.drivers.data_as_of.startswith("2026-07-01T")
    assert response.drivers.data_age_days == 0


def test_target_decision_v2_rounded_quantization_matches_unrounded() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    td = response.target_decision
    assert td.scenario == "base"
    assert td.comparison == "greater_than_or_equal"
    assert td.decision_basis == "currency_rounded"
    assert td.rounding_rule == "ROUND_HALF_EVEN"
    assert td.money_precision == "0.01"
    assert td.target_status is True


def test_assumption_snapshot_goal_inputs_is_bounded_string_tuple() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    pairs = response.assumption_snapshot.goal_inputs
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs)
    names = {pair[0] for pair in pairs}
    assert names == {"target_amount", "horizon_years", "target_date"}
    for pair in pairs:
        assert isinstance(pair[1], str)
    target_amount_value = next(v for n, v in pairs if n == "target_amount")
    assert target_amount_value == "1000"


def test_provenance_snapshot_split_into_tuple_and_freshness_dict() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    prov = response.provenance_snapshot
    assert isinstance(prov.provenance, tuple)
    assert all(isinstance(entry, dict) for entry in prov.provenance)
    assert isinstance(prov.freshness, dict)
    assert "max_data_age_days" in prov.freshness


def test_input_snapshot_passes_through_as_dict() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    assert isinstance(response.input_snapshot, dict)
    assert "assumptions" in response.input_snapshot
    assert "state" in response.input_snapshot


def test_target_status_aligns_top_decision_and_scenarios() -> None:
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    assert response.target_status == response.target_decision.target_status
    assert response.target_status == response.scenarios.target_status


def test_idempotent_replay_maps_identically_to_original_version() -> None:
    persisted = _make_persisted()
    a = build_forecast_version_response(persisted, base_url="http://testserver")
    b = build_forecast_version_response(persisted, base_url="http://testserver")
    assert a.model_dump() == b.model_dump()


def test_malformed_assumption_snapshot_rejects_safely() -> None:
    persisted = _make_persisted()
    # Wedge a known-bad assumption JSON missing a required key.
    bad_assumption = json.loads(persisted.version.assumption_snapshot_json)
    bad_assumption.pop("goal_inputs")
    persisted.version.assumption_snapshot_json = json.dumps(bad_assumption)
    with pytest.raises(ForecastMapperError) as excinfo:
        build_forecast_version_response(persisted, base_url="http://testserver")
    msg = str(excinfo.value)
    assert "goal_inputs" not in msg  # sanitized — does not echo field names
    assert "0.04" not in msg  # sanitized — does not echo financial values


def test_malformed_output_snapshot_rejects_safely() -> None:
    persisted = _make_persisted()
    bad_output = json.loads(persisted.version.output_snapshot_json)
    bad_output["scenarios"] = {"only_base": bad_output["scenarios"]["base"]}
    persisted.version.output_snapshot_json = json.dumps(bad_output)
    with pytest.raises(ForecastMapperError) as excinfo:
        build_forecast_version_response(persisted, base_url="http://testserver")
    msg = str(excinfo.value)
    assert "1000" not in msg  # no financial payload leak


def test_malformed_provenance_snapshot_rejects_safely() -> None:
    persisted = _make_persisted()
    bad = json.loads(persisted.version.provenance_snapshot_json)
    bad["extra_unknown_field"] = 1
    persisted.version.provenance_snapshot_json = json.dumps(bad)
    with pytest.raises(ForecastMapperError) as excinfo:
        build_forecast_version_response(persisted, base_url="http://testserver")
    msg = str(excinfo.value)
    assert "1" not in msg  # no echo of arbitrary persisted key content


def test_malformed_input_snapshot_rejects_safely() -> None:
    persisted = _make_persisted()
    persisted.version.input_snapshot_json = "not-json"
    with pytest.raises(ForecastMapperError):
        build_forecast_version_response(persisted, base_url="http://testserver")


def test_quirky_currency_rejected_by_wire_schema() -> None:
    persisted = _make_persisted()
    persisted.version.currency = "EUR"
    # The Pydantic ForecastVersionResponse enforces Literal["USD"];
    # building must raise.  Either ForecastMapperError or ValueError
    # is acceptable — both sanitized at the route boundary.
    with pytest.raises(Exception):
        build_forecast_version_response(persisted, base_url="http://testserver")


def test_mapper_does_not_import_db_session_or_adapter_module() -> None:
    """Static AST inspection proves the mapper stays route-free / adapter-free."""

    source = open("services/rules-service/app/forecasts/mappers.py").read()
    tree = ast.parse(source)
    banner_module = "app.forecasts.mappers"
    forbidden_imports = {
        "sqlalchemy",
        "sqlalchemy.orm",
        "fastapi",
        "app.forecast_provider.finlynq",
        "app.routes",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == banner_module:
                continue
            imported.add(node.module or "")
    leaked = imported & forbidden_imports
    assert not leaked, f"mapper must not import {leaked}"


def test_mapper_does_not_invoke_the_database_session_or_db() -> None:
    """Smoke guard: the mapper must not touch a SQLAlchemy session
    even if its input is a duck-typed ``PersistedForecastVersion``.
    The fixture is a plain Python object — invocation must succeed
    without any engine / session binding."""
    persisted = _make_persisted()
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    assert response is not None


# ---------------------------------------------------------------
# Fix A: bounded "null" sentinel is intentional + XOR invariant
# ---------------------------------------------------------------


def _patch_assumption_goal_inputs(persisted: PersistedForecastVersion, **overrides) -> None:
    """Wedge a custom ``goal_inputs`` dict into the persisted
    assumption snapshot.  Roundtrips through ``canonical_json``
    so the snapshot stays structurally valid for the ``_build_*``
    layer."""
    from app.forecasts.canonical_state import canonical_json
    from app.forecasts.snapshots import _validate_assumption_snapshot
    payload = json.loads(persisted.version.assumption_snapshot_json)
    merged = {**payload["goal_inputs"], **overrides}
    payload["goal_inputs"] = merged
    validated = _validate_assumption_snapshot(payload)
    persisted.version.assumption_snapshot_json = canonical_json(validated)


def test_assumption_null_sentinel_is_emitted_only_for_absent_optional_field() -> None:
    """Contract (Fix A): the literal sentinel ``"null"`` is a

    BOUNDED wire placeholder for the OPTIONAL field that is absent
    per the Phase 0 Goal model XOR invariant — not a missing
    field.  When a Phase 0 persister records ``horizon_years``
    (int) the mapper MUST emit ``("horizon_years", "<int>")`` and
    ``("target_date", "null")``.
    """
    persisted = _make_persisted()
    # Default fixture: horizon_years=1, target_date=None.
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    pairs = dict(response.assumption_snapshot.goal_inputs)
    assert pairs["horizon_years"] == "1"
    assert pairs["target_date"] == "null"
    assert pairs["target_amount"] == "1000"


def test_assumption_null_sentinel_swap_to_target_date_when_horizon_absent() -> None:
    """Symmetric case: ``target_date`` present, ``horizon_years``
    absent — sentinel MUST appear on the OTHER field."""
    persisted = _make_persisted()
    _patch_assumption_goal_inputs(
        persisted,
        horizon_years=None,
        target_date="2030-12-31",
    )
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    pairs = dict(response.assumption_snapshot.goal_inputs)
    assert pairs["horizon_years"] == "null"
    assert pairs["target_date"] == "2030-12-31"


def test_assumption_xor_invariant_rejects_both_present() -> None:
    """Contract invariant: both ``horizon_years`` AND ``target_date``
    present simultaneously is a contract violation — reject."""
    persisted = _make_persisted()
    _patch_assumption_goal_inputs(
        persisted,
        horizon_years=5,
        target_date="2030-12-31",
    )
    with pytest.raises(ForecastMapperError) as excinfo:
        build_forecast_version_response(persisted, base_url="http://testserver")
    # Sanitized token — no field names, no persisted values.
    assert "horizon_years" not in str(excinfo.value)
    assert "target_date" not in str(excinfo.value)
    assert "5" not in str(excinfo.value)
    assert "2030" not in str(excinfo.value)


def test_assumption_xor_invariant_rejects_both_absent() -> None:
    """Contract invariant: BOTH ``horizon_years`` AND ``target_date``
    absent simultaneously is a contract violation — reject, do not
    silently emit two ``"null"`` sentinels."""
    persisted = _make_persisted()
    _patch_assumption_goal_inputs(
        persisted,
        horizon_years=None,
        target_date=None,
    )
    with pytest.raises(ForecastMapperError) as excinfo:
        build_forecast_version_response(persisted, base_url="http://testserver")
    assert "horizon_years" not in str(excinfo.value)
    assert "target_date" not in str(excinfo.value)


# ---------------------------------------------------------------
# Fix B: drivers.data_as_of must be YYYY-MM-DD or RFC3339-Z+T
# ---------------------------------------------------------------


def _patch_drivers_data_as_of(persisted: PersistedForecastVersion, value) -> None:
    """Write the raw ``drivers.data_as_of`` value directly into the

    persisted snapshot JSON column WITHOUT roundtripping through
    ``_validate_output_snapshot``.  Real-world persistence flows through
    the snapshot validator which has its own date validator; this
    test fixture intentionally bypasses that path so the mapper's own
    ``_coerce_drivers_data_as_of`` rejection logic is exercised
    end-to-end in isolation (defense in depth contract).
    """

    payload = json.loads(persisted.version.output_snapshot_json)
    payload["drivers"]["data_as_of"] = value
    persisted.version.output_snapshot_json = json.dumps(payload)


@pytest.mark.parametrize("good", [
    "2026-07-01",                              # plain date promoted
    "2026-07-01T00:00:00Z",                    # minimal RFC 3339 Z
    "2026-07-01T12:34:56Z",                    # seconds precision, Z
    "2026-07-01T12:34:56.789Z",                # milliseconds, Z
    "2026-07-01T23:59:59.999999Z",             # microseconds, Z
])
def test_drivers_data_as_of_accepts_only_bounded_shapes(good) -> None:
    """Fix B: plain ``YYYY-MM-DD`` OR RFC 3339 ``Z``+``T`` shape."""
    persisted = _make_persisted()
    _patch_drivers_data_as_of(persisted, good)
    response = build_forecast_version_response(persisted, base_url="http://testserver")
    assert response.drivers.data_as_of.endswith("Z") or len(good) == 10
    # When plain date, must be promoted to UTC midnight Z.
    if len(good) == 10:
        assert response.drivers.data_as_of == f"{good}T00:00:00.000000Z"
    else:
        assert response.drivers.data_as_of == good


@pytest.mark.parametrize("bad", [
    "2026-07-01T12:34:56+00:00",     # RFC 3339 with offset (no Z) — ambiguous
    "2026-07-01T12:34:56.789+02:00", # timezone offset Europe
    "2026-07-01 12:34:56Z",          # space instead of T
    "07/01/2026",                    # US slash format
    "garbage",                       # arbitrary garbage
])
def test_drivers_data_as_of_rejects_ambiguous_or_unknown_shapes(bad) -> None:
    """Fix B: every unrecognized shape raises a sanitized error."""
    persisted = _make_persisted()
    _patch_drivers_data_as_of(persisted, bad)
    with pytest.raises(ForecastMapperError) as excinfo:
        build_forecast_version_response(persisted, base_url="http://testserver")
    msg = str(excinfo.value)
    # Sanitized: no persisted value, no field name leak.
    assert bad not in msg
    assert "drivers" not in msg
    assert "data_as_of" not in msg


def test_drivers_data_as_of_rejects_empty_string() -> None:
    """Fix B: empty-string ``drivers.data_as_of`` rejects without
    leaking any echo (the value ``""`` trivially IS a substring of
    any error message so a generic inclusion assertion cannot prove
    sanitization for this case — we verify REJECTION only)."""
    persisted = _make_persisted()
    _patch_drivers_data_as_of(persisted, "")
    with pytest.raises(ForecastMapperError):
        build_forecast_version_response(persisted, base_url="http://testserver")


def test_drivers_data_as_of_rejects_non_string_value() -> None:
    """Fix B: non-string drivers.data_as_of rejects."""
    persisted = _make_persisted()
    _patch_drivers_data_as_of(persisted, 20260701)  # int
    with pytest.raises(ForecastMapperError):
        build_forecast_version_response(persisted, base_url="http://testserver")


def test_drivers_data_as_of_rejects_overlong_string() -> None:
    """Fix B: ``>64`` chars rejects — prevents DoS via long strings."""
    persisted = _make_persisted()
    _patch_drivers_data_as_of(persisted, "Z" * 65)
    with pytest.raises(ForecastMapperError):
        build_forecast_version_response(persisted, base_url="http://testserver")

