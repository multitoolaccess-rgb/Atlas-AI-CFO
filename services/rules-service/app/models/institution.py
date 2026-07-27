"""Institution model — banks, brokers, crypto exchanges, etc.

Phase 3 lift (see ``docs/wealthiq-merge-plan.md`` §4 item 6). One trivial edit
(see ``app/models/user.py`` docstring — same reason).

`institutions.id` is referenced by Account only. The migration must create this
table BEFORE ``accounts`` so the FK binds.
"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True, index=True)
    plaid_id = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    institution_type = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    official_website = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Institution {self.name}>"
