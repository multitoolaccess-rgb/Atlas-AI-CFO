"""add relationship / working_status / age to family_members

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-03 18:00:00.000000

Phase 16+ -- richer household profile per member.

Adds three NULLABLE columns to ``family_members``:

- ``relationship`` VARCHAR (locked to a Pydantic Literal enum on the
  API: ``Self``, ``Spouse``, ``Child``, ``Parent``, ``Sibling``,
  ``Other``).
- ``working_status`` VARCHAR (Literal enum: ``Employed``,
  ``Unemployed``, ``Student``, ``Retired``, ``Homemaker``,
  ``Other``).
- ``age`` INTEGER (Pydantic ``Field(ge=0, le=120)`` cap).

Why NULLABLE rather than NOT-NULL with a default:

- A user who creates a brand-new Spouse / Child row via
  ``POST /api/family-members/`` may not have filled out working
  status + age at insert time. Forcing ``age=0`` or
  ``working_status='Other'`` pollutes the data the user later
  edits over. Nullable + UNSET (``NULL``) is the honest "not yet
  collected" state.
- The migration's backfill sets ``relationship='Self'`` ONLY on
  the per-user Self row to lock the canonical relationship value;
  every other row is left ``NULL`` so the user fills it in via the
  ``PUT /api/family-members/{id}`` path.

Backfill safety:

- ``UPDATE family_members SET relationship='Self' WHERE is_self=1``
  is idempotent on a re-run (overwrites 'Self' with 'Self').
- Re-applying the migration on a DB already at head is a no-op:
  ``op.add_column`` raises on duplicate column add, but the
  caller uses alembic's ``alembic upgrade`` which short-circuits
  per-revision tracking.

Downgrade drops the three columns. Because ``family_members`` has
no inbound FKs (the FK is OUTBOUND to ``users.id``), the drop is
reversible without scrubbing child tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 3 nullable columns + backfill Self-row relationship."""
    bind = op.get_bind()

    op.add_column(
        "family_members",
        sa.Column("relationship", sa.String(), nullable=True),
    )
    op.add_column(
        "family_members",
        sa.Column("working_status", sa.String(), nullable=True),
    )
    op.add_column(
        "family_members",
        sa.Column("age", sa.Integer(), nullable=True),
    )

    # Backfill ``relationship = 'Self'`` ONLY on rows where the
    # ``is_self`` flag is set. Spouse / Kid / Parent rows are
    # intentionally left NULL so the FE prompts the user to fill
    # them in via the Settings Family Members card. Without this
    # UPDATE, the Self row would have ``relationship == NULL``
    # after upgrade -- the route layer's "force='Self' on PUT"
    # defence would still keep a fresh browser rendering correct,
    # but a stale browser snapshot (cached FamilyMemberResponse
    # with relationship=null) would render "(Self)" badge
    # alongside a missing relationship label -- a visually broken
    # row.
    bind.execute(
        text(
            "UPDATE family_members "
            "SET relationship = 'Self' "
            "WHERE is_self = 1"
        )
    )


def downgrade() -> None:
    """Drop the 3 columns in reverse order."""
    op.drop_column("family_members", "age")
    op.drop_column("family_members", "working_status")
    op.drop_column("family_members", "relationship")
