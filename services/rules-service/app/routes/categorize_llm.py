"""Phase 22 + Phase 31 — ``/api/categorize/*`` routes.

Routes:

- ``POST /api/categorize/llm-batch``  — Pass 4 (Ollama JSON-mode) on a
  batch of transaction IDs. ``MAX_BATCH_SIZE`` = 20 per call; FE
  chunks larger lists into multiple invocations.
- ``POST /api/categorize/run-all``    — Phase 31: bulk-categorize
  every transaction belonging to the local user via the heuristic
  Pass-1/2/3 chain. Returns ``(total, categorized, skipped)`` so
  the FE's "Rule created + auto-categorized: N of M" toast can
  display ground-truth counts.
- ``POST /api/categorize/llm``        — singular alias of
  ``/api/categorize/llm-batch`` for the FE's
  ``rulesService.categorizeWithLlm`` helper.

Auth: every route requires a valid JWT cookie (``Depends(require_user)``).
The cross-service invariant is documented on each route's docstring.
"""
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_user
# ``get_db`` is wired into the route signatures only so FastAPI's
# dependency injection resolves the request-scoped session (matches
# the pattern used by every other route in this service).
from app.database import get_db
from app.models import Account, Transaction
from app.routes.shared import get_or_create_local_user
from app.services.categorizer import categorize_transactions
from app.services.llm_categorizer import (
    MAX_BATCH_SIZE,
    categorize_with_llm_async,
)

LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/categorize", tags=["categorize"])


# ---------------------------------------------------------------------
# Phase 22 — request/response shapes for /api/categorize/llm-batch.
# Mirrors ``app.services.llm_categorizer`` so the stub validator can
# pick a row by ``transaction_id`` without any rename fight.
# ---------------------------------------------------------------------
class LLMBatchInputRow(BaseModel):
    transaction_id: int
    merchant_name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None


class LLMBatchRequest(BaseModel):
    transactions: List[LLMBatchInputRow] = Field(default_factory=list)


class LLMSuggestionOut(BaseModel):
    txn_id: int
    suggested_category: str
    confidence: float
    coerced: Optional[bool] = None
    cached: Optional[bool] = None


class LLMBatchResponse(BaseModel):
    suggestions: List[LLMSuggestionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------
# Phase 31 — request/response shapes for /api/categorize/run-all.
# Returns ``(total, categorized, skipped)`` so the FE's auto-tag
# toast can show ground-truth counts after a new Merchant Rule.
# ---------------------------------------------------------------------
class RunAllResponse(BaseModel):
    total: int
    categorized: int
    skipped: int


# ---------------------------------------------------------------------
# Phase 31 alias — singular /api/categorize/llm
# ---------------------------------------------------------------------
class CategorizeWithLlmRequest(BaseModel):
    # Singular FE contract: ``rulesService.categorizeWithLlm({transaction_ids})``
    # sends a chunk of ``transaction_id`` ints. The route loads the
    # Transactions for the local user, transforms to the service-layer
    # dict shape, and calls ``categorize_with_llm_async``.
    transaction_ids: List[int] = Field(default_factory=list)


@router.post("/llm-batch", response_model=LLMBatchResponse)
async def categorize_llm_batch(
    payload: LLMBatchRequest,
    _db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 22 — run Pass 4 (Ollama JSON-mode) on a batch of transaction IDs.

    The FE's Activity page submits the IDs of every untagged row, up
    to ``MAX_BATCH_SIZE`` per call (20). The HE-side batch splitters
    can chunk larger lists into multiple invocations; the BE just
    enforces the per-call cap.

    Errors map to the wire codes the FE's ``classifyError`` already
    handles (503 → "retry later" banner; 502 → "model misbehaved,
    retry" banner; 422 → inline form-validation message).
    """
    if len(payload.transactions) == 0:
        return LLMBatchResponse(suggestions=[])
    if len(payload.transactions) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"At most {MAX_BATCH_SIZE} transactions per Pass-4 batch "
                f"(got {len(payload.transactions)}). Chunk the FE's picker "
                f"into multiple calls."
            ),
        )

    rows = [r.model_dump() for r in payload.transactions]
    try:
        suggestions = await categorize_with_llm_async(rows)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Ollama is unreachable. Pass 4 (AI categorization) is "
                "offline — the heuristic bulk auto-categorize button "
                "still works. Retry once Ollama is back up, or skip "
                f"this pass. ({str(exc)[:120]})"
            ),
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Ollama timed out after 60s. Try a smaller batch "
                f"or a faster model. ({str(exc)[:120]})"
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Ollama returned an invalid Pass-4 response (likely "
                "ignored the JSON-mode prompt). Retry once with a "
                "smaller batch, or fall back to the heuristic button. "
                f"({str(exc)[:200]})"
            ),
        )

    return LLMBatchResponse(
        suggestions=[LLMSuggestionOut(**s) for s in suggestions]
    )


@router.post("/llm", response_model=LLMBatchResponse)
async def categorize_with_llm(
    payload: CategorizeWithLlmRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 31 — singular alias for ``/api/categorize/llm-batch`` so the
    FE's ``rulesService.categorizeWithLlm`` helper hits a real wire
    instead of a 404.

    The route loads the local user's transactions for the requested
    IDs (chunked into 20-row batches per :func:`_run_llm_chunks`) so
    the caller doesn't have to know about ``MAX_BATCH_SIZE``. The
    response shape is identical to ``/api/categorize/llm-batch``.

    Errors:
    - 503 / 504 / 502 — same Ollama ladder as ``/llm-batch``. Per-
      chunk failures fall through to chunk-by-chunk error surface so
      a single Ollama blip doesn't nuke a 100-transaction run.
    """
    if not payload.transaction_ids:
        return LLMBatchResponse(suggestions=[])
    local_user = get_or_create_local_user(db, _current_user)
    # Load only the local user's rows (cross-user leak guard).
    # ``Transaction`` has no direct ``user_id`` column: ownership flows
    # through the owning ``Account`` (mirrors the transactions list
    # route's join), so filter through ``Account.user_id``.
    txn_rows = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Transaction.id.in_(payload.transaction_ids),
            Account.user_id == local_user.id,
        )
        .all()
    )
    if not txn_rows:
        return LLMBatchResponse(suggestions=[])

    # Build the service-layer dict shape; respects MAX_BATCH_SIZE by
    # chunking into multiple categorize_with_llm_async calls.
    chunk_dicts: list[dict] = []
    for t in txn_rows:
        chunk_dicts.append({
            "transaction_id": t.id,
            "merchant_name": t.merchant_name,
            "description": t.description,
            "amount": float(t.amount) if t.amount is not None else None,
        })

    aggregated: list[dict] = []
    try:
        for i in range(0, len(chunk_dicts), MAX_BATCH_SIZE):
            sub = chunk_dicts[i : i + MAX_BATCH_SIZE]
            suggestions = await categorize_with_llm_async(sub)
            aggregated.extend(suggestions)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Ollama is unreachable. Pass 4 (AI categorization) is "
                f"offline. ({str(exc)[:120]})"
            ),
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Ollama timed out after 60s. ({str(exc)[:120]})"
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Ollama returned an invalid Pass-4 response. "
                f"({str(exc)[:200]})"
            ),
        )

    return LLMBatchResponse(
        suggestions=[LLMSuggestionOut(**s) for s in aggregated]
    )


@router.post("/run-all", response_model=RunAllResponse)
async def run_all(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 31 — bulk-categorize every transaction for the local user.

    Drives the heuristic Pass-1/2/3 chain (alias → substring → fuzzy)
    WITHOUT any LLM/Ollama involvement. Used by:
      - The Settings page's "Rule created + auto-categorize" toast
        (after a new Merchant Rule is created).
      - Manual button on the Activity page (no FE wiring today, but
        the FE stub is reserved in ``ui/lib/api.ts``).

    Returns ``(total, categorized, skipped)`` so the FE can render
    something useful without parsing the third tuple element (the
    ``conflicts`` list — surfaced on a future iteration).

    Authentication: ``Depends(require_user)`` gates the route; the
    shared helper ``get_or_create_local_user`` keys the user's
    transactions correctly.
    """
    local_user = get_or_create_local_user(db, _current_user)
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == local_user.id)
        .all()
    )
    if not transactions:
        return RunAllResponse(total=0, categorized=0, skipped=0)

    categorized, skipped, _conflicts = categorize_transactions(
        db, transactions, allow_other=True,
    )
    LOG.info(
        "run-all categorize for user=%s: total=%d categorized=%d skipped=%d",
        local_user.local_user_sub,
        len(transactions), categorized, skipped,
    )
    return RunAllResponse(
        total=len(transactions),
        categorized=categorized,
        skipped=skipped,
    )
