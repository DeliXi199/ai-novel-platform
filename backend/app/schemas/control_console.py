from typing import Any

from pydantic import BaseModel, Field


class ControlConsoleResponse(BaseModel):
    novel_id: int
    title: str
    project_card: dict[str, Any] = Field(default_factory=dict)
    world_bible: dict[str, Any] = Field(default_factory=dict)
    cultivation_system: dict[str, Any] = Field(default_factory=dict)
    current_volume_card: dict[str, Any] = Field(default_factory=dict)
    control_console: dict[str, Any] = Field(default_factory=dict)
    planning_layers: dict[str, Any] = Field(default_factory=dict)
    planning_state: dict[str, Any] = Field(default_factory=dict)
    continuity_rules: list[str] = Field(default_factory=list)
    daily_workflow: dict[str, Any] = Field(default_factory=dict)
