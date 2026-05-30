"""ORM model for tracking processed AlphaSignal publications."""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


class SeenPublication(Base):
    """A newsletter publication already processed by the agent."""

    __tablename__ = "seen_publications"
    __table_args__ = (UniqueConstraint("publication_url", name="uq_publication_url"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    publication_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
    )
    dedup_key: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
