from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InterventionCreate(BaseModel):
    chapter_no: int = Field(..., ge=1)
    raw_instruction: str = Field(..., min_length=1)
    effective_chapter_span: int = Field(default=5, ge=1, le=100)


class InterventionResponse(BaseModel):
    id: int
    novel_id: int
    chapter_no: int
    raw_instruction: str
    parsed_constraints: dict[str, Any]
    effective_chapter_span: int
    applied: bool
    created_at: datetime

    model_config = {"from_attributes": True}
