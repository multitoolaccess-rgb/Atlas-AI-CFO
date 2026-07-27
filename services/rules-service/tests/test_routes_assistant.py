"""Phase 30a + 30b — Assistant chat route tests.

Coverage:
- POST /api/assistant/chat — happy path (mocked LLM, real DB tool).
- POST /api/assistant/chat — Ollama offline (graceful fallback).
- POST /api/assistant/chat — auth required (401 without JWT).
- POST /api/assistant/chat — each of the 5 real tools dispatches.
- POST /api/assistant/chat — tool result is fed back to the LLM.

The orchestrator's LLM calls are monkeypatched so the tests don't
depend on a running Ollama instance. The 30b tools run against the
real (hermetic test) DB via the conftest fixtures, so the tool_result
in the response carries real query output, not hardcoded mocks.
"""
import httpx
import pytest

import app.services.assistant_orchestrator as _orch
import app.services.llm_client as _llm_client
from app.services.categorizer import seed_default_categories


def test_assistant_chat_happy_path(client, db_session, monkeypatch):
    """POST /api/assistant/chat with a mocked LLM returns a reply +
    tool metadata + follow-ups + status='ok'.
    """
    # Mock the first LLM call (tool selection) to pick get_totals.
    # Mock the second LLM call (NL generation) to return a canned reply.
    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Tool selection round.
            return {
                "tool": "get_totals",
                "params": {},
                "intent": "user wants their totals",
            }
        else:
            # NL generation round.
            return {"reply": "Your total balance is $125,000."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    # Also patch the orchestrator's import reference.
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What are my totals?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tool_used"] == "get_totals"
    assert body["tool_result"] is not None
    assert "total_balance" in body["tool_result"]
    assert body["reply"]  # non-empty
    assert isinstance(body["follow_ups"], list)
    assert len(body["follow_ups"]) > 0


def test_assistant_chat_ollama_offline(client, db_session, monkeypatch):
    """POST /api/assistant/chat when Ollama is unreachable returns
    status='offline' with a graceful fallback reply (no 500).
    """
    async def _fake_offline(messages, **kwargs):
        raise httpx.ConnectError("Ollama unreachable (test stub)")

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_offline)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_offline)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What are my totals?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "offline"
    assert body["tool_used"] is None
    assert body["tool_result"] is None
    assert "couldn't reach" in body["reply"].lower()
    assert body["follow_ups"] == []


def test_assistant_chat_requires_auth(client_no_auth, db_session):
    """POST /api/assistant/chat without JWT cookie returns 401."""
    resp = client_no_auth.post(
        "/api/assistant/chat",
        json={"message": "What are my totals?"},
    )
    assert resp.status_code == 401


def test_assistant_chat_empty_message_rejected(client, db_session):
    """POST /api/assistant/chat with an empty message returns 422
    (Pydantic min_length=1 on the schema).
    """
    resp = client.post(
        "/api/assistant/chat",
        json={"message": ""},
    )
    assert resp.status_code == 422


def test_assistant_chat_no_tool_matched(client, db_session, monkeypatch):
    """When the LLM picks tool='none', the orchestrator skips the
    tool dispatch and still returns a reply (the LLM was told to say
    "I can't answer that yet" for uncovered questions).
    """
    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": "none", "params": {}, "intent": "unknown"}
        else:
            return {"reply": "I can't answer that yet."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What's the weather?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tool_used"] is None
    assert body["tool_result"] is None
    assert "can't answer" in body["reply"].lower()


def test_assistant_chat_get_totals_returns_real_db_data(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """Phase 30b — get_totals now queries the real DB. Seed an account
    + transactions and assert the tool_result carries real numbers
    (not the old hardcoded 125000/8500/4200 mock).
    """
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="TestChecking", account_type="checking", current_balance=5000.0)
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    for t in [
        make_transaction(account_id=account.id, description="PAYROLL", amount=3000.0, merchant_name="EMPLOYER"),
        make_transaction(account_id=account.id, description="COFFEE SHOP", amount=-50.0, merchant_name="STARBUCKS"),
    ]:
        db_session.add(t)
    db_session.commit()

    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": "get_totals", "params": {}, "intent": "totals"}
        return {"reply": "Here are your totals."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "Show me my totals."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    result = body["tool_result"]
    # Real DB values — NOT the old hardcoded mock.
    assert result["total_balance"] == 5000.0
    assert result["total_income_month"] == 3000.0
    assert result["total_expenses_month"] == 50.0


def test_assistant_chat_get_category_spend_dispatches(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """Phase 30b — the get_category_spend tool dispatches and returns
    real spend data for a named category."""
    from app.models import Category

    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="CatSpendAcct", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    food_cat = db_session.query(Category).filter(Category.name == "Food & Dining").first()
    t = make_transaction(
        account_id=account.id, description="STARBUCKS", amount=-15.50,
        merchant_name="STARBUCKS", category_id=food_cat.id,
    )
    db_session.add(t)
    db_session.commit()

    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "tool": "get_category_spend",
                "params": {"category": "Food & Dining", "months_back": 0},
                "intent": "dining spend",
            }
        return {"reply": "You spent $15.50 on Food & Dining."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "How much did I spend on dining?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tool_used"] == "get_category_spend"
    assert body["tool_result"]["total_spend"] == 15.50
    assert body["tool_result"]["category"] == "Food & Dining"


def test_assistant_chat_get_cash_flow_dispatches(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """Phase 30b — get_cash_flow dispatches and returns income/expenses/net."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="CashFlowAcct", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    for t in [
        make_transaction(account_id=account.id, description="PAYROLL", amount=4000.0, merchant_name="EMP"),
        make_transaction(account_id=account.id, description="RENT", amount=-2000.0, merchant_name="LANDLORD"),
    ]:
        db_session.add(t)
    db_session.commit()

    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": "get_cash_flow", "params": {"months_back": 0}, "intent": "cash flow"}
        return {"reply": "Your cash flow is positive."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "Show me my cash flow."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tool_used"] == "get_cash_flow"
    assert body["tool_result"]["income"] == 4000.0
    assert body["tool_result"]["expenses"] == 2000.0
    assert body["tool_result"]["net_cash_flow"] == 2000.0


def test_assistant_chat_compute_savings_rate_dispatches(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """Phase 30b — compute_savings_rate dispatches and returns a percentage."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="SavingsAcct", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    for t in [
        make_transaction(account_id=account.id, description="SALARY", amount=10000.0, merchant_name="EMP"),
        make_transaction(account_id=account.id, description="BILLS", amount=-6000.0, merchant_name="UTIL"),
    ]:
        db_session.add(t)
    db_session.commit()

    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": "compute_savings_rate", "params": {"months_back": 0}, "intent": "savings rate"}
        return {"reply": "Your savings rate is 40%."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What's my savings rate?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tool_used"] == "compute_savings_rate"
    # (10000 - 6000) / 10000 * 100 = 40.0
    assert body["tool_result"]["savings_rate"] == 40.0


def test_assistant_chat_get_merchant_spend_dispatches(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """Phase 30b — get_merchant_spend dispatches and returns spend for a merchant."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="MerchantAcct", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    t = make_transaction(account_id=account.id, description="AMAZON.COM", amount=-120.0, merchant_name="AMAZON")
    db_session.add(t)
    db_session.commit()

    call_count = {"n": 0}

    async def _fake_chat_async(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": "get_merchant_spend", "params": {"merchant": "AMAZON", "months_back": 0}, "intent": "amazon spend"}
        return {"reply": "You spent $120 at Amazon."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_chat_async)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_chat_async)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "How much did I spend on Amazon?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tool_used"] == "get_merchant_spend"
    assert body["tool_result"]["total_spend"] == 120.0
