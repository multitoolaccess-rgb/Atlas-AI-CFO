# services/rules-service/tests/test_llm_category_proposals.py
#
# Phase 30h — LLM Pass-4 new-category proposals + accept flow.
#
# Proposal boundary tests (the high bar that keeps the feature from
# becoming noise):
#   1. A confident (>= 0.85) non-canonical proposal surfaces with
#      ``is_new=True`` + ``proposed_category`` / ``proposed_parent``.
#   2. A proposal below the confidence floor is NOT surfaced — the row
#      coerces to ``Other`` (existing behaviour).
#   3. A ``new_category`` that is already canonical is NOT a proposal.
#   4. When the LLM also picked a canonical ``category``, the canonical
#      wins and the proposal is ignored.
#   5. A non-canonical ``category`` with no ``new_category`` still
#      coerces to ``Other`` (backward compat).
#
# Accept-flow boundary tests (creates category + rule + tags txn):
#   6. Accepting creates the category (+ parent), the ``llm``-source
#      merchant rule, and tags the transaction in one commit.
#   7. Repeat accept is idempotent (reuses category + rule).
#   8. Missing parent → 404 (proposals nest only under existing cats).
#   9. A transaction the user does not own → 404.
#  10. Accepting without a keyword creates no rule, just tags.
import pytest

from app.services.categorizer import seed_default_categories


@pytest.fixture(autouse=True)
def _clear_llm_prompt_cache():
    from app.services.llm_categorizer import clear_prompt_cache

    clear_prompt_cache()
    yield
    clear_prompt_cache()


# ---------------------------------------------------------------
# Helpers (mirror test_routes_categorize_llm_batch.py).
# ---------------------------------------------------------------
def mock_ollama_chat(monkeypatch, response_bodies: list[dict]):
    state = {"calls": 0, "response_bodies": response_bodies}

    def _stub(prompt: str, *, model: str = "qwen2.5-coder:latest", **kwargs) -> dict:
        idx = state["calls"]
        state["calls"] += 1
        return state["response_bodies"][idx]

    monkeypatch.setattr(
        "app.services.llm_categorizer._post_ollama_chat", _stub
    )
    return state


def _seed_txn(client, db_session, make_account, make_transaction, description="PETSMART"):
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Proposal Account")
    db_session.add(account)
    db_session.flush()
    txn = make_transaction(account_id=account.id, description=description, amount=-45.00)
    db_session.add(txn)
    db_session.commit()
    return txn.id


# ---------------------------------------------------------------
# Proposal gating
# ---------------------------------------------------------------
def test_confident_new_category_surfaces_as_proposal(
    client, db_session, make_account, make_transaction, monkeypatch,
):
    """A high-confidence non-canonical proposal (Pet Supplies under
    Shopping) is surfaced with is_new=True, not coerced to Other."""
    txn_id = _seed_txn(client, db_session, make_account, make_transaction)
    mock_ollama_chat(monkeypatch, [{
        "categories": [{
            "transaction_id": txn_id,
            "category": "Pet Supplies",
            "new_category": "Pet Supplies",
            "new_category_parent": "Shopping",
            "confidence": 0.92,
        }],
    }])

    resp = client.post("/api/categorize/llm", json={"transaction_ids": [txn_id]})
    assert resp.status_code == 200, resp.text
    s = resp.json()["suggestions"][0]
    assert s["is_new"] is True
    assert s["proposed_category"] == "Pet Supplies"
    assert s["proposed_parent"] == "Shopping"
    # The safe fallback if the user rejects.
    assert s["suggested_category"] == "Other"


def test_proposal_below_confidence_floor_is_not_surfaced(
    client, db_session, make_account, make_transaction, monkeypatch,
):
    """0.7 < 0.85 floor → the row coerces to Other (no proposal)."""
    txn_id = _seed_txn(client, db_session, make_account, make_transaction)
    mock_ollama_chat(monkeypatch, [{
        "categories": [{
            "transaction_id": txn_id,
            "category": "Gym Memberships",
            "new_category": "Gym Memberships",
            "new_category_parent": "Health",
            "confidence": 0.7,
        }],
    }])

    resp = client.post("/api/categorize/llm", json={"transaction_ids": [txn_id]})
    assert resp.status_code == 200, resp.text
    s = resp.json()["suggestions"][0]
    assert s.get("is_new") is not True
    assert s["suggested_category"] == "Other"
    assert s["coerced"] is True


def test_canonical_new_category_is_not_a_proposal(
    client, db_session, make_account, make_transaction, monkeypatch,
):
    """new_category=Groceries is already canonical — nothing to create."""
    txn_id = _seed_txn(client, db_session, make_account, make_transaction)
    mock_ollama_chat(monkeypatch, [{
        "categories": [{
            "transaction_id": txn_id,
            "category": "Groceries",
            "new_category": "Groceries",
            "confidence": 0.95,
        }],
    }])

    resp = client.post("/api/categorize/llm", json={"transaction_ids": [txn_id]})
    assert resp.status_code == 200, resp.text
    s = resp.json()["suggestions"][0]
    assert s.get("is_new") is not True
    assert s["suggested_category"] == "Groceries"


def test_canonical_category_wins_over_proposal(
    client, db_session, make_account, make_transaction, monkeypatch,
):
    """The LLM picked a canonical fit (Shopping) AND proposed a new
    category — trust the canonical fit, ignore the proposal."""
    txn_id = _seed_txn(client, db_session, make_account, make_transaction)
    mock_ollama_chat(monkeypatch, [{
        "categories": [{
            "transaction_id": txn_id,
            "category": "Shopping",
            "new_category": "Pet Supplies",
            "new_category_parent": "Shopping",
            "confidence": 0.9,
        }],
    }])

    resp = client.post("/api/categorize/llm", json={"transaction_ids": [txn_id]})
    assert resp.status_code == 200, resp.text
    s = resp.json()["suggestions"][0]
    assert s.get("is_new") is not True
    assert s["suggested_category"] == "Shopping"


def test_non_canonical_without_new_category_still_coerces(
    client, db_session, make_account, make_transaction, monkeypatch,
):
    """Backward compat: a non-canonical category with no new_category
    still coerces to Other with a low-confidence marker."""
    txn_id = _seed_txn(client, db_session, make_account, make_transaction)
    mock_ollama_chat(monkeypatch, [{
        "categories": [{
            "transaction_id": txn_id,
            "category": "Pet Supplies",
            "confidence": 0.9,
        }],
    }])

    resp = client.post("/api/categorize/llm", json={"transaction_ids": [txn_id]})
    assert resp.status_code == 200, resp.text
    s = resp.json()["suggestions"][0]
    assert s.get("is_new") is not True
    assert s["suggested_category"] == "Other"
    assert s["coerced"] is True


# ---------------------------------------------------------------
# Accept flow
# ---------------------------------------------------------------
def test_accept_creates_category_rule_and_tags_txn(
    client, db_session, make_account, make_transaction,
):
    """Accepting a proposal creates the sub-category under its parent,
    an ``llm``-source rule, and tags the transaction — one response."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Accept Account")
    db_session.add(account)
    db_session.flush()
    txn = make_transaction(account_id=account.id, description="PETSMART", amount=-45.00)
    db_session.add(txn)
    db_session.commit()
    txn_id = txn.id

    resp = client.post("/api/categories/accept-proposal", json={
        "transaction_id": txn_id,
        "proposed_category": "Pet Supplies",
        "proposed_parent": "Shopping",
        "keyword": "PETSMART",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category_created"] is True
    assert body["category_name"] == "Pet Supplies"
    assert body["parent_name"] == "Shopping"
    assert body["rule_created"] is True
    assert body["rule_id"] is not None

    # The transaction is tagged with the new category.
    db_session.refresh(txn)
    assert txn.category_id == body["category_id"]

    # The rule exists with source='llm' (the reserved provenance).
    from app.models import MerchantRule
    rule = db_session.query(MerchantRule).filter(
        MerchantRule.id == body["rule_id"]
    ).one()
    assert rule.source == "llm"
    assert rule.keyword == "PETSMART"


def test_accept_is_idempotent(client, db_session, make_account, make_transaction):
    """Re-accepting the same proposal reuses the category + rule."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Accept Account 2")
    db_session.add(account)
    db_session.flush()
    txn = make_transaction(account_id=account.id, description="CHEWY", amount=-30.00)
    db_session.add(txn)
    db_session.commit()
    txn_id = txn.id

    payload = {
        "transaction_id": txn_id,
        "proposed_category": "Pet Supplies",
        "proposed_parent": "Shopping",
        "keyword": "CHEWY",
    }
    first = client.post("/api/categories/accept-proposal", json=payload)
    assert first.status_code == 201, first.text
    second = client.post("/api/categories/accept-proposal", json=payload)
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["category_created"] is False
    assert body["rule_created"] is False
    assert body["category_id"] == first.json()["category_id"]


def test_accept_missing_parent_404(client, db_session, make_account, make_transaction):
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Accept Account 3")
    db_session.add(account)
    db_session.flush()
    txn = make_transaction(account_id=account.id, description="XYZ", amount=-10.00)
    db_session.add(txn)
    db_session.commit()

    resp = client.post("/api/categories/accept-proposal", json={
        "transaction_id": txn.id,
        "proposed_category": "Mystery",
        "proposed_parent": "Does Not Exist",
    })
    assert resp.status_code == 404
    assert "Parent category" in resp.json()["detail"]


def test_accept_unowned_transaction_404(client, db_session, make_account, make_transaction):
    """A transaction owned by another user must never be touched."""
    from app.models import User

    seed_default_categories(db_session)
    db_session.commit()
    other_user = User(
        local_user_sub="other-proposal-user", email="other@example.com",
        hashed_password="x", is_active=True,
    )
    db_session.add(other_user)
    db_session.flush()
    other_acc = make_account(account_name="Other Bank")
    # Re-point at the other user directly via ORM.
    other_acc.user_id = other_user.id
    db_session.add(other_acc)
    db_session.flush()
    txn = make_transaction(account_id=other_acc.id, description="SECRET", amount=-5.00)
    db_session.add(txn)
    db_session.commit()

    resp = client.post("/api/categories/accept-proposal", json={
        "transaction_id": txn.id,
        "proposed_category": "Secret Cat",
    })
    assert resp.status_code == 404


def test_accept_without_keyword_creates_no_rule(client, db_session, make_account, make_transaction):
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Accept Account 4")
    db_session.add(account)
    db_session.flush()
    txn = make_transaction(account_id=account.id, description="ONE OFF", amount=-8.00)
    db_session.add(txn)
    db_session.commit()

    resp = client.post("/api/categories/accept-proposal", json={
        "transaction_id": txn.id,
        "proposed_category": "One Off Cat",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category_created"] is True
    assert body["rule_id"] is None
    assert body["rule_created"] is False
    db_session.refresh(txn)
    assert txn.category_id == body["category_id"]
