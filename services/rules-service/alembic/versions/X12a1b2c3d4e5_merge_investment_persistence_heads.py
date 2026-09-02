"""Merge investment persistence with the category migration head."""
from typing import Sequence, Union

revision: str = "X12a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = ("U3e4f5a6b7c8", "W11a1b2c3d4e5")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
