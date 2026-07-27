"""Phase 30b — Categorizer custom-category fix regression test.

Locks the fix for the user-reported bug:
  "I have a rule for servicemac but when I go to activity, it is still
   showing as untagged. I clicked auto categorize, still the same."

Root cause: ``build_category_lookup`` only loaded the 12 default seed
category names. A user-created custom category (e.g. "Mortgage") with
an active merchant rule (keyword "SERVICEMAC") was NOT in the seed
dict, so ``lookup.get("Mortgage")`` returned ``None`` and the rule
silently failed — the transaction stayed untagged.

The fix unions the seed names with the category ids referenced by
ACTIVE merchant rules so every resolvable category is in the lookup.

This test seeds a custom "Mortgage" category + a "SERVICEMAC" rule,
runs the categorizer on a matching transaction, and asserts the
transaction is tagged.
"""
import pytest

from app.models import Category, MerchantRule, Transaction
from app.services.categorizer import (
    build_category_lookup,
    categorize_transactions,
    seed_default_categories,
    seed_default_merchant_rules,
)


@pytest.fixture
def seeded_custom_category(client, db_session):
    """Seed defaults + a custom 'Mortgage' category + a SERVICEMAC rule."""
    seed_default_categories(db_session)
    db_session.commit()

    # Create a custom category (NOT in the default seed). "Mortgage"
    # became a default category in the hierarchical-categories refactor,
    # so use a distinct custom name.
    mortgage_cat = Category(
        name="Custom Mortgage",
        description="Mortgage payments",
        icon="🏠",
        color="#8b5cf6",
    )
    db_session.add(mortgage_cat)
    db_session.commit()
    db_session.refresh(mortgage_cat)

    seed_default_merchant_rules(db_session)

    # Add a merchant rule: keyword "SERVICEMAC" → Custom Mortgage category.
    rule = MerchantRule(
        category_id=mortgage_cat.id,
        keyword="SERVICEMAC",
        is_archived=False,
        source="manual",
        priority=100,
    )
    db_session.add(rule)
    db_session.commit()

    return mortgage_cat


def test_build_category_lookup_includes_custom_category(
    client, db_session, seeded_custom_category
):
    """build_category_lookup must include custom categories referenced
    by active merchant rules, not just the default seed names."""
    lookup = build_category_lookup(db_session)
    # The 12 default seed categories should all be present.
    assert "Food & Dining" in lookup
    assert "Other" in lookup
    # The custom category must ALSO be present (the bug: it was missing).
    assert "Custom Mortgage" in lookup
    assert lookup["Custom Mortgage"].name == "Custom Mortgage"


def test_categorize_tags_transaction_matching_custom_category_rule(
    client, db_session, seeded_custom_category, make_account, make_transaction
):
    """A transaction whose description contains "SERVICEMAC" must be
    tagged with the custom "Mortgage" category after categorize_transactions
    runs — the core regression test for the user-reported bug."""
    account = make_account(account_name="Checking", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    txn = make_transaction(
        account_id=account.id,
        description="SERVICEMAC PMT DES:MTGE PAYMT ID:8014021467",
        amount=-1846.85,
        merchant_name=None,
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)
    txn_id = txn.id
    assert txn.category_id is None  # pre-condition: untagged

    categorized, skipped, _conflicts = categorize_transactions(db_session, [txn])
    db_session.commit()

    assert categorized == 1, "Expected 1 transaction categorized"
    # Re-query the transaction from DB to confirm the category_id was
    # written (refresh can fail if the ORM object was detached during
    # the categorizer's flush cycle).
    updated = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert updated is not None
    assert updated.category_id == seeded_custom_category.id


def test_categorize_does_not_tag_when_rule_is_archived(
    client, db_session, seeded_custom_category, make_account, make_transaction
):
    """An ARCHIVED merchant rule must NOT categorize matching transactions.
    The build_category_lookup fix loads categories for ACTIVE rules only;
    archived rules should not pollute the lookup."""
    # Archive the SERVICEMAC rule.
    rule = (
        db_session.query(MerchantRule)
        .filter(MerchantRule.keyword == "SERVICEMAC")
        .first()
    )
    assert rule is not None
    rule.is_archived = True
    db_session.commit()

    account = make_account(account_name="Checking2", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    txn = make_transaction(
        account_id=account.id,
        description="SERVICEMAC PMT DES:MTGE PAYMT",
        amount=-1000.00,
        merchant_name=None,
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)
    txn_id = txn.id

    categorized, skipped, _conflicts = categorize_transactions(db_session, [txn])
    db_session.commit()
    updated = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert updated is not None

    # The SERVICEMAC rule is archived, so the transaction should NOT be
    # tagged with Mortgage. It may match a different rule (MORTGAGE is
    # in the default seed under Bills & Utilities) — that's fine; the
    # key assertion is it's NOT tagged with the custom Mortgage category.
    assert updated.category_id != seeded_custom_category.id, (
        "Archived rule should not categorize into the custom category"
    )


def test_build_category_lookup_with_no_active_rules(client, db_session):
    """When there are zero active merchant rules, build_category_lookup
    still loads the default seed categories (the union with an empty
    rule set falls back to seed-only)."""
    seed_default_categories(db_session)
    db_session.commit()
    # No merchant rules at all.
    lookup = build_category_lookup(db_session)
    assert "Food & Dining" in lookup
    assert "Other" in lookup
