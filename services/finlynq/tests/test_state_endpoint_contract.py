"""Phase-F5 contract — GET /state/* returns the real aggregator OR a
locked 501 stub.

Locked post-F5 shape (``StateOut`` + ``StateSummaryOut`` in
``app/routes/state.py``):

GET /state          -> 501 (Phase F6; composite listing)
GET /state/summary  -> 200 with canonical 9-field shape (Phase F5)
                       401 without a valid JWT cookie

``StateSummaryOut`` keys (Phase-F5 ship target):

- total_balance, total_income_month, total_expenses_month
- accounts_count, transactions_count
- last_sync, import_batches_count, last_import_at
- user_goals (list)

Reviewer hardening: each ``Optional[...]`` field MUST keep its
``Optional`` annotation AND a ``= None`` default — see
``test_round6_widened_fields_have_optional_typing_and_none_default``
below.
"""
from typing import Union, get_args, get_origin

from fastapi.testclient import TestClient
from pydantic_core import PydanticUndefined

from app.main import app
from app.routes.state import StateOut, StateSummaryOut
from app.schemas import AccountSummary, GoalSummary, TransactionSummary


# ---- /state — still a 501 stub (Phase-F6 deliverable) --------------------


def test_state_returns_401_without_auth(client):
    """Phase F6 — /state now requires auth (no longer a 501 stub)."""
    response = client.get("/state")
    assert response.status_code == 401, (
        f"GET /state without JWT must return 401 (got {response.status_code}). "
        f"Phase F6 replaced the 501 stub with a real aggregator + auth gate."
    )


def test_state_returns_200_with_auth_and_shape(client_with_auth):
    """Phase F6 — /state returns the full composite state."""
    response = client_with_auth.get("/state")
    assert response.status_code == 200, (
        f"GET /state with JWT must return 200 (got "
        f"{response.status_code} {response.text!r})."
    )
    body = response.json()
    # StateOut extends StateSummaryOut with accounts[] and transactions[]
    expected_keys = {
        "total_balance",
        "total_income_month",
        "total_expenses_month",
        "accounts_count",
        "transactions_count",
        "last_sync",
        "import_batches_count",
        "last_import_at",
        "user_goals",
        "accounts",
        "transactions",
    }
    actual_keys = set(body.keys())
    assert actual_keys == expected_keys, (
        f"GET /state response shape drifted. "
        f"missing={expected_keys - actual_keys}, extra={actual_keys - expected_keys}. "
        f"Phase F6 locked the shape: StateOut = StateSummaryOut + accounts[] + transactions[]."
    )
    assert isinstance(body["accounts"], list), (
        f"accounts must be a list, got {type(body['accounts'])}"
    )
    assert isinstance(body["transactions"], list), (
        f"transactions must be a list, got {type(body['transactions'])}"
    )
    assert isinstance(body["user_goals"], list), (
        f"user_goals must be a list, got {type(body['user_goals'])}"
    )


# ---- /state/summary — Phase-F5 real aggregator ---------------------------


def test_state_summary_auth_and_schema(client_with_auth):
    """Phase-F5 ship test:

    1. Unauthenticated request -> 401 (Depends(require_user) rejects).
    2. Authenticated request -> 200 with the canonical 9-field shape.

    Cross-service invariant: rules-service's
    ``/api/dashboard/summary`` forwarder coerces this exact shape via
    ``DashboardSummary(**r.json())`` -- the F5 wire-parity contract.

    Uses ``client_with_auth`` (which carries a valid ``fc_session``
    cookie for ``Depends(require_user)``); the ``client`` fixture in
    this conftest is NO-COOKIE -- it would 401 even with the F5 ship
    target verified-correct.
    """
    no_auth = TestClient(app)
    no_auth_resp = no_auth.get("/state/summary")
    assert no_auth_resp.status_code == 401, (
        f"GET /state/summary without JWT must return 401 (got "
        f"{no_auth_resp.status_code} {no_auth_resp.text!r}). F5 added "
        f"Depends(require_user) precisely to lock 401-on-no-cookie."
    )

    response = client_with_auth.get("/state/summary")
    assert response.status_code == 200, (
        f"GET /state/summary with JWT must return 200 (got "
        f"{response.status_code} {response.text!r})."
    )
    body = response.json()
    expected_keys = {
        "total_balance",
        "total_income_month",
        "total_expenses_month",
        "accounts_count",
        "transactions_count",
        "last_sync",
        "import_batches_count",
        "last_import_at",
        "user_goals",
    }
    actual_keys = set(body.keys())
    assert actual_keys == expected_keys, (
        f"/state/summary response shape drifted. "
        f"missing={expected_keys - actual_keys}, extra={actual_keys - expected_keys}. "
        f"F5 LOCKED the shape: any drift here breaks rules-service's "
        f"/api/dashboard/summary DashboardSummary(**r.json()) coercion."
    )


# ---- Shape locks (unchanged by F5; pin schema state across phases) ------


def test_state_out_shape_is_locked():
    """Pin the StateOut Pydantic shape Phase F6 must respect."""
    expected = {
        "total_balance",
        "total_income_month",
        "total_expenses_month",
        "accounts_count",
        "transactions_count",
        "last_sync",
        "import_batches_count",
        "last_import_at",
        "user_goals",
        "accounts",
        "transactions",
    }
    actual = set(StateOut.model_fields.keys())
    assert actual == expected, (
        f"StateOut drifted. missing={expected - actual}, extra={actual - expected}"
    )


def test_state_summary_shape_matches_dashboard_summary():
    """``StateSummaryOut`` must match ``DashboardSummary`` shape that
    rules-service returns (via the F5 forwarder); this is the cross-service
    invariant F5 is committed to.

    The F5 contract: rules-service's ``/api/dashboard/summary`` routes
    through Finlynq's ``/state/summary`` and coerces the response via
    ``DashboardSummary(**r.json())`` -- field-set equality between
    ``StateSummaryOut`` and ``DashboardSummary`` is the load-bearing
    invariant for that path.

    **Cross-service import is INTENTIONALLY avoided.** The
    expected field set below is locked against
    ``services/rules-service/app/schemas/__init__.py::DashboardSummary``
    (authoritative spec lives on the rules-service side). Updating
    one side without the other must trip this test.
    """
    expected = {
        "total_balance",
        "total_income_month",
        "total_expenses_month",
        "accounts_count",
        "transactions_count",
        "last_sync",
        "import_batches_count",
        "last_import_at",
        "user_goals",
    }
    actual = set(StateSummaryOut.model_fields.keys())
    assert actual == expected, (
        f"StateSummaryOut drifted from DashboardSummary. "
        f"missing={expected - actual}, extra={actual - expected}. F5 must "
        f"emit the EXACT same fields rules-service emits today so the "
        f"/api/dashboard/summary forwarder is mechanical."
    )


def _assert_is_optional_type(annotation):
    """``Optional[X]`` collapses to ``Union[X, None]`` under ``typing``."""
    return get_origin(annotation) is Union and type(None) in get_args(annotation)


# Round-6 reviewer hardening: the deny-list of known PII-shaped column
# names that the Finlynq canonical store must NEVER carry on the wire.
# Update this list (and the rationale in app/schemas/__init__.py) to
# add new columns; the load-bearing test below iterates this constant.
_KNOWN_PII_DENY_LIST = frozenset(
    {
        # PII-shaped financial identifiers. Add new ones here as the
        # privacy policy evolves.
        "account_number",
        "routing_number",
        "iban",
        "ssn",
        "ssn_last_4",
        "tax_id",
    }
)


def test_round6_widened_fields_have_optional_typing_and_none_default():
    """Pin (annotation, default) for the 13 round-3 widened fields.

    Round-6 reviewer hardening (incorporating the round-4 model's
    ``model_construct`` drop + round-5 default-check tightening):

    1. Annotation must be ``Optional[...]``. Pydantic v2 raises
       ``ValidationError`` at wire-serialization time for a NULL row
       on a non-Optional field.

    2. Default must be exactly ``None`` - not ``PydanticUndefined``.
    """
    optional_pairs = [
        (AccountSummary, "account_subtype"),
        (AccountSummary, "last_sync"),
        (TransactionSummary, "merchant_name"),
        (TransactionSummary, "account_id"),
        (TransactionSummary, "account_name"),
        (TransactionSummary, "account_type"),
        (TransactionSummary, "category_id"),
        (TransactionSummary, "category_name"),
        (GoalSummary, "target_date"),
        (GoalSummary, "horizon_years"),
        (GoalSummary, "notes"),
        (GoalSummary, "created_at"),
        (GoalSummary, "updated_at"),
    ]
    for cls, field in optional_pairs:
        field_info = cls.model_fields[field]
        annotation = field_info.annotation
        default = field_info.default

        # (1) Optional[X] annotation.
        assert _assert_is_optional_type(annotation), (
            f"{cls.__name__}.{field} annotation must be Optional[...] "
            f"(got {annotation!r}). Tightening this to non-Optional would "
            f"500 wire serialization for any SQLAlchemy row with NULL in "
            f"this column -- a regression F5 can't catch without this guard."
        )

        # (2) Default is None EXACTLY.
        assert default is None, (
            f"{cls.__name__}.{field} default must be None exactly "
            f"(got {default!r})."
        )


def test_account_summary_emits_no_known_pii_columns():
    """Round-6 reviewer hardening -- broader PII deny-list."""
    leaked = _KNOWN_PII_DENY_LIST & set(AccountSummary.model_fields.keys())
    assert not leaked, (
        f"AccountSummary must NOT carry any known-PII column from "
        f"{sorted(_KNOWN_PII_DENY_LIST)!r}; leaked: {sorted(leaked)!r}. "
        f"See ``_KNOWN_PII_DENY_LIST`` in tests/test_state_endpoint_contract.py "
        f"and ``app/schemas/__init__.py`` module docstring for the rationale."
    )
