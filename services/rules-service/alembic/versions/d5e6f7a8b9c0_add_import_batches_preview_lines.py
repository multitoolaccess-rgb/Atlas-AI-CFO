"""add import_batches.preview_lines

Revision ID: d5e6f7a8b9c0
Revises: c1d2e3f4a5b6
Create Date: 2026-07-02 12:00:00.000000

Phase 11 — activity-page improvements.

Adds a TEXT column ``preview_lines`` on ``import_batches``. The route
writes the parser's first-N text lines (or first-N parsed rows for
CSV/XLSX) so the FE's "View" affordance on historical imports can
render a preview panel even when ``saved_transactions == 0`` (the
user's "nothing loads" complaint on PDF / OCR batches).

Why TEXT instead of JSON:
- SQLite (the dev DB at ``finance.db``) does not have a native JSON
  type that round-trips lists cleanly with SQLAlchemy 2.x — TEXT is
  portable across SQLite + Postgres without branching the ORM.
- The route stores ``json.dumps(list)`` server-side and parses on
  read; downstream consumers do NOT need typed access (only the FE
  needs to know whether to render as a list of strings or a table).

Why nullable:
- Pre-Phase 11 rows have no preview at all; back-filling the
  parser is expensive (would re-open EVERY upload's PDF) and
  pointless (the user already saw the original preview banner
  at upload time). Leaving null cleanly distinguishes
  "preview was never persisted" from "preview was empty
  (genuine OCR failure)" — both render the same empty-state
  but only the latter benefits from a UI hint.

Downgrade drops the column. The migration is irreversible on
production but a backward-compatible ENGINE-only operation:
no other table FKs ``import_batches.preview_lines``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_batches",
        sa.Column("preview_lines", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_batches", "preview_lines")
