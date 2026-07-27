"""add source + description columns to accounts — Phase 40 provenance

Revision ID: L0b1c2d3e4f5
Revises: 5a76428de6eb
Create Date: 2026-07-05 22:00:00.000000

Phase 40 — Surface WHERE-WAS-THIS-ACCOUNT-FROM on every ``accounts`` row so
the user can read the Accounts page and instantly answer "did I add this
manually, or did it come from a Fidelity PDF / Plaid link / Robinhood
holdings CSV?". The previous state left the user with an "Imported
Statements" + 4 Fidelity accounts spread and no clue which was which.

Schema change
-------------
Adds two columns to ``accounts``:

- ``source VARCHAR(20) NOT NULL DEFAULT 'manual'`` — coarse provenance.
  Values are constrained to ``manual`` / ``imported`` / ``plaid`` at the
  Pydantic schema layer (see ``AccountSource`` in
  ``app/schemas/__init__.py``); the DB column is plain VARCHAR so a
  future enum expansion (e.g. ``brokerage-api``) requires a code change
  but NOT a schema migration.
- ``description TEXT NULL`` — free-text note. Auto-filled at every BE
  create-path with a parser-aware diagnostic (e.g.
  ``"Fidelity Investment Report: 4 accounts from Portfolio_Positions.csv"``)
  and editable via ``PUT /api/accounts/{id}``.

Back-fill strategy
------------------
1. ``server_default='manual'`` so any pre-existing ``accounts`` rows
   (the orphan "Imported Statements" + any past Fidelity / Robinhood
   / rollover Manual rows) silently get ``source='manual'`` at ALTER
   time. This is intentionally a default; legacy rows CANNOT be
   back-filled more precisely without a separate UPDATE pass that
   joins on account_name patterns, and the cosmetic mislabel is
   fixable by re-running the relevant past import (which the route
   layer now stamps with the correct value).
2. ``description NULL`` is the default — legacy rows show no
   diagnostic text. Re-running the import appends a fresh description
   via the route layer; editorial edits via PUT persist.

Down-grade
----------
Drops both columns in reverse declaration order. After downgrade,
the route layer still serves a 200 on GET (the ``source`` /
``description`` fields are silently absent from the pydantic
response model until the migration is re-applied) so monitoring
triggers a follow-up re-deploy rather than a 500 cascade.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "L0b1c2d3e4f5"
down_revision: Union[str, None] = "5a76428de6eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``description`` first, then ``source`` so a downgrade (DROP in
    # reverse order) matches the natural declaration order. ``source``
    # carries ``server_default='manual'`` so any pre-existing
    # ``accounts`` rows land with the runtime default; new ORM-row
    # construction goes through the route layer's explicit source
    # stamp (the model-level ``default`` is also 'manual' as a
    # belt-and-braces fallback for ad-hoc scripts).
    op.add_column(
        "accounts",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "source")
    op.drop_column("accounts", "description")
