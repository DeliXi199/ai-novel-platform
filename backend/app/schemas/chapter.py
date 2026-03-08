from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChapterResponse(BaseModel):
    id: int
    novel_id: int
    chapter_no: int
    title: str
    content: str
    generation_meta: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
