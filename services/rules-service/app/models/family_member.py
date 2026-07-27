"""Phase 16 — Family Member model.

Per-user record that groups accounts. Every user has exactly ONE
``is_self`` row (bootstrapped by :func:`app.routes.shared.
get_or_create_local_user`) so accounts that omit ``family_member_id``
auto-default to Self. Additional members (Spouse, Kid, ...) are
created through ``POST /api/family-members/`` and soft-deleted via
``DELETE /api/family-members/{id}``.

Design choices:

- **Owner-scoped** via ``user_id`` FK to ``users.id``. Routes never
  return rows from another user.
- **UNIQUE (user_id, name)** prevents accidental duplicate member
  names per user (two kids both named "Alex" → POST second time →
  409 via the global IntegrityError handler in ``app.main``).
- **is_self BOOL** is the canonical flag — the auto-seed uses it
  rather than a name-string lookup (``app.routes.shared``
  finds the existing Self row via ``WHERE is_self=True`` instead
  of WHERE name='Self' so users CAN rename Self to e.g. "Alex"
  without breaking the auto-seed). Read-only on the PUT path;
  Pydantic ``FamilyMemberUpdate`` excludes the column entirely so
  clients cannot promote an arbitrary member to Self.
- **is_archived BOOL** mirrors the Goal soft-delete convention:
  list excludes archived rows; the row stays in the DB so any FK
  reference (transactions, account snapshots) can still resolve.
  ``Account.family_member_id`` FK is NOT CASCADE-archived.
- **color VARCHAR(7)** holds the ``#RRGGBB`` hex string with the
  regex enforced by the FE/BE Pydantic ``Field(pattern=...)`` layer.
  We do NOT validate the regex at the ORM level (defence-in-
  depth would require a SQL CHECK constraint that breaks SQLite
  ALTER TABLE; Pydantic is the single source of truth).
- **created_at / updated_at** mirrors the rest of the schema so
  a future audit-log feature can diff rows uniformly.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    # 7-char string ``#RRGGBB`` per Pydantic regex; the schema does
    # NOT enforce the regex (defence-in-depth would require a
    # CHECK constraint that breaks SQLite ALTER TABLE on a column
    # that's part of a later batch_alter_table operation).
    color = Column(String, nullable=False, default="#10b981")
    is_archived = Column(Boolean, default=False, nullable=False)
    # Per-user self-flag. Single source of truth for the auto-seed
    # branch in :func:`get_or_create_local_user`. Set to True
    # exactly once at Self-row creation; never mutated thereafter.
    is_self = Column(Boolean, default=False, nullable=False)
    # Phase 16+ — richer household profile. Captures each member's
    # role in the household + employment + age so the BE can drive
    # household-level analytics (e.g. "two earners, one dependent")
    # without N+1 follow-up reads on the FE.
    #
    # All three are NULLABLE on purpose:
    #   • ``relationship`` is "" (kept empty by the column default
    #     semantics) for any row that hasn't filled out the household
    #     profile; the migration's data backfill sets ``'Self'`` only
    #     on the per-user Self row so the locked semantics are
    #     preserved across restarts.
    #   • ``working_status`` is free-form at the column layer; the
    #     Pydantic Literal on the request schemas enforces the
    #     canonical 6-value enum (Employed / Unemployed / Student /
    #     Retired / Homemaker / Other).
    #   • ``age`` is a plain INT, no CHECK constraint (which would
    #     break SQLite ALTER TABLE on a column that's later mutated
    #     in a ``batch_alter_table``). Pydantic ``Field(ge=0,
    #     le=120)`` is the schema-layer guard.
    #
    # We deliberately don't store ``date_of_birth`` instead of ``age``
    # — the user explicitly asked for "age", and "today − DOB" is
    # awkward to maintain (every birthday would silently stale a
    # stored age). A Phase 18+ refactor can swap the column for DOB
    # + a computed view if the household analytics require it.
    relationship = Column(String, nullable=True)
    working_status = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        # UNIQUE constraint enforces (user_id, name) so duplicate
        # member names per owner are rejected; the global
        # IntegrityError handler maps the resulting error to HTTP 409.
        UniqueConstraint("user_id", "name", name="uq_family_member_user_name"),
        # No explicit ``Index("ix_family_members_user_id", "user_id")``
        # here — the column-level ``user_id = Column(..., index=True)``
        # above already declares that index, and a SECOND declaration
        # with the same name would emit TWO ``CREATE INDEX`` statements
        # during ``Base.metadata.create_all``, which SQLite rejects
        # with ``index ix_family_members_user_id already exists``. The
        # migration's sibling ``op.create_index(... if_not_exists=True)``
        # owns the alembic-driven path (cold-start upgrade on a brand
        # new DB); the column-level ``index=True`` owns the create_all-
        # driven path (test bootstrap + Development hot-reload).
        # Index on is_self WHERE=... True is omitted intentionally:
        # the auto-seed path is one filter on a small per-user table,
        # so a partial index would offer no measurable win and
        # would complicate the SQLite migration.
    )

    def __repr__(self) -> str:
        flag = " (Self)" if self.is_self else ""
        return f"<FamilyMember {self.name!r}{flag} color={self.color}>"
