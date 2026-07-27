#!/usr/bin/env python3
"""Generate deterministic, wholly synthetic Atlas parser fixtures.

Run from the repository root with either Atlas Python 3.12 environment:
    .venv-rules/bin/python tests/synthetic_fixtures/generate.py

The generator writes only the two service test-fixture trees and this area's
manifest. It deliberately uses fictional identifiers and fixed dates.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "services/rules-service/tests/fixtures"
FINLYNQ = ROOT / "services/finlynq/tests/fixtures"
LABEL = "SYNTHETIC TEST DATA — NOT A REAL FINANCIAL STATEMENT"
GENERATOR_VERSION = "1.0.0"


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def write_pdf(path: Path, lines: list[str]) -> None:
    """Create a deterministic text-layer PDF with synthetic metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=letter, pageCompression=0, invariant=1)
    canvas.setTitle("Atlas Synthetic Test Data")
    canvas.setAuthor("Atlas AI CFO synthetic fixture generator")
    canvas.setSubject(LABEL)
    canvas.setCreator("Atlas synthetic fixture generator v1.0.0")
    y = 760
    for line in lines:
        canvas.drawString(40, y, line)
        y -= 13
        if y < 40:
            canvas.showPage()
            y = 760
    canvas.save()
    path.write_bytes(buffer.getvalue())


def checking_rows(count: int) -> list[list[str]]:
    rows = [
        ["Description", "", "Summary Amt."],
        [LABEL, "", ""],
        ["Atlas Test Bank Checking", "", "TEST-ACCOUNT-0001"],
        ["Test Household Alpha", "", ""],
        ["Synthetic period", "", "2026-06-30"],
        [],
        ["Date", "Description", "Amount", "Running Bal."],
    ]
    for index in range(count):
        day = (index % 28) + 1
        description = f"ATLAS SYNTHETIC MERCHANT {index:03d}"
        amount = f"-{(index % 90) + 10}.25"
        if index < 3:
            description = f"SERVICEMAC SYNTHETIC MORTGAGE {index + 1}"
            amount = "-1250.00"
        if 490 <= index < 496:
            # Repeated values exercise duplicate-warning behavior without PII.
            description = "ATLAS SYNTHETIC CASH WITHDRAWAL"
            amount = "-40.00"
            day = 20
        rows.append([f"06/{day:02d}/2026", description, amount, "10000.00"])
    return rows


def edge_rows() -> list[list[str]]:
    valid = [
        ("Refund accounting", "(50.00)"), ("Padded sign negative", "- 100.00"),
        ("Trailing dash negative", "100.00-"), ("Signed parens", "-(75.50)"),
        ("Euro symbol", "€500.50"), ("Pound symbol", "£1,200.99"),
        ("Us thousands", "$1,234.56"), ("Big payroll", "$1,250,000.00"),
    ]
    valid += [(f"Synthetic edge {n}", f"{n + 10}.10") for n in range(10)]
    rows = [["Date", "Description", "Amount"]]
    rows += [["06/15/2026", description, amount] for description, amount in valid]
    return rows


def generic_rules_fixtures() -> None:
    write_csv(RULES / "sample-bank-statement.csv", [
        ["Date", "Description", "Amount", "Merchant"],
        ["06/01/2026", "Coffee shop", "-4.50", "Blue Bottle Coffee"],
        ["06/02/2026", "Atlas synthetic payroll", "2500.00", "Atlas Test Employer"],
        ["06/03/2026", "Synthetic groceries", "-82.10", "Atlas Test Market"],
        ["06/04/2026", "Synthetic utility", "-115.00", "Atlas Test Utility"],
        ["06/05/2026", "Synthetic transfer", "-50.00", "Test Household Alpha"],
    ])
    write_csv(RULES / "empty-statement.csv", [["Date", "Description", "Amount"]])
    write_csv(RULES / "bad-statement.csv", [["Synthetic", "Not a supported statement"], ["x", "y"]])
    write_csv(RULES / "citi_credit_card.csv", [
        ["Status", "Date", "Description", "Debit", "Credit"],
        ["Cleared", "06/19/2026", "ATLAS SYNTHETIC BURRITOS TEST-0001", "10.68", ""],
        ["Cleared", "06/18/2026", "ATLAS SYNTHETIC REGISTRATION", "116.39", ""],
        ["Cleared", "05/16/2026", "ATLAS SYNTHETIC AUTOPAY TEST-0002", "", "25.00"],
        ["Cleared", "04/12/2026", "ATLAS SYNTHETIC PAYMENT", "", "971.38"],
        ["Cleared", "03/28/2026", "ATLAS SYNTHETIC REFUND", "", "15.00"],
    ])
    write_csv(RULES / "sample-merchant-rules.csv", [
        ["category_name", "keyword", "priority", "is_archived", "source"],
        ["Food & Dining", "SAMPLE-FIXTURE-FOOD-A", "10", "false", "synthetic"],
        ["Food & Dining", "SAMPLE-FIXTURE-FOOD-B", "20", "false", "synthetic"],
        ["Groceries", "SAMPLE-FIXTURE-GROCERY-A", "30", "false", "synthetic"],
        ["Transportation", "SAMPLE-FIXTURE-TRANSIT", "40", "false", "synthetic"],
        ["Shopping", "SAMPLE-FIXTURE-SHOP-A", "50", "false", "synthetic"],
    ])
    write_csv(RULES / "sample-merchant-rules-with-errors.csv", [
        ["category_name", "keyword", "priority", "is_archived", "source"],
        ["Food & Dining", "EDGE-OK-FOOD", "10", "false", "synthetic"],
        ["Transportation", "EDGE-OK-TRANSIT", "20", "false", "synthetic"],
        ["", "EDGE-BLANK-CATEGORY", "30", "false", "synthetic"],
        ["No Such Category", "EDGE-BAD-CATEGORY", "40", "false", "synthetic"],
        ["Food & Dining", "EDGE-BAD-PRIORITY", "not-a-number", "false", "synthetic"],
        ["Food & Dining", "EDGE-BAD-ARCHIVED", "50", "maybe", "synthetic"],
        ["Food & Dining", "", "60", "false", "synthetic"],
    ])


def write_csv_sets() -> None:
    rules_samples = RULES / "sample_statements"
    write_csv(rules_samples / "checking_stmt.csv", checking_rows(505))
    write_csv(rules_samples / "savings_stmt.csv", [
        ["Date", "Particulars", "Withdrawals", "Deposits"],
        *[[f"06/{day:02d}/2026", f"ATLAS SYNTHETIC SAVINGS {day}", "25.00" if day % 2 else "", "" if day % 2 else "75.00"] for day in range(1, 13)],
    ])
    write_csv(rules_samples / "edge_cases.csv", edge_rows())
    write_csv(RULES / "sample_statements_real/chase_checking_3100.csv", [
        ["Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"],
        ["DEBIT", "06/01/2026", "ATLAS SYNTHETIC DEBIT", "-25.00", "DEBIT", "1000.00", "", ""],
        ["CREDIT", "06/02/2026", "ATLAS SYNTHETIC CREDIT", "125.00", "CREDIT", "1125.00", "", ""],
    ])
    write_csv(RULES / "sample_statements_real/chase_credit_3407_activity.csv", [
        ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"],
        ["06/29/2026", "07/01/2026", "ATLAS SYNTHETIC BAKERY 9028", "Food & Drink", "Sale", "-5.50", ""],
    ])
    generic_rules_fixtures()

    f_samples = FINLYNQ / "sample_statements"
    write_csv(f_samples / "checking_stmt.csv", checking_rows(120))
    write_csv(f_samples / "savings_stmt.csv", [
        ["Date", "Particulars", "Withdrawals", "Deposits"],
        *[[f"06/{day:02d}/2026", f"ATLAS SYNTHETIC SAVINGS {day}", "20.00" if day % 2 else "", "" if day % 2 else "80.00"] for day in range(1, 13)],
    ])
    f_real = FINLYNQ / "sample_statements_real"
    write_csv(f_real / "bofa_checking_stmt.csv", checking_rows(8))
    write_csv(f_real / "bofa_savings_stmt.csv", [["Date", "Description", "Amount"], ["06/01/2026", "ATLAS SYNTHETIC SAVINGS", "100.00"]])
    write_csv(f_real / "robinhood-transactions.csv", [["Activity Date", "Process Date", "Settle Date", "Instrument", "Description", "Trans Code", "Quantity", "Price", "Amount"], ["06/01/2026", "06/02/2026", "06/03/2026", "ATLS", "ATLAS SYNTHETIC MULTILINE DESCRIPTION", "Buy", "1", "10.00", "-10.00"]])


def write_pdf_sets() -> None:
    samples = FINLYNQ / "sample_statements"
    credi = [LABEL, "Atlas Test Bank annual synthetic summary"]
    amounts = [160.27, 1868.73, 143.37, 99.50, 27.81] + [float(10 + index) for index in range(200)]
    for index, amount in enumerate(amounts):
        suffix = "CR" if index in {3, 4} or 10 <= index < 20 else ""
        credi.append(f"06/{(index % 28) + 1:02d}/2026 ATLAS SYNTHETIC PURCHASE {index:03d} {amount:,.2f}{suffix}")
    write_pdf(samples / "credi_YearEndSummary_2026.pdf", credi)
    write_pdf(samples / "Fidelity NetBenefits - Statement Details.pdf", [
        LABEL, "Statement Period: 01/01/2026 to 03/31/2026", "Your Account Activity By Fund",
        "Activity Total", "Employee Contributions 0.00 9,988.62", "Employer Contributions 0.00 8,739.88", "Dividends 0.00 1,906.90",
    ])
    brokerage = [LABEL, "April 1, 2026 - April 30, 2026"]
    brokerage += [f"04/{(index % 28) + 1:02d} ATLAS SYNTHETIC SECURITY (YOU BOUGHT) -{index + 10}.00" for index in range(60)]
    brokerage[2] = "04/08 ATLAS ALPHABET SYNTHETIC (YOU BOUGHT) -199.84"
    brokerage[3] = "04/01 ATLAS NVIDIA SYNTHETIC DIVIDEND RECEIVED 1.59"
    brokerage[4] = "04/09 04/09 WWW.PROVID SYNTHETIC -50.00"
    write_pdf(samples / "individual_Statement4302026.pdf", brokerage)
    real = FINLYNQ / "sample_statements_real"
    shutil.copyfile(samples / "credi_YearEndSummary_2026.pdf", real / "bofa_credi_YearEndSummary_2026.pdf")
    for name in ("chase-credit-stmt.pdf", "chase-checking-stmt.pdf", "robinhood-statement.pdf"):
        write_pdf(real / name, [LABEL, "06/01/2026 ATLAS SYNTHETIC PDF ENTRY -10.00"])


def write_manifest() -> None:
    test_map = {
        "checking_stmt.csv": ["Rules CSV import, categorizer, finance-query integration", "Finlynq summary-preamble parity"],
        "savings_stmt.csv": ["Rules finance-query integration", "Finlynq split debit/credit parsing"],
        "edge_cases.csv": ["Rules amount normalization and import persistence"],
        "sample-bank-statement.csv": ["Rules CSV parser normalization and preview"],
        "empty-statement.csv": ["Rules empty-statement rejection/zero-record paths"],
        "bad-statement.csv": ["Rules malformed-schema rejection path"],
        "citi_credit_card.csv": ["Rules dual debit/credit dashboard import"],
        "sample-merchant-rules.csv": ["Rules merchant-rule CSV import"],
        "sample-merchant-rules-with-errors.csv": ["Rules merchant-rule per-row errors"],
        "chase_checking_3100.csv": ["Rules trailing-column CSV reconciliation"],
        "chase_credit_3407_activity.csv": ["Rules description/merchant auto-promotion"],
        "credi_YearEndSummary_2026.pdf": ["Finlynq Credi text-layer PDF extraction"],
        "Fidelity NetBenefits - Statement Details.pdf": ["Finlynq 401k period rollup extraction"],
        "individual_Statement4302026.pdf": ["Finlynq brokerage text-layer extraction"],
        "bofa_credi_YearEndSummary_2026.pdf": ["Finlynq parser-real PDF structural contract"],
        "chase-credit-stmt.pdf": ["Finlynq best-effort PDF no-garbage contract"],
        "chase-checking-stmt.pdf": ["Finlynq best-effort PDF no-garbage contract"],
        "robinhood-statement.pdf": ["Finlynq best-effort PDF no-garbage contract"],
        "bofa_checking_stmt.csv": ["Finlynq top-summary suppression"],
        "bofa_savings_stmt.csv": ["Finlynq savings CSV structural contract"],
        "robinhood-transactions.csv": ["Finlynq wide activity CSV structural contract"],
    }
    paths = sorted(path for root in (RULES, FINLYNQ) for path in root.rglob("*") if path.is_file())
    payload = {
        "schema_version": "atlas-synthetic-fixtures/v1",
        "generator_version": GENERATOR_VERSION,
        "safety": "All fixtures are independently generated synthetic test data; no legacy statement payloads were read or reused.",
        "fixtures": [
            {"path": str(path.relative_to(ROOT)), "format": path.suffix.lstrip("."), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "institution": "Atlas Test Bank", "person": "Test Household Alpha", "tests": test_map.get(path.name, ["Synthetic fixture documentation/supporting test"]) }
            for path in paths
        ],
    }
    (Path(__file__).with_name("MANIFEST.json")).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    write_csv_sets()
    write_pdf_sets()
    write_manifest()


if __name__ == "__main__":
    main()
