from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.time_utils import utcnow_naive


class Monster(Base):
    __tablename__ = "monsters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    novel_id: Mapped[int] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    species_type: Mapped[str] = mapped_column(String(80), default="monster")
    threat_level: Mapped[str] = mapped_column(String(80), default="待判定")
    core_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    dynamic_state: Mapped[dict] = mapped_column(JSON, default=dict)
    reader_weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    novel = relationship("Novel", back_populates="monsters")
