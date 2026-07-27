"""ImportBatch — one CSV/PDF/OCR statement upload's processing envelope.

Phase 3 lift (``docs/wealthiq-merge-plan.md`` §4 item 10). Same trivial edit.

`import_batches.id` is FK-referenced by Transaction.
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
    # Phase 11 — first 50 text lines captured at upload time so
    # the FE's "View" affordance can render a preview panel for
    # historical PDF / OCR imports where ``saved_transactions == 0``.
    # For CSV/XLSX these are dict-shaped (the first parsed rows);
    # for PDF/OFX/OCR these are the raw text lines the parser saw.
    # Stored on the row rather than re-running the parser on every
    # View click (avoids re-opening 200-page statements).
    # SQLite/TEXT so the JSON-shaped payload from CSV rows survives.
    preview_lines = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ImportBatch {self.filename} ({self.file_type})>"
