"""MerchantRule — substring keywords the categorizer uses as Pass 2 fallback.

Phase 24 — DB-backed SEED rules, admin-editable without BE redeploy.

Today (pre-Phase-24) the categorizer reads ``MERCHANT_RULES`` from a
Python module-level dict (~117 keywords across 12 categories,
declaration-ordered for greedy short-circuit). Stable, but additive
cost: every new merchant the user wants to tag requires a code
change + uvicorn restart. Phase 24 moves the dict into the DB so the
Settings UI can add/remove/disable keywords without a redeploy.

Schema decisions:

- ``category_id`` FK ``categories.id`` (NOT NULL) — the relationship
  between a rule and the resolved category is by id, NOT by name;
  renaming a Category row stays valid because the FK tracks
  ``categories.id`` (already-stable across renames).

- ``keyword`` String NOT NULL — the substring pattern matched against
  ``(merchant_name + " " + description).upper()``. Stored uppercased
  by the seed + route-write paths so the categorizer's per-row scan
  skips a per-call upper (saves O(N) microseconds on bulk imports).

- ``priority`` Int NOT NULL default 100 — preserves the greedy
  short-circuit ordering of the old static dict (Income keywords hit
  before Transfer keywords; within Income, "PAYROLL" before
  "DIRECT DEPOSIT"). Seed assigns monotonically increasing values
  (10, 20, 30, ...) across the dict's declaration order so existing
  test fixtures that walk dict-order keep working. User-added rules
  default to 100 (LAST per category) so they do not silently displace
  system order unless the user explicitly re-prioritises via PUT.

- ``is_archived`` Bool NOT NULL default False — soft-delete flag.
  Hard-deleting a system rule would let the boot-time seed re-insert
  the same keyword on next uvicorn restart, undoing the user's delete.
  Soft-delete keeps the row but excludes it from the categorizer's
  per-batch scan. The seed helper checks for ``is_archived`` and
  SKIPS rows that are soft-deleted, so the keyword stays gone forever
  (a future re-enable is a one-line PUT).

- ``created_at`` / ``updated_at`` DateTime — lightweight audit.

- ``UNIQUE(category_id, keyword)`` — the SAME substring can map to
  multiple categories across time (e.g., one user wants
  "STARBUCKS"→"Food & Dining", another wants it→"Other"), but only
  ONE row per category at any moment. A user re-adding a previously
  archived keyword must ``PUT is_archived=false`` on the archived
  row OR (re)POST it and let IntegrityError resolve; the route layer
  documents this contract.

Indexes:

- PK on ``id`` — every other table in this ORM has it; matcher parity.
- Index on ``(priority)`` — the categorizer's per-batch SELECTs
  ``WHERE is_archived = false ORDER BY priority ASC``; the index
  keeps the read O(log N) even with 500+ rows of user additions.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class MerchantRule(Base):
    """Phase 24 — DB-backed substring categorizer rule.

    One row per (category, keyword) pair. System seeds are inserted
    by ``app.services.categorizer.seed_default_merchant_rules`` on
    FastAPI startup; user additions land via ``POST /api/merchant-rules/``.
    Both paths converge here so the categorizer's runtime SELECT
    sees ONE merged set.
    """

    __tablename__ = "merchant_rules"

    id = Column(Integer, primary_key=True, index=True)
    # FK to ``categories.id``. ON DELETE behavior is governed by
    # the SQLAlchemy relationship + the migration's ON DELETE CASCADE
    # for ``category_id``; a category deletion will sweep its rules
    # so we never end up with orphan rows pointing at a missing
    # category. See migration ``h3c4d5e6f7a8`` for the SQL-side
    # semantics.
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=False,
    )
    # Uppercased substring pattern. Always stored uppercased by the
    # write paths (``seed_default_merchant_rules`` + the route's
    # POST/PUT handlers) so the categorizer's per-row scan skips a
    # per-call upper.
    keyword = Column(String, nullable=False)
    # Greedy short-circuit ordering. ``categorize_transactions``
    # does ``ORDER BY priority ASC`` on its per-batch SELECT; seed
    # assigns 10, 20, 30 ... across the dict's declaration order.
    priority = Column(Integer, nullable=False, default=100)
    # Soft-delete flag. The categorizer's SELECT filters
    # ``is_archived = false`` AND the seed helper skips rows that
    # are archived so a one-time DELETE stays gone forever.
    is_archived = Column(Boolean, nullable=False, default=False)
    # Phase 27 — provenance column. One of:
    #   - 'system'    — boot-time seed (migration ``J0a1b2c3d4e5``
    #                   back-fills with this default; seed.py also
    #                   explicitly sets it on each INSERT).
    #   - 'manual'    — Add rule form on /settings.
    #   - 'tag-rule'  — Promote-to-Rule flow on /activity (Phase 25+).
    #   - 'imported'  — CSV import via POST /api/merchant-rules/import.
    #   - 'llm'       — Forward-compatible: NOT YET emitted by any
    #                   write path (the categorizer reads rules but
    #                   does not auto-create them today; a Phase 28
    #                   LLM-rule-suggester will set this).
    # IMMUTABLE past creation: ``MerchantRuleUpdate`` does NOT
    # declare a ``source`` field so a client cannot rewrite history
    # via PUT (whitelist contract on Pydantic ``model_dump``).
    source = Column(
        String(length=20),
        nullable=False,
        # ORM-level default. Runtime route POSTs / imports always
        # pass ``source`` explicitly so this default only matters
        # for raw ORM-row construction outside the routes (tests,
        # fixtures). The migration's ``server_default`` covers the
        # ALTER-time back-fill (existing rows → 'system').
        default="manual",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "keyword",
            name="uq_merchant_rules_category_keyword",
        ),
        # The categorizer reads ``WHERE is_archived = false
        # ORDER BY priority ASC`` per batch. A composite index on
        # (``is_archived``, ``priority``) keeps the scan narrow even
        # with 500+ rows of user additions.
        Index(
            "ix_merchant_rules_archived_priority",
            "is_archived",
            "priority",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MerchantRule id={self.id} category_id={self.category_id} "
            f"keyword={self.keyword!r} priority={self.priority} "
            f"is_archived={self.is_archived}>"
        )
