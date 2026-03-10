from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChapterResponse(BaseModel):
    id: int
    novel_id: int
    chapter_no: int
    title: str
    content: str
    generation_meta: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChapterBatchGenerateRequest(BaseModel):
    count: int = Field(1, ge=1, le=20, description="接下来要连续生成的章节数")


class ChapterBatchResponse(BaseModel):
    novel_id: int
    requested_count: int
    generated_count: int
    started_from_chapter: int
    ended_at_chapter: int | None = None
    chapters: list[ChapterResponse] = Field(default_factory=list)
    progress: list[dict[str, Any]] = Field(default_factory=list)
