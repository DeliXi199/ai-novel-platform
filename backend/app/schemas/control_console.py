from typing import Any

from pydantic import BaseModel, Field


class ControlConsoleResponse(BaseModel):
    novel_id: int
    title: str
    project_card: dict[str, Any] = Field(default_factory=dict)
    world_bible: dict[str, Any] = Field(default_factory=dict)
    cultivation_system: dict[str, Any] = Field(default_factory=dict)
    serial_rules: dict[str, Any] = Field(default_factory=dict)
    serial_runtime: dict[str, Any] = Field(default_factory=dict)
    fact_ledger: dict[str, Any] = Field(default_factory=dict)
    hard_fact_guard: dict[str, Any] = Field(default_factory=dict)
    long_term_state: dict[str, Any] = Field(default_factory=dict)
    initialization_packet: dict[str, Any] = Field(default_factory=dict)
    current_volume_card: dict[str, Any] = Field(default_factory=dict)
    control_console: dict[str, Any] = Field(default_factory=dict)
    planning_layers: dict[str, Any] = Field(default_factory=dict)
    planning_state: dict[str, Any] = Field(default_factory=dict)
    continuity_rules: list[str] = Field(default_factory=list)
    daily_workflow: dict[str, Any] = Field(default_factory=dict)

    story_state: dict[str, Any] = Field(default_factory=dict)
