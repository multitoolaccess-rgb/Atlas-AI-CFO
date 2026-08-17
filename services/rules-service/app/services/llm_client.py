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

# Ollama loads a model into GPU/CPU memory on first use (cold start).
# On a local M-series laptop this can take 30-120s for a 7B model, so
# requests that trigger a cold load use this much longer budget instead
# of the chat timeout above — otherwise the first Scout message after a
# model switch would 504 even though the model is just warming up.
MODEL_LOAD_TIMEOUT_SECONDS: float = 300.0

# Short budget for the lightweight /api/tags + /api/ps discovery calls
# (they never trigger a model load).
MODEL_DISCOVERY_TIMEOUT_SECONDS: float = 5.0


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


# ---------------------------------------------------------------------
# Model discovery — lets the Scout UI render a picker of the user's
# installed local models (instead of silently defaulting to
# ``DEFAULT_MODEL``) and report whether the chosen model is already
# warm in memory (so a cold start doesn't look like a hang).
# ---------------------------------------------------------------------


def list_ollama_models(base_url: str = OLLAMA_DEFAULT_BASE_URL) -> list[str]:
    """Return the names of every model installed in the local Ollama.

    Hits ``GET {base_url}/api/tags`` (a lightweight, non-loading call)
    and returns the ``name`` fields, sorted for a stable dropdown.

    Raises:
        httpx.TransportError: Ollama unreachable (the route maps this
            to a clean 503 so the FE can show an offline hint).
        ValueError: Ollama returned a body without a ``models`` list.
    """
    with httpx.Client(timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS) as client:
        r = client.get(f"{base_url}/api/tags")
    r.raise_for_status()
    body = r.json()
    models = body.get("models")
    if not isinstance(models, list):
        raise ValueError(f"Ollama /api/tags missing 'models' list: {body!r}")
    names = [m.get("name") for m in models if isinstance(m, dict) and m.get("name")]
    return sorted(set(names))


def get_loaded_ollama_models(base_url: str = OLLAMA_DEFAULT_BASE_URL) -> list[str]:
    """Return the names of models currently loaded into Ollama memory.

    Hits ``GET {base_url}/api/ps`` and returns the ``name`` fields of
    the loaded models. Used by the assistant stream so it can emit a
    ``model_loading`` event (and use the longer load timeout) when the
    user's chosen model is cold.

    Raises:
        httpx.TransportError: Ollama unreachable.
        ValueError: Ollama returned a body without a ``models`` list.
    """
    with httpx.Client(timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS) as client:
        r = client.get(f"{base_url}/api/ps")
    r.raise_for_status()
    body = r.json()
    models = body.get("models")
    if not isinstance(models, list):
        raise ValueError(f"Ollama /api/ps missing 'models' list: {body!r}")
    return [m.get("name") for m in models if isinstance(m, dict) and m.get("name")]


def warm_ollama_model(base_url: str = OLLAMA_DEFAULT_BASE_URL, model: str = DEFAULT_MODEL) -> None:
    """Pre-load ``model`` into Ollama memory so the next chat call is fast.

    Sends an empty ``/api/generate`` request with a long ``keep_alive``
    so Ollama keeps the weights resident. This is the "no hang on first
    use" companion to the model picker: when the user selects a model
    the FE can call the warm endpoint, and the first actual message
    won't stall on a cold load.

    Raises:
        httpx.TransportError: Ollama unreachable.
    """
    payload = {
        "model": model,
        "prompt": "",
        "stream": False,
        "keep_alive": "30m",
    }
    with httpx.Client(timeout=MODEL_LOAD_TIMEOUT_SECONDS) as client:
        client.post(f"{base_url}/api/generate", json=payload)

