from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.time_utils import utcnow_naive


class Intervention(Base):
    __tablename__ = "interventions"
    __table_args__ = (
        Index("ix_interventions_novel_created_at", "novel_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    novel_id: Mapped[int] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    effective_chapter_span: Mapped[int] = mapped_column(Integer, default=5)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    novel = relationship("Novel", back_populates="interventions")
