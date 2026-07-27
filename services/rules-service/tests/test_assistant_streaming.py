"""Phase 30e — SSE streaming endpoint tests.

Verifies the ``POST /api/assistant/chat/stream`` endpoint yields the
correct SSE event sequence: conversation → thinking → tool_call →
tool_result → reply_chunk(s) → done.

The orchestrator's LLM calls are monkeypatched so the tests don't
depend on a running Ollama instance. The SSE stream is consumed via
the TestClient's streaming response support.
"""
import httpx
import pytest

import app.services.assistant_orchestrator as _orch
import app.services.llm_client as _llm_client
from app.models import AssistantConversation, AssistantMessage
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


def _parse_sse_stream(raw_text: str) -> list[dict]:
    """Parse raw SSE text into a list of {event, data} dicts."""
    events = []
    for block in raw_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = "message"
        data_str = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data_str = line[len("data: "):]
        if data_str:
            import json
            events.append({"event": event_type, "data": json.loads(data_str)})
    return events


def test_stream_yields_correct_event_sequence(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """POST /api/assistant/chat/stream yields conversation → thinking →
    tool_call → tool_result → reply_chunk(s) → done."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Test", account_type="checking", current_balance=1000.0)
    db_session.add(account)
    db_session.commit()

    mock = _make_mock_chat(reply="Your balance is $1000.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "What are my totals?"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    event_types = [e["event"] for e in events]

    # Verify the event sequence.
    assert "conversation" in event_types
    assert "thinking" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "reply_chunk" in event_types
    assert "done" in event_types

    # The conversation event should be first.
    assert event_types[0] == "conversation"

    # The done event should be last.
    assert event_types[-1] == "done"

    # Verify the done event has the full response.
    done_event = [e for e in events if e["event"] == "done"][0]
    assert done_event["data"]["reply"] == "Your balance is $1000."
    assert done_event["data"]["status"] == "ok"
    assert done_event["data"]["conversation_id"] is not None
    assert done_event["data"]["tool_used"] == "get_totals"

    # Verify the tool_result event has the tool result.
    tool_result_event = [e for e in events if e["event"] == "tool_result"][0]
    assert tool_result_event["data"]["tool"] == "get_totals"
    assert "total_balance" in tool_result_event["data"]["result"]


def test_stream_persists_conversation_and_messages(
    client, db_session, monkeypatch, make_account
):
    """The streaming endpoint persists the conversation + messages just
    like the blocking endpoint."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    mock = _make_mock_chat(reply="Reply from stream.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "Streamed question"},
    ) as response:
        assert response.status_code == 200
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    done_event = [e for e in events if e["event"] == "done"][0]
    conv_id = done_event["data"]["conversation_id"]
    assert conv_id is not None

    # Verify the conversation + 2 messages were persisted.
    conv = db_session.query(AssistantConversation).filter(
        AssistantConversation.id == conv_id
    ).first()
    assert conv is not None
    assert conv.title == "Streamed question"

    msgs = (
        db_session.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv_id)
        .order_by(AssistantMessage.id.asc())
        .all()
    )
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "Streamed question"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Reply from stream."


def test_stream_offline_yields_done_with_offline_status(
    client, db_session, monkeypatch, make_account
):
    """When Ollama is unreachable, the stream yields a done event with
    status='offline'."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    async def _fake_offline(messages, **kwargs):
        raise httpx.ConnectError("Ollama unreachable (test stub)")

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake_offline)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake_offline)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "Question while offline"},
    ) as response:
        assert response.status_code == 200
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    event_types = [e["event"] for e in events]

    # Should have conversation + done (with offline status).
    assert "conversation" in event_types
    assert "done" in event_types
    assert "tool_call" not in event_types
    assert "tool_result" not in event_types

    done_event = [e for e in events if e["event"] == "done"][0]
    assert done_event["data"]["status"] == "offline"
    assert "Ollama" in done_event["data"]["reply"]


def test_stream_requires_auth(client_no_auth, db_session):
    """POST /api/assistant/chat/stream without auth returns 401."""
    resp = client_no_auth.post(
        "/api/assistant/chat/stream",
        json={"message": "test"},
    )
    assert resp.status_code == 401


def test_stream_with_conversation_id_appends_to_existing(
    client, db_session, monkeypatch, make_account
):
    """The streaming endpoint respects conversation_id for multi-turn."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    # First message via the blocking endpoint to create a conversation.
    mock1 = _make_mock_chat(reply="First reply.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock1)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock1)

    resp = client.post("/api/assistant/chat", json={"message": "First question"})
    conv_id = resp.json()["conversation_id"]

    # Second message via the stream endpoint with the same conversation_id.
    mock2 = _make_mock_chat(reply="Second reply from stream.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock2)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock2)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "Second question", "conversation_id": conv_id},
    ) as response:
        assert response.status_code == 200
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    conv_event = [e for e in events if e["event"] == "conversation"][0]
    assert conv_event["data"]["conversation_id"] == conv_id

    done_event = [e for e in events if e["event"] == "done"][0]
    assert done_event["data"]["conversation_id"] == conv_id

    # Verify 4 messages total (2 from first + 2 from second).
    msgs = (
        db_session.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv_id)
        .order_by(AssistantMessage.id.asc())
        .all()
    )
    assert len(msgs) == 4
    assert msgs[2].content == "Second question"
    assert msgs[3].content == "Second reply from stream."


def test_stream_reply_chunks_form_full_reply(
    client, db_session, monkeypatch, make_account
):
    """The reply_chunk events, when concatenated, form the full reply."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    full_reply = "Your savings rate is 74 percent this month."
    mock = _make_mock_chat(reply=full_reply)
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "What is my savings rate?"},
    ) as response:
        assert response.status_code == 200
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    chunk_events = [e for e in events if e["event"] == "reply_chunk"]
    assert len(chunk_events) > 0

    # Concatenate all chunks.
    assembled = "".join(e["data"]["chunk"] for e in chunk_events)
    # The assembled reply should match the full reply (with trailing space handling).
    assert assembled.strip() == full_reply.strip()
