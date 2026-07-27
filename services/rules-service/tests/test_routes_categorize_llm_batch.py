"""Phase 22 — failing tests for the LLM-backed batch categorizer.

User's spec:
- POST /api/categorize/llm-batch takes a list of
  {transaction_id, merchant_name?, description, amount?} payloads.
- Calls Ollama via httpx (qwen2.5-coder JSON-mode, ≤20 rows/batch).
- In-process SHA-256 prompt cache with **7-day TTL**.
- Returns [{txn_id, suggested_category, confidence, reason?}].
- Server validates against the canonical 12 categories; maps
  unknown → "Other" with low confidence (so the FE can pre-tick
  the user to eyeball low-confidence rows).

Test-first contract:
- These tests are written BEFORE the implementation. They should
  FAIL on first run (the route file doesn't exist yet). The
  implementation lands in :mod:`app.services.llm_categorizer` and
  :mod:`app.routes.categorize_llm` and turns them green.
- The Ollama httpx call is monkeypatched via
  :func:`mock_ollama_chat` (below), which both stubs the upstream
  response AND records the cache-key shape for the cache test.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import pytest
from fastapi.testclient import TestClient


# Phase 22 — per-test cache isolation. Without this autouse fixture,
# the module-level ``_PROMPT_CACHE`` in ``app.services.llm_categorizer``
# leaks across tests: the ``cache_invalidation_on_amount_change`` test
# (which expects exactly 2 Ollama calls — different amount = different
# fingerprint = cache miss on call 2) would report only 1 if the
# preceding ``happy_path`` and ``caches_duplicate_call`` tests had
# already populated the slot for ``BLUE BOTTLE COFFEE`` with ``amount=12.34``.
# Clear BEFORE and AFTER so no test can contaminate its neighbours.
@pytest.fixture(autouse=True)
def _clear_llm_prompt_cache():
    from app.services.llm_categorizer import clear_prompt_cache

    clear_prompt_cache()
    yield
    clear_prompt_cache()


# ---------------------------------------------------------------
# Helpers: monkeypatchable Ollama stub + a deterministic cache
# inspection path.
# ---------------------------------------------------------------
def mock_ollama_chat(monkeypatch, response_bodies: list[dict]):
    """Replace ``app.services.llm_categorizer._post_ollama_chat``
    with a stub that returns canned responses in order.

    Each call increments an internal counter; the test inspects the
    call count via :func:`ollama_call_count`.

    The stub accepts ``**kwargs`` so a call site that passes
    ``base_url`` / ``timeout_seconds`` alongside ``prompt`` and
    ``model`` (which is what the real production wrapper does) does
    NOT raise ``TypeError: unexpected keyword argument`` and surface
    as a 500. The kwargs are recorded for diagnostic purposes only.
    """
    state = {"calls": 0, "prompts": [], "kwargs_log": [], "response_bodies": response_bodies}

    def _stub(prompt: str, *, model: str = "qwen2.5-coder:latest", **kwargs) -> dict:
        idx = state["calls"]
        state["calls"] += 1
        state["prompts"].append(prompt)
        state["kwargs_log"].append({"model": model, **kwargs})
        return state["response_bodies"][idx]

    monkeypatch.setattr(
        "app.services.llm_categorizer._post_ollama_chat", _stub
    )
    return state


def ollama_call_count(state) -> int:
    return state["calls"]


def ollama_prompts(state) -> list[str]:
    return state["prompts"]


# ---------------------------------------------------------------
# Tests — auth + happy path + cache + validation + offline handling.
# ---------------------------------------------------------------
def _txn_payload(txn_id: int, label: str) -> dict:
    """Realistic input row. The LLM categorizer receives exactly
    this shape from the FE; tests below should match the same."""
    return {
        "transaction_id": txn_id,
        "merchant_name": label,
        "description": f"{label} POS #1234",
        "amount": 12.34,
    }


def test_post_categorize_llm_batch_requires_auth(client_no_auth):
    """No JWT cookie → 401, regardless of payload."""
    resp = client_no_auth.post(
        "/api/categorize/llm-batch",
        json={"transactions": [_txn_payload(1, "STARBUCKS")]},
    )
    assert resp.status_code == 401


def test_post_categorize_llm_batch_happy_path(client, monkeypatch):
    """Mocked Ollama returns a clean JSON body; route passes through
    suggested_category + confidence per row."""

    response_body = {
        "categories": [
            {"transaction_id": 1, "category": "Food & Dining", "confidence": 0.92},
            {"transaction_id": 2, "category": "Shopping", "confidence": 0.81},
        ]
    }
    state = mock_ollama_chat(monkeypatch, [response_body])

    resp = client.post(
        "/api/categorize/llm-batch",
        json={"transactions": [
            _txn_payload(1, "BLUE BOTTLE COFFEE"),
            _txn_payload(2, "AMAZON MKTPLACE"),
        ]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["suggestions"][0]["txn_id"] == 1
    assert body["suggestions"][0]["suggested_category"] == "Food & Dining"
    assert body["suggestions"][0]["confidence"] == 0.92
    assert body["suggestions"][1]["txn_id"] == 2
    assert body["suggestions"][1]["suggested_category"] == "Shopping"
    # First Ollama call (cache empty).
    assert ollama_call_count(state) == 1


def test_post_categorize_llm_batch_unknown_category_coerced_to_other(
    client, monkeypatch,
):
    """If Ollama hallucinates a non-canonical category, the server
    coerces to ``Other`` so the FE never gets an unrecognised label."""

    response_body = {
        "categories": [
            {"transaction_id": 1, "category": "Pet Supplies (Hallucinated!)",
             "confidence": 0.71},
        ]
    }
    state = mock_ollama_chat(monkeypatch, [response_body])

    resp = client.post(
        "/api/categorize/llm-batch",
        json={"transactions": [_txn_payload(1, "CHEWY.COM")]},
    )
    assert resp.status_code == 200, resp.text
    sugg = resp.json()["suggestions"][0]
    assert sugg["suggested_category"] == "Other"
    # Coerced rows should be visibly down-weighted so the UI
    # can pre-tick them for a manual eyeball.
    assert sugg["confidence"] <= 0.5
    assert sugg.get("coerced") is True


def test_post_categorize_llm_batch_caches_duplicate_call(
    client, monkeypatch,
):
    """Same payload twice → second call hits in-process cache.
    Only ONE Ollama round-trip."""

    response_body = {
        "categories": [
            {"transaction_id": 1, "category": "Food & Dining", "confidence": 0.92},
        ]
    }
    state = mock_ollama_chat(monkeypatch, [response_body])

    payload = {"transactions": [_txn_payload(1, "BLUE BOTTLE COFFEE")]}
    first = client.post("/api/categorize/llm-batch", json=payload)
    second = client.post("/api/categorize/llm-batch", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    # Critical: ONE upstream call, not two.
    assert ollama_call_count(state) == 1


def test_post_categorize_llm_batch_cache_invalidation_on_amount_change(
    client, monkeypatch,
):
    """Different amount = different cache key = fresh Ollama call."""

    state = mock_ollama_chat(
        monkeypatch,
        [
            {"categories": [{"transaction_id": 1, "category": "Food & Dining",
                             "confidence": 0.92}]},
            {"categories": [{"transaction_id": 1, "category": "Other",
                             "confidence": 0.4}]},
        ],
    )
    payload_a = {
        "transactions": [{**_txn_payload(1, "BLUE BOTTLE COFFEE"), "amount": 12.34}],
    }
    payload_b = {
        "transactions": [{**_txn_payload(1, "BLUE BOTTLE COFFEE"), "amount": 99.99}],
    }
    client.post("/api/categorize/llm-batch", json=payload_a)
    client.post("/api/categorize/llm-batch", json=payload_b)
    assert ollama_call_count(state) == 2


def test_post_categorize_llm_batch_7day_ttl_expiry(
    client, monkeypatch,
):
    """7-day TTL: cached entry older than 7 days triggers a fresh call."""

    state = mock_ollama_chat(
        monkeypatch,
        [
            {"categories": [{"transaction_id": 1, "category": "Food & Dining",
                             "confidence": 0.92}]},
            {"categories": [{"transaction_id": 1, "category": "Food & Dining",
                             "confidence": 0.94}]},
        ],
    )
    payload = {"transactions": [_txn_payload(1, "BLUE BOTTLE COFFEE")]}
    # First call seeds the cache.
    client.post("/api/categorize/llm-batch", json=payload)
    assert ollama_call_count(state) == 1

    # Manually backdate the cache entry by 8 days. The next call
    # should miss and re-query Ollama.
    from app.services.llm_categorizer import _PROMPT_CACHE  # type: ignore

    cache_key = _PROMPT_CACHE_KEY_FOR_TEST(
        payload["transactions"][0],
    )
    if cache_key in _PROMPT_CACHE:
        _PROMPT_CACHE[cache_key] = (
            _PROMPT_CACHE[cache_key][0],
            datetime.now(timezone.utc) - timedelta(days=8),
        )

    client.post("/api/categorize/llm-batch", json=payload)
    assert ollama_call_count(state) == 2


def test_post_categorize_llm_batch_rejects_more_than_twenty_rows(client):
    """Batch size ≤ 20 (per user's spec). 21 rows → 422."""

    rows = [_txn_payload(i, f"VENDOR_{i}") for i in range(1, 22)]
    resp = client.post(
        "/api/categorize/llm-batch",
        json={"transactions": rows},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "20" in detail or "batch" in detail.lower()


def test_post_categorize_llm_batch_503_when_ollama_unreachable(
    client, monkeypatch,
):
    """Ollama offline / unreachable → 503 with a clear message so
    the FE surfaces a banner, not a generic 500."""

    async def _broken(*args, **kwargs):
        import httpx
        raise httpx.ConnectError("Ollama refused connection")

    monkeypatch.setattr(
        "app.services.llm_categorizer._post_ollama_chat_async",
        _broken,
    )

    resp = client.post(
        "/api/categorize/llm-batch",
        json={"transactions": [_txn_payload(1, "BLUE BOTTLE COFFEE")]},
    )
    assert resp.status_code == 503
    assert "ollama" in resp.json()["detail"].lower() or "unreachable" in resp.json()["detail"].lower()


def test_post_categorize_llm_batch_prompt_includes_canonical_categories(
    client, monkeypatch,
):
    """The system prompt MUST enumerate the canonical 12 categories
    so the LLM output can be coerced deterministically. A generic
    \"categorize this\" prompt would invite hallucination."""

    state = mock_ollama_chat(
        monkeypatch,
        [{"categories": [{"transaction_id": 1, "category": "Food & Dining",
                          "confidence": 0.92}]}],
    )
    client.post(
        "/api/categorize/llm-batch",
        json={"transactions": [_txn_payload(1, "BLUE BOTTLE COFFEE")]},
    )
    prompt_text = ollama_prompts(state)[0].lower()
    # All 12 canonical categories should appear in the prompt so
    # llama3.1 / qwen-coder has the enum to constrain against.
    canonical = [
        "income", "transfer", "food & dining", "groceries",
        "transportation", "shopping", "entertainment",
        "bills & utilities", "health", "travel", "education", "other",
    ]
    missing = [c for c in canonical if c not in prompt_text]
    assert missing == [], (
        f"Canonical categories missing from prompt: {missing}. "
        f"The LLM has no enum to constrain against and will "
        f"hallucinate freely without it."
    )


def test_post_categorize_llm_batch_json_mode_enforced(
    client, monkeypatch,
):
    """If Ollama returns prose instead of JSON (because qwen-coder
    bileaked), the server should surface a 502 with a clear detail
    so the FE knows to retry."""

    state = mock_ollama_chat(
        monkeypatch,
        [{"text": "This is not JSON! Food & Dining probably."}],
    )

    resp = client.post(
        "/api/categorize/llm-batch",
        json={"transactions": [_txn_payload(1, "BLUE BOTTLE COFFEE")]},
    )
    assert resp.status_code == 502


# ---------------------------------------------------------------
# Helper: expose cache key computation for the TTL test.
# ---------------------------------------------------------------
def _PROMPT_CACHE_KEY_FOR_TEST(input_row: dict) -> str:
    """Build the canonical cache key for the cache-key backdating test.

    The service stores cache entries BY BATCH FINGERPRINT (keys on the
    sorted list of per-row hashes + prompt version) so a same-row
    re-run by the UI doesn't bust the cache due to UI re-ordering.
    Wrapping the row in a list mirrors ``categorize_with_llm_async``'s
    compute_batch_fingerprint call site so the key the helper
    computes is the SAME one the service stored.
    """
    from app.services.llm_categorizer import (
        compute_batch_fingerprint,  # type: ignore
    )
    return compute_batch_fingerprint([input_row])
