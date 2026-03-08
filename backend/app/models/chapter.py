from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Text, UniqueConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("novel_id", "chapter_no", name="uq_chapter_novel_chapter_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    novel_id: Mapped[int] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    generation_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    novel = relationship("Novel", back_populates="chapters")
    summary = relationship("ChapterSummary", back_populates="chapter", uselist=False, cascade="all, delete-orphan")
