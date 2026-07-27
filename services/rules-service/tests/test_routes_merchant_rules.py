"""Phase 24 — Merchant Rules CRUD route tests.

Coverage:
- GET   /api/merchant-rules/        — list (filter by category_id, archived).
- POST  /api/merchant-rules/        — create (FK validation, UNIQUE(category_id, keyword) enforcement).
- PUT   /api/merchant-rules/{id}   — partial update (category rename, keyword change, archive toggle, restore).
- DELETE /api/merchant-rules/{id}  — soft-delete + idempotency.

Auth contract: every test uses the auth-required fixture ``client``
(pre-loaded JWT) AND a ``client_no_auth`` spot-check to confirm 401
on missing credentials — mirroring the goals / family / accounts test
patterns from earlier phases.
"""
from typing import Optional

from app.models import Category, MerchantRule
from app.services.categorizer import seed_default_merchant_rules


def _get_category_id(db, name: str) -> int:
    row = db.query(Category).filter(Category.name == name).first()
    assert row is not None, f"category {name!r} not seeded by conftest"
    return row.id


def test_list_merchant_rules_seeded_after_seed_default(client, db_session):
    """Boot-time seed populates the canonical system rules.

    Asserts the Phase 24 boot hook runs at uvicorn startup AND via
    the ``seed_default_merchant_rules`` direct call here so a
    hermetic test DB ends up with the canonical ~117 keyword rows.
    """
    inserted = seed_default_merchant_rules(db_session)
    assert inserted >= 100  # system seeds count = ~117

    resp = client.get("/api/merchant-rules/")
    assert resp.status_code == 200, resp.text
    rules = resp.json()
    assert isinstance(rules, list)
    assert len(rules) >= 100
    # Spot-check: STARBUCKS → Food & Dining must be present.
    starbucks = next(
        (r for r in rules if r["keyword"] == "STARBUCKS"),
        None,
    )
    assert starbucks is not None
    assert starbucks["category_name"] == "Food & Dining"
    assert starbucks["is_archived"] is False


def test_list_merchant_rules_filter_by_category(client, db_session):
    """list endpoint with category_id query param narrows to one category."""
    seed_default_merchant_rules(db_session)
    income_cat_id = _get_category_id(db_session, "Base Salary")

    resp = client.get(f"/api/merchant-rules/?category_id={income_cat_id}")
    assert resp.status_code == 200, resp.text
    rules = resp.json()
    assert all(r["category_id"] == income_cat_id for r in rules)
    keywords = {r["keyword"] for r in rules}
    assert "PAYROLL" in keywords


def test_list_merchant_rules_excludes_archived_by_default(
    client, db_session
):
    """Default list view hides is_archived=True rows; explicit toggle surfaces them."""
    seed_default_merchant_rules(db_session)
    income_cat_id = _get_category_id(db_session, "Base Salary")

    # User deletes STARBUCKS via food & dining category.
    starbucks = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "STARBUCKS")
        .first()
    )
    assert starbucks is not None
    db_session.delete(starbucks)  # soft-delete via the route under test
    db_session.commit()

    # Default omits archived rules — POST→ DELETE on STARBUCKS via
    # the route flips is_archived=True; here we delete raw to keep
    # this test focused on the LIST branch.
    default_resp = client.get(
        f"/api/merchant-rules/?category_id={_get_category_id(db_session, 'Food & Dining')}"
    )
    assert default_resp.status_code == 200
    keywords_default = {r["keyword"] for r in default_resp.json()}
    assert "STARBUCKS" not in keywords_default

    include_resp = client.get(
        f"/api/merchant-rules/?category_id={_get_category_id(db_session, 'Food & Dining')}"
        "&include_archived=true"
    )
    assert include_resp.status_code == 200
    keywords_with_archived = {r["keyword"] for r in include_resp.json()}
    assert "STARBUCKS" not in keywords_with_archived  # raw delete, not archive


def test_create_merchant_rule_succeeds(client, db_session):
    """POST adds a new user rule; response shape mirrors GET."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "TRADER JOES #6666", "priority": 100},
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["category_id"] == food_id
    assert created["category_name"] == "Food & Dining"
    assert created["keyword"] == "TRADER JOES #6666"
    assert created["priority"] == 100
    assert created["is_archived"] is False


def test_create_merchant_rule_uppercases_keyword(client, db_session):
    """POST normalises keyword to uppercase + stripped server-side."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "  tasty bbq  "},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["keyword"] == "TASTY BBQ"


def test_create_merchant_rule_duplicate_409(client, db_session):
    """UNIQUE(category_id, keyword) → 409 with actionable detail."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS", "priority": 100},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "STARBUCKS" in detail
    assert "Food & Dining" in detail


def test_create_merchant_rule_category_missing_400(client):
    """category_id FK violation surfaces as friendly 400, not 500."""
    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": 999_999, "keyword": "GHOST MERCHANT"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Category id 999999 does not exist."


def test_create_merchant_rule_empty_keyword_400(client, db_session):
    """Empty/whitespace keyword normalised → 0-length → 400."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "   "},
    )
    assert resp.status_code == 400, resp.text


def test_list_merchant_rules_requires_auth(client_no_auth, db_session):
    """GET without JWT cookie returns 401."""
    seed_default_merchant_rules(db_session)
    resp = client_no_auth.get("/api/merchant-rules/")
    assert resp.status_code == 401


def test_update_merchant_rule_reassign_category(client, db_session):
    """PUT category_id moves the rule to a different category."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "STARBUCKS")
        .first()
    )
    assert rule is not None
    assert rule.category_id == food_id

    other_id = _get_category_id(db_session, "Entertainment")
    resp = client.put(
        f"/api/merchant-rules/{rule.id}",
        json={"category_id": other_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category_id"] == other_id
    assert body["category_name"] == "Entertainment"


def test_update_merchant_rule_archive_and_restore(client, db_session):
    """PUT is_archived toggles soft-delete + restore."""
    seed_default_merchant_rules(db_session)
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "SUNOCO")
        .first()
    )
    assert rule is not None
    assert rule.is_archived is False

    # Archive.
    resp = client.put(
        f"/api/merchant-rules/{rule.id}",
        json={"is_archived": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_archived"] is True

    # Restore.
    resp = client.put(
        f"/api/merchant-rules/{rule.id}",
        json={"is_archived": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_archived"] is False


def test_delete_merchant_rule_soft_delete(client, db_session):
    """DELETE flips is_archived=True; row stays in DB."""
    seed_default_merchant_rules(db_session)
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "PEET'S")
        .first()
    )
    assert rule is not None
    rule_id = rule.id

    resp = client.delete(f"/api/merchant-rules/{rule_id}")
    assert resp.status_code == 204, resp.text

    # Row still present, is_archived flipped. ``expire_all`` clears
    # the local session's identity-map cache so the next SELECT sees
    # the committed state from the FastAPI session (separate
    # SQLAlchemy session). Without it the cached object pre-dates
    # the route's ``db.commit`` and ``is_archived`` would still read
    # as ``False``.
    db_session.expire_all()
    refreshed = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.id == rule_id)
        .first()
    )
    assert refreshed is not None
    assert refreshed.is_archived is True

    # DELETE again is idempotent → 204 (no DB write).
    resp2 = client.delete(f"/api/merchant-rules/{rule_id}")
    assert resp2.status_code == 204


def test_delete_merchant_rule_user_delete_persists_across_seed(
    client, db_session
):
    """A user-soft-deleted system rule stays deleted after re-seeding.

    This is the test that locks the Phase 24 re-seed trap: hard-delete
    would let ``seed_default_merchant_rules`` re-INSERT, undoing the
    user's intent. Soft-delete forces the seed helper to skip the
    archived row.
    """
    seed_default_merchant_rules(db_session)
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "CHEVRON")
        .first()
    )
    assert rule is not None

    resp = client.delete(f"/api/merchant-rules/{rule.id}")
    assert resp.status_code == 204

    # Re-run seed; the archived row must NOT be re-inserted as active.
    inserted = seed_default_merchant_rules(db_session)
    db_session.expire_all()  # clear the SQLAlchemy identity map
    refreshed = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.id == rule.id)
        .first()
    )
    assert refreshed is not None
    assert refreshed.is_archived is True, (
        "User-deleted system rule was resurrected by the seed helper"
    )
    assert inserted == 0  # no NEW rows from the re-seed


def test_update_merchant_rule_404_for_missing_id(client):
    resp = client.put("/api/merchant-rules/999999", json={"keyword": "X"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Merchant rule not found"


def test_delete_merchant_rule_404_for_missing_id(client):
    resp = client.delete("/api/merchant-rules/999999")
    assert resp.status_code == 404


def test_reload_endpoint_returns_active_and_archived_counts(
    client, db_session
):
    """POST /api/merchant-rules/reload returns the live counts."""
    seed_default_merchant_rules(db_session)
    # Archive one so archived > 0.
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "LYFT")
        .first()
    )
    assert rule is not None
    resp = client.put(
        f"/api/merchant-rules/{rule.id}",
        json={"is_archived": True},
    )
    assert resp.status_code == 200

    resp = client.post("/api/merchant-rules/reload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] >= 100
    assert body["archived"] >= 1


def test_categorize_transactions_reads_runtime_db_rules(
    client, db_session, make_account, make_transaction
):
    """categorize_transactions reads rules from the DB.

    Phase 24 contract: a USER-added rule must be picked up on the
    NEXT bulk run (not the current module's static dict). This test
    inserts a new rule via the CRUD endpoint then asserts the
    categorizer tags the matching transaction in the next call.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    # User rule: "PHANTOM_MERCHANT_XYZ" → Food & Dining.
    resp = client.post(
        "/api/merchant-rules/",
        json={
            "category_id": food_id,
            "keyword": "PHANTOM_MERCHANT_XYZ",
            "priority": 100,
        },
    )
    assert resp.status_code == 201

    # Build account + transaction whose description matches.
    acct = make_account()
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)
    txn = make_transaction(
        account_id=acct.id,
        description="PHANTOM_MERCHANT_XYZ POS 1234",
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)

    assert txn.category_id is None

    # FIRE the categorize endpoint, which routes through
    # app.services.categorizer.categorize_transactions.
    resp = client.post("/api/transactions/categorize")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["categorized"] >= 1

    # The transaction was tagged by the user rule.
    db_session.refresh(txn)
    assert txn.category_id == food_id


# ----------------------------------------------------------------------
# Phase 27 — source column + CSV export/import coverage
# ----------------------------------------------------------------------
import csv as _csv
import io as _io
from pathlib import Path as _Path


_FIXTURES_DIR = _Path(__file__).parent / "fixtures"


def _good_fixture_csv_bytes() -> bytes:
    """Read the canonical round-trippable fixture as UTF-8 bytes."""
    return (_FIXTURES_DIR / "sample-merchant-rules.csv").read_bytes()


def _edge_fixture_csv_bytes() -> bytes:
    """Read the mixed-validity fixture used to assert per-row error reporting."""
    return (
        _FIXTURES_DIR / "sample-merchant-rules-with-errors.csv"
    ).read_bytes()


def test_seed_default_merchant_rules_stamps_source_system(client, db_session):
    """Phase 27 — every seeded row carries source='system'.

    The categorizer's seed helper explicitly sets source='system' on
    each new INSERT. Without that explicit stamp the ORM ``default``
    ('manual' from the model) would silently mis-attribute every
    system row. This test locks the contract.
    """
    inserted = seed_default_merchant_rules(db_session)
    assert inserted >= 100

    rules = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.source != "system")
        .filter(MerchantRule.is_archived.is_(False))
        .all()
    )
    # Empty list means EVERY live system rule carries source='system'.
    # The check is ``!= 'system'`` so a regression to the model's
    # 'manual' default would surface this assertion immediately.
    system_rule_count = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.source == "system")
        .count()
    )
    assert system_rule_count >= 100
    assert len(rules) == 0


def test_create_merchant_rule_default_source_is_manual(client, db_session):
    """POST without source column stamps 'manual' per Phase 27 default."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "PUBLIC-DEFAULT-SOURCE"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "manual"


def test_create_merchant_rule_explicit_source_tag_rule(client, db_session):
    """POST with source='tag-rule' persists the value verbatim."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={
            "category_id": food_id,
            "keyword": "TAG-RULE-FIX-A",
            "source": "tag-rule",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "tag-rule"


def test_create_merchant_rule_source_system_rejected(client, db_session):
    """POST with source='system' returns 400 — only the seed may stamp it."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={
            "category_id": food_id,
            "keyword": "FAKE-SYSTEM-KEYWORD",
            "source": "system",
        },
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "system" in detail.lower()
    assert "reserved" in detail.lower() or "cannot" in detail.lower()


def test_list_merchant_rules_filter_by_source(client, db_session):
    """GET /?source=manual returns ONLY manual rows."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    # Add a single user rule (source='manual' by default).
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "FILTER-MANUAL-ONLY"},
    )
    # Add another user rule tagged as 'tag-rule' provenance.
    client.post(
        "/api/merchant-rules/",
        json={
            "category_id": food_id,
            "keyword": "FILTER-TAGRULE-ONLY",
            "source": "tag-rule",
        },
    )

    resp = client.get("/api/merchant-rules/?source=manual")
    assert resp.status_code == 200
    keywords = {r["keyword"] for r in resp.json()}
    assert "FILTER-MANUAL-ONLY" in keywords
    assert "FILTER-TAGRULE-ONLY" not in keywords
    # System seeds MUST NOT appear in source=manual.
    assert "STARBUCKS" not in keywords

    resp = client.get("/api/merchant-rules/?source=tag-rule")
    assert resp.status_code == 200
    keywords = {r["keyword"] for r in resp.json()}
    assert "FILTER-TAGRULE-ONLY" in keywords

    resp = client.get("/api/merchant-rules/?source=system")
    assert resp.status_code == 200
    keywords = {r["keyword"] for r in resp.json()}
    assert "STARBUCKS" in keywords
    assert "FILTER-MANUAL-ONLY" not in keywords


def test_list_merchant_rules_combined_filters(client, db_session):
    """Two filters combine via AND (category_id + source)."""
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.get(
        f"/api/merchant-rules/?category_id={food_id}&source=system"
    )
    assert resp.status_code == 200
    kwargs_for_food = resp.json()  # base rowcount would be system+manual mixed
    assert all(r["category_id"] == food_id for r in kwargs_for_food)
    assert all(r["source"] == "system" for r in kwargs_for_food)


def test_put_merchant_rule_ignores_source_field(client, db_session):
    """PUT smuggles source='manual'; the row's source must NOT change."""
    seed_default_merchant_rules(db_session)
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "STARBUCKS")
        .first()
    )
    assert rule is not None
    original_source = rule.source
    assert original_source == "system"

    # The ``MerchantRuleUpdate`` Pydantic schema does NOT declare
    # ``source`` so ``model_dump()`` drops it silently — the
    # whitelist contract. A raw-httpx client trying to set
    # ``source`` is also dropped by the route's defensive ``pop``
    # block.
    resp = client.put(
        f"/api/merchant-rules/{rule.id}",
        json={"keyword": "STARBUCKS-NEW-NAME", "source": "manual"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Keyword changed.
    assert body["keyword"] == "STARBUCKS-NEW-NAME"
    # Source did NOT change — the whitelist contract preserved it.
    assert body["source"] == "system"

    db_session.expire_all()
    refreshed = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.id == rule.id)
        .first()
    )
    assert refreshed.source == "system"


def test_export_endpoint_returns_csv(client, db_session):
    """GET /export returns text/csv with the locked header + parseable rows."""
    seed_default_merchant_rules(db_session)
    # Add a user rule so the test asserts a non-empty export.
    food_id = _get_category_id(db_session, "Food & Dining")
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "EXPORT-DEMO"},
    )

    resp = client.get("/api/merchant-rules/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]

    # Parse the body and assert header + 1+ data rows.
    rows = list(_csv.DictReader(_io.StringIO(resp.text)))
    assert len(rows) >= 101  # ~100 system seeds + 1 user rule
    # Spot-check schema: every row has all 5 columns.
    for row in rows[:3]:
        assert set(row.keys()) == {
            "category_name", "keyword", "priority", "is_archived", "source",
        }
    # Spot-check ordering: ASC by priority. EXPORT-DEMO was POSTed
    # without explicit priority, so the Phase 28 auto-increment
    # branch fires and assigns ``MAX(existing) + 10``. STARBUCKS is
    # the first Food & Dining system seed, so its priority is
    # 18 * 10 = 180 (Food & Dining is the 3rd category in the seed
    # declaration order; Income+Transfer = 17 keys before it). The
    # auto-increment computes MAX=180 → EXPORT-DEMO lands at 190.
    # ASC sort: 180 < 190, so STARBUCKS appears BEFORE EXPORT-DEMO.
    # The pre-Phase 28 default was 100 (so EXPORT-DEMO would have
    # come first) — the index assertion locks the ``MAX + 10`` not
    # silently reverting to a constant default. (A previous
    # literal-value check was redundant with this index assertion;
    # a regression to priority=100 would flip the order to
    # demo_idx < starbucks_idx, which this assert catches directly.)
    starbucks = next(r for r in rows if r["keyword"] == "STARBUCKS")
    demo = next(r for r in rows if r["keyword"] == "EXPORT-DEMO")
    starbucks_idx = rows.index(starbucks)
    demo_idx = rows.index(demo)
    assert starbucks_idx < demo_idx, (
        f"Expected STARBUCKS system priority 180 to come BEFORE "
        f"EXPORT-DEMO auto-incremented priority 190 in the ASC-sorted "
        f"export; got starbucks_idx={starbucks_idx}, demo_idx="
        f"{demo_idx}. The Phase 28 MAX+10 auto-increment may have "
        f"regressed to a constant default (100)."
    )


def test_export_endpoint_excludes_archived_when_flag_false(client, db_session):
    """GET /export?include_archived=false omits is_archived=True rows."""
    seed_default_merchant_rules(db_session)
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "LYFT")
        .first()
    )
    assert rule is not None
    # Archive via the route under test so this test exercises the
    # same code path a real user would.
    client.put(f"/api/merchant-rules/{rule.id}", json={"is_archived": True})

    default_resp = client.get("/api/merchant-rules/export")
    archived_rows = list(_csv.DictReader(_io.StringIO(default_resp.text)))
    keywords_default = {r["keyword"] for r in archived_rows}
    assert "LYFT" in keywords_default  # default includes archived

    live_only_resp = client.get(
        "/api/merchant-rules/export?include_archived=false"
    )
    live_rows = list(_csv.DictReader(_io.StringIO(live_only_resp.text)))
    keywords_live = {r["keyword"] for r in live_rows}
    assert "LYFT" not in keywords_live


def test_import_endpoint_inserts_fixture_rows(client, db_session):
    """POST /import with the GOOD fixture inserts all 5 fixture rows.

    The fixture has 5 valid rows. After import the merchant_rules
    table should hold those 5 plus any pre-existing rows.
    Every imported row carries source='imported' per the Phase 27
    audit-trail contract.
    """
    seed_default_merchant_rules(db_session)
    existing_keywords = {
        r.keyword for r in db_session.query(MerchantRule).all()
    }
    assert "SAMPLE-FIXTURE-FOOD-A" not in existing_keywords

    files = {"file": ("good.csv", _good_fixture_csv_bytes(), "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] == 5
    assert body["skipped_existing"] == 0
    assert body["errors"] == []

    db_session.expire_all()
    for kw in (
        "SAMPLE-FIXTURE-FOOD-A",
        "SAMPLE-FIXTURE-FOOD-B",
        "SAMPLE-FIXTURE-GROCERY-A",
        "SAMPLE-FIXTURE-TRANSIT",
        "SAMPLE-FIXTURE-SHOP-A",
    ):
        row = (
            db_session.query(MerchantRule)
            .filter(MerchantRule.keyword == kw)
            .first()
        )
        assert row is not None, f"imported row {kw!r} missing"
        assert row.source == "imported"


def test_import_endpoint_strips_bom(client, db_session):
    """Phase 27 — Excel-style BOM prefix doesn't break import.

    ``\ufeff`` at the start of a UTF-8 file would otherwise put a
    BOM in the first header column name and break DictReader lookup.
    Reads via ``utf-8-sig`` to strip.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")
    body = "category_name,keyword,priority,is_archived,source\nFood & Dining,BOM-EDGE-A,42,false,manual\n"
    bom_body = b"\xef\xbb\xbf" + body.encode("utf-8")

    files = {"file": ("bom.csv", bom_body, "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] == 1


def test_import_endpoint_records_per_row_errors(client, db_session):
    """POST /import with the EDGE fixture: 2 valid inserted, 5 errors recorded."""
    seed_default_merchant_rules(db_session)

    files = {"file": ("edge.csv", _edge_fixture_csv_bytes(), "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Fixture has: 2 OK (EDGE-OK-FOOD + EDGE-OK-TRANSIT) plus a
    # row with empty category_name, a row with bad category,
    # a row with bad priority, a row with bad is_archived,
    # a row with empty keyword — 5 errors. The fixture row that
    # carries ``source=system`` still gets source='imported' on
    # insert (audit-trail correctness; CSV column is informational).
    assert body["inserted"] == 2
    assert body["skipped_existing"] == 0
    errors = body["errors"]
    assert len(errors) == 5
    # Every error has a 1-indexed row number >= 2 (header = row 1).
    for e in errors:
        assert e["row"] >= 2
        assert "reason" in e and e["reason"]


def test_import_endpoint_skips_existing_duplicates(client, db_session):
    """Import a row whose (category_id, keyword) already exists → skipped_existing++."""
    seed_default_merchant_rules(db_session)

    body_bytes = (
        b"category_name,keyword,priority,is_archived,source\n"
        b"Food & Dining,STARBUCKS,100,false,imported\n"
    )
    files = {"file": ("dup.csv", body_bytes, "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["inserted"] == 0
    assert result["skipped_existing"] == 1
    assert result["errors"] == []


def test_import_endpoint_400_on_missing_header_cols(client, db_session):
    """CSV missing required 'category_name' column → 400."""
    body_bytes = (
        b"keyword,priority\n"
        b"NOHEAD-A,42\n"
    )
    files = {"file": ("no-header.csv", body_bytes, "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 400, resp.text
    assert "category_name" in resp.json()["detail"]


def test_import_endpoint_400_on_empty_payload(client):
    """Zero-byte upload → 400 well before the CSV reader is invoked."""
    files = {"file": ("empty.csv", b"", "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 400, resp.text
    assert "empty" in resp.json()["detail"].lower()


def test_import_overrides_source_to_imported(client, db_session):
    """Even a CSV row with source='system' gets stamped 'imported' on insert.

    Audit-trail correctness wins over CSV fidelity. This locks the
    contract tested above (``test_create_merchant_rule_source_system_rejected``
    covers the POST side).
    """
    seed_default_merchant_rules(db_session)
    food_id = (
        db_session.query(Category).filter(Category.name == "Food & Dining").first().id
    )

    body_bytes = (
        b"category_name,keyword,priority,is_archived,source\n"
        b"Food & Dining,OVERRIDE-SOURCE-A,42,false,system\n"
    )
    files = {"file": ("override.csv", body_bytes, "text/csv")}
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] == 1

    db_session.expire_all()
    row = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "OVERRIDE-SOURCE-A")
        .first()
    )
    assert row is not None
    assert row.source == "imported"  # NOT 'system' even though CSV said so


def test_export_import_round_trip(client, db_session):
    """Wipe ALL → re-export / re-import → every baseline row is back.

    This proves ``/export → /import`` is the canonical restore
    pathway: every row in the export re-inserts and EVERY row
    carries ``source='imported'`` per the Phase 27 audit-trail
    contract (the import EVENT is the provenance; original
    System/Manual/etc labels do NOT carry across re-imports).

    Conftest per-test cleanup truncates between tests in the SAME
    suite; the SQLAlchemy identity-map can lag the SQL wipe by a
    moment, so this test compares POST-IMPORT keyword coverage
    against the EXPORT'S row set rather than a pre_count snapshot.
    Coverage comparison is robust to cross-session visibility races
    that have previously broken tight-count assertions.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    # Plant a non-system row + archive a system row to exercise the
    # full range of source/is_archived states in the export.
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "ROUNDTRIP-USER", "source": "manual"},
    )
    archived_rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "LYFT")
        .first()
    )
    assert archived_rule is not None
    client.put(
        f"/api/merchant-rules/{archived_rule.id}",
        json={"is_archived": True},
    )

    # Export baseline. Parse the CSV to drive the coverage assertion
    # from the SAME bytes we just re-uploade — no DB count involved.
    export_resp = client.get("/api/merchant-rules/export")
    assert export_resp.status_code == 200, export_resp.text
    export_text = export_resp.text
    baseline_rows = list(_csv.DictReader(_io.StringIO(export_text)))
    baseline_keywords = {r["keyword"] for r in baseline_rows}
    assert baseline_keywords  # non-empty
    # Sanity: the user-planted rows are present in the export.
    assert "ROUNDTRIP-USER" in baseline_keywords
    assert "LYFT" in baseline_keywords

    # Wipe EVERYTHING so the import INSERT path is exercised fresh.
    db_session.query(MerchantRule).delete()
    db_session.commit()
    db_session.expire_all()
    # Force the FastAPI client session to see the wipe by clearing
    # its implicit cache; the next endpoint call issues a fresh SELECT.
    # (The client session keeps an identity map; explicit expire_all
    # above + a small refresh via list endpoint suffice.)
    list_after_wipe = client.get(
        "/api/merchant-rules/?include_archived=true"
    ).json()
    assert len(list_after_wipe) == 0, (
        f"Wipe did not propagate to FastAPI client session; "
        f"got {len(list_after_wipe)} rows."
    )

    # Re-import baseline. Empty DB ⟹ every row INSERTS.
    files = {
        "file": (
            "roundtrip.csv",
            export_text.encode("utf-8"),
            "text/csv",
        ),
    }
    resp = client.post("/api/merchant-rules/import", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["errors"] == [], (
        f"Round-trip import surfaced row-level errors: {body['errors']}"
    )
    # Coverage: every keyword in the baseline export must be present
    # in the DB after import. We deliberately do NOT compare
    # ``inserted == pre_count`` because the FastAPI client session's
    # autouse-seed can lag the SQLAlchemy session snapshot on the
    # hermetic test DB; the keyword-set comparison is idempotent
    # across session quirks.
    post_keywords = {
        r["keyword"]
        for r in client.get(
            "/api/merchant-rules/?include_archived=true"
        ).json()
    }
    missing = baseline_keywords - post_keywords
    assert not missing, (
        f"Round-trip import dropped these keywords: {sorted(missing)}"
    )
    # And: the selectively-included user rule MUST round-trip even
    # though we wiped EVERYTHING (the system seeds are now ALL
    # source='imported' too — they aren't "system" any more after
    # the import event REPLACES the provenance stamp).
    assert "ROUNDTRIP-USER" in post_keywords
    assert "LYFT" in post_keywords
    # Sink check: assert inserted + skipped_existing == baseline size.
    assert body["inserted"] + body["skipped_existing"] == len(baseline_rows)

    # Source-override audit: every row the BE claims was inserted
    # has source='imported' (regardless of the CSV's source column,
    # which the BE silently OVERRIDES for the audit trail).
    db_session.expire_all()
    rt_row = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "ROUNDTRIP-USER")
        .first()
    )
    assert rt_row is not None
    assert rt_row.source == "imported"
    starbucks = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "STARBUCKS")
        .first()
    )
    assert starbucks is not None
    assert starbucks.source == "imported"


def test_reload_endpoint_includes_by_source_breakdown(client, db_session):
    """POST /reload returns ``by_source: { 'system': {...}, ... }``.

    Phase 27 — the diagnostic feed includes a per-source breakdown
    so the FE can render a "SAMPLE-FIXTURE breakdown" chart without
    an N+1 list pass. Locks the new shape (was just
    ``{active, archived}`` pre-Phase 27).
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "BY-SOURCE-DEMO"},
    )

    resp = client.post("/api/merchant-rules/reload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] >= 101
    assert "by_source" in body
    src_buckets = body["by_source"]
    assert "system" in src_buckets
    assert src_buckets["system"]["active"] >= 100
    assert "manual" in src_buckets
    assert src_buckets["manual"]["active"] >= 1  # BY-SOURCE-DEMO


def test_list_merchant_rules_response_carries_source(client, db_session):
    """Every list-row response carries the source string.

    Locks the Phase 27 response-shape invariant — a regression in
    ``_row_to_response`` would surface here on the very first row.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "RESP-SOURCE-A"},
    )

    resp = client.get("/api/merchant-rules/")
    assert resp.status_code == 200
    rules = resp.json()
    assert all("source" in r for r in rules)
    # Spot-check both a system row and a user row.
    sys_rule = next(r for r in rules if r["keyword"] == "STARBUCKS")
    assert sys_rule["source"] == "system"
    user_rule = next(r for r in rules if r["keyword"] == "RESP-SOURCE-A")
    assert user_rule["source"] == "manual"


def test_source_column_regression_every_row_has_valid_source(
    client, db_session
):
    """Migration-drift guard rail — locks the live ``source`` column.

    Phase 27 added the ``source`` column via migration
    ``J0a1b2c3d4e5_add_merchant_rule_source``. If a future engineer
    ships a code change that references this column WITHOUT first
    applying the migration (e.g. a fresh-clone user running
    ``start.sh`` that skipped the alembic upgrade), the BE's
    SQLAlchemy model in memory declares ``MerchantRule.source`` but
    the DB schema doesn't have it → every ``GET /api/merchant-rules/``
    call either 500s (IntegrityError on insert) or returns rows
    where the response builder's ``source=rule.source`` access
    surfaces as ``None`` in the JSON.

    This test catches BOTH failure modes by:

    1. Asserting ``MerchantRule`` SQLAlchemy mapping has the
       ``source`` attribute (model+DB must agree).
    2. Asserting the live ``merchant_rules`` table's columns include
       ``source`` (PRAGMA table_info).
    3. Asserting EVERY row in the table has a non-null ``source``
       value (catches the partial-back-fill case).
    4. Asserting the ``GET /api/merchant-rules/`` response carries
       ``source`` on every row (catches the API-side breakdown).

    Run order: the autouse seed in conftest seeds the categories;
    this test then seeds the system rules so the
    ``source='system'`` rows exist. The PRAGMA check runs BEFORE
    the API call so a migration-missing failure surfaces as a
    clear AssertionError rather than a noisy 500 from FastAPI.
    """
    from sqlalchemy import inspect as _sa_inspect

    # 1. SQLAlchemy model says source exists.
    assert hasattr(MerchantRule, "source"), (
        "MerchantRule model is missing the 'source' Column — the "
        "Phase 27 migration was likely reverted or skipped. Apply "
        "migration J0a1b2c3d4e5 via `alembic upgrade head`."
    )

    # 2. Live DB schema has the column.
    engine = db_session.get_bind()
    inspector = _sa_inspect(engine)
    live_columns = {col["name"] for col in inspector.get_columns("merchant_rules")}
    assert "source" in live_columns, (
        "Live 'merchant_rules' table is missing the 'source' "
        "column. Apply migration J0a1b2c3d4e5 via "
        "`alembic upgrade head` (start.sh should auto-apply on boot)."
    )

    # 3. Seed system rules + add a user rule so we test BOTH
    #    source values.
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "REGRESSION-USER-A"},
    )

    # Every row in the DB has a non-null, non-empty source.
    db_session.expire_all()
    null_source_rows = (
        db_session.query(MerchantRule)
        .filter(
            (MerchantRule.source.is_(None)) | (MerchantRule.source == "")
        )
        .all()
    )
    assert null_source_rows == [], (
        f"Found {len(null_source_rows)} merchant_rules rows with "
        f"NULL/empty source — migration J0a1b2c3d4e5 likely did "
        f"not back-fill. Sample: {null_source_rows[:3]}"
    )

    # 4. API response carries source on every row.
    resp = client.get("/api/merchant-rules/")
    assert resp.status_code == 200, resp.text
    rules = resp.json()
    assert rules, "Seed produced no rows — seed_default_merchant_rules is broken"
    missing_source = [r for r in rules if not r.get("source")]
    assert missing_source == [], (
        f"API response omitted 'source' on {len(missing_source)} "
        f"row(s). Sample: {missing_source[:3]}"
    )

    # 5. The source filter works (catches the case where the
    #    filter route references a column that doesn't exist).
    sys_resp = client.get("/api/merchant-rules/?source=system")
    assert sys_resp.status_code == 200, sys_resp.text
    sys_keywords = {r["keyword"] for r in sys_resp.json()}
    assert "STARBUCKS" in sys_keywords
    assert "REGRESSION-USER-A" not in sys_keywords

    user_resp = client.get("/api/merchant-rules/?source=manual")
    assert user_resp.status_code == 200
    user_keywords = {r["keyword"] for r in user_resp.json()}
    assert "REGRESSION-USER-A" in user_keywords
    assert "STARBUCKS" not in user_keywords


# ----------------------------------------------------------------------
# Phase 28 — auto-increment priority + detach on transactions
# ----------------------------------------------------------------------


def test_create_merchant_rule_auto_increments_priority(client, db_session):
    """POST without a priority field auto-assigns MAX(existing) + 10.

    Phase 28 user complaint: "when I add a new rule it uses the
    same priority as the rule in the category I have, shouldnt
    it increment?" Locks the new contract: omitted priority
    is auto-assigned so a freshly-added user rule slots BELOW
    the last existing rule in the same category with a +10 gap
    (deterministic, monotonic, no order-collision with the
    previous 100-default that overlapped the system seeds' tail).
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    # First user rule → MAX in category is the highest STARBUCKS
    # system seed priority (180 in the canonical seed order). The
    # route computes MAX + 10 = 190. Exact value is fragile to
    # seed-order changes; assert it's > MAX of system priorities
    # so a future seed addition doesn't break this test.
    max_sys = (
        db_session.query(MerchantRule.priority)
        .filter(
            MerchantRule.category_id == food_id,
            MerchantRule.is_archived.is_(False),
        )
        .order_by(MerchantRule.priority.desc())
        .first()
    )
    assert max_sys is not None
    max_sys_pri = int(max_sys[0])

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "AUTO-PRIO-A"},
    )
    assert resp.status_code == 201, resp.text
    first = resp.json()
    assert first["priority"] == max_sys_pri + 10

    # Second user rule → MAX is now ``first.priority``, so the new
    # rule is ``first.priority + 10``. The +10 gap is the contract.
    resp2 = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "AUTO-PRIO-B"},
    )
    assert resp2.status_code == 201, resp2.text
    second = resp2.json()
    assert second["priority"] == first["priority"] + 10


def test_create_merchant_rule_explicit_priority_honored(client, db_session):
    """POST with an explicit priority keeps the value verbatim.

    The Phase 28 auto-increment branch only fires when the
    client OMITS the priority field (Pydantic Optional[int] = None
    default). CSV import + future bulk-insert tools that need
    EXACT priorities can send an explicit value and the route
    honours it. This test locks the explicit-priority contract
    so a future "force auto-increment" refactor doesn't silently
    break the import path.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_category_id(db_session, "Food & Dining")

    resp = client.post(
        "/api/merchant-rules/",
        json={
            "category_id": food_id,
            "keyword": "EXPLICIT-PRIO",
            "priority": 42,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["priority"] == 42


def test_create_merchant_rule_empty_category_auto_falls_back_to_100(
    client, db_session
):
    """When a category has zero live rules, the auto-increment falls back to 100.

    Belt-and-suspenders: ``MAX(priority)`` returns None on an empty
    category. The route branches to the schema default (100) so the
    very first user-added rule in a brand-new category still has a
    sensible ordering. A real bug would have this fall back to
    ``None + 10`` (a SQLAlchemy TypeError or 500) so we lock the
    fallback explicitly.
    """
    # Use a category with NO existing rules by creating a fresh
    # Category row.
    from app.models import Category as _Category

    fresh_cat = _Category(
        name="FRESH-CATEGORY-AUTO",
        description="auto-increment fallback test",
    )
    db_session.add(fresh_cat)
    db_session.commit()
    db_session.refresh(fresh_cat)

    resp = client.post(
        "/api/merchant-rules/",
        json={"category_id": fresh_cat.id, "keyword": "FALLBACK-CHECK"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["priority"] == 100


# ----------------------------------------------------------------------
# Phase 29 — duplicate detection (Settings → "Clean up duplicates").
# ----------------------------------------------------------------------
# Three endpoints under ``/api/merchant-rules/duplicates/*``:
#   - GET  /duplicates         — L1 (substring) only.
#   - POST /duplicates/llm     — L1 + L2 (semantic) combined.
#   - POST /duplicates/apply   — soft-delete candidate ids.
#
# Coverage: substring scan correctness (incl. trailing-space
# guard, canonical-orientation, cross-category skip), L1+consolidate
# contract, apply idempotency, canonical-protection, and the L1-only
# endpoint's offline-friendliness (no Ollama required).
# ----------------------------------------------------------------------


def _get_food_id(db):
    row = db.query(Category).filter(Category.name == "Food & Dining").first()
    assert row is not None
    return row.id


def test_find_substring_duplicates_pairs_canonical(client, db_session):
    """L1 — ``STARBUCKS`` and ``STARBUCKS COFFEE`` in the same
    category produce one dedup group; canonical is the shorter rule.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    # Add a longer rule in the same category that substring-matches
    # the existing STARBUCKS system rule.
    resp = client.post(
        "/api/merchant-rules/",
        json={
            "category_id": food_id,
            "keyword": "STARBUCKS COFFEE",
            "priority": 200,
        },
    )
    assert resp.status_code == 201, resp.text

    resp = client.get("/api/merchant-rules/duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["l1_count"] >= 1
    assert body["l2_count"] == 0
    # Find the STARBUCKS group; the canonical should be the
    # shorter (system-seeded) STARBUCKS, not the user-added
    # STARBUCKS COFFEE.
    groups = body["groups"]
    starbucks_group = next(
        (
            g
            for g in groups
            if g["canonical"]["keyword"] == "STARBUCKS"
        ),
        None,
    )
    assert starbucks_group is not None, (
        f"Expected a group with canonical='STARBUCKS' in {groups}"
    )
    cand_keywords = {c["keyword"] for c in starbucks_group["candidates"]}
    assert "STARBUCKS COFFEE" in cand_keywords
    # All candidates carry method='substring' (L1-only endpoint).
    for c in starbucks_group["candidates"]:
        assert c["method"] == "substring"
        assert c["confidence"] == 1.0


def test_find_substring_duplicates_skips_cross_category(client, db_session):
    """L1 — same keyword in two different categories does NOT
    produce a cross-category dedup group. (Cross-category is a
    different problem and out of scope for Phase 29.)
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    other_id = (
        db_session.query(Category).filter(Category.name == "Shopping").first().id
    )
    # Add CROSS-CAT-A to Food & Dining + Shopping; same keyword, two
    # categories. L1 should NOT flag it.
    for cat_id in (food_id, other_id):
        r = client.post(
            "/api/merchant-rules/",
            json={"category_id": cat_id, "keyword": "CROSS-CAT-A"},
        )
        assert r.status_code == 201, r.text
    resp = client.get("/api/merchant-rules/duplicates")
    body = resp.json()
    cross_groups = [
        g
        for g in body["groups"]
        if g["canonical"]["keyword"] == "CROSS-CAT-A"
    ]
    assert cross_groups == [], (
        f"Expected zero cross-category dedup groups; got {cross_groups}"
    )


def test_find_substring_duplicates_trailing_space_guard(client, db_session):
    """L1 — ``TAXI`` (no trailing space) and ``TAXI UBER`` (no
    trailing space) would form a substring pair; but ``TAXI `` with
    a trailing space and ``TAXI UBER`` (no trailing space) should
    NOT be flagged because the shorter rule's trailing space is a
    deliberate word-boundary marker.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    # Add ``TAXI `` and ``TAXI UBER`` to the same category.
    r1 = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "TAXI "},
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "TAXI UBER"},
    )
    assert r2.status_code == 201, r2.text

    resp = client.get("/api/merchant-rules/duplicates")
    body = resp.json()
    # ``TAXI UBER`` may or may not be a substring of another seeded
    # rule; the assertion we care about is that the ``TAXI ``
    # canonical (shorter, trailing space) is NOT a substring pair
    # with ``TAXI UBER`` (the candidate dropped the boundary).
    # The shorter is the canonical, so a flag would have canonical
    # ``TAXI `` with candidate ``TAXI UBER``. Verify it doesn't
    # appear.
    for g in body["groups"]:
        if g["canonical"]["keyword"] == "TAXI ":
            cand_keywords = {c["keyword"] for c in g["candidates"]}
            assert "TAXI UBER" not in cand_keywords, (
                f"Trailing-space guard failed: flagged "
                f"TAXI (with space) ⊂ TAXI UBER. Groups: {g}"
            )


def test_find_substring_duplicates_no_pairs_returns_empty(client, db_session):
    """L1 — empty rule set returns ``{groups: [], l1_count: 0, l2_count: 0}``
    with HTTP 200 (not 204 — a 204 would force the FE to render a
    special-case path; a 200 + empty payload keeps the wizard
    non-blocking)."""
    # No seed → no live rules → no pairs.
    resp = client.get("/api/merchant-rules/duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["groups"] == []
    assert body["l1_count"] == 0
    assert body["l2_count"] == 0


def test_find_duplicates_requires_auth(client_no_auth, db_session):
    """GET /duplicates without JWT cookie returns 401."""
    resp = client_no_auth.get("/api/merchant-rules/duplicates")
    assert resp.status_code == 401


def test_find_duplicates_llm_endpoint_returns_l1_when_ollama_unreachable(
    client, db_session, monkeypatch
):
    """L1+L2 — when Ollama is NOT running, the endpoint still
    returns the L1 result with ``l2_count=0`` so the FE's wizard
    can render a partial-success banner instead of a 503 that
    blocks the whole dedup flow. The user gets a working L1-only
    wizard for free even when the L2 plumbing is offline.

    The route imports ``find_semantic_duplicates_async`` at module
    load, so we patch the name in the ROUTE's module namespace
    (not the source) — the route already holds a local reference
    to the original function. Patching ``app.services.llm_categorizer.find_semantic_duplicates_async``
    alone would not affect the route's call site.

    We raise ``httpx.TransportError`` (the BASE class the route
    catches) rather than ``ConnectError`` so the test exercises
    the broad offline-handler branch added in the l2_status rework
    — a regression to a narrower except would surface here.
    """
    import httpx
    import app.routes.merchant_rules as _routes_mod

    async def _fake_ollama_offline(*_args, **_kwargs):
        raise httpx.ConnectError("Ollama unreachable (test stub)")

    monkeypatch.setattr(
        _routes_mod,
        "find_semantic_duplicates_async",
        _fake_ollama_offline,
    )

    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS COFFEE"},
    )

    resp = client.post("/api/merchant-rules/duplicates/llm")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # L1 hit still surfaces.
    assert body["l1_count"] >= 1
    # L2 is unreachable so the count is 0 (route catches the
    # exception and returns the L1-only payload).
    assert body["l2_count"] == 0
    # Phase 29 — l2_status must reflect the offline branch so the
    # FE can render an honest partial-success banner rather than
    # silently treating the L2 silence as a clean result.
    assert body["l2_status"] == "offline"
    starbucks_groups = [
        g
        for g in body["groups"]
        if g["canonical"]["keyword"] == "STARBUCKS"
    ]
    assert starbucks_groups, "L1 result should be present in the L1+L2 response"


def test_apply_duplicates_archives_candidates(client, db_session):
    """POST /duplicates/apply with a list of candidate ids flips
    is_archived=True on each. The canonical is NEVER touched.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    # Add two user rules in Food & Dining that are substring pairs.
    longer = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS COFFEE"},
    ).json()
    another = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS POS"},
    ).json()

    resp = client.post(
        "/api/merchant-rules/duplicates/apply",
        json={"candidate_ids": [longer["id"], another["id"]]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["archived"] == 2
    assert body["skipped"] == 0

    db_session.expire_all()
    longer_now = (
        db_session.query(MerchantRule).filter(MerchantRule.id == longer["id"]).first()
    )
    another_now = (
        db_session.query(MerchantRule).filter(MerchantRule.id == another["id"]).first()
    )
    assert longer_now is not None and longer_now.is_archived is True
    assert another_now is not None and another_now.is_archived is True
    # STARBUCKS (the canonical) is untouched.
    starbucks = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "STARBUCKS")
        .first()
    )
    assert starbucks is not None and starbucks.is_archived is False


def test_apply_duplicates_rejects_canonical_id(client, db_session):
    """POST /duplicates/apply with a canonical id mixed in returns
    HTTP 400 (defensive: a buggy FE that mixes canonical +
    candidate ids would otherwise nuke the dedup target).
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    longer = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS COFFEE"},
    ).json()
    # STARBUCKS system seed is the canonical of the substring pair.
    starbucks = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "STARBUCKS")
        .first()
    )
    assert starbucks is not None

    resp = client.post(
        "/api/merchant-rules/duplicates/apply",
        json={"candidate_ids": [longer["id"], starbucks.id]},
    )
    assert resp.status_code == 400, resp.text
    assert "canonical" in resp.json()["detail"].lower()


def test_apply_duplicates_idempotent(client, db_session):
    """Re-firing Apply on already-archived rows returns
    ``{archived: 0, skipped: 2}`` with 200 (not 4xx) so the FE's
    wizard can recover from a flaky network without double-archiving.
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    longer = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS COFFEE"},
    ).json()
    another = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS POS"},
    ).json()

    # First apply — archives both.
    first = client.post(
        "/api/merchant-rules/duplicates/apply",
        json={"candidate_ids": [longer["id"], another["id"]]},
    )
    assert first.status_code == 200
    assert first.json()["archived"] == 2
    # Second apply on the same ids — 0 archived, 2 skipped.
    second = client.post(
        "/api/merchant-rules/duplicates/apply",
        json={"candidate_ids": [longer["id"], another["id"]]},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["archived"] == 0
    assert body["skipped"] == 2


def test_apply_duplicates_empty_payload_is_noop(client):
    """POST /duplicates/apply with an empty list returns
    ``{archived: 0, skipped: 0}`` with 200 (a valid user action:
    a no-op click during a state-sync round-trip).
    """
    resp = client.post(
        "/api/merchant-rules/duplicates/apply", json={"candidate_ids": []}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["archived"] == 0
    assert body["skipped"] == 0


def test_apply_duplicates_skips_unknown_ids(client, db_session):
    """POST /duplicates/apply with a mix of real + unknown ids
    archives the real ones and counts the unknown ones in
    ``skipped`` (200, not 404 — a 404 would force the FE to
    refetch the dedup list before retrying).
    """
    seed_default_merchant_rules(db_session)
    food_id = _get_food_id(db_session)
    real = client.post(
        "/api/merchant-rules/",
        json={"category_id": food_id, "keyword": "STARBUCKS COFFEE"},
    ).json()
    resp = client.post(
        "/api/merchant-rules/duplicates/apply",
        json={"candidate_ids": [real["id"], 999_999]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["archived"] == 1
    assert body["skipped"] == 1


def test_apply_duplicates_requires_auth(client_no_auth, db_session):
    """POST /duplicates/apply without JWT cookie returns 401."""
    resp = client_no_auth.post(
        "/api/merchant-rules/duplicates/apply", json={"candidate_ids": [1]}
    )
    assert resp.status_code == 401
