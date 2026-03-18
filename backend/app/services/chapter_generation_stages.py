from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.novel import Novel
from app.services.chapter_generation_draft import draft_chapter_content
from app.services.chapter_generation_finalize import finalize_chapter
from app.services.chapter_generation_planning import (
    auto_prepare_future_planning as _auto_prepare_future_planning_impl,
    pending_arc_window_preview as _pending_arc_window_preview_impl,
)
from app.services.chapter_generation_prepare import prepare_generation_context
from app.services.chapter_generation_progress import emit_progress
from app.services.chapter_generation_support import _release_generation_slot

logger = logging.getLogger(__name__)


def pending_arc_window_preview(story_bible: dict[str, Any], *, current_chapter_no: int) -> tuple[int, int, int]:
    return _pending_arc_window_preview_impl(story_bible, current_chapter_no=current_chapter_no)


def auto_prepare_future_planning(
    db: Session,
    novel: Novel,
    *,
    current_chapter_no: int,
    recent_summaries: list[dict[str, Any]],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return _auto_prepare_future_planning_impl(
        db,
        novel,
        current_chapter_no=current_chapter_no,
        recent_summaries=recent_summaries,
        progress_callback=progress_callback,
    )


def run_chapter_generation(
    db: Session,
    locked_novel: Novel,
    *,
    previous_status: str,
    trace_id: str,
    chapter_started_at: float,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> Chapter:
    next_no = locked_novel.current_chapter_no + 1
    logger.info("chapter_generation start novel_id=%s chapter_no=%s trace=%s", locked_novel.id, next_no, trace_id)
    existing = (
        db.query(Chapter)
        .filter(Chapter.novel_id == locked_novel.id, Chapter.chapter_no == next_no)
        .first()
    )
    if existing:
        _release_generation_slot(db, locked_novel.id, previous_status)
        return existing

    prepared = prepare_generation_context(
        db,
        locked_novel,
        next_no=next_no,
        chapter_started_at=chapter_started_at,
        progress_callback=progress_callback,
    )
    drafted = draft_chapter_content(db, prepared, chapter_started_at=chapter_started_at)
    return finalize_chapter(
        db,
        drafted,
        trace_id=trace_id,
        previous_status=previous_status,
        chapter_started_at=chapter_started_at,
    )
