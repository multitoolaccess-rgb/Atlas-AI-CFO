"""Lock the duplicated shared-table currency declarations in step."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RULES_ACCOUNT = ROOT / "services/rules-service/app/models/account.py"
FINLYNQ_ACCOUNT = ROOT / "services/finlynq/app/models/account.py"


def test_account_currency_provenance_columns_match_across_service_models():
    rules = RULES_ACCOUNT.read_text(encoding="utf-8")
    finlynq = FINLYNQ_ACCOUNT.read_text(encoding="utf-8")
    for declaration in (
        "currency_code = Column(String(3), nullable=True)",
        "currency_source = Column(String(32), nullable=True)",
        "currency_observed_at = Column(DateTime(timezone=True), nullable=True)",
        "currency_source_reference = Column(String(128), nullable=True)",
    ):
        assert declaration in rules
        assert declaration in finlynq
