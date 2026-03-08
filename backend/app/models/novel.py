from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), nullable=False)
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    protagonist_name: Mapped[str] = mapped_column(String(100), nullable=False)
    style_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    story_bible: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="active")
    current_chapter_no: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    characters = relationship("Character", back_populates="novel", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan")
    interventions = relationship("Intervention", back_populates="novel", cascade="all, delete-orphan")
