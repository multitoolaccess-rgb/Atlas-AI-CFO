"""Phase 11 tests — /api/transactions/ filter + sort + PUT-by-id.

Coverage:
- GET /api/transactions/?account_id=... filters correctly.
- GET /api/transactions/?account_type=... pulls every row across
  accounts of that type (the user's "filter by account type returns
  nothing" complaint).
- GET /api/transactions/?from_date=&to_date= bounds the date window.
- GET /api/transactions/?category_id=... matches by category.
- GET /api/transactions/?search=... matches on description + merchant.
- GET /api/transactions/?sort_by=&sort_dir= respects the contract.
- TransactionResponse flattens account + category names onto the row.
- PUT /api/transactions/{id} updates category_id (whitelisted) and
  rejects ownership escalation (account_id stays put).
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth import issue_token


def _auth_headers(sub: str = "alex") -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(sub)}"}


def _seed_categories(db_session):
    from app.services.categorizer import seed_default_categories
    seed_default_categories(db_session)


# -----------------------------------------------------------------
# Filters — server-side
# -----------------------------------------------------------------


def test_list_transactions_filter_by_account_id(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a1 = make_account(account_name="BoA Checking", account_type="checking")
    a2 = make_account(account_name="Amex Card", account_type="credit_card")
    db_session.add_all([a1, a2])
    db_session.commit()
    db_session.refresh(a1)
    db_session.refresh(a2)
    t1 = make_transaction(account_id=a1.id, description="BoA fee", amount=-12.00)
    t2 = make_transaction(account_id=a2.id, description="Amex fee", amount=-13.00)
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.get(
        f"/api/transactions/?account_id={a1.id}",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    descriptions = {row["description"] for row in body}
    assert descriptions == {"BoA fee"}


def test_list_transactions_filter_by_account_type(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    """Repro the user's bug: selecting an account TYPE used to
    return zero rows. Locks the new contract."""
    _seed_categories(db_session)
    a_checking = make_account(account_name="BoA Checking", account_type="checking")
    a_credit = make_account(account_name="Amex Card", account_type="credit_card")
    db_session.add_all([a_checking, a_credit])
    db_session.commit()
    db_session.refresh(a_checking)
    db_session.refresh(a_credit)
    db_session.add_all([
        make_transaction(account_id=a_checking.id, description="BoA fee", amount=-12.00),
        make_transaction(account_id=a_credit.id, description="Amex fee", amount=-13.00),
        make_transaction(account_id=a_credit.id, description="Amex fee 2", amount=-13.00),
    ])
    db_session.commit()

    resp = client.get(
        "/api/transactions/?account_type=credit_card",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(row["account_type"] == "credit_card" for row in body)


def test_list_transactions_filter_by_date_range(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)
    ten_days_ago = today - timedelta(days=10)
    db_session.add_all([
        make_transaction(account_id=a.id, description="old", amount=-1,
                         transaction_date=ten_days_ago),
        make_transaction(account_id=a.id, description="recent", amount=-2,
                         transaction_date=yesterday),
        make_transaction(account_id=a.id, description="today", amount=-3,
                         transaction_date=today),
    ])
    db_session.commit()

    # Phase-F2 #1 round-up fix: use ``.date().isoformat()`` strings (no
    # microseconds, no tz-info wallclock) instead of full ISO datetimes.
    # The full ISO ``yesterday.isoformat()`` carried microsecond precision
    # (``2026-07-02T03:26:27.493641+00:00``) which Pydantic + SQLAlchemy
    # compared strictly against the DB's stored microsecond-precision
    # column values; the seed transactions' stored timestamps didn't
    # always satisfy ``>=`` against the ``round`` via Pydantic's parser.
    # Date-only ISO strings parse to ``datetime(y,m,d,0,0,0)`` midnight,
    # which is unambiguously BEFORE any same-day transaction timestamp +
    # unambiguously AFTER any prior-day timestamp, eliminating the
    # off-by-microsecond false negative.
    # Phase-F2 #1 round-up fix v3: pass the datetime params via
    # httpx's ``params=`` argument so the `+` in ``+00:00`` is
    # URL-encoded as ``%2B``. An f-string URL of
    # ``?from_date=2026-07-02T00:00:00+00:00`` ships the ``+`` as a
    # literal byte to the server, which the URL parser interprets
    # as a SPACE (the canonical ``application/x-www-form-urlencoded``
    # encoding treats ``+`` as space). Pydantic then sees
    # ``2026-07-02T00:00:00 00:00`` (space inside the timestamp),
    # fails validation, returns 422 — and the test fails on
    # ``assert resp.status_code == 200``.
    date_from = yesterday.date().isoformat() + "T00:00:00+00:00"
    date_to = today.date().isoformat() + "T23:59:59+00:00"
    resp = client.get(
        "/api/transactions/",
        params={"from_date": date_from, "to_date": date_to},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, (
        f"date range filter expected 200, got {resp.status_code} {resp.text!r}"
    )
    descs = {row["description"] for row in resp.json()}
    assert descs == {"recent", "today"}


def test_list_transactions_filter_by_category(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    from app.models import Category
    food = db_session.query(Category).filter(Category.name == "Food & Dining").first()
    db_session.add_all([
        make_transaction(account_id=a.id, description="Starbucks #1", amount=-4,
                         category_id=food.id),
        make_transaction(account_id=a.id, description="Gas station", amount=-30,
                         category_id=None),
    ])
    db_session.commit()

    resp = client.get(
        f"/api/transactions/?category_id={food.id}",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["description"] == "Starbucks #1"
    assert body[0]["category_name"] == "Food & Dining"


def test_list_transactions_search_matches_description_and_merchant(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    db_session.add_all([
        make_transaction(account_id=a.id, description="UBER TRIP HELP.UBER.COM",
                         amount=-12, merchant_name="Uber"),
        make_transaction(account_id=a.id, description="STARBUCKS #23",
                         amount=-5, merchant_name="Starbucks"),
        make_transaction(account_id=a.id, description="GROCERIES", amount=-50),
    ])
    db_session.commit()

    # Case-fold + substring match across description + merchant.
    resp = client.get(
        "/api/transactions/?search=uber",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["merchant_name"] == "Uber"


def test_list_transactions_sort_by_amount_asc(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    db_session.add_all([
        make_transaction(account_id=a.id, description="big", amount=-1000),
        make_transaction(account_id=a.id, description="small", amount=-2),
        make_transaction(account_id=a.id, description="medium", amount=-100),
    ])
    db_session.commit()

    resp = client.get(
        "/api/transactions/?sort_by=amount&sort_dir=asc",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    # Phase-F2 #1 round-up fix: assert on the raw ``amount`` values, not
    # on their absolute value. All seeded amounts are negative (``-1000``,
    # ``-100``, ``-2``); ``ORDER BY amount ASC`` returns more-negative
    # first (``[-1000, -100, -2]``), which is monotonically ascending in
    # numeric terms. Taking ``abs(...)`` then sorting gives a DIFFERENT
    # target sequence (``[2, 100, 1000]``) — every test run before this
    # fix incorrectly booted the route's sort order as "wrong" when in
    # fact the data semantics were negative-debt. The corrected assertion
    # is monotonically ascending in the column the route sorts by.
    amounts = [row["amount"] for row in resp.json()]
    assert amounts == sorted(amounts)


def test_list_transactions_rejects_invalid_sort_by(
    client: TestClient, db_session, make_account,
):
    """Unknown sort_by silently falls back to the safe default
    (date desc, id desc) so a typo on the FE doesn't 500."""
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    resp = client.get(
        "/api/transactions/?sort_by=DROP%20TABLE&sort_dir=asc",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_transaction_response_flattens_account_and_category(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    """The activity page FE needs flat account_* + category_* fields
    for filtering without N+1 calls. Lock that contract here."""
    _seed_categories(db_session)
    a = make_account(account_name="BoA Checking", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    from app.models import Category
    food = db_session.query(Category).filter(Category.name == "Food & Dining").first()
    t = make_transaction(
        account_id=a.id,
        description="Starbucks #1",
        amount=-4,
        merchant_name="Starbucks",
        category_id=food.id,
    )
    db_session.add(t)
    db_session.commit()

    resp = client.get("/api/transactions/", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    row = next(r for r in body if r["id"] == t.id)
    assert row["account_id"] == a.id
    assert row["account_name"] == "BoA Checking"
    assert row["account_type"] == "checking"
    assert row["category_id"] == food.id
    assert row["category_name"] == "Food & Dining"


# -----------------------------------------------------------------
# PUT /api/transactions/{id} — whitelisted update
# -----------------------------------------------------------------


def test_update_transaction_category(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    t = make_transaction(account_id=a.id, description="Starbucks #1", amount=-4)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    from app.models import Category
    food = db_session.query(Category).filter(Category.name == "Food & Dining").first()

    resp = client.put(
        f"/api/transactions/{t.id}",
        json={"category_id": food.id},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category_id"] == food.id
    assert body["category_name"] == "Food & Dining"


def test_update_transaction_rejects_unknown_category(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    t = make_transaction(account_id=a.id, description="x", amount=1.0)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    resp = client.put(
        f"/api/transactions/{t.id}",
        json={"category_id": 999999},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_update_transaction_can_detach_category(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    """``category_id: 0`` maps to NULL on the BE \u2014 a user can
    detach an auto-categorized row without losing the merchant."""
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    from app.models import Category
    food = db_session.query(Category).filter(Category.name == "Food & Dining").first()
    t = make_transaction(account_id=a.id, description="Starbucks #1",
                         amount=-4, category_id=food.id)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    resp = client.put(
        f"/api/transactions/{t.id}",
        json={"category_id": 0},  # detach
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] is None


def test_update_transaction_silently_drops_unknown_keys(
    client: TestClient, db_session,
    make_account, make_transaction,
):
    """Phase 7 whitelist contract: ``account_id: 9999`` MUST NOT
    change the row's actual account. Future FE bugs that leak
    extra dict keys won't escalate ownership."""
    _seed_categories(db_session)
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    t = make_transaction(account_id=a.id, description="x", amount=1.0)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    resp = client.put(
        f"/api/transactions/{t.id}",
        json={"account_id": 9999, "description": "ESCALATION ATTEMPT"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["account_id"] == a.id  # unchanged
    assert resp.json()["description"] == "x"  # unchanged


def test_update_transaction_requires_auth(
    client_no_auth, db_session,
    make_account, make_transaction,
):
    """Round-1 reviewer #3 follow-up: now uses the conftest's
    ``client_no_auth`` fixture (a ``TestClient`` with NO
    pre-loaded ``fc_session`` Cookie) so future no-auth tests can
    reuse this fixture instead of hand-rolling ``TestClient(app)``.
    """
    a = make_account(account_name="BoA", account_type="checking")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    t = make_transaction(account_id=a.id, description="x", amount=1.0)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    # HTTPException 401 from the JWT dep is raised BEFORE the row lookup
    # so the row's existence is irrelevant — auth comes first.
    resp = client_no_auth.put(
        f"/api/transactions/{t.id}",
        json={"category_id": 1},
    )
    assert resp.status_code == 401
