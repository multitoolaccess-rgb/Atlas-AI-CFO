"""Phase 30c — Conversation persistence + multi-turn + search_history tests.

Coverage:
- POST /api/assistant/chat creates a conversation on first message.
- POST /api/assistant/chat with conversation_id appends to existing.
- GET /api/assistant/conversations lists the user's conversations.
- GET /api/assistant/conversations/{id} returns messages in order.
- search_history tool finds past messages by keyword.
- Auto-prune deletes conversations beyond 50 per user.
- Offline messages are still persisted.
- Cross-user isolation (user A can't see user B's conversations).

The orchestrator's LLM calls are monkeypatched so the tests don't
depend on a running Ollama instance. Messages are persisted to the
real (hermetic test) DB via the conftest fixtures.
"""
import httpx
import pytest

import app.services.assistant_orchestrator as _orch
import app.services.llm_client as _llm_client
from app.models import AssistantConversation, AssistantMessage, User
from app.services.categorizer import seed_default_categories


def _make_mock_chat(tool_name="get_totals", reply="Here are your totals."):
    """Return a mock async function that simulates the two LLM rounds."""
    call_count = {"n": 0}

    async def _fake(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": tool_name, "params": {}, "intent": "test"}
        return {"reply": reply}

    return _fake


def test_chat_creates_conversation_on_first_message(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """POST /api/assistant/chat without conversation_id creates a new
    conversation and returns its id + title."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Test", account_type="checking", current_balance=1000.0)
    db_session.add(account)
    db_session.commit()

    mock = _make_mock_chat(reply="Your balance is $1000.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What are my totals?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conversation_id"] is not None
    assert body["conversation_title"] == "What are my totals?"
    assert body["status"] == "ok"

    # Verify the conversation + 2 messages (user + assistant) were persisted.
    conv_id = body["conversation_id"]
    conv = db_session.query(AssistantConversation).filter(
        AssistantConversation.id == conv_id
    ).first()
    assert conv is not None
    assert conv.title == "What are my totals?"

    msgs = (
        db_session.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv_id)
        .order_by(AssistantMessage.id.asc())
        .all()
    )
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "What are my totals?"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Your balance is $1000."


def test_chat_with_conversation_id_appends_to_existing(
    client, db_session, monkeypatch, make_account
):
    """POST /api/assistant/chat with conversation_id appends the message
    to the existing conversation (multi-turn)."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Test", account_type="checking")
    db_session.add(account)
    db_session.commit()

    # First message — creates a conversation.
    mock1 = _make_mock_chat(reply="Reply 1.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock1)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock1)

    resp1 = client.post(
        "/api/assistant/chat",
        json={"message": "First question"},
    )
    assert resp1.status_code == 200
    conv_id = resp1.json()["conversation_id"]
    assert conv_id is not None

    # Second message — should append to the same conversation.
    mock2 = _make_mock_chat(reply="Reply 2.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock2)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock2)

    resp2 = client.post(
        "/api/assistant/chat",
        json={"message": "Second question", "conversation_id": conv_id},
    )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == conv_id

    # Verify 4 messages total (2 user + 2 assistant).
    msgs = (
        db_session.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv_id)
        .order_by(AssistantMessage.id.asc())
        .all()
    )
    assert len(msgs) == 4
    assert msgs[0].content == "First question"
    assert msgs[1].content == "Reply 1."
    assert msgs[2].content == "Second question"
    assert msgs[3].content == "Reply 2."


def test_list_conversations_returns_user_conversations(
    client, db_session, monkeypatch, make_account
):
    """GET /api/assistant/conversations returns the user's conversations
    newest-first, without messages."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    mock = _make_mock_chat(reply="Reply.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    # Create 2 conversations.
    client.post("/api/assistant/chat", json={"message": "Question A"})
    client.post("/api/assistant/chat", json={"message": "Question B"})

    resp = client.get("/api/assistant/conversations")
    assert resp.status_code == 200
    convs = resp.json()
    assert len(convs) == 2
    # Newest first (by updated_at desc).
    assert convs[0]["title"] == "Question B"
    assert convs[1]["title"] == "Question A"
    # No messages in the list response.
    assert convs[0]["messages"] == []


def test_get_conversation_returns_messages_in_order(
    client, db_session, monkeypatch, make_account
):
    """GET /api/assistant/conversations/{id} returns the conversation
    with its messages in chronological order."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    mock = _make_mock_chat(reply="Reply to question.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    resp = client.post("/api/assistant/chat", json={"message": "My question"})
    conv_id = resp.json()["conversation_id"]

    resp2 = client.get(f"/api/assistant/conversations/{conv_id}")
    assert resp2.status_code == 200
    conv = resp2.json()
    assert conv["id"] == conv_id
    assert conv["title"] == "My question"
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][0]["content"] == "My question"
    assert conv["messages"][1]["role"] == "assistant"
    assert conv["messages"][1]["content"] == "Reply to question."


def test_get_conversation_404_for_nonexistent(
    client, db_session
):
    """GET /api/assistant/conversations/999 returns 404."""
    resp = client.get("/api/assistant/conversations/999")
    assert resp.status_code == 404


def test_offline_messages_are_persisted(
    client, db_session, monkeypatch, make_account
):
    """When Ollama is offline, the user + offline assistant messages
    are still persisted so the conversation history is intact."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    async def _fake_offline(messages, **kwargs):
        raise httpx.ConnectError("Ollama unreachable (test stub)")

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_offline)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_offline)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "Question while offline"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "offline"
    assert body["conversation_id"] is not None

    conv_id = body["conversation_id"]
    msgs = (
        db_session.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv_id)
        .all()
    )
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "Question while offline"
    assert msgs[1].role == "assistant"
    assert msgs[1].status == "offline"


def test_search_history_tool_finds_past_messages(
    client, db_session, monkeypatch, make_account
):
    """The search_history tool finds past conversation messages by keyword."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    # First, create a conversation with a known message.
    mock1 = _make_mock_chat(reply="You spent $200 on dining.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock1)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock1)
    client.post("/api/assistant/chat", json={"message": "How much on dining?"})

    # Now search for "dining" via the search_history tool.
    call_count = {"n": 0}

    async def _fake_search(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tool": "search_history", "params": {"query": "dining"}, "intent": "search"}
        return {"reply": "You asked about dining earlier."}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_search)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_search)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What did I ask about earlier?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool_used"] == "search_history"
    result = body["tool_result"]
    assert result["query"] == "dining"
    assert result["count"] > 0
    assert any("dining" in m["content"].lower() for m in result["matches"])


def test_auto_prune_deletes_old_conversations(
    client, db_session, monkeypatch, make_account
):
    """When a user exceeds MAX_CONVERSATIONS_PER_USER, the oldest
    conversations are hard-deleted.

    Uses a small MAX (3) via monkeypatch so the test doesn't create 55
    conversations (which would exhaust the mock's call_count + slow
    the suite). The prune logic is identical regardless of the MAX
    value — the test verifies the deletion + ordering, not the exact
    production threshold.
    """
    # Monkeypatch the MAX to 3 so we only need to create 5 conversations.
    monkeypatch.setattr(_orch, "MAX_CONVERSATIONS_PER_USER", 3)
    test_max = 3

    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    # Create test_max + 2 conversations.
    total = test_max + 2
    for i in range(total):
        # Each iteration needs a fresh mock so call_count resets.
        mock = _make_mock_chat(reply=f"Reply {i}.")
        monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
        monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)
        resp = client.post(
            "/api/assistant/chat",
            json={"message": f"Question {i}"},
        )
        assert resp.status_code == 200, f"Request {i} failed: {resp.text}"

    # Verify only test_max conversations remain.
    convs = (
        db_session.query(AssistantConversation)
        .filter(AssistantConversation.user_id == 1)
        .all()
    )
    assert len(convs) <= test_max, (
        f"Expected <= {test_max} conversations, got {len(convs)}"
    )

    # Verify the remaining conversations are the most recent ones.
    titles = {c.title for c in convs}
    assert f"Question {total - 1}" in titles  # most recent
    assert f"Question 0" not in titles  # oldest, should be pruned


def test_conversation_id_from_other_user_not_found(
    client, db_session, monkeypatch
):
    """A user can't append to a conversation owned by another user.
    The orchestrator falls through to creating a new conversation."""
    seed_default_categories(db_session)
    db_session.commit()

    # Create a real second owner before its conversation; SQLite FK checks
    # now mirror PostgreSQL rather than allowing an orphaned fixture row.
    db_session.add(User(id=999, local_user_sub="other-user", email="other@example.com", hashed_password="x"))
    db_session.commit()
    # Create a conversation owned by a different user (id=999).
    other_conv = AssistantConversation(user_id=999, title="Other user's conv")
    db_session.add(other_conv)
    db_session.commit()
    other_conv_id = other_conv.id

    mock = _make_mock_chat(reply="Reply.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    # The local user (id=1) sends a message with the other user's conv id.
    resp = client.post(
        "/api/assistant/chat",
        json={"message": "My message", "conversation_id": other_conv_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    # A NEW conversation should be created (different id).
    assert body["conversation_id"] != other_conv_id
    assert body["conversation_id"] is not None


def test_list_conversations_requires_auth(client_no_auth, db_session):
    """GET /api/assistant/conversations without auth returns 401."""
    resp = client_no_auth.get("/api/assistant/conversations")
    assert resp.status_code == 401


def test_get_conversation_requires_auth(client_no_auth, db_session):
    """GET /api/assistant/conversations/1 without auth returns 401."""
    resp = client_no_auth.get("/api/assistant/conversations/1")
    assert resp.status_code == 401
