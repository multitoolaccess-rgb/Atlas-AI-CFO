"""User model — authentication anchor + extended profile fields.

Phase 3 lift from the legacy WealthIQ user model (see
``docs/wealthiq-merge-plan.md`` §4 Reuse Map item 5). Two adaptions,
the original + a Phase 7 identity-key split:

- ``from app.db import Base`` → ``from app.database import Base`` (Phase 2 renamed
  ``db.py`` → ``database.py`` and switched to a class-based ``DeclarativeBase``).
- **Phase 7 — identity key**: ``local_user_sub`` (String, UNIQUE) carries the
  JWT ``sub`` claim that ``app.auth.require_user`` validates against
  ``settings.local_user``. ``get_or_create_local_user`` now keys off this
  column instead of ``email``, so a Settings-page save that re-saves with
  a different email can no longer fork the row into a duplicate (the
  cause of the original "Network Error" on /api/profile/ PUT).
  ``email`` remains UNIQUE for display purposes but is no longer the
  identity key.

`users.id` is referenced as a foreign key by Account, Budget, and ImportBatch —
the migration order in ``alembic/versions/0001_initial.py`` MUST create `users`
FIRST for the FKs to bind.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Identity key (Phase 7+) — the JWT ``sub`` claim as stored on the row.
    # ``get_or_create_local_user`` looks up by this column; ``email`` is
    # display-only. The Phase 7 migration added this column with a NOT
    # NULL + UNIQUE constraint and backfilled existing rows to 'alex'.
    local_user_sub = Column(String, unique=True, index=True, nullable=False)
    # Display address (kept UNIQUE for backward compatibility; NOT used
    # by the auth/identity path after Phase 7).
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
    goals = Column(String, nullable=True)  # JSON or text summary of goals
    risk_profile = Column(String, nullable=True)  # conservative / moderate / aggressive
    target_net_worth = Column(String, nullable=True)
    time_horizon_years = Column(Integer, nullable=True)
    annual_income = Column(String, nullable=True)
    total_liabilities = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<User sub={self.local_user_sub!r} email={self.email!r}>"
