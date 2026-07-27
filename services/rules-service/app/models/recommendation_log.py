"""Phase 4 — Recommendation approval workflow audit trail.

Stores every AI-generated recommendation so the user can approve, deny,
or dismiss them. Each row is an immutable record: the ``status`` column
tracks the lifecycle (pending → approved / denied / dismissed) and
``resolved_at`` / ``resolved_by`` capture the resolution metadata.

The ``metadata_json`` column stores a JSON blob with extra context
(category, source insight, related transaction ids, etc.) so the
ApprovalQueue UI can render a rich card without a second query.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    priority = Column(
        String(16),
        nullable=False,
        default="medium",
        server_default="medium",
    )  # high | medium | low
    status = Column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )  # pending | approved | denied | dismissed
    category = Column(
        String(64),
        nullable=False,
        default="general",
        server_default="general",
    )  # savings | spending | goal | general
    impact = Column(String(255), nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON blob for extra context
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(
        String(32),
        nullable=True,
    )  # user | auto | system

    # Relationship back to user (optional, for eager loading).
    user = relationship("User", backref="recommendation_logs", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<RecommendationLog id={self.id} status={self.status!r} "
            f"priority={self.priority!r} title={self.title!r}>"
        )
