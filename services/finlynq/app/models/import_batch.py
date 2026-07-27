"""ImportBatch — one CSV/PDF/OCR statement upload's processing envelope.

Phase-F5 verbatim lift of ``services/rules-service/app/models/import_batch.py``.

`import_batches.id` is FK-referenced by Transaction on BOTH services'
read-side ORM graph (shared-DB wiring). The aggregator at Finlynq's
``/state/summary`` queries ``ImportBatch.processed_at`` for the
``last_import_at`` field.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    record_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    # Captured-at-upload preview lines. See rules-service comment for
    # the rationale ("View" affordance on historical PDF/OCR imports
    # where ``saved_transactions == 0``).
    preview_lines = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ImportBatch {self.filename} ({self.file_type})>"
