from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.time_utils import utcnow_naive


class Novel(Base):
    __tablename__ = "novels"
    __table_args__ = (
        Index("ix_novels_updated_at", "updated_at"),
        Index("ix_novels_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), nullable=False)
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    protagonist_name: Mapped[str] = mapped_column(String(100), nullable=False)
    style_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    story_bible: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="active")
    current_chapter_no: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    characters = relationship("Character", back_populates="novel", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan")
    interventions = relationship("Intervention", back_populates="novel", cascade="all, delete-orphan")
    async_tasks = relationship("AsyncTask", back_populates="novel", cascade="all, delete-orphan")
