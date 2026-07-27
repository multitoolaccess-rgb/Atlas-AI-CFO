"""AssistantMessage — Phase 30c individual chat message.

Each row is a single turn in a conversation: either a user message
(``role="user"``) or an assistant reply (``role="assistant"``).

Design choices:
- **FK to assistant_conversations** with ``ON DELETE CASCADE`` —
  deleting a conversation removes all its messages (no orphans).
- **role** is a plain string (``"user"`` or ``"assistant"``) rather
  than an enum — keeps the schema portable across SQLite + Postgres
  without an import dependency on a Python enum class.
- **tool_used / tool_result** are stored on the assistant message
  row so the FE can re-render inline tool cards when loading a past
  conversation (Phase 30e will use these for chart/table cards).
- **follow_ups** is a JSON-encoded string (SQLite has no native JSON
  column type that's portable; we store a JSON string and parse it
  on read). The route layer handles serialization.
- **status** mirrors the orchestrator's ``"ok" | "offline" | "error"``
  so the FE can render the offline banner for historical messages too.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    # Assistant-only fields (NULL for user messages):
    tool_used = Column(String(100), nullable=True)
    tool_result = Column(Text, nullable=True)  # JSON-encoded dict or None
    follow_ups = Column(Text, nullable=True)   # JSON-encoded list or None
    status = Column(String(20), nullable=False, default="ok")  # "ok"|"offline"|"error"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Phase 30c — back-reference to the parent conversation.
    conversation = relationship("AssistantConversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<AssistantMessage id={self.id} role={self.role!r}>"
