"""Phase 30 — Reusable Ollama HTTP client.

Extracted from ``llm_categorizer.py`` so the assistant orchestrator
(Phase 30a) and the categorizer (Phase 22) share the same httpx
plumbing, constants, and error-mapping contract.

Local-first contract (unchanged from llm_categorizer):
- Ollama is reached over plain HTTP loopback (``localhost:11434``).
- No API key, no outbound traffic, no third-party telemetry.
- ``format="json"`` constrains the model into JSON grammar.
- Transport errors (``httpx.TransportError``) propagate to the caller.
- Malformed upstream bodies raise ``ValueError``.

The categorizer's existing ``_post_ollama_chat`` function is kept as
a thin wrapper that calls :func:`post_ollama_chat` with the categorizer's
system prompt — no behaviour change, existing tests still pass.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Constants — pinned at module load (re-exported by llm_categorizer
# for backward compat).
# ---------------------------------------------------------------------

OLLAMA_DEFAULT_BASE_URL: str = "http://localhost:11434"
DEFAULT_MODEL: str = "qwen2.5-coder:latest"
REQUEST_TIMEOUT_SECONDS: float = 60.0


def post_ollama_chat(
    messages: list[dict[str, str]],
    *,
    base_url: str = OLLAMA_DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> dict:
    """Synchronous POST to ``{base_url}/api/chat`` with JSON-mode.

    Takes a list of ``{"role": "system"|"user"|"assistant", "content": "..."}``
    messages so callers can build arbitrary multi-turn prompts (the
    categorizer sends system+user; the assistant orchestrator sends
    system+user+tool-result).

    Uses ``format="json"`` + ``temperature=0.0`` for deterministic
    JSON output. The response's ``message.content`` is a JSON string;
    we parse it BEFORE returning so the caller sees a clean dict.

    Raises:
        httpx.TransportError: Ollama unreachable (caller maps to 503).
        ValueError: Malformed upstream body (caller maps to 502).
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        r = client.post(f"{base_url}/api/chat", json=payload)
    r.raise_for_status()
    body = r.json()
    content = (body.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            f"Ollama returned empty/non-string content: {body!r}"
        )
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Ollama returned non-JSON content: {content!r}"
        ) from exc


async def post_ollama_chat_async(
    messages: list[dict[str, str]],
    **kwargs: Any,
) -> dict:
    """Async twin — offloads to a thread via ``asyncio.to_thread`` so
    a single inference round never blocks the event loop.

    Tests can monkeypatch THIS function to simulate transport-level
    failures without touching the sync helper.
    """
    return await asyncio.to_thread(post_ollama_chat, messages, **kwargs)
