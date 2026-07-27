"""Phase 52 — standardise account types to canonical set.

Adds the canonical account_types module and standardises the accepted
values on ``accounts.account_type``. The existing enumeration was ad-hoc:
``checking``, ``savings``, ``credit``, ``credit_card``, ``investment``,
``hsa``, ``loan``, ``other`` — with ``credit`` and ``credit_card`` both
in use depending on the write path (FE dropdown used ``credit``, PDF
auto-detection used ``credit_card``).

This migration:

1. Renames any existing ``credit`` rows to ``credit_card`` (the canonical
   name). The FE dropdown is also updated to use ``credit_card`` so the
   two surfaces stay in lockstep.

2. Does NOT alter the column type or add a CHECK constraint — the
   Pydantic schema layer (:class:`AccountCreate`, :class:`AccountUpdate`)
   validates against the canonical set at write time, and existing rows
   keep whatever value they had (defence-in-depth: a future bug that
   writes an invalid type surfaces as a Pydantic 422, not a silent DB
   pollute).

Revision ID: L1c2d3e4f5a6
Revises: L0b1c2d3e4f5
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "L1c2d3e4f5a6"
down_revision: Union[str, None] = "L0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename any existing 'credit' account_type rows to 'credit_card'."""
    # SQLite-compatible: UPDATE with WHERE filter
    op.execute(
        sa.text("UPDATE accounts SET account_type = 'credit_card' WHERE account_type = 'credit'")
    )


def downgrade() -> None:
    """Reverse: rename 'credit_card' back to 'credit'.
    
    Note: this is lossy — rows that were originally 'credit_card' from
    PDF auto-detection (i.e. never 'credit') would also get renamed to
    'credit'. The upgrade is intended to be permanent; this downgrade
    exists only for migration-chain reversibility.
    """
    op.execute(
        sa.text("UPDATE accounts SET account_type = 'credit' WHERE account_type = 'credit_card'")
    )
