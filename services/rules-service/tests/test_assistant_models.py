"""Phase 30f — Scout model picker + cold-start tests.

Covers:
- GET /api/assistant/models returns the installed models + default +
  loaded subset (with Ollama's /api/tags + /api/ps monkeypatched).
- GET /api/assistant/models returns an empty list (not 503) when
  Ollama is offline, so the FE can render a disabled picker.
- POST /api/assistant/warm pre-loads a model (status=warmed) and
  reports offline when Ollama is unreachable.
- The chat routes accept an explicit ``model`` and forward it to the
  orchestrator's LLM call.
- The stream emits a ``model_loading`` event when the chosen model is
  cold, and skips it when the model is already warm.

The orchestrator's LLM calls are monkeypatched so the tests don't
depend on a running Ollama instance.
"""
import httpx
import pytest

import app.routes.assistant as _assistant_routes
import app.services.assistant_orchestrator as _orch
import app.services.llm_client as _llm_client
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
    import json

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
            events.append({"event": event_type, "data": json.loads(data_str)})
    return events


# ---------------------------------------------------------------------
# GET /api/assistant/models
# ---------------------------------------------------------------------

def test_list_models_returns_installed_and_loaded(
    client, monkeypatch, make_account
):
    """GET /api/assistant/models surfaces the installed models, the
    service default, and which are warm in memory."""
    make_account(account_name="Test", account_type="checking")

    def _fake_tags(base_url=None, **kwargs):
        # The real ``list_ollama_models`` returns names sorted for a
        # stable dropdown — mirror that contract here.
        return ["llama3.1:8b", "mistral:7b", "qwen2.5-coder:latest"]

    def _fake_ps(base_url=None, **kwargs):
        return ["qwen2.5-coder:latest"]

    monkeypatch.setattr(_assistant_routes, "list_ollama_models", _fake_tags)
    monkeypatch.setattr(_assistant_routes, "get_loaded_ollama_models", _fake_ps)

    resp = client.get("/api/assistant/models")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["models"] == ["llama3.1:8b", "mistral:7b", "qwen2.5-coder:latest"]
    assert body["default"] == "qwen2.5-coder:latest"
    assert body["loaded"] == ["qwen2.5-coder:latest"]


def test_list_models_returns_empty_when_ollama_offline(
    client, monkeypatch, make_account
):
    """When Ollama is unreachable, the models endpoint returns an empty
    list (not 503) so the FE renders a disabled picker with a hint."""
    make_account(account_name="Test", account_type="checking")

    def _fake_offline(base_url=None, **kwargs):
        raise httpx.ConnectError("Ollama unreachable (test stub)")

    monkeypatch.setattr(_assistant_routes, "list_ollama_models", _fake_offline)
    monkeypatch.setattr(_assistant_routes, "get_loaded_ollama_models", _fake_offline)

    resp = client.get("/api/assistant/models")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["models"] == []
    assert body["loaded"] == []
    assert body["default"] == "qwen2.5-coder:latest"


def test_list_models_requires_auth(client_no_auth, db_session):
    """GET /api/assistant/models without auth returns 401."""
    resp = client_no_auth.get("/api/assistant/models")
    assert resp.status_code == 401


# ---------------------------------------------------------------------
# POST /api/assistant/warm
# ---------------------------------------------------------------------

def test_warm_model_returns_warmed(client, monkeypatch, make_account):
    """POST /api/assistant/warm pre-loads the model and reports warmed."""
    make_account(account_name="Test", account_type="checking")

    warmed = {"model": None}

    def _fake_warm(base_url, model):
        warmed["model"] = model

    monkeypatch.setattr(_assistant_routes, "warm_ollama_model", _fake_warm)

    resp = client.post(
        "/api/assistant/warm",
        json={"model": "llama3.1:8b"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "warmed"
    assert body["model"] == "llama3.1:8b"
    assert warmed["model"] == "llama3.1:8b"


def test_warm_model_defaults_to_default_model(client, monkeypatch, make_account):
    """POST /api/assistant/warm without a model warms DEFAULT_MODEL."""
    make_account(account_name="Test", account_type="checking")

    warmed = {"model": None}

    def _fake_warm(base_url, model):
        warmed["model"] = model

    monkeypatch.setattr(_assistant_routes, "warm_ollama_model", _fake_warm)

    resp = client.post("/api/assistant/warm", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["model"] == "qwen2.5-coder:latest"
    assert warmed["model"] == "qwen2.5-coder:latest"


def test_warm_model_reports_offline(client, monkeypatch, make_account):
    """When Ollama is unreachable, warm reports offline (no 500)."""
    make_account(account_name="Test", account_type="checking")

    def _fake_warm_offline(base_url, model):
        raise httpx.ConnectError("Ollama unreachable (test stub)")

    monkeypatch.setattr(_assistant_routes, "warm_ollama_model", _fake_warm_offline)

    resp = client.post(
        "/api/assistant/warm",
        json={"model": "llama3.1:8b"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "offline"


def test_warm_requires_auth(client_no_auth, db_session):
    """POST /api/assistant/warm without auth returns 401."""
    resp = client_no_auth.post("/api/assistant/warm", json={"model": "x"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------
# Explicit model passthrough on the chat routes
# ---------------------------------------------------------------------

def test_chat_forwards_explicit_model(
    client, db_session, monkeypatch, make_account
):
    """POST /api/assistant/chat sends the explicit ``model`` to the
    orchestrator's LLM call."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    seen_models = []

    async def _fake(messages, **kwargs):
        seen_models.append(kwargs.get("model"))
        return {"tool": "get_totals", "params": {}, "intent": "test"}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What are my totals?", "model": "llama3.1:8b"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert seen_models, "expected at least one LLM call"
    assert all(m == "llama3.1:8b" for m in seen_models)


def test_chat_defaults_model_when_omitted(
    client, db_session, monkeypatch, make_account
):
    """POST /api/assistant/chat without ``model`` falls back to the
    service default."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    seen_models = []

    async def _fake(messages, **kwargs):
        seen_models.append(kwargs.get("model"))
        return {"tool": "get_totals", "params": {}, "intent": "test"}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake)

    resp = client.post(
        "/api/assistant/chat",
        json={"message": "What are my totals?"},
    )
    assert resp.status_code == 200, resp.text
    assert all(m == "qwen2.5-coder:latest" for m in seen_models)


# ---------------------------------------------------------------------
# Cold-start handling
# ---------------------------------------------------------------------

def test_stream_emits_model_loading_when_model_cold(
    client, db_session, monkeypatch, make_account, make_transaction
):
    """When the chosen model is NOT warm in memory, the stream emits a
    ``model_loading`` event (so the FE can show a loading state instead
    of a silent hang) and still yields the full reply."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Test", account_type="checking", current_balance=1000.0)
    db_session.add(account)
    db_session.commit()

    mock = _make_mock_chat(reply="Your balance is $1000.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    # Simulate a cold start: /api/ps reports nothing loaded.
    def _fake_ps(base_url=None, **kwargs):
        return []

    monkeypatch.setattr(_orch, "get_loaded_ollama_models", _fake_ps)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "What are my totals?", "model": "llama3.1:8b"},
    ) as response:
        assert response.status_code == 200
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    event_types = [e["event"] for e in events]

    assert "model_loading" in event_types
    loading_event = [e for e in events if e["event"] == "model_loading"][0]
    assert loading_event["data"]["model"] == "llama3.1:8b"

    # The reply still arrives.
    done_event = [e for e in events if e["event"] == "done"][0]
    assert done_event["data"]["status"] == "ok"
    assert done_event["data"]["reply"] == "Your balance is $1000."


def test_stream_skips_model_loading_when_warm(
    client, db_session, monkeypatch, make_account
):
    """When the chosen model is already warm, the stream does NOT emit
    a ``model_loading`` event."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    mock = _make_mock_chat(reply="Reply.")
    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", mock)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", mock)

    # Simulate a warm start: /api/ps reports the model loaded.
    def _fake_ps(base_url=None, **kwargs):
        return ["llama3.1:8b"]

    monkeypatch.setattr(_orch, "get_loaded_ollama_models", _fake_ps)

    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "What are my totals?", "model": "llama3.1:8b"},
    ) as response:
        assert response.status_code == 200
        raw = ""
        for chunk in response.iter_text():
            raw += chunk

    events = _parse_sse_stream(raw)
    event_types = [e["event"] for e in events]
    assert "model_loading" not in event_types
    assert "done" in event_types


def test_stream_model_loading_uses_longer_timeout_on_cold_start(
    client, db_session, monkeypatch, make_account
):
    """On a cold start the first LLM call uses the longer load timeout
    (so a slow model load doesn't 504), while a warm start keeps the
    standard chat timeout."""
    seed_default_categories(db_session)
    db_session.commit()
    make_account(account_name="Test", account_type="checking")

    seen_timeouts = []

    async def _fake(messages, **kwargs):
        seen_timeouts.append(kwargs.get("timeout_seconds"))
        return {"tool": "get_totals", "params": {}, "intent": "test"}

    monkeypatch.setattr(_llm_client, "post_ollama_chat_async", _fake)
    monkeypatch.setattr(_orch, "post_ollama_chat_async", _fake)

    from app.services.llm_client import (
        MODEL_LOAD_TIMEOUT_SECONDS,
        REQUEST_TIMEOUT_SECONDS,
    )

    # Cold start.
    monkeypatch.setattr(_orch, "get_loaded_ollama_models", lambda base_url=None, **k: [])
    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "hi", "model": "llama3.1:8b"},
    ) as response:
        for _ in response.iter_text():
            pass
    assert seen_timeouts and seen_timeouts[0] == MODEL_LOAD_TIMEOUT_SECONDS

    # Warm start.
    seen_timeouts.clear()
    monkeypatch.setattr(
        _orch,
        "get_loaded_ollama_models",
        lambda base_url=None, **k: ["llama3.1:8b"],
    )
    with client.stream(
        "POST",
        "/api/assistant/chat/stream",
        json={"message": "hi", "model": "llama3.1:8b"},
    ) as response:
        for _ in response.iter_text():
            pass
    assert seen_timeouts and seen_timeouts[0] == REQUEST_TIMEOUT_SECONDS
