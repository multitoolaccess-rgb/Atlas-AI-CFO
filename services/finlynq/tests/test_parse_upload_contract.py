"""Phase F1 contract: POST /parse/upload returns 501 today with a
stable detail message. Phase F3 must replace the 501 with a real
parser; the locked shape lives in ``app/routes/parse.py::FinlynqParseResponse``
(mirrors rules-service's ImportResponse) — the F3 swap is then a
mechanical check against this contract.

Why 501 vs 404: 501 explicitly signals "we own this endpoint, not yet
implemented" — distinct from "we do not own this URL". The
rules-service forwarder at ``POST /api/imports/upload`` (Phase F3)
interprets 501 to surface a debug banner instead of the misleading
Network Error.

Locked post-F3 shape (FinlynqParseResponse mirrors ImportResponse):

```
{
  "filename": str,
  "file_type": "csv" | "pdf" | "ofx" | "xlsx",
  "record_count": int,
  "preview": List[Any],          # CSV dicts; PDF/OFX raw lines
  "batch_id": Optional[int],
  "account_id": Optional[int],
  "saved_transactions": Optional[int],
}
```
"""
from app.routes.parse import FinlynqParseResponse


def test_parse_upload_returns_200_with_finlynq_parse_response_shape(client_with_auth):
    """Phase-F3 ships the real parser — POST /parse/upload returns 200
    + a :class:`FinlynqParseResponse`-shaped body. Phase F1's 501 stub
    is removed (this contract test now enforces the post-F3 shape).

    The test feeds a minimal CSV (4 rows: header + 3 data rows) so the
    parser exercises ``parse_csv_file`` and the field-mapping logic.
    Compare against ``FINLYNQ_PARSE_RESPONSE_EXPECTED_KEYS`` to lock
    parity with rules-service's ``ImportResponse``.

    Uses ``client_with_auth`` because ``/parse/upload`` has
    ``Depends(require_user)``; an unauthenticated POST would 401 before
    the parser runs.
    """
    csv_body = (
        b"date,description,amount,merchant_name\n"
        b"2025-01-15,Coffee shop,-4.50,Blue Bottle\n"
        b"2025-01-16,Payroll,3500.00,Acme Corp\n"
        b"2025-01-17,Grocery,-87.32,Whole Foods\n"
    )
    response = client_with_auth.post(
        "/parse/upload",
        files={"file": ("sample.csv", csv_body, "text/csv")},
    )
    assert response.status_code == 200, (
        f"POST /parse/upload must return 200 with the real parser "
        f"(got {response.status_code} {response.text}). Phase-F3 ships "
        f"the parser; a regression to 501 is a contract violation."
    )
    body = response.json()

    # All :class:`FinlynqParseResponse` fields present.
    FINLYNQ_PARSE_RESPONSE_EXPECTED_KEYS = {
        "filename", "file_type", "record_count", "preview",
        "batch_id", "account_id", "saved_transactions",
    }
    actual_keys = set(body.keys())
    assert FINLYNQ_PARSE_RESPONSE_EXPECTED_KEYS <= actual_keys, (
        f"FinlynqParseResponse shape drifted. missing="
        f"{FINLYNQ_PARSE_RESPONSE_EXPECTED_KEYS - actual_keys}, "
        f"extra={actual_keys - FINLYNQ_PARSE_RESPONSE_EXPECTED_KEYS}"
    )

    # CSV-specific assertions confirming the parser actually ran.
    assert body["filename"] == "sample.csv", f"filename mismatch: {body['filename']!r}"
    assert body["file_type"] == "csv", f"file_type mismatch: {body['file_type']!r}"
    assert body["record_count"] == 3, f"record_count mismatch: {body['record_count']!r}"
    assert isinstance(body["preview"], list) and len(body["preview"]) >= 1, (
        f"preview should be non-empty when records survive: {body['preview']!r}"
    )

    # Phase-F3 contract: persistence is Finlynq's job in F5+; the
    # IDs are None today. If a future phase populates them, this
    # assertion tracks.
    assert body["batch_id"] is None, (
        f"Phase-F3 must emit batch_id=None (Finlynq has no DB yet): got {body['batch_id']!r}"
    )
    assert body["saved_transactions"] is None, (
        f"Phase-F3 must emit saved_transactions=None: got {body['saved_transactions']!r}"
    )


def test_parse_upload_handles_unsupported_extension_returns_400(client_with_auth):
    """Phase-F3 contract: an unsupported extension (e.g. ``.xyz``)
    fails FAST inside the parser with ``ValueError`` → mapped to
    HTTP 400 by the route. The 501 detail-message phase-marker
    precedent (F1) no longer applies — the route never throws.

    NOTE: uses ``client_with_auth`` (NOT the bare ``client`` fixture)
    because ``/parse/upload`` has ``Depends(require_user)`` on the
    route. An unauthenticated POST would short-circuit at 401 BEFORE
    the parser ever runs, masking the real ``ValueError → 400`` mapping.
    """
    response = client_with_auth.post(
        "/parse/upload",
        files={"file": ("statement.xyz", b"binary junk", "application/octet-stream")},
    )
    assert response.status_code == 400, (
        f"unsupported extension must return 400 (got {response.status_code} {response.text})"
    )
    detail = str(response.json().get("detail", "")).lower()
    assert "csv" in detail or "pdf" in detail or "ofx" in detail or "xlsx" in detail or "unsupported" in detail or "format" in detail


def test_finlynq_parse_response_shape_is_locked():
    """Assert the ImportResponse-mirror Pydantic model exposes the
    same keys rules-service's ImportResponse does — Phase F3's real
    parsing must return this shape OR the migration of the
    forwarder breaks every existing FE upload.
    """
    expected_keys = {
        "filename",
        "file_type",
        "record_count",
        "preview",
        "batch_id",
        "account_id",
        "saved_transactions",
    }
    actual_keys = set(FinlynqParseResponse.model_fields.keys())
    assert expected_keys == actual_keys, (
        f"FinlynqParseResponse field set drifted from rules-service's "
        f"ImportResponse. Missing: {expected_keys - actual_keys}. "
        f"Extra: {actual_keys - expected_keys}. Phase F3's real "
        f"parser must emit the same wire shape."
    )


def test_finlynq_parse_response_has_empty_model_config():
    """Round-5 reviewer hardening: load-bearing pin for the YAGNI-drop
    of ``arbitrary_types_allowed=True``.

    rules-service's ``ImportResponse`` carries ``model_config =
    ConfigDict(arbitrary_types_allowed=True)`` because Plaid ingest
    populates ``preview`` with rich Pydantic-typed rows. Finlynq's
    parser will always emit ``preview: List[Any]`` at F3 because we
    lift the same dict-of-CSV-rows shape, NOT a typed-list. The
    flag would be a no-op today; adding it speculatively is YAGNI.

    This test is the executable enforcement of the asymmetry. The
    docstring in ``app/routes/parse.py`` documents the intent; this
    makes it survive in CI. If F3 actually introduces a custom
    Pydantic type into ``preview``, re-evaluate: either widen the
    shape to ``List[TransactionSummary]`` (then the bit IS needed)
    or keep the YAGNI-drop with a comment in this test.
    """
    config = FinlynqParseResponse.model_config
    assert config == {}, (
        f"FinlynqParseResponse.model_config must be empty dict (got {config!r}). "
        f"The YAGNI-drop of ``arbitrary_types_allowed=True`` is load-bearing for "
        f"F1; an F3 lift that adds it speculatively is a regression against this "
        f"covenant. See app/routes/parse.py module docstring for the rationale."
    )
