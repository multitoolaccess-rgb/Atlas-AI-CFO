"""MerchantAlias — per-user effective-merchant → category map.

Phase 18 — categorizer v2 (alias-learning layer).

The categorizer has three passes (alias → substring → fuzzy). The
substring pass writes to this table on every successful match, so the
NEXT import of the same merchant text skips past the substring scan
and goes straight to Pass 1 (cheaper, deterministic, exact lookup).

Why a table (not just a Python dict at module load): the alias map is
PER-USER. A family member's payroll merchant may be entirely unrelated
to another family member's expense at the same string. Storing the
alias per-user means the categorizer learns THIS household's habits
without leaking them across users (single-user production today, multi-
user future when auth is expanded).

Schema:

- ``alias_key`` = canonical text key, computed by
  :func:`app.services.categorizer.normalize_alias_key` (uppercase,
  non-alphanumeric collapsed to single-space, no small-token drop).
  Storing the canonical form so the lookup SELECT is an exact match
  instead of a per-row normalize-then-compare loop.

- ``source_text`` = the original (non-normalized) merchant text from
  the row that produced this alias. Used for audit + a future
  "show me your learned aliases" debug surface. NOT used in
  matching — only for display / debugging.

- ``category_id`` FK → ``categories.id``. ON DELETE isn't cascaded
  because a category deletion should NOT silently wipe years of
  per-user learned aliases (a future "re-create this category and
  retag" migration can re-attach the aliases by name).

- ``use_count`` + ``last_used_at`` = lightweight telemetry. The
  categorizer bumps ``use_count`` on every alias hit so a future
  Phase 18.1+ dashboard can show "Top 50 categories by alias hits".
  Not surfaced today; the column is cheap and forward-compatible.

- ``UNIQUE(user_id, alias_key)`` = single-row uniqueness invariant
  per-user per-key. The upsert helper ``_upsert_alias`` in
  categorizer.py relies on this constraint to do an INSERT-or-INCREMENT
  without a SELECT-then-UPDATE race.

Indexes:

- PK on ``id`` (every other table has it; matcher parity).
- Indexed on ``user_id`` so the categorizer's bulk SELECT
  (``WHERE user_id = :user AND alias_key IN (...)``) is index-only.
- Indexed on ``alias_key`` so reverse lookups ("which user has
  learned this alias?") are fast for the audit surface.
"""
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    category_id = Column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False,
    )
    # Canonical text key (case-folded, punctuation-collapsed). Used
    # for exact-match lookups in the categorizer's Pass 1.
    alias_key = Column(
        String,
        nullable=False,
        index=True,
    )
    # Original merchant text this alias was learned FROM (for audit).
    # Stored untouched so a future debug console can show the
    # "user typed ... and we learned Y" lineage.
    source_text = Column(String, nullable=False)
    # Lightweight telemetry — bumped on every alias hit.
    use_count = Column(Integer, nullable=False, default=1)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Per-user single-row uniqueness. The upsert in categorizer.py
    # relies on this constraint to do INSERT-or-INCREMENT atomically.
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "alias_key",
            name="uq_merchant_aliases_user_alias",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MerchantAlias user_id={self.user_id} "
            f"alias_key={self.alias_key!r} category_id={self.category_id} "
            f"use_count={self.use_count}>"
        )
