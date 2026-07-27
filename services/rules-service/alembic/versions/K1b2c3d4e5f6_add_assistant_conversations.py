"""add assistant_conversations + assistant_messages — Phase 30c

Revision ID: K1b2c3d4e5f6
Revises: J0a1b2c3d4e5
Create Date: 2026-07-04

Phase 30c — conversation persistence for the AI Finance Assistant.
Two new tables:

- ``assistant_conversations``: per-user conversation grouping.
  FK'd to ``users.id`` via ``user_id``. Auto-pruned to last 50 per
  user by the orchestrator's ``_prune_old_conversations`` helper.

- ``assistant_messages``: individual chat turns (user + assistant).
  FK'd to ``assistant_conversations.id`` with ``ON DELETE CASCADE``
  so deleting a conversation removes all its messages (no orphans).

Index strategy:
- ``ix_assistant_conversations_user_id`` — speeds up the user-scoped
  list query (``WHERE user_id = ? ORDER BY updated_at DESC``).
- ``ix_assistant_messages_conversation_id`` — speeds up the per-
  conversation message load (``WHERE conversation_id = ? ORDER BY id``).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "K1b2c3d4e5f6"
down_revision = "J0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- assistant_conversations ---
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="New conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_conversations_id", "assistant_conversations", ["id"])
    op.create_index("ix_assistant_conversations_user_id", "assistant_conversations", ["user_id"])

    # --- assistant_messages ---
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_used", sa.String(100), nullable=True),
        sa.Column("tool_result", sa.Text(), nullable=True),
        sa.Column("follow_ups", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_messages_id", "assistant_messages", ["id"])
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_conversation_id", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_conversations_user_id", table_name="assistant_conversations")
    op.drop_index("ix_assistant_conversations_id", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
