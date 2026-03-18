from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.chapter import Chapter
from app.models.novel import Novel


@dataclass(slots=True)
class PreparedChapterState:
    locked_novel: Novel
    next_no: int
    last_chapter: Chapter | None
    recent_full_texts: list[str]
    recent_plan_meta: list[dict[str, Any]]
    recent_summaries: list[dict[str, Any]]
    story_bible: dict[str, Any]
    plan: dict[str, Any]
    chapter_plan_packet: dict[str, Any]
    execution_brief: dict[str, Any]
    serialized_last: dict[str, Any]
    serialized_active: list[dict[str, Any]]
    active_interventions: list[Any]
    novel_context: dict[str, Any]
    context_stats: dict[str, Any]


@dataclass(slots=True)
class DraftPhaseResult:
    prepared: PreparedChapterState
    title: str
    content: str
    draft_payload: dict[str, Any]
    used_plan: dict[str, Any]
    length_targets: dict[str, Any]
    attempt_meta: dict[str, Any]
    payoff_delivery: dict[str, Any]
