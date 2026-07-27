"""User model — authentication anchor + extended profile fields.

Phase-F5 verbatim lift of ``services/rules-service/app/models/user.py``.

Mirrors the Phase-7 identity-key split independently: ``local_user_sub``
carries the JWT ``sub`` claim that ``app.auth.require_user`` validates
against ``settings.local_user``. ``get_or_create_local_user`` (lifted
into ``app/routes/shared.py`` in F5b) keys off this column.

Cross-DB invariant: ``users.id`` is the FK target for Account, Budget,
Goal, and ImportBatch. Phase-F5f's cross-DB aggregator test seeds the
User row BEFORE any FK-bearing row to satisfy the NOT-NULL FK on
those models.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Identity key — JWT ``sub`` claim as stored on the row. NOT NULL
    # + UNIQUE. ``get_or_create_local_user`` looks up by this column.
    local_user_sub = Column(String, unique=True, index=True, nullable=False)
    # Display address — kept UNIQUE for backward compatibility; NOT
    # used by the auth/identity path.
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Extended profile fields.
    date_of_birth = Column(DateTime, nullable=True)
    phone_number = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    currency_preference = Column(String, nullable=True, default="USD")
    goals = Column(String, nullable=True)
    risk_profile = Column(String, nullable=True)
    target_net_worth = Column(String, nullable=True)
    time_horizon_years = Column(Integer, nullable=True)
    annual_income = Column(String, nullable=True)
    total_liabilities = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<User sub={self.local_user_sub!r} email={self.email!r}>"
