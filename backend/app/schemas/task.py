from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TaskType = Literal["generate_next_chapter", "generate_next_chapters_batch", "generate_chapter_tts", "bootstrap_novel"]
TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class AsyncTaskResponse(BaseModel):
    id: int
    novel_id: int
    chapter_no: int | None = None
    task_type: TaskType
    status: TaskStatus
    reused_existing: bool = False
    owner_key: str
    request_payload: dict[str, Any] = Field(default_factory=dict)
    progress_message: str | None = None
    progress_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_payload: dict[str, Any] = Field(default_factory=dict)
    retry_of_task_id: int | None = None
    cancel_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    retryable: bool = False
    can_cancel: bool = False
    can_retry: bool = False
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    queue_wait_seconds: float | None = None
    status_url: str | None = None
    events_url: str | None = None

    model_config = {"from_attributes": True}


class AsyncTaskListResponse(BaseModel):
    novel_id: int
    total: int
    items: list[AsyncTaskResponse] = Field(default_factory=list)


class AsyncTaskEventResponse(BaseModel):
    id: int
    task_id: int
    novel_id: int
    event_type: str
    level: str = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    attempt_no: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AsyncTaskEventListResponse(BaseModel):
    novel_id: int
    task_id: int
    total: int
    items: list[AsyncTaskEventResponse] = Field(default_factory=list)


class AsyncTaskCleanupResponse(BaseModel):
    novel_id: int
    keep_latest: int
    deleted_count: int
    deleted_task_ids: list[int] = Field(default_factory=list)
