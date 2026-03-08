from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NovelCreate(BaseModel):
    genre: str = Field(..., min_length=1, max_length=100)
    premise: str = Field(..., min_length=1)
    protagonist_name: str = Field(..., min_length=1, max_length=100)
    style_preferences: dict[str, Any] = Field(default_factory=dict)


class NovelResponse(BaseModel):
    id: int
    title: str
    genre: str
    premise: str
    protagonist_name: str
    style_preferences: dict[str, Any]
    story_bible: dict[str, Any]
    current_chapter_no: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
