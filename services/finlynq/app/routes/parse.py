"""Finlynq /parse/* routes (Phase F3 parser + Phase F5 persistence).

Phase F1 ships the 501 stub at ``POST /parse/upload`` (versus 404) so the
FE can distinguish "service is up, contract not yet shipped" from a
Network Error. Phase F3 REPLACES the stub with the real parser
implementation. Phase F5 adds local persistence:

1. Parse the uploaded statement via :func:`parse_uploaded_statement`.
2. Create an ``ImportBatch`` row (envelope).
3. Persist ``Transaction`` rows for every parsed record.
4. Recalculate ``Account.current_balance`` from the sum of all
   transactions for that account.
5. Return :class:`FinlynqParseResponse` with real ``batch_id``,
   ``account_id``, and ``saved_transactions``.

``POST /parse/text`` stays a 501 stub (Phase F3 follow-up).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Account, ImportBatch, Transaction
from app.routes.shared import get_or_create_local_user
from app.projection_state.currency import CurrencyEvidenceConflict, CurrencyEvidenceError, record_currency_evidence

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse", tags=["parse"])


class FinlynqParseResponse(BaseModel):
    """Locked shape mirroring rules-service's ``ImportResponse``.

    Phase F3 must return this shape (or a strict superset) so the
    forwarder at rules-service's ``POST /api/imports/upload`` works
    without adjustment. Field set is locked by
    ``tests/test_parse_upload_contract.py::test_finlynq_parse_response_shape_is_locked``.

    Phase F5: ``batch_id`` / ``account_id`` / ``saved_transactions``
    are now populated with real values after local persistence.
    """

    filename: str
    file_type: str
    record_count: int
    preview: List[Any]
    batch_id: Optional[int] = None
    account_id: Optional[int] = None
    saved_transactions: Optional[int] = None


@router.post("/upload", response_model=FinlynqParseResponse)
async def upload_statement(
    file: UploadFile = File(...),
    account_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> FinlynqParseResponse:
    """Phase-F3 parser + Phase-F5 persistence.

    1. Parse the uploaded statement via :func:`parse_uploaded_statement`.
    2. Resolve the target account (explicit ``account_id`` or first
       active account for the user).
    3. Persist an ``ImportBatch`` + ``Transaction`` rows.
    4. Recalculate ``Account.current_balance``.
    5. Return the response with real ``batch_id`` / ``account_id`` /
       ``saved_transactions``.
    """
    try:
        result = parse_uploaded_statement_safe(file)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Phase 5b.2 OCR fallback for text-less PDFs.
    if result["file_type"] == "pdf" and result["record_count"] == 0:
        try:
            from app.services.ocr_parser import ocr_parse_statement

            ocr_result = ocr_parse_statement(file)
            if ocr_result.get("record_count", 0) > 0:
                result = ocr_result
        except ValueError:
            pass

    # --- Phase F5 persistence ------------------------------------------
    batch_id: Optional[int] = None
    saved_txn_count: Optional[int] = None
    resolved_account_id: Optional[int] = account_id

    if account_id is not None:
        local_user = get_or_create_local_user(db, _current_user)
        account = (
            db.query(Account)
            .filter(Account.id == account_id, Account.user_id == local_user.id)
            .first()
        )
        if account:
            declared_currency = result.get("declared_currency")
            if declared_currency is not None:
                try:
                    record_currency_evidence(
                        db,
                        account=account,
                        event_type="assertion",
                        source_kind="structured_statement",
                        code=declared_currency,
                        observed_at=datetime.now(timezone.utc),
                        source_reference=f"statement-import:{account.id}",
                        actor_category="statement_parser",
                        idempotency_key=f"statement-currency:{account.id}:{declared_currency}",
                        apply=True,
                    )
                except CurrencyEvidenceConflict:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="account currency evidence conflicts; reconciliation required",
                    ) from None
                except CurrencyEvidenceError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="account currency evidence is unavailable",
                    ) from None
            parsed_records = result.get("parsed_records", [])
            if parsed_records:
                preview_json = json.dumps(
                    [r for r in parsed_records[:50]],
                    default=str,
                )
                batch = ImportBatch(
                    user_id=account.user_id,
                    account_id=account.id,
                    filename=result["filename"],
                    file_type=result["file_type"],
                    record_count=len(parsed_records),
                    processed_at=datetime.now(timezone.utc),
                    preview_lines=preview_json,
                )
                db.add(batch)
                db.flush()
                batch_id = batch.id

                saved_count = 0
                dropped_no_date = 0
                for rec in parsed_records:
                    # Parsers emit "transaction_date" (NOT "date") as the
                    # canonical key — CSV/PDF/OFX/Excel all use it. Using
                    # rec.get("date") silently returned None and fell back
                    # to datetime.now(), stamping every imported transaction
                    # with today's date instead of the real statement date.
                    txn_date = rec.get("transaction_date")
                    if isinstance(txn_date, str):
                        try:
                            txn_date = datetime.fromisoformat(txn_date)
                        except (ValueError, TypeError):
                            dropped_no_date += 1
                            _logger.warning(
                                "Could not parse transaction_date string %r; "
                                "dropping record", txn_date,
                            )
                            continue
                    elif txn_date is None:
                        dropped_no_date += 1
                        _logger.warning(
                            "Record missing transaction_date (desc=%s); "
                            "dropping", rec.get("description", "?")[:40],
                        )
                        continue

                    txn = Transaction(
                        account_id=account.id,
                        import_batch_id=batch.id,
                        description=rec.get("description", "Unknown"),
                        amount=float(rec.get("amount", 0)),
                        transaction_date=txn_date,
                        merchant_name=rec.get("merchant_name"),
                        is_pending=False,
                    )
                    db.add(txn)
                    saved_count += 1

                db.flush()
                saved_txn_count = saved_count

                if dropped_no_date:
                    _logger.info(
                        "Dropped %d record(s) with missing/unparseable "
                        "transaction_date during persistence of %s.",
                        dropped_no_date, result["filename"],
                    )

                # Recalculate account balance from settled transactions
                # (exclude pending so they don't inflate the balance).
                total = (
                    db.query(
                        sa_func.coalesce(sa_func.sum(Transaction.amount), 0.0)
                    )
                    .filter(
                        Transaction.account_id == account.id,
                        Transaction.is_pending.is_(False),
                    )
                    .scalar()
                )
                account.current_balance = float(total)
                db.add(account)
                db.commit()

                _logger.info(
                    "Persisted %d transactions for account %d, "
                    "updated balance to %.2f",
                    saved_count,
                    account.id,
                    float(total),
                )
            else:
                db.commit()
        else:
            _logger.warning(
                "account_id=%d not found; skipping persistence",
                account_id,
            )
    # else: no account_id provided — parse-only (backward compat)

    return FinlynqParseResponse(
        filename=result["filename"],
        file_type=result["file_type"],
        record_count=result["record_count"],
        preview=result.get("preview", []),
        batch_id=batch_id,
        account_id=resolved_account_id,
        saved_transactions=saved_txn_count,
    )


def parse_uploaded_statement_safe(file: UploadFile) -> dict:
    """Defensive dispatch wrapper.

    ``parse_uploaded_statement`` (lifted from rules-service) accepts
    a FastAPI ``UploadFile``. We re-import here (instead of at module
    top) so the ``app.services`` package isn't dragged into the
    ``app.routes`` import chain at process start.

    Phase F5 refactor: ``parse_uploaded_statement`` now returns
    ``parsed_records`` alongside ``preview`` in a single call (the
    format-specific transaction parser is invoked inside the same
    dispatch), so the safe wrapper no longer needs to re-read the
    raw bytes and re-parse via a second pass.
    """
    from app.services.import_parser import parse_uploaded_statement

    return parse_uploaded_statement(file)


@router.post("/text")
async def parse_text(payload: dict) -> None:
    """Phase F3 follow-up stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Finlynq POST /parse/text lands in Phase F4.",
    )
