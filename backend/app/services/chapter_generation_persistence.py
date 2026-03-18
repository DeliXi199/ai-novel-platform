from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel


def collect_active_interventions(db: Session, novel_id: int, next_chapter_no: int) -> list[Intervention]:
    interventions = (
        db.query(Intervention)
        .filter(Intervention.novel_id == novel_id)
        .order_by(Intervention.created_at.asc())
        .all()
    )
    active: list[Intervention] = []
    for item in interventions:
        start = item.chapter_no + 1
        end = item.chapter_no + item.effective_chapter_span
        if start <= next_chapter_no <= end:
            active.append(item)
    return active



def load_recent_titles(db: Session, novel_id: int, *, limit: int | None = None) -> list[str]:
    size = limit or max(int(getattr(settings, "chapter_title_recent_window", 20) or 20), 5)
    rows = (
        db.query(Chapter.title)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.asc())
        .all()
    )
    titles = [str(title or "").strip() for (title,) in rows if str(title or "").strip()]
    return titles[-size:]



def persist_chapter_and_summary(
    db: Session,
    novel: Novel,
    chapter_no: int,
    chapter_title: str,
    content: str,
    generation_meta: dict[str, Any],
    event_summary: str,
    character_updates: dict[str, Any],
    new_clues: list[str],
    open_hooks: list[str],
    closed_hooks: list[str],
) -> Chapter:
    chapter = Chapter(
        novel_id=novel.id,
        chapter_no=chapter_no,
        title=chapter_title,
        content=content,
        generation_meta=generation_meta,
    )
    db.add(chapter)
    db.flush()

    summary = ChapterSummary(
        chapter_id=chapter.id,
        event_summary=event_summary,
        character_updates=character_updates,
        new_clues=new_clues,
        open_hooks=open_hooks,
        closed_hooks=closed_hooks,
    )
    db.add(summary)
    db.flush()
    novel.current_chapter_no = chapter_no
    db.add(novel)
    return chapter


# Backward-compatible private aliases kept for split finalize modules.
_load_recent_titles = load_recent_titles
_persist_chapter_and_summary = persist_chapter_and_summary
