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


def test_append_only_currency_evidence_models_are_mirrored():
    rules = (ROOT / "services/rules-service/app/models/account_currency_evidence.py").read_text(encoding="utf-8")
    finlynq = (ROOT / "services/finlynq/app/models/account_currency_evidence.py").read_text(encoding="utf-8")
    for declaration in (
        "__tablename__ = \"account_currency_evidence\"",
        "event_type = Column(String(16), nullable=False)",
        "source_kind = Column(String(32), nullable=False)",
        "source_reference_hash = Column(String(64), nullable=False)",
        "idempotency_key_hash = Column(String(64), nullable=False)",
        "supersedes_event_id = Column(String(36), ForeignKey(\"account_currency_evidence.id\", ondelete=\"RESTRICT\"), nullable=True)",
    ):
        assert declaration in rules
        assert declaration in finlynq
