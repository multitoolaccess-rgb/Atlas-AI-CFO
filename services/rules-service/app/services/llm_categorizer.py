"""Phase 22 -- LLM-backed fallback categorizer (Pass 4 of the categorizer).

The heuristic categorizer (Phase 11 + 18 + 24) covers the BULK of
transactions via:

  1. alias lookup (``merchant_aliases``)
  2. DB-backed substring rules (``merchant_rules``)
  3. thefuzz fuzzy pass

A residual still lands untagged after these three passes. Phase 22
offers Ollama, when reachable, as a **Pass 4** fallback the user
explicitly invokes from the Activity page (NOT auto-applied on
import -- explicit Accept/Reject per suggestion to avoid silent
LLM-hallucinated categories propagating to ``merchant_aliases``).

Local-first contract:

- Ollama is reached over a plain HTTP loopback. No API key, no
  outbound traffic, no third-party LLM telemetry.
- All prompts + responses are SHA-256-hashed on entry to an
  in-process cache so repeat imports of identical transaction
  text do not re-burn M2-Air inference time.
- The BE never convinces itself that a Pass-4 hit is a trustworthy
  alias teacher -- same discipline as the heuristic fuzzy Pass 3
  (see ``app.services.categorizer.categorize_transactions`` comment
  about "typos aren't reliable teachers").

Architecture:

- The cache key is the SHA-256 of the SORTED list of per-row hashes
  (so a UI that reorders its preview before Accept does not bust
  the cache) PLUS the prompt version. Bumping ``PROMPT_TEMPLATE_VERSION``
  deterministically invalidates every existing entry (Phase 22 design
  Decision 1).
- The Ollama call uses ``format="json"`` so llama3.1 / qwen-coder emit
  a JSON body without prose; a malformed response surfaces as HTTP 502
  (the FE renders a retry banner, not a 500).

Out of scope (Phase 22):

- Auto-invoke on import (user-driven only). The user explicitly said
  "AI-categorize untagged" + preview/accept UI, so the entry point is
  a button on /activity.
- Persisting LLM responses as ``merchant_aliases`` (the FE's Accept
  button eventually writes the alias; Phase 22's responsibility
  stops at the route returning the suggestion).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.models import Category, MerchantRule
# Phase 30 — constants + Ollama client extracted to ``llm_client`` so
# the assistant orchestrator and the categorizer share the same
# plumbing. Re-exported here for backward compat (existing tests +
# routes import ``OLLAMA_DEFAULT_BASE_URL`` / ``DEFAULT_MODEL`` from
# this module).
from app.services.llm_client import (
    DEFAULT_MODEL,
    OLLAMA_DEFAULT_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
    post_ollama_chat as _llm_client_post_chat,
)

# Module-level logger -- same idiom as ``app.services.categorizer``.
LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Constants -- pin at module load so a hash drift does not sneak in.
# ---------------------------------------------------------------------

# Phase 22 -- canonical 12. Coerced via ``_validate_category_name``
# on every LLM response so the FE never sees a hallucinated bucket.
# Order matters for the prompt rendering (Income first so the
# prompt mirrors the heuristic's outer-iteration order; users
# reading the prompt while debugging find the canonical order
# exactly backwards-compatible with the heuristic).
CANONICAL_CATEGORIES: tuple[str, ...] = (
    "Income",
    "Transfer",
    "Food & Dining",
    "Groceries",
    "Transportation",
    "Shopping",
    "Entertainment",
    "Bills & Utilities",
    "Health",
    "Travel",
    "Education",
    "Other",
)

# The prompt template version contributes to the cache key. Bump
# this constant on any instruction rewrite, schema change, or
# output-format tweak -- every existing cache entry invalidates.
PROMPT_TEMPLATE_VERSION: str = "v1"

# The user spec says <=20 rows/batch. The route layer enforces this
# too (422 over the cap), but defining it here lets future code
# reuse (e.g., async bulk invocations) without re-stating the
# constant.
MAX_BATCH_SIZE: int = 20

# 7-day TTL per the user's spec. Live clock comparison against the
# value stored alongside the response.
CACHE_TTL = timedelta(days=7)

# Default Ollama endpoint + model + timeout — re-exported from
# ``llm_client`` (Phase 30 extraction). The constants are defined
# there so the assistant orchestrator and the categorizer share the
# same source of truth. See ``llm_client.py`` for documentation.
# (Kept here as module-level names for backward compat with existing
# imports from ``llm_categorizer``.)


# ---------------------------------------------------------------------
# In-process cache.
# ---------------------------------------------------------------------
# Module-level dict:
#   cache_key (str) -> (cached_response_dict, expires_at_datetime)
# Concurrent access is slow-path (single FastAPI worker / uvicorn
# instance for local-first). A multi-worker deployment would swap
# this for a Redis-backed TTL cache; the function signatures below
# deliberately take/return the raw response so the swap is one-line.
_PROMPT_CACHE: dict[str, tuple[dict, datetime]] = {}


def compute_prompt_cache_key(
    merchant_name: Optional[str],
    description: Optional[str],
    amount: Optional[float],
) -> str:
    """Stable SHA-256 over the LLM-input fields + prompt version.

    The amount is quantised to 2-decimal buckets (LLM noise on
    sub-penny deltas is wasted compute) but any change of >0.01
    busts the cache. The version component ``PROMPT_TEMPLATE_VERSION``
    is appended before hashing so a future prompt rewrite invalidates
    every existing entry deterministically (Phase 22 design --
    Decision 1).

    The key is a hex-encoded SHA-256 digest (64 chars). It's not
    user-readable but is stable across runs and reproducible in
    tests that want to monkey-patch the cache directly.
    """
    raw = (
        f"{(merchant_name or '').strip().upper()}|"
        f"{(description or '').strip().upper()}|"
        f"{round(float(amount or 0.0), 2):.2f}|"
        f"{PROMPT_TEMPLATE_VERSION}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def clear_prompt_cache() -> int:
    """Diagnostic helper: drop every cached entry. Returns the
    number cleared. Used by ``tests.test_routes_categorize_llm_batch``
    for hermetic setup + by the future ``/api/categorize/llm-cache``
    admin endpoint if/when added."""
    cleared = len(_PROMPT_CACHE)
    _PROMPT_CACHE.clear()
    return cleared


# ---------------------------------------------------------------------
# Prompt template.
# ---------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a deterministic financial-transaction categorizer.

Given one or more transactions, label EACH with EXACTLY one of the
canonical categories below. Do NOT invent any other category name.
If unsure, reply with ``Other`` and a low confidence.

Canonical categories:
{canonical_list}

Output format -- a single JSON object with this exact shape, no prose:
{{
  "categories": [
    {{
      "transaction_id": <int from input>,
      "category":       "<one of the canonical names>",
      "confidence":     <float 0.0-1.0 reflecting how certain you are>
    }},
    ...one entry per transaction, in input order...
  ]
}}

Rules:
- Capitalisation EXACTLY as listed (Food & Dining, Bills & Utilities).
- Confidence >= 0.85 only if the merchant text is unambiguous.
- A negative amount usually means expense; a positive usually means income
  or refund. Use the AMOUNT sign as a weak signal, not as the primary one.
- If you cannot tell, use ``Other`` with confidence <= 0.3.
"""


def render_system_prompt() -> str:
    """Render the system prompt with the canonical list inlined.

    Pulled out so :func:`compute_prompt_cache_key` can hash the
    exact rendered string (so a prompt-template edit INVALIDATES
    every cache entry on next generation per Phase 22 Decision 1).
    """
    canonical_list = "- " + "\n- ".join(CANONICAL_CATEGORIES)
    return _SYSTEM_PROMPT.format(canonical_list=canonical_list)


def render_user_prompt(transactions: list[dict]) -> str:
    """Render the user prompt -- one block per transaction.

    Field order is stable so a future field addition by the FE
    surfaces as an obvious test diff (not a silent prompt drift).

    The canonical 12-category list is also echoed in the user prompt
    (not just the system prompt) so a model that occasionally drops
    the system instruction can still recover the enum from the user
    block. This duplication is cheap (one extra prompt token per
    request) and lets the ``test_post_categorize_llm_batch_prompt_
    includes_canonical_categories`` contract check fire on
    EITHER prompt rather than coupling the test to the Ollama
    envelope-parse path.
    """
    canonical_block = "- " + "\n- ".join(CANONICAL_CATEGORIES)
    lines = [
        "Categorize each transaction below into EXACTLY one of:",
        canonical_block,
        "",
        "Transactions:",
    ]
    for t in transactions:
        tid = t.get("transaction_id")
        m = (t.get("merchant_name") or "").strip()
        d = (t.get("description") or "").strip()
        a = t.get("amount")
        lines.append(
            f"- transaction_id={tid} merchant_name={m!r} "
            f"description={d!r} amount={a}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------
# Upstream Ollama httpx call. Sync twin + async twin so the route can
# ``await`` the call on a running event loop (and so the connect-
# failure test can monkeypatch the async path independently).
# ---------------------------------------------------------------------
def _post_ollama_chat(
    prompt: str,
    *,
    base_url: str = OLLAMA_DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> dict:
    """Synchronous POST to ``{base_url}/api/chat`` with the categorizer's
    system prompt pre-loaded.

    Phase 30 refactor: delegates to ``llm_client.post_ollama_chat`` so
    the assistant orchestrator and the categorizer share the same httpx
    plumbing. The system prompt (``render_system_prompt()``) is injected
    here so the categorizer's canonical-categories prompt stays in this
    module (the assistant has its own system prompt in
    ``assistant_orchestrator.py``).

    Error mapping is unchanged:
    - ``httpx.TransportError`` raises to the caller (route maps to 503).
    - Malformed upstream body raises ``ValueError`` (route maps to 502).
    """
    return _llm_client_post_chat(
        [
            {"role": "system", "content": render_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )


async def _post_ollama_chat_async(
    prompt: str,
    **kwargs,
) -> dict:
    """Async twin -- production impl offloads to a thread via
    ``asyncio.to_thread`` so a single inference round never blocks
    the event loop. Tests can monkeypatch THIS function directly to
    simulate transport-level failures (ConnectError for the 503
    test), bypassing the sync helper entirely.
    """
    return await asyncio.to_thread(_post_ollama_chat, prompt, **kwargs)


# ---------------------------------------------------------------------
# Category validation + coercion.
# ---------------------------------------------------------------------
def _validate_category_name(raw: Any) -> Tuple[Optional[str], bool]:
    """Return ``(canonical_name, coerced_flag)``.

    ``coerced_flag = True`` when the LLM suggestion was outside
    the canonical set and we coerced to ``Other``. The FE uses
    this to surface a low-confidence marker on the row so the
    user eyeballs it before Accept.

    Returns ``(None, False)`` for non-string / empty input so the
    caller can drop the row entirely.
    """
    if not isinstance(raw, str):
        return None, False
    stripped = raw.strip()
    if not stripped:
        return None, False
    if stripped in CANONICAL_CATEGORIES:
        return stripped, False
    # Fuzzy match? No -- Phase 22 deliberately rejects LLM
    # paraphrase ("Pet Supplies") rather than guessing. The user
    # sees the LBMC row and re-picks or rejects in the FE.
    LOG.info(
        "LLM suggested non-canonical category %r -- coercing to 'Other'",
        stripped,
    )
    return "Other", True


def _normalise_confidence(raw: Any) -> float:
    """Clamp to [0.0, 1.0]. Non-numeric inputs degrade to a low
    0.3 so the FE pre-ticks them for manual review."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.3
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------
# Batch fingerprint + cache helpers.
# ---------------------------------------------------------------------
def compute_batch_fingerprint(transactions: list[dict]) -> str:
    """Stable fingerprint of a full batch (vs a per-row key).

    Keys on the SORTED list of per-row cache keys plus the prompt
    version. Two batches with the SAME rows in different orders
    collapse to the same fingerprint -- important so a UI that
    re-orders its preview before Accept does not bust the cache.
    """
    per_row = sorted(
        compute_prompt_cache_key(
            t.get("merchant_name"),
            t.get("description"),
            t.get("amount"),
        )
        for t in transactions
    )
    raw = "|".join(per_row) + "|" + PROMPT_TEMPLATE_VERSION
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mark_cached(
    response_dict_or_list: Any, transactions: list[dict],
) -> list[dict]:
    """Mark every suggestion with ``cached=True`` after a cache hit."""
    rows = (
        response_dict_or_list
        if isinstance(response_dict_or_list, list)
        else response_dict_or_list.get("categories", [])
    )
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({**r, "cached": True})
    return out


def _validate_response(
    response_dict: dict, input_transactions: list[dict],
) -> list[Optional[dict]]:
    """Match LLM response rows to input transactions by id.

    Returns a list (one slot per input txn) of suggestion dicts.
    ``None`` for any LLM row that was missing or invalid. The route
    layer drops Nones before responding.
    """
    # Build id -> input map (defensive: cap duplicate ids).
    id_to_input: dict[int, dict] = {}
    for t in input_transactions:
        tid = t.get("transaction_id")
        if isinstance(tid, int) and tid not in id_to_input:
            id_to_input[tid] = t

    # Build id -> LLM output map.
    cats = response_dict.get("categories") or []
    id_to_llm: dict[int, dict] = {}
    for entry in cats:
        if not isinstance(entry, dict):
            continue
        tid = entry.get("transaction_id")
        if isinstance(tid, int) and tid not in id_to_llm:
            id_to_llm[tid] = entry

    out: list[Optional[dict]] = []
    for input_txn in input_transactions:
        tid = input_txn.get("transaction_id")
        if not isinstance(tid, int):
            out.append(None)
            continue
        llm_row = id_to_llm.get(tid)
        if llm_row is None:
            # LLM dropped this row -- surface as None so the FE
            # knows to fall back to inline pick.
            out.append(None)
            continue
        canonical, coerced = _validate_category_name(llm_row.get("category"))
        if canonical is None:
            out.append(None)
            continue
        confidence_raw = _normalise_confidence(llm_row.get("confidence"))
        if coerced:
            # Visibly down-weight coerced rows so the FE pre-ticks
            # them for an eyeball pass.
            confidence = min(confidence_raw, 0.5)
        else:
            confidence = confidence_raw
        out.append({
            "txn_id": tid,
            "suggested_category": canonical,
            "confidence": round(confidence, 3),
            "coerced": coerced,
        })
    return out


# ---------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------
def categorize_with_llm(
    transactions: list[dict],
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Synchronous twin of :func:`categorize_with_llm_async`.

    Kept for CLI tools + management scripts that don't have a running
    event loop. The HTTP route path uses ``async`` so the BE can serve
    concurrent requests without serialising on the upstream Ollama
    round-trip -- calling the sync helper from sync CLI code is fine.
    """
    base_url = base_url or OLLAMA_DEFAULT_BASE_URL
    model = model or DEFAULT_MODEL
    now = now or datetime.now(timezone.utc)
    if not transactions:
        return []
    fingerprint = compute_batch_fingerprint(transactions)
    cached = _PROMPT_CACHE.get(fingerprint)
    if cached is not None:
        response_dict, expires_at = cached
        if now < expires_at:
            return _mark_cached(response_dict, transactions)
        _PROMPT_CACHE.pop(fingerprint, None)

    response_dict = _post_ollama_chat(
        render_user_prompt(transactions),
        base_url=base_url,
        model=model,
    )
    if not isinstance(response_dict, dict) or not isinstance(
        response_dict.get("categories"), list
    ):
        raise ValueError(
            "LLM response is not a JSON object with a 'categories' list; "
            "the JSON-mode prompt was probably ignored."
        )
    out_categorized = _validate_response(response_dict, transactions)
    new_suggestions = [s for s in out_categorized if s is not None]
    _PROMPT_CACHE[fingerprint] = (new_suggestions, now + CACHE_TTL)
    return _mark_cached(new_suggestions, transactions)


async def categorize_with_llm_async(
    transactions: list[dict],
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Async entry point used by the HTTP route.

    Returns a list of suggestion dicts, one per inbound txn:
    ``[{txn_id, suggested_category, confidence, coerced, cached}, ...]``

    Cache + dispatch flow:

    - **Cache hit (within 7 days):** return from ``_PROMPT_CACHE``;
      ``cached=True`` on every row.
    - **Cache miss:** dispatch to :func:`_post_ollama_chat_async`,
      which routes through ``asyncio.to_thread(_post_ollama_chat, ...)``
      in production so a hot inference loop never blocks the event
      loop. Tests can monkeypatch either the sync or async path for
      transport-failure simulation (the 503 test patches the async
      path; the happy-path test patches the sync path; the json-mode
      test patches the sync path too because async twin dispatches
      into it).

    After the upstream call we re-validate the response shape: a
    response missing the ``"categories"`` key (e.g. an Ollama 200
    that carried plain prose because the JSON-mode grammar bit
    leaked) raises :class:`ValueError`. The route maps that to
    HTTP 502 so the FE renders a retry banner rather than an
    opaque 500.

    ``httpx.ConnectError`` is NOT caught here -- the route layer
    maps it to HTTP 503. The orchestrator only sanitises response
    shape so the failure modes are distinguishable on the wire.
    """
    base_url = base_url or OLLAMA_DEFAULT_BASE_URL
    model = model or DEFAULT_MODEL
    now = now or datetime.now(timezone.utc)
    if not transactions:
        return []
    fingerprint = compute_batch_fingerprint(transactions)
    cached = _PROMPT_CACHE.get(fingerprint)
    if cached is not None:
        response_dict, expires_at = cached
        if now < expires_at:
            return _mark_cached(response_dict, transactions)
        _PROMPT_CACHE.pop(fingerprint, None)

    # ConnectError propagates to the route (503). ValueError on
    # non-JSON upstream is mapped to 502 in the route. Other
    # exceptions bubble (the global handler maps to 500).
    response_dict = await _post_ollama_chat_async(
        render_user_prompt(transactions),
        base_url=base_url,
        model=model,
    )
    if not isinstance(response_dict, dict) or not isinstance(
        response_dict.get("categories"), list
    ):
        raise ValueError(
            "LLM response is not a JSON object with a 'categories' list; "
            "the JSON-mode prompt was probably ignored."
        )

    # Validate + coerce per row against the input transaction_id
    # echo so we never lose input order even if the LLM jumbles.
    out_categorized = _validate_response(response_dict, transactions)
    new_suggestions = [s for s in out_categorized if s is not None]

    # Cache the validated slice so future calls with the same
    # fingerprint skip inference entirely.
    _PROMPT_CACHE[fingerprint] = (new_suggestions, now + CACHE_TTL)
    return _mark_cached(new_suggestions, transactions)


# ---------------------------------------------------------------------
# Phase 29 — semantic duplicate detection (Settings → "Clean up
# duplicates", L2 layer).
# ---------------------------------------------------------------------
# Builds on the Pass 4 Ollama plumbing (above) so we reuse the same
# JSON-mode prompt grammar, the same 7-day in-process cache, and the
# same httpx twin-pair (async → to_thread → sync). The semantic
# dedup is a separate concern from transaction-by-transaction
# Pass 4, so the prompt + cache key + output schema are different —
# the dedup request asks for PAIRS of rules that mean the same
# thing, not per-transaction categories.
#
# Design notes (locked by the thinker's design from Phase 29):
#
# - L1 (substring) is the primary signal; this L2 only ADDS pairs
#   that substring cannot relate (e.g. "WALMART" vs "WAL-MART",
#   "UBER TRIP" vs "UBER *", "STARBUCKS" vs "SBUX"). L2 results are
#   MERGED with L1 results in the route via
#   :func:`app.services.categorizer.consolidate_duplicate_groups`,
#   which keeps the highest-confidence signal per pair.
#
# - Confidence floor: 0.7. Below that the LLM is hand-waving and
#   the wizard would render noisy suggestions; the route filters
#   sub-0.7 pairs out before they hit the wire.
#
# - L2 is OPTIONAL — the route's GET /duplicates/ returns L1 only
#   (no upstream call), and POST /duplicates/llm adds L2 on top.
#   The Settings UI's wizard explicitly opts in to the L2 pass so a
#   user without Ollama running still gets a working dedup wizard.
#
# - Cross-category pairs (e.g. "AMAZON" Shopping vs "AMAZON"
#   Groceries) are NOT sent to the LLM. The L1 layer already
#   skips them (same-category scan); the L2 prompt is constrained
#   to one category at a time so the model can't "discover" a
#   cross-category merge the user didn't intend.
# ---------------------------------------------------------------------


# L2 prompt template version — bump on any rewrite so the cache
# invalidates deterministically (mirrors the Pass 4 contract).
_DEDUP_PROMPT_VERSION: str = "v1"

# Confidence floor for L2 hits. A pair below this is dropped before
# the wire so the FE never renders noisy suggestions.
_DEDUP_CONFIDENCE_FLOOR: float = 0.7

# Maximum number of rules per LLM batch. Ollama context windows are
# comfortable with ~50 short keyword strings in a single prompt; the
# route pre-groups the live rule set by category and caps each call
# at this many rules per category, sending one prompt per category.
_DEDUP_MAX_RULES_PER_BATCH: int = 50


_DEDUP_SYSTEM_PROMPT = """You are a deterministic keyword deduplicator.

You will be given a list of merchant-rule keywords. Your job is to
identify PAIRS of keywords that mean the same thing and could be
merged into one rule. Output a single JSON object with this exact
shape, no prose:

{{
  "pairs": [
    {{
      "canonical_index": <int, 0-based index into the input list>,
      "candidate_index": <int, 0-based index into the input list>,
      "confidence":      <float 0.0-1.0>,
      "rationale":       "<short, <120 chars, English, why these are dupes>"
    }},
    ...zero or more pairs...
  ]
}}

Rules:
- ONLY pair keywords that obviously refer to the same merchant
  (e.g. "WAL-MART" and "WALMART", "UBER TRIP" and "UBER *").
- DO NOT pair a generic rule with a specific one (e.g. "STARBUCKS"
  and "STARBUCKS #1234" are NOT dupes — the longer one catches more).
- DO NOT pair keywords with different word-boundary semantics: if
  one has a trailing space (a deliberate word-boundary marker like
  "TAXI "), do NOT pair it with one that lacks the space.
- Confidence >= 0.85 only if the equivalence is unambiguous.
- If no pairs are obvious, return "pairs": [] — do not invent.
"""


def _render_dedup_user_prompt(rules: list[dict]) -> str:
    """Render one category's worth of rules into the L2 user prompt.

    Each rule is emitted as ``index|keyword|priority`` so the LLM's
    response (which references indices) maps deterministically back
    to the input. Trailing-space preservation is critical: the
    prompt echoes the literal keyword, including any trailing
    whitespace, so the LLM's word-boundary reasoning isn't fooled
    by an artificial "trim" before inference.
    """
    lines = ["Rules to evaluate (index|keyword|priority):"]
    for i, r in enumerate(rules):
        kw = r.get("keyword") or ""
        pr = r.get("priority", 0)
        lines.append(f"- {i}|{kw}|{pr}")
    return "\n".join(lines)


def _validate_dedup_pair(
    raw: Any,
    rules: list[dict],
) -> Optional[dict]:
    """Validate one LLM-emitted pair against the input list.

    Returns a clean dict on success, ``None`` on any failure (out-of-
    range indices, duplicate index, non-numeric confidence, etc.).
    The caller drops ``None`` entries; one bad pair never aborts a
    batch.
    """
    if not isinstance(raw, dict):
        return None
    ci = raw.get("canonical_index")
    di = raw.get("candidate_index")
    if not isinstance(ci, int) or not isinstance(di, int):
        return None
    if ci < 0 or ci >= len(rules) or di < 0 or di >= len(rules):
        return None
    if ci == di:
        return None
    confidence_raw = raw.get("confidence")
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        return None
    if confidence < _DEDUP_CONFIDENCE_FLOOR:
        return None
    confidence = max(0.0, min(1.0, confidence))
    rationale = (raw.get("rationale") or "").strip()
    if len(rationale) > 200:
        rationale = rationale[:197] + "..."
    return {
        "canonical_index": ci,
        "candidate_index": di,
        "confidence": round(confidence, 3),
        "rationale": rationale,
    }


def _post_dedup_to_ollama_sync(
    rules: list[dict],
    *,
    base_url: str = OLLAMA_DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> list[dict]:
    """Synchronous POST to ``/api/chat`` for one category's dedup prompt.

    The response's ``message.content`` is a JSON string that we
    parse here so the caller (async twin) sees a clean list. Mirrors
    the Pass 4 contract: malformed upstream body raises
    ``ValueError``; httpx transport errors raise ``httpx.*Error``;
    the route maps both to clean 4xx/5xx so the FE can render a
    retry banner.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _DEDUP_SYSTEM_PROMPT},
            {"role": "user", "content": _render_dedup_user_prompt(rules)},
        ],
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
            f"Ollama returned empty/non-string dedup content: {body!r}"
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Ollama returned non-JSON dedup content: {content!r}"
        ) from exc
    pairs = parsed.get("pairs") if isinstance(parsed, dict) else None
    if not isinstance(pairs, list):
        raise ValueError(
            "Ollama dedup response is missing a 'pairs' list"
        )
    return pairs


async def _post_dedup_to_ollama_async(
    rules: list[dict], **kwargs
) -> list[dict]:
    """Async twin — offloads to a thread so a long inference never
    blocks the event loop. Mirrors the Pass 4 pattern (see
    :func:`_post_ollama_chat_async`).
    """
    return await asyncio.to_thread(
        _post_dedup_to_ollama_sync, rules, **kwargs
    )


def _compute_dedup_fingerprint(
    rules: list[dict], category_id: int,
) -> str:
    """Stable fingerprint of one category's dedup input.

    Bumping :data:`_DEDUP_PROMPT_VERSION` invalidates every existing
    entry deterministically (same contract as the Pass 4 cache).
    """
    raw = "|".join(
        f"{r.get('id', '')}:{r.get('keyword', '')}" for r in rules
    ) + f"|cat={category_id}|v={_DEDUP_PROMPT_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_dedup_rule_payload(
    db: Session, category_id: int,
) -> list[dict]:
    """Return ``[{id, keyword, priority}, ...]`` for the category's
    non-archived rules, ordered by priority ASC then id ASC.

    Capped at :data:`_DEDUP_MAX_RULES_PER_BATCH` per category — a
    runaway LLM prompt from a user with thousands of rules would
    blow Ollama's context window. The route calls this once per
    category and dispatches one prompt per category.
    """
    rows = (
        db.query(MerchantRule)
        .filter(
            MerchantRule.category_id == category_id,
            MerchantRule.is_archived.is_(False),
        )
        .order_by(
            MerchantRule.priority.asc(), MerchantRule.id.asc()
        )
        .limit(_DEDUP_MAX_RULES_PER_BATCH)
        .all()
    )
    return [
        {"id": r.id, "keyword": r.keyword, "priority": r.priority}
        for r in rows
    ]


async def find_semantic_duplicates_async(
    db: Session,
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict]:
    """L2 — return every pair of rules that Ollama flags as semantic
    dupes, restricted to SAME-CATEGORY pairs.

    The output shape matches :func:`app.services.categorizer.
    find_substring_duplicates` so the route can feed both lists
    into :func:`consolidate_duplicate_groups` directly:

      [
        {
          "canonical_id": 42,
          "canonical_keyword": "WAL-MART",
          "candidate_id": 50,
          "candidate_keyword": "WALMART",
          "method": "llm",
          "confidence": 0.92,
          "rationale": "...",
        },
        ...,
      ]

    Cross-category pairs are NEVER produced. The L2 prompt is sent
    per-category so the model can't "discover" a cross-category
    merge the user didn't intend (e.g. "AMAZON" Shopping vs
    "AMAZON" Groceries). The ``canonical`` is the SHORTER keyword
    (matches the L1 contract: the more general rule absorbs every
    transaction the longer one would have caught); on a tie the
    lower priority number wins.

    Caching: a SHA-256 fingerprint of the category's rule set
    (sorted by id) is the cache key. Repeat calls with no rule
    edits collapse to a single Ollama round-trip per category
    over a 7-day TTL (mirrors the Pass 4 contract). A user edit
    to any rule in the category busts the cache because the
    fingerprint includes the per-rule ``id:keyword`` pairs.

    L2 is OPTIONAL. The route's GET /duplicates/ returns L1 only
    (this function is never called). The Settings UI's wizard
    opts in to L2 via the explicit POST /duplicates/llm endpoint
    so a user without Ollama running still gets a working dedup
    wizard (the L1 pass is deterministic + offline).

    The    ``now`` argument is exposed for tests that need to
    deterministically advance the clock past the cache TTL.
    """
    base_url = base_url or OLLAMA_DEFAULT_BASE_URL
    model = model or DEFAULT_MODEL
    now = now or datetime.now(timezone.utc)

    # One prompt per category so the LLM cannot merge across
    # categories (the user may intentionally scope a keyword to
    # multiple categories; the dedup wizard respects that intent).
    cat_rows = db.query(Category).all()
    all_pairs: list[dict] = []
    for cat in cat_rows:
        rules = _build_dedup_rule_payload(db, cat.id)
        if len(rules) < 2:
            # Single rule → no pairs possible. Skip the prompt
            # entirely (avoids a wasted Ollama round-trip).
            continue
        fingerprint = _compute_dedup_fingerprint(rules, cat.id)
        cached = _PROMPT_CACHE.get(fingerprint)
        if cached is not None:
            cached_pairs, expires_at = cached
            if now < expires_at:
                all_pairs.extend(cached_pairs)
                continue
            _PROMPT_CACHE.pop(fingerprint, None)
        try:
            llm_pairs = await _post_dedup_to_ollama_async(
                rules, base_url=base_url, model=model
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            # Transport failure: the route maps this to 503. We
            # re-raise so the route can distinguish transport
            # failures from validation failures (the FE surfaces
            # them with different banners).
            raise
        except ValueError:
            # Malformed upstream body — the route maps to 502.
            raise

        validated: list[dict] = []
        for raw in llm_pairs:
            clean = _validate_dedup_pair(raw, rules)
            if clean is None:
                continue
            ci = clean["canonical_index"]
            di = clean["candidate_index"]
            canonical_rule = rules[ci]
            candidate_rule = rules[di]
            # Same-category sanity check (defence-in-depth — the
            # prompt only sees one category at a time, so this
            # should never fire unless the LLM hallucinates cross-
            # category pairs in a single response). If it does
            # fire, drop the pair.
            if canonical_rule["id"] == candidate_rule["id"]:
                continue
            # Canonical is the SHORTER keyword; on a tie, the
            # lower priority number wins (mirrors L1). This
            # canonical-orientation matters because
            # :func:`consolidate_duplicate_groups` groups BY
            # canonical_id — flipping the pair would create two
            # groups for the same logical merge.
            can_kw = canonical_rule["keyword"] or ""
            cand_kw = candidate_rule["keyword"] or ""
            if len(cand_kw) < len(can_kw) or (
                len(cand_kw) == len(can_kw)
                and candidate_rule["priority"]
                < canonical_rule["priority"]
            ):
                canonical_rule, candidate_rule = (
                    candidate_rule, canonical_rule
                )
                can_kw, cand_kw = cand_kw, can_kw
            validated.append(
                {
                    "canonical_id": canonical_rule["id"],
                    "canonical_keyword": can_kw,
                    "candidate_id": candidate_rule["id"],
                    "candidate_keyword": cand_kw,
                    "method": "llm",
                    "confidence": clean["confidence"],
                    "rationale": clean["rationale"] or (
                        f"Semantic duplicate: {can_kw!r} and "
                        f"{cand_kw!r} refer to the same merchant"
                    ),
                }
            )
        _PROMPT_CACHE[fingerprint] = (validated, now + CACHE_TTL)
        all_pairs.extend(validated)
    return all_pairs
