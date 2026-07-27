"""Phase 18 — categorizer v2 tests.

Three-pass behavior + alias learning + thefuzz safety net:

- Pass 1 (alias lookup): an existing ``merchant_aliases`` row for the
  user short-circuits the rest.
- Pass 2 (substring rules): unchanged from Phase 11 + auto-leans an
  alias on every successful match.
- Pass 3 (thefuzz fuzzy): catches typos / OCR noise above score=85;
  excludes Transfer / Income / Other from the candidate list.

These tests run against a hermetic DB created via the project's
``conftest.py`` ``client`` fixture (auth + DB session wired to the
test app). The ``seeded_db`` fixture below wraps the per-test reset
+ a call to ``seed_default_categories`` so the 12 default categories
exist when the categorizer runs.
"""
import pytest

from app.models import Category, MerchantAlias, Transaction
from app.services.categorizer import (
    _FLAT_FUZZY_KEYWORDS,
    _FUZZY_SCORE_CUTOFF,
    categorize_transactions,
    fuzzy_keywords_size,
    learn_alias_for_category,
    normalize_alias_key,
    seed_default_categories,
    seed_default_merchant_rules,  # Phase 24 — DB-backed substring rules.
)


# Phase 18 — tests that call categorize_transactions with real Transaction
# rows + a real local user (and expect a populated Category tree on the
# Pass-2 substring lookup) need the 12 default categories seeded BEFORE the
# test runs. ``_reset_test_db()`` flushes everything per-test, so the
# seed runs INSIDE the test body via this fixture (it can't move into
# the session-scope fixture because pre-Phase-18 tests assume a
# freshly-flushed ``categories`` table).
@pytest.fixture
def seeded_db(client, db_session):
    """Yield a db_session AFTER seeding the 12 default categories.

    Fixture-order lock: depends on ``client`` so pytest resolves the
    fixtures in dependency order. The ``client`` fixture flushes via
    ``_reset_test_db()`` BEFORE our seed runs — the seed is what
    populates the categories table on a freshly-flushed DB. Without
    depending on ``client``, pytest runs ``seeded_db`` first (seeded
    categories) then ``client`` (which DELETEs them), leaving the
    test body with an empty categories table — the categorizer
    functions fail with ``other_cat is None``.

    Tests should reference BOTH ``client`` AND ``seeded_db`` so pytest
    can resolve the dep graph. Both share the same underlying
    ``db_session`` (pytest caches fixtures within a test), so the
    seed survives the client's reset.
    """
    # Phase 24 — reads rules from the merchant_rules DB table so
    # the runtime categorizer's Pass 2 + Pass 3 candidates are
    # populated. ``seed_default_merchant_rules`` internally calls
    # ``seed_default_categories`` first (the FK chain), so the
    # explicit categories seed that used to live here is now
    # implicit and removable.
    seed_default_merchant_rules(db_session)
    return db_session


# --------------------------------------------------------------
# Alias-key normalization contract (locked — single source of truth).
# --------------------------------------------------------------
@pytest.mark.parametrize(
    "merchant,description,expected",
    [
        ("Starbucks", "Latte and bagel", "STARBUCKS LATTE AND BAGEL"),
        ("Blue Bottle", "Coffee #1234", "BLUE BOTTLE COFFEE 1234"),
        ("DOORDASH*", "MCDONALD'S #5678", "DOORDASH MCDONALD S 5678"),
        (None, "Imported transaction", "IMPORTED TRANSACTION"),
        ("", "", ""),
        (None, None, ""),
        ("Blue\tBottle", "Coffee\n#1234", "BLUE BOTTLE COFFEE 1234"),
        ("SQ *12345", "Coffee", "SQ 12345 COFFEE"),
    ],
)
def test_normalize_alias_key_contract(merchant, description, expected):
    """The alias_key normalization contract. Locked: any future
    contract change breaks Pass-1 SELECT matches silently. Do not
    refactor without updating ALL three sites (writer +
    reader + this test)."""
    assert normalize_alias_key(merchant, description) == expected


# --------------------------------------------------------------
# Fuzzy layer — coverage + exclusion guard.
# --------------------------------------------------------------
def test_fuzzy_keywords_excludes_dangerous_categories():
    """The fuzzy candidate list MUST exclude Transfer / Income / Other.
    Otherwise typos that fuzzy-match (e.g. 'TRANSFER' → 'TRANSIT',
    'PAYROLL' → 'PAYPAL') would silently invent wrong categorisations."""
    excluded = {"Transfer", "Base Salary", "Other"}
    present_names = {cat_name for _kw, cat_name in _FLAT_FUZZY_KEYWORDS}
    assert excluded.isdisjoint(present_names), (
        f"Fuzzy candidate list still contains excluded categories: "
        f"{excluded & present_names}"
    )


def test_fuzzy_keywords_size_lock():
    """Locks the expansion to ≥ 100 keywords so a future refactor that
    drops (or never adds) the banker expansion trips this test
    instead of silently regressing coverage."""
    assert fuzzy_keywords_size() >= 100, (
        f"Expected ≥ 100 fuzzy keywords after Phase 18 expansion; "
        f"got {fuzzy_keywords_size()}"
    )


def test_fuzzy_cutoff_is_85():
    """Cutoff must be 85 (verified empirically — 70 had ~12% false
    positives on bank transactions)."""
    assert _FUZZY_SCORE_CUTOFF == 85


# --------------------------------------------------------------
# Pass 1 — alias short-circuits substring + fuzzy.
# --------------------------------------------------------------
def test_pass1_alias_hit_short_circuits_substring_and_fuzzy(
    client, seeded_db,
):
    """Pre-seeded merchant_alias row wins over substring Pass 2.

    Setup: inject ``FOODIE EXPRESS → Other`` alias. Pass a
    ``FOODIE EXPRESS`` transaction. Verify the alias hits, NOT
    String's substring layer. Also verify ``use_count`` bumped.
    """
    client.post("/api/auth/devlogin")

    from app.config import settings
    from app.routes.shared import get_or_create_local_user

    local_user = get_or_create_local_user(seeded_db, settings.local_user)
    other_cat = seeded_db.query(Category).filter_by(name="Other").first()
    assert other_cat is not None

    # Phase 18 — the (merchant + description) string fed to the
    # categorizer IS normalised by ``normalize_alias_key`` (uppercase,
    # letters/digits only, spaces only). The DB row must use the
    # SAME normalised form or alias Pass-1 misses silently.
    aliased_key = normalize_alias_key(
        "FOODIE EXPRESS", "FOODIE EXPRESS raw text",
    )
    seeded_db.add(
        MerchantAlias(
            user_id=local_user.id,
            category_id=other_cat.id,
            alias_key=aliased_key,
            source_text="FOODIE EXPRESS raw text",
            use_count=1,
        )
    )
    seeded_db.commit()

    account_resp = client.post(
        "/api/accounts/",
        json={
            "account_name": "Categorizer v2 test",
            "account_type": "checking",
            "institution_name": "Test Bank",
            "current_balance": 0.0,
        },
    )
    # POST creates return 201 (FastAPI default + project convention
    # across accounts / family-members / goals routes; see
    # ``test_routes_accounts.py::test_create_account_returns_201_*``).
    # Accept 200 OR 201 so a future project-wide flip to ``200`` doesn't
    # break this test in lockstep.
    assert account_resp.status_code in (200, 201), account_resp.text
    account_id = account_resp.json()["id"]

    from datetime import datetime, timezone
    fillin_txn = Transaction(
        account_id=account_id,
        description="FOODIE EXPRESS raw text",
        merchant_name="FOODIE EXPRESS",
        amount=-12.34,
        transaction_date=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    seeded_db.add(fillin_txn)
    seeded_db.commit()
    seeded_db.refresh(fillin_txn)

    pre_alias_use = (
        seeded_db.query(MerchantAlias)
        .filter_by(user_id=local_user.id, alias_key=aliased_key)
        .one()
        .use_count
    )

    categorized, skipped, _conflicts = categorize_transactions(seeded_db, [fillin_txn])
    seeded_db.commit()
    seeded_db.refresh(fillin_txn)

    assert categorized == 1, f"Expected 1 categorized, got {categorized}"
    assert skipped == 0
    assert fillin_txn.category_id == other_cat.id

    post_alias_use = (
        seeded_db.query(MerchantAlias)
        .filter_by(user_id=local_user.id, alias_key=aliased_key)
        .one()
        .use_count
    )
    assert post_alias_use == pre_alias_use + 1, (
        f"use_count should increment from {pre_alias_use} to "
        f"{pre_alias_use + 1}; got {post_alias_use}"
    )


# --------------------------------------------------------------
# Pass 2 — substring success writes alias for future Pass-1 hits.
# --------------------------------------------------------------
def test_pass2_substring_hit_writes_alias_for_next_pass(
    client, seeded_db,
):
    """First call substring-matches → no alias before → alias written.
    Second call (same text) hits alias → use_count++ (no second row)."""
    client.post("/api/auth/devlogin")

    account_resp = client.post(
        "/api/accounts/",
        json={
            "account_name": "Categorizer alias-learn test",
            "account_type": "checking",
            "institution_name": "Test Bank Learn",
            "current_balance": 0.0,
        },
    )
    # POST creates return 201 (FastAPI default + project convention
    # across accounts / family-members / goals routes; see
    # ``test_routes_accounts.py::test_create_account_returns_201_*``).
    # Accept 200 OR 201 so a future project-wide flip to ``200`` doesn't
    # break this test in lockstep.
    assert account_resp.status_code in (200, 201), account_resp.text
    account_id = account_resp.json()["id"]

    vendor_text = "ZZTEST-CAFE-MOCK-12345"
    from datetime import datetime, timezone
    fillin_txn = Transaction(
        account_id=account_id,
        description=vendor_text + " walkup order",
        merchant_name=vendor_text,
        amount=-8.88,
        transaction_date=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    seeded_db.add(fillin_txn)
    seeded_db.commit()
    seeded_db.refresh(fillin_txn)

    from app.config import settings
    from app.routes.shared import get_or_create_local_user

    local_user = get_or_create_local_user(seeded_db, settings.local_user)

    # Same normalised key for both seed query + post-categorize assertion.
    expected_alias_key = normalize_alias_key(
        vendor_text, vendor_text + " walkup order",
    )
    pre_count = (
        seeded_db.query(MerchantAlias)
        .filter_by(user_id=local_user.id, alias_key=expected_alias_key)
        .count()
    )
    assert pre_count == 0

    categorized, skipped, _conflicts = categorize_transactions(seeded_db, [fillin_txn])
    seeded_db.commit()

    assert categorized == 1
    food_cat = seeded_db.query(Category).filter_by(name="Food & Dining").first()
    assert fillin_txn.category_id == food_cat.id

    alias_row = (
        seeded_db.query(MerchantAlias)
        .filter_by(user_id=local_user.id, alias_key=expected_alias_key)
        .one()
    )
    assert alias_row.category_id == food_cat.id
    assert alias_row.use_count == 1

    categorized_2, skipped_2, _conflicts_2 = categorize_transactions(seeded_db, [fillin_txn])
    seeded_db.commit()
    seeded_db.refresh(alias_row)
    assert categorized_2 == 0  # already tagged
    assert alias_row.use_count == 2


# --------------------------------------------------------------
# Pass 2 — user-issuer substrings (Phase 21).
# --------------------------------------------------------------
def test_pass2_substring_matches_user_issuer_descriptions(
    client, seeded_db,
):
    """Phase 21 — explicit substring rules for common-issuer bank
    strings the user observed un-categorized on /activity:

    - FID BPG SVC (Fidelity Brokerage wire) -> Transfer
    - WASTE MANAGEMENT (utility payment) -> Bills & Utilities
    - AT&T SERVICES DES:PYMT (phone-bill, no PAYROLL substring)
                                          -> Bills & Utilities
    - AT&T SERVICES DES:PAYROLL (payroll deposit)
                                          -> Base Salary

    The last one is the canary: Python dict iteration order keeps
    ``Base Salary`` BEFORE ``Bills & Utilities`` in ``MERCHANT_RULES``, so
    the ``"PAYROLL"`` substring in the Base Salary list short-circuits
    before the ``"AT&T SERVICES"`` substring in the Bills list is
    evaluated. A future alphabetization of the top-level category
    keys would silently flip the categorization for ANY payroll that
    happens to share wording with a Bill keyword — this assertion
    catches the regression loudly.
    """
    client.post("/api/auth/devlogin")

    from app.services.categorizer import suggest_category_for

    lookup = {
        name: seeded_db.query(Category).filter_by(name=name).first()
        for name in ("Transfer", "Bills & Utilities", "Base Salary", "Other")
    }
    assert all(v is not None for v in lookup.values()), (
        "Default category seed didn't run; missing one of "
        "[Transfer, Bills & Utilities, Base Salary, Other]."
    )

    # 1) Fidelity Brokerage wire -> Transfer.
    cat = suggest_category_for(
        None,
        "FID BPG SVC LLC LES-MONEYLINE ID:21934876/1HITLIU "
        "INDN:VLIJAY UPPALA CO ID:9368064600 PPD",
        lookup,
    )
    assert cat is not None and cat.name == "Transfer", (
        f"Expected Transfer for FID BPG SVC wire, got {cat!r}"
    )

    # 2) WASTE MANAGEMENT utility payment -> Bills & Utilities.
    cat = suggest_category_for(
        None,
        "WASTE MANAGEMENT DES:PAYMENT ID:0502022791S3D01 "
        "INDN:VLIJAY UPPALA CO ID:958906300T PPD",
        lookup,
    )
    assert cat is not None and cat.name == "Bills & Utilities", (
        f"Expected Bills & Utilities for WASTE MANAGEMENT, got {cat!r}"
    )

    # 3a) AT&T SERVICES phone-bill (no PAYROLL substring).
    #    Falls through to Bills & Utilities -> "AT&T SERVICES".
    cat = suggest_category_for(
        None,
        "AT&T SERVICES DES:PYMT ID:12345 ATTBILL PAYMENT",
        lookup,
    )
    assert cat is not None and cat.name == "Bills & Utilities", (
        f"Expected Bills & Utilities for AT&T phone bill, got {cat!r}"
    )

    # 3b) AT&T SERVICES payroll deposit -> Base Salary (NOT Bills).
    #     Locks dict-iteration-order priority of "PAYROLL" substring.
    cat = suggest_category_for(
        None,
        "AT&T SERVICES DES:PAYROLL ID:260521VU1021 "
        "INDN:VLIJAY UPPALA CO ID:5742782655 PPD",
        lookup,
    )
    assert cat is not None and cat.name == "Base Salary", (
        f"Expected Base Salary (PAYROLL substring short-circuits via "
        f"MERCHANT_RULES insertion order BEFORE Bills & Utilities), "
        f"got {cat!r}. Either Base Salary was alphabetized below Bills or "
        f"the 'PAYROLL' keyword in Base Salary's list was removed."
    )


# --------------------------------------------------------------
# Pass 3 — fuzzy catches typos that substring misses.
# --------------------------------------------------------------
def test_pass3_fuzzy_matches_ocr_noise_substring_misses(
    client, seeded_db,
):
    """The classic Phase 18 case: ``AMAZ0N PRIME`` (zero-for-O typo) is
    bypassed by Pass 2 substring (no rule contains ``AMAZ0N``) but
    thefuzz Pass 3 scores ≥85 against ``AMAZON`` → Shopping.

    NOTE: ``BLUE BOTL COFFE`` would NOT exercise Pass 3 — substring
    Pass 2 matches it via ``BLUE BOTL`` (a deliberately-listed
    near-spelling in MERCHANT_RULES).
    """
    client.post("/api/auth/devlogin")

    account_resp = client.post(
        "/api/accounts/",
        json={
            "account_name": "Categorizer fuzzy test",
            "account_type": "checking",
            "institution_name": "Fuzzy Test Bank",
            "current_balance": 0.0,
        },
    )
    # POST creates return 201 (FastAPI default + project convention
    # across accounts / family-members / goals routes; see
    # ``test_routes_accounts.py::test_create_account_returns_201_*``).
    # Accept 200 OR 201 so a future project-wide flip to ``200`` doesn't
    # break this test in lockstep.
    assert account_resp.status_code in (200, 201), account_resp.text
    account_id = account_resp.json()["id"]

    from datetime import datetime, timezone
    # Phase 18 — ``merchant_name=None`` keeps the normalised string
    # short (just ``description``) so the fuzzy Pass 3 has a
    # reasonable length to score against. Setting
    # ``merchant_name="AMAZ0N PRIME"`` would double the string to
    # ``AMAZ0N PRIME AMAZ0N PRIME 1234`` and crush the ratio score
    # below the 85 cutoff, turning this test into a false negative.
    #
    # The test asserts Entertainment (not Shopping) intentionally:
    # AMZN's "AMAZON PRIME" canonical keyword maps to Entertainment in
    # ``MERCHANT_RULES`` (streaming subscription); "AMAZ0N PRIME" with
    # the 0/O typo still fuzzy-matches "AMAZON PRIME" with a score
    # above the 85 cutoff. Locking this assertion means a future
    # refactor that demotes the Prime keyword to Shopping has to
    # consciously update this test instead of silently flipping the
    # user-visible category for Amazon Prime subscriptions.
    typoed_transaction = Transaction(
        account_id=account_id,
        description="AMAZ0N PRIME 1234",
        merchant_name=None,
        amount=-14.99,
        transaction_date=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    seeded_db.add(typoed_transaction)
    seeded_db.commit()
    seeded_db.refresh(typoed_transaction)

    # Substring proof: pre-categorize-confirmation that substring
    # genuinely missed.
    from app.services.categorizer import suggest_category_for
    pre = suggest_category_for(
        typoed_transaction.merchant_name,
        typoed_transaction.description,
        {"Entertainment": seeded_db.query(Category).filter_by(name="Entertainment").first()},
    )
    assert pre is None, (
        f"Test is invalid: substring Pass 2 already matches 'AMAZ0N PRIME' → "
        f"{pre!r}. Pick a fuzzy-only text the substring rules miss."
    )

    categorized, skipped, _conflicts = categorize_transactions(seeded_db, [typoed_transaction])
    seeded_db.commit()
    seeded_db.refresh(typoed_transaction)

    entertainment_cat = seeded_db.query(Category).filter_by(name="Entertainment").first()
    assert categorized == 1, "fuzzy hit expected for OCR-noisy AMAZ0N PRIME"
    assert typoed_transaction.category_id == entertainment_cat.id, (
        "Per MERCHANT_RULES, AMAZON PRIME is Entertainment (streaming). "
        "A test failure here means a rule refactor moved Prime elsewhere; "
        "update this assertion deliberately rather than silently flipping "
        "the user-visible category for Amazon Prime subscriptions."
    )


def test_pass3_fuzzy_below_cutoff_does_not_match(
    client, seeded_db,
):
    """Random gibberish strings should NOT match the fuzzy layer."""
    client.post("/api/auth/devlogin")

    account_resp = client.post(
        "/api/accounts/",
        json={
            "account_name": "Pass3 negative test",
            "account_type": "checking",
            "institution_name": "Test Bank negative",
            "current_balance": 0.0,
        },
    )
    # POST creates return 201 (FastAPI default + project convention
    # across accounts / family-members / goals routes; see
    # ``test_routes_accounts.py::test_create_account_returns_201_*``).
    # Accept 200 OR 201 so a future project-wide flip to ``200`` doesn't
    # break this test in lockstep.
    assert account_resp.status_code in (200, 201), account_resp.text
    account_id = account_resp.json()["id"]

    from datetime import datetime, timezone
    gibberish = Transaction(
        account_id=account_id,
        description="asdfqwertyuiop12345",
        merchant_name="asdfqwertyuiop12345",
        amount=-1.00,
        transaction_date=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    seeded_db.add(gibberish)
    seeded_db.commit()
    seeded_db.refresh(gibberish)

    categorized, skipped, _conflicts = categorize_transactions(seeded_db, [gibberish])
    seeded_db.commit()
    assert categorized == 0
    assert gibberish.category_id is None


# --------------------------------------------------------------
# Manual-tag alias learning (Phase 18).
# --------------------------------------------------------------
def test_manual_category_tag_creates_alias(
    client, seeded_db,
):
    """``learn_alias_for_category`` writes an alias row so the user's
    explicit choice reinforces the heuristic for the same raw
    merchant text on future imports."""
    client.post("/api/auth/devlogin")

    account_resp = client.post(
        "/api/accounts/",
        json={
            "account_name": "Manual-tag alias test",
            "account_type": "checking",
            "institution_name": "Manual-Tag Test Bank",
            "current_balance": 0.0,
        },
    )
    # POST creates return 201 (FastAPI default + project convention
    # across accounts / family-members / goals routes; see
    # ``test_routes_accounts.py::test_create_account_returns_201_*``).
    # Accept 200 OR 201 so a future project-wide flip to ``200`` doesn't
    # break this test in lockstep.
    assert account_resp.status_code in (200, 201), account_resp.text
    account_id = account_resp.json()["id"]

    from datetime import datetime, timezone
    txn = Transaction(
        account_id=account_id,
        description="ZZTEST-VENDOR-X-9999 refund",
        merchant_name="ZZTEST-VENDOR-X-9999",
        amount=10.00,
        transaction_date=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    seeded_db.add(txn)
    seeded_db.commit()
    seeded_db.refresh(txn)

    from app.config import settings
    from app.routes.shared import get_or_create_local_user

    local_user = get_or_create_local_user(seeded_db, settings.local_user)
    other_cat = seeded_db.query(Category).filter_by(name="Other").first()

    learn_alias_for_category(
        seeded_db,
        user_id=local_user.id,
        txn=txn,
        category_id=other_cat.id,
    )
    seeded_db.commit()

    row = (
        seeded_db.query(MerchantAlias)
        .filter_by(
            user_id=local_user.id,
            alias_key=normalize_alias_key(
                "ZZTEST-VENDOR-X-9999",
                "ZZTEST-VENDOR-X-9999 refund",
            ),
        )
        .one()
    )
    assert row.category_id == other_cat.id
    assert row.use_count == 1


# --------------------------------------------------------------
# Return-tuple compatibility — Phase 11 callers (imports + txns
# routes) still get the same (categorized, skipped) shape.
# --------------------------------------------------------------
def test_categorize_transactions_returns_same_2tuple_signature(
    client, db_session,
):
    """Pin the 3-tuple return contract (Phase 39 — added conflicts list).
    ``routes/imports.py`` reads
    ``auto_categorized, auto_categorize_no_match, _conflicts`` and
    ``routes/transactions.py`` reads ``categorized, skipped, conflicts``.
    All three callers must continue to work."""
    result = categorize_transactions(db_session, [])
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert result == (0, 0, [])
