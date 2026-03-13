from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ChapterSerialStage = Literal["draft", "stock", "published"]
DeliveryMode = Literal["live_publish", "stockpile"]


class ChapterListItemResponse(BaseModel):
    id: int
    chapter_no: int
    title: str
    content_preview: str = ""
    char_count: int = 0
    serial_stage: ChapterSerialStage = "stock"
    is_published: bool = False
    locked_from_edit: bool = False
    published_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChapterListResponse(BaseModel):
    novel_id: int
    total: int
    items: list[ChapterListItemResponse] = Field(default_factory=list)


class ChapterResponse(BaseModel):
    id: int
    novel_id: int
    chapter_no: int
    title: str
    content: str
    generation_meta: dict[str, Any]
    serial_stage: ChapterSerialStage = "stock"
    is_published: bool = False
    locked_from_edit: bool = False
    published_at: datetime | None = None
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


class ChapterDeleteTailRequest(BaseModel):
    count: int | None = Field(None, ge=1, description="从末尾删除多少章")
    from_chapter_no: int | None = Field(None, ge=1, description="从哪一章开始删除到末尾（含该章）")
    chapter_nos: list[int] = Field(default_factory=list, description="可选：要删除的章节号列表，必须严格是末尾连续章节")

    @model_validator(mode="after")
    def validate_selector(self):
        selectors = sum(1 for value in (self.count, self.from_chapter_no) if value is not None)
        if self.chapter_nos:
            selectors += 1
        if selectors != 1:
            raise ValueError("count、from_chapter_no、chapter_nos 三者必须且只能提供一种")
        return self


class ChapterDeleteTailResponse(BaseModel):
    novel_id: int
    deleted_count: int
    deleted_chapter_nos: list[int] = Field(default_factory=list)
    deleted_titles: list[str] = Field(default_factory=list)
    current_chapter_no: int


class ChapterPublishBatchRequest(BaseModel):
    count: int = Field(1, ge=1, le=50, description="从当前最早未发布库存开始，连续发布多少章")


class ChapterPublishBatchResponse(BaseModel):
    novel_id: int
    published_count: int
    published_chapter_nos: list[int] = Field(default_factory=list)
    published_titles: list[str] = Field(default_factory=list)
    published_through: int = 0
    delivery_mode: DeliveryMode


class SerialModeUpdateRequest(BaseModel):
    delivery_mode: DeliveryMode


class SerialModeResponse(BaseModel):
    novel_id: int
    delivery_mode: DeliveryMode
    serial_runtime: dict[str, Any] = Field(default_factory=dict)
