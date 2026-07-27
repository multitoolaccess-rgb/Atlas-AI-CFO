"""Category model — transactional taxonomy.

Phase-F4 lift of ``services/rules-service/app/models/category.py``
verbatim. Finlynq owns the canonical ``categories`` table per the
Phase-F2 shared-DB wiring decision (both services bind to the SAME
``settings.database_url``); having identical ORM classes referring
to the same DB table on both services is acceptable.

`categories.id` is FK-referenced by Transaction and Budget in
rules-service's read-side ORM graph (rules-service reads those FK
columns via the Finlynq forwarder — F5 preset). The Phase-F4 router
only writes / reads the ``categories`` rows themselves.
"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    color = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
