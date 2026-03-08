from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChapterSummary(Base):
    __tablename__ = "chapter_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, unique=True)
    event_summary: Mapped[str] = mapped_column(Text, nullable=False)
    character_updates: Mapped[dict] = mapped_column(JSON, default=dict)
    new_clues: Mapped[list] = mapped_column(JSON, default=list)
    open_hooks: Mapped[list] = mapped_column(JSON, default=list)
    closed_hooks: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chapter = relationship("Chapter", back_populates="summary")
