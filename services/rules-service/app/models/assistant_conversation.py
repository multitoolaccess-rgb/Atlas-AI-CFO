"""AssistantConversation — Phase 30c conversation persistence.

A conversation groups a sequence of user + assistant messages exchanged
in a single chat session. Scoped to the local user via ``user_id`` FK
to ``users.id`` (same identity-key pattern as Goals/Accounts).

Design choices:
- **owner-scoped** via ``user_id`` — every conversation belongs to the
  local user; routes never return another user's conversations.
- **auto-pruned to last 50** — a background prune (called from the
  orchestrator on each new conversation creation) hard-deletes older
  conversations per user. Local-first = no cloud retention needed.
- **title** is auto-generated from the first user message (truncated
  to 80 chars) so the FE sidebar can show a meaningful label without
  a separate title-edit flow.
- **created_at / updated_at** for ordering — the FE sorts by
  ``updated_at DESC`` so the most-recently-active conversation is on top.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="New conversation")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Phase 30c — one-to-many relationship to messages.
    # ``cascade="all, delete-orphan"`` so deleting a conversation
    # also removes its messages (no orphaned rows).
    messages = relationship(
        "AssistantMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.id.asc()",
    )

    def __repr__(self) -> str:
        return f"<AssistantConversation id={self.id} title={self.title!r}>"
