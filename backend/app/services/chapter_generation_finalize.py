from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.services.chapter_generation_finalize_commit import commit_finalized_chapter
from app.services.chapter_generation_finalize_prepare import prepare_finalization_snapshot
from app.services.chapter_generation_types import DraftPhaseResult


def finalize_chapter(
    db: Session,
    draft: DraftPhaseResult,
    *,
    trace_id: str,
    previous_status: str,
    chapter_started_at: float,
) -> Chapter:
    snapshot = prepare_finalization_snapshot(
        db,
        draft,
        chapter_started_at=chapter_started_at,
    )
    return commit_finalized_chapter(
        db,
        draft,
        snapshot,
        trace_id=trace_id,
        previous_status=previous_status,
    )
