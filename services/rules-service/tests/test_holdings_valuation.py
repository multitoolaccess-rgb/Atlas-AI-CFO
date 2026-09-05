"""Tests for ``GET /api/holdings/summary`` — the server-owned portfolio
valuation projection (GAP-12 closure).

The endpoint is the authoritative source for portfolio totals,
allocation percentages, and gain percentages; the browser formats the
projection and performs no portfolio arithmetic. These tests pin:

- authentication (401 without a session),
- the empty-portfolio contract (zeros, empty lists, computed_at),
- stored-value consistency with ``GET /api/holdings/`` (``current_value``;
  live quotes are ephemeral refresh responses and never persisted),
- per-account / per-holding / per-type rollups with allocation %,
- gain % semantics (``None`` — never invented zeros — when cost basis
  is absent or zero; absolute-denominator handling for short basis),
- zero-grand-total behavior (allocation % ``None``, not 0),
- owner isolation (another user's holdings never leak into the
  projection).
"""
import pytest


def _create_holding(db_session, account, **kwargs) -> None:
    from app.models import Holding

    # ``make_account`` returns a transient Account (not yet added), and
    # the test session runs with autoflush disabled, so attach + flush to
    # materialize the account id before the Holding's NOT NULL FK is
    # written.
    db_session.add(account)
    db_session.flush()
    db_session.add(Holding(account_id=account.id, **kwargs))
    db_session.commit()


def test_valuation_summary_requires_auth(client_no_auth):
    resp = client_no_auth.get("/api/holdings/summary")
    assert resp.status_code == 401


def test_valuation_summary_empty_portfolio_returns_zeroed_contract(client, db_session):
    resp = client.get("/api/holdings/summary")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "portfolio-valuation/v1"
    assert payload["grand_total"] == 0.0
    assert payload["currency"] == "USD"
    assert payload["accounts"] == []
    assert payload["holdings"] == []
    assert payload["types"] == []
    assert payload["computed_at"]  # non-empty ISO timestamp


def test_valuation_summary_computes_totals_allocation_and_gain(client, db_session, make_account):
    acct = make_account(account_name="Brokerage", account_type="investment")
    _create_holding(
        db_session,
        acct,
        symbol="AAPL",
        description="Apple Inc.",
        quantity=10,
        last_price=200.0,
        current_value=1900.0,
        cost_basis_total=1500.0,
        type="Stock",
    )
    _create_holding(
        db_session,
        acct,
        symbol="VTI",
        description="Vanguard Total Stock Market ETF",
        quantity=5,
        last_price=220.0,
        current_value=1000.0,
        cost_basis_total=None,
        type="ETF",
    )
    _create_holding(
        db_session,
        acct,
        symbol="CASH",
        description="Cash",
        quantity=None,
        last_price=None,
        current_value=100.0,
        cost_basis_total=None,
        type="Cash",
    )

    resp = client.get("/api/holdings/summary")
    assert resp.status_code == 200
    payload = resp.json()

    # Value precedence: current_value is used when live_value is absent.
    assert payload["grand_total"] == pytest.approx(3000.0, abs=1e-6)
    assert len(payload["accounts"]) == 1
    acct_row = payload["accounts"][0]
    assert acct_row["account_name"] == "Brokerage"
    assert acct_row["account_type"] == "investment"
    assert acct_row["total"] == pytest.approx(3000.0, abs=1e-6)
    assert acct_row["positions_count"] == 3
    assert acct_row["allocation_pct"] == pytest.approx(100.0, abs=1e-6)

    by_symbol = {h["symbol"]: h for h in payload["holdings"]}
    assert by_symbol["AAPL"]["value"] == pytest.approx(1900.0, abs=1e-6)
    assert by_symbol["AAPL"]["allocation_pct"] == pytest.approx(63.3333, abs=1e-3)
    assert by_symbol["AAPL"]["gain_pct"] == pytest.approx(26.6667, abs=1e-3)
    # No cost basis → gain is None, never an invented 0.
    assert by_symbol["VTI"]["gain_pct"] is None
    assert by_symbol["VTI"]["allocation_pct"] == pytest.approx(33.3333, abs=1e-3)
    assert by_symbol["CASH"]["allocation_pct"] == pytest.approx(3.3333, abs=1e-3)

    types = {t["type"]: t for t in payload["types"]}
    assert set(types) == {"Stock", "ETF", "Cash"}
    assert types["Stock"]["total"] == pytest.approx(1900.0, abs=1e-6)
    assert types["Stock"]["allocation_pct"] == pytest.approx(63.3333, abs=1e-3)
    # Rollups are sorted by total descending.
    assert [t["type"] for t in payload["types"]] == ["Stock", "ETF", "Cash"]


def test_valuation_summary_matches_list_endpoint_stored_values(client, db_session, make_account):
    """The projection is built from the same stored rows the list
    endpoint serves — the authoritative persisted valuation, not the
    ephemeral live-quote refresh response."""
    acct = make_account(account_name="Brokerage", account_type="investment")
    _create_holding(
        db_session,
        acct,
        symbol="MU",
        quantity=4,
        last_price=975.41,
        current_value=3901.64,
        cost_basis_total=1598.0,
        type="Stock",
    )
    listed = client.get("/api/holdings/").json()
    assert listed[0]["current_value"] == pytest.approx(3901.64, abs=1e-6)
    payload = client.get("/api/holdings/summary").json()
    assert payload["grand_total"] == pytest.approx(3901.64, abs=1e-6)
    assert payload["holdings"][0]["value"] == pytest.approx(3901.64, abs=1e-6)
    assert payload["holdings"][0]["gain_pct"] == pytest.approx(
        ((3901.64 - 1598.0) / 1598.0) * 100.0, abs=1e-6
    )


def test_valuation_summary_zero_cost_basis_and_zero_grand_total_are_null(client, db_session, make_account):
    acct = make_account(account_name="Zeroes", account_type="investment")
    _create_holding(
        db_session,
        acct,
        symbol="ZERO",
        current_value=0.0,
        cost_basis_total=0.0,
        type="Cash",
    )
    payload = client.get("/api/holdings/summary").json()
    assert payload["grand_total"] == 0.0
    assert payload["holdings"][0]["gain_pct"] is None  # zero basis → None
    assert payload["holdings"][0]["allocation_pct"] is None  # zero total → None
    assert payload["accounts"][0]["allocation_pct"] is None
    assert payload["types"][0]["allocation_pct"] is None


def test_valuation_summary_negative_cost_basis_uses_abs_denominator(client, db_session, make_account):
    acct = make_account(account_name="Short", account_type="investment")
    _create_holding(
        db_session,
        acct,
        symbol="SHRT",
        current_value=500.0,
        cost_basis_total=-400.0,
        type="Stock",
    )
    payload = client.get("/api/holdings/summary").json()
    # (500 - (-400)) / abs(-400) → +225% — matches the pre-projection
    # client math so the projection is a pure relocation of authority.
    assert payload["holdings"][0]["gain_pct"] == pytest.approx(225.0, abs=1e-6)


def test_valuation_summary_owner_isolation(client, db_session, make_account):
    """Another owner's holdings must never appear in the projection."""
    from app.models import Account, Holding, User
    from app.routes.shared import get_or_create_institution

    mine = make_account(account_name="Mine", account_type="investment")
    _create_holding(db_session, mine, symbol="AAPL", current_value=100.0, type="Stock")

    other_user = User(
        local_user_sub="other-owner",
        email="other@example.com",
        hashed_password="x",
    )
    db_session.add(other_user)
    db_session.commit()
    institution = get_or_create_institution(db_session, "Other Bank")
    from app.routes.shared import get_or_create_family_member_self

    other_member = get_or_create_family_member_self(db_session, other_user)
    other_acct = Account(
        user_id=other_user.id,
        institution_id=institution.id,
        account_name="Theirs",
        account_type="investment",
        current_balance=0.0,
        family_member_id=other_member.id,
    )
    db_session.add(other_acct)
    db_session.commit()
    db_session.add(
        Holding(
            account_id=other_acct.id,
            symbol="TSLA",
            current_value=99999.0,
            type="Stock",
        )
    )
    db_session.commit()

    payload = client.get("/api/holdings/summary").json()
    assert payload["grand_total"] == pytest.approx(100.0, abs=1e-6)
    assert [h["symbol"] for h in payload["holdings"]] == ["AAPL"]