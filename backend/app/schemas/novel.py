from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NovelCreate(BaseModel):
    genre: str = Field(..., min_length=1, max_length=100)
    premise: str = Field(..., min_length=1)
    protagonist_name: str = Field(..., min_length=1, max_length=100)
    style_preferences: dict[str, Any] = Field(default_factory=dict)


class NovelListItemResponse(BaseModel):
    id: int
    title: str
    genre: str
    protagonist_name: str
    current_chapter_no: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NovelListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[NovelListItemResponse] = Field(default_factory=list)


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
    updated_at: datetime

    model_config = {"from_attributes": True}


class NovelDeleteResponse(BaseModel):
    deleted_novel_id: int
    deleted_title: str
    deleted_chapter_count: int
