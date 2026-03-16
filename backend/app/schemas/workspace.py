from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chapter import ChapterListResponse, ChapterResponse
from app.schemas.control_console import ControlConsoleResponse
from app.schemas.intervention import InterventionListResponse
from app.schemas.novel import NovelResponse
from app.schemas.task import AsyncTaskResponse


class WorkspaceResponse(BaseModel):
    novel: NovelResponse
    chapters: ChapterListResponse
    console_data: ControlConsoleResponse
    planning_data: dict[str, Any] = Field(default_factory=dict)
    interventions: InterventionListResponse
    selected_chapter: ChapterResponse | None = None
    selected_chapter_no: int | None = None
    active_tasks: list[AsyncTaskResponse] = Field(default_factory=list)
    recent_tasks: list[AsyncTaskResponse] = Field(default_factory=list)
