from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.time_utils import utcnow_naive


class AsyncTask(Base):
    __tablename__ = "async_tasks"
    __table_args__ = (
        Index("ix_async_tasks_novel_status", "novel_id", "status"),
        Index("ix_async_tasks_owner_status", "owner_key", "status"),
        Index("ix_async_tasks_novel_type_created_at", "novel_id", "task_type", "created_at"),
        Index("ix_async_tasks_retry_of_task_id", "retry_of_task_id"),
        Index("ix_async_tasks_cancel_requested_at", "cancel_requested_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    novel_id: Mapped[int] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    progress_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    progress_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    retry_of_task_id: Mapped[int | None] = mapped_column(ForeignKey("async_tasks.id", ondelete="SET NULL"), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    novel = relationship("Novel", back_populates="async_tasks")
    retry_of_task = relationship("AsyncTask", remote_side=[id], foreign_keys=[retry_of_task_id], uselist=False)
    events = relationship("AsyncTaskEvent", back_populates="task", cascade="all, delete-orphan")
