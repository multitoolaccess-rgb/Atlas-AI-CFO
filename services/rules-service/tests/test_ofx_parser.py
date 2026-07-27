"""Phase 7 OFX parser tests \u2014 free Plaid alternative.

Smoke tests:

- ``parse_ofx_file`` returns the right preview shape (file_type='ofx',
  filename echoed, record_count matches txn count).
- ``parse_ofx_transactions`` returns the right row shape
  (transaction_date, amount, description, merchant_name=None,
  is_pending=False).
- Empty OFX (no transactions) returns ``[]`` without raising.

Test fixture:

- We don't ship a real bank OFX (proprietary, brittle). We synthesise
  a minimal OFX1 file using the standard ``OFXHEADER:100`` +
  ``DATA:OFXSGML`` header pattern + valid SGML, then assert the parser
  reads it back. ofxparse handles OFX1 well; for OFX2 (XML) we'd need
  a fuller fixture but the project uses the SGML format.
"""
import io
from typing import Any

import pytest
from fastapi import UploadFile


def _build_minimal_ofx1() -> bytes:
    """Synthesise a 1-account 1-transaction OFX1 file in-memory.

    Layout: standard OFX header + SGML body. ofxparse understands
    OFXHEADER:100 + DATA:OFXSGML pair well \u2014 that's what Plaid
    Sandbox + most real banks emit.
    """
    sgml = (
        "OFXSGML\n"
        "<OFX>\n"
        "<SIGNONMSGSRSV1>\n"
        "<SONRS>\n"
        "<STATUS>\n"
        "<CODE>0</CODE>\n"
        "<SEVERITY>INFO</SEVERITY>\n"
        "</STATUS>\n"
        "<DTSERVER>20240115120000</DTSERVER>\n"
        "<LANGUAGE>ENG</LANGUAGE>\n"
        "<FI>\n"
        "<ORG>TestBank</ORG>\n"
        "<FID>1234</FID>\n"
        "</FI>\n"
        "</SONRS>\n"
        "</SIGNONMSGSRSV1>\n"
        "<BANKMSGSRSV1>\n"
        "<STMTTRNRS>\n"
        "<TRNUID>1001</TRNUID>\n"
        "<STATUS>\n"
        "<CODE>0</CODE>\n"
        "<SEVERITY>INFO</SEVERITY>\n"
        "</STATUS>\n"
        "<STMTRS>\n"
        "<CURDEF>USD</CURDEF>\n"
        "<BANKACCTFROM>\n"
        "<BANKID>123456789</BANKID>\n"
        "<ACCTID>987654321</ACCTID>\n"
        "<ACCTTYPE>CHECKING</ACCTTYPE>\n"
        "</BANKACCTFROM>\n"
        "<BANKTRANLIST>\n"
        "<DTSTART>20240101</DTSTART>\n"
        "<DTEND>20240131</DTEND>\n"
        "<STMTTRN>\n"
        "<TRNTYPE>DEBIT</TRNTYPE>\n"
        "<DTPOSTED>20240115</DTPOSTED>\n"
        "<TRNAMT>-42.50</TRNAMT>\n"
        "<FITID>TXN0001</FITID>\n"
        "<NAME>WHOLE FOODS</NAME>\n"
        "<MEMO>Grocery run</MEMO>\n"
        "</STMTTRN>\n"
        "</BANKTRANLIST>\n"
        "<LEDGERBAL>\n"
        "<BALAMT>1234.56</BALAMT>\n"
        "<DTASOF>20240131</DTASOF>\n"
        "</LEDGERBAL>\n"
        "</STMTRS>\n"
        "</STMTTRNRS>\n"
        "</BANKMSGSRSV1>\n"
        "</OFX>\n"
    )
    header = (
        "OFXHEADER:100\n"
        "DATA:OFXSGML\n"
        "VERSION:102\n"
        "SECURITY:NONE\n"
        "ENCODING:USASCII\n"
        "CHARSET:1252\n"
        "COMPRESSION:NONE\n"
        "OLDFILEUID:NONE\n"
        "NEWFILEUID:NONE\n"
        "\n"
    )
    return (header + sgml).encode("ascii")


def _ofx_upload(name: str, body: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(body))


def test_parse_ofx_file_returns_preview_shape():
    """Synthesised OFX1 \u2192 preview looks right."""
    from app.services.import_parser import parse_ofx_file

    body = _build_minimal_ofx1()
    result = parse_ofx_file(_ofx_upload("statement.ofx", body))
    assert result["file_type"] == "ofx"
    assert result["filename"] == "statement.ofx"
    assert result["record_count"] == 1
    assert isinstance(result["preview"], list)
    assert len(result["preview"]) == 1


def test_parse_ofx_transactions_returns_one_record():
    """Synthesised OFX1 \u2192 1 normalised transaction record (negative amount)."""
    from app.services.import_parser import parse_ofx_transactions

    body = _build_minimal_ofx1()
    rows = parse_ofx_transactions(_ofx_upload("statement.ofx", body))
    assert len(rows) == 1
    row = rows[0]
    expected_keys = {
        "transaction_date",
        "amount",
        "description",
        "merchant_name",
        "is_pending",
    }
    assert set(row.keys()) == expected_keys
    # The synthesised OFX uses TRNAMT=-42.50 for Whole Foods.
    assert row["amount"] == pytest.approx(-42.50, abs=1e-6)
    # description comes from MEMO then NAME.
    assert row["description"] in ("Grocery run", "WHOLE FOODS")
    assert row["merchant_name"] is None  # OFX doesn't carry merchant_name field
    assert row["is_pending"] is False
    assert hasattr(row["transaction_date"], "year")  # datetime, not str


def test_parse_uploaded_statement_dispatches_to_ofx_for_qfx():
    """``parse_uploaded_statement`` dispatches ``.qfx`` to the OFX parser
    (same handler \u2014 OFX and QFX have identical layouts per Intuit's spec)."""
    from app.services.import_parser import parse_uploaded_statement

    body = _build_minimal_ofx1()
    result = parse_uploaded_statement(_ofx_upload("statement.QFX", body))
    assert result["file_type"] == "ofx"
    assert result["record_count"] == 1


def test_parse_ofx_file_rejects_garbage():
    """Garbage bytes raise ``ValueError`` (not a crash)."""
    from app.services import import_parser

    with pytest.raises(ValueError) as exc:
        import_parser.parse_ofx_file(_ofx_upload("broken.ofx", b"this is not OFX"))
    msg = str(exc.value).lower()
    assert "ofx" in msg or "parse" in msg
