# Atlas Synthetic Financial Fixtures

These fixtures are independently generated synthetic test data. They are not
customer data, legacy Finance Copilot payloads, transformed statements, or
production exports. Every identity uses `Atlas Test Bank` and `Test Household
Alpha`; account identifiers are intentionally obvious test identifiers.

Run `.venv-rules/bin/python tests/synthetic_fixtures/generate.py` from the
repository root to regenerate the CSV and text-layer PDF fixtures and their
SHA-256 manifest. The generator is deterministic, uses fixed 2026 dates, has
no network access, and writes only service test-fixture directories plus
`MANIFEST.json`.

Do not replace these with real statements, customer data, credentials, or
financial exports. Review `MANIFEST.json` after regeneration and run the
fixture tests before committing.

| Fixture group | Coverage restored |
| --- | --- |
| Rules CSV fixtures | Normalization, summary suppression, malformed/empty inputs, amount edge cases, merchant-rule import, duplicate detection, and debit/credit persistence. |
| Finlynq CSV fixtures | Summary suppression, split debit/credit amounts, wide activity exports, and parser-real structural contracts. |
| Text-layer PDF fixtures | Credi-style transaction extraction, 401k period rollups, brokerage extraction, and best-effort no-garbage behavior. |

`MANIFEST.json` records every generated repository-relative filename, format,
its exact consumer tests, synthetic identifiers, generator version, and
SHA-256 checksum. Relative paths are unique keys; duplicate paths make
generation fail.

The credit-year-end PDF deliberately contains `1,234.56`, `2,345.67`,
`456.78`, `321.09CR`, and `654.32CR`, plus a synthetic `9,999.99` summary
balance. Its `merchant.example, ZZ` layout exercises the Credi-specific
parser without real institution, merchant, or location data.
