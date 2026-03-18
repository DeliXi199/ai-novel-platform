from __future__ import annotations

import logging
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.novel import Novel
from app.services.chapter_generation_stages import run_chapter_generation
from app.services.chapter_generation_support import _acquire_generation_slot, _load_novel_or_404, _persist_generation_failure_snapshot
from app.services.generation_exceptions import GenerationError
from app.services.openai_story_engine import begin_llm_trace, clear_llm_trace, get_llm_trace
from app.services.story_architecture import prepare_story_workspace_for_chapter_entry
from app.services.story_workspace_archive import archive_story_workspace_snapshot

logger = logging.getLogger(__name__)




def _next_chapter_no(novel: Novel) -> int:
    return int(getattr(novel, "current_chapter_no", 0) or 0) + 1



def _chapter_identity(novel: Novel, locked_novel: Novel | None = None) -> tuple[int, int]:
    resolved = locked_novel or novel
    return resolved.id, _next_chapter_no(resolved)



def _append_trace_details(exc: GenerationError, trace_snapshot: list[dict[str, Any]] | None) -> None:
    exc.details = {
        **(exc.details or {}),
        "code": exc.code,
        "stage": exc.stage,
        "retryable": exc.retryable,
        **({"llm_call_trace": trace_snapshot[-6:]} if trace_snapshot else {}),
    }



def _record_generation_failure(
    db: Session,
    novel: Novel,
    *,
    previous_status: str,
    chapter_no: int,
    stage: str,
    message: str,
    details: dict[str, Any],
) -> None:
    db.rollback()
    _persist_generation_failure_snapshot(
        db,
        novel_id=novel.id,
        restore_status=previous_status,
        next_chapter_no=chapter_no,
        stage=stage,
        message=message,
        details=details,
    )



def generate_next_chapters_batch(
    db: Session,
    novel_id: int,
    count: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[Chapter]:
    total = max(int(count), 1)
    chapters: list[Chapter] = []
    started_from_chapter: int | None = None
    if progress_callback:
        progress_callback({"event": "batch_started", "novel_id": novel_id, "requested_count": total})

    for index in range(total):
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            raise GenerationError(
                code="NOVEL_NOT_FOUND",
                message="Novel not found",
                stage="batch_generation",
                retryable=False,
                http_status=404,
                details={"novel_id": novel_id},
            )
        next_no = _next_chapter_no(novel)
        started_from_chapter = started_from_chapter or next_no
        if progress_callback:
            progress_callback(
                {
                    "event": "chapter_started",
                    "novel_id": novel_id,
                    "index": index + 1,
                    "total": total,
                    "chapter_no": next_no,
                    "message": f"开始生成第 {next_no} 章（{index + 1}/{total}）",
                }
            )
        started_at = time.monotonic()
        try:
            chapter = generate_next_chapter(db, novel, progress_callback=progress_callback)
        except GenerationError as exc:
            if progress_callback:
                progress_callback(
                    {
                        "event": "chapter_failed",
                        "novel_id": novel_id,
                        "index": index + 1,
                        "total": total,
                        "chapter_no": next_no,
                        "code": exc.code,
                        "stage": exc.stage,
                        "message": exc.message,
                        "retryable": exc.retryable,
                        "details": exc.details or {},
                    }
                )
            raise
        duration_ms = int(round((time.monotonic() - started_at) * 1000))
        chapters.append(chapter)
        if progress_callback:
            progress_callback(
                {
                    "event": "chapter_succeeded",
                    "novel_id": novel_id,
                    "index": index + 1,
                    "total": total,
                    "chapter_no": chapter.chapter_no,
                    "title": chapter.title,
                    "duration_ms": duration_ms,
                    "message": f"第 {chapter.chapter_no} 章生成完成：{chapter.title}",
                }
            )

    if progress_callback:
        progress_callback(
            {
                "event": "batch_completed",
                "novel_id": novel_id,
                "requested_count": total,
                "generated_count": len(chapters),
                "started_from_chapter": started_from_chapter,
                "ended_at_chapter": chapters[-1].chapter_no if chapters else None,
            }
        )
    return chapters



def generate_next_chapter(
    db: Session,
    novel: Novel,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Chapter:
    previous_status = _acquire_generation_slot(db, novel.id)
    locked_novel = _load_novel_or_404(db, novel.id)
    next_no = _next_chapter_no(locked_novel)
    trace_id = begin_llm_trace(f"novel-{locked_novel.id}-chapter-{next_no}")
    locked_novel.story_bible = prepare_story_workspace_for_chapter_entry(
        locked_novel.story_bible or {},
        next_chapter_no=next_no,
    )
    archive_story_workspace_snapshot(
        locked_novel,
        chapter_no=next_no,
        phase="before",
        stage="chapter_generation_entry",
        note=f"第 {next_no} 章生成前 Story Workspace 快照。",
        extra={"trace_id": trace_id},
    )
    chapter_started_at = time.monotonic()
    try:
        return run_chapter_generation(
            db,
            locked_novel,
            previous_status=previous_status,
            trace_id=trace_id,
            chapter_started_at=chapter_started_at,
            progress_callback=progress_callback,
        )
    except GenerationError as exc:
        trace_snapshot = get_llm_trace()
        _append_trace_details(exc, trace_snapshot)
        log_novel_id, log_chapter_no = _chapter_identity(novel, locked_novel)
        logger.warning(
            "chapter_generation failed novel_id=%s chapter_no=%s stage=%s code=%s details=%s",
            log_novel_id,
            log_chapter_no,
            exc.stage,
            exc.code,
            exc.details,
        )
        _record_generation_failure(
            db,
            novel,
            previous_status=previous_status,
            chapter_no=log_chapter_no,
            stage=exc.stage,
            message=exc.message,
            details=exc.details or {},
        )
        raise
    except Exception as exc:
        log_novel_id, log_chapter_no = _chapter_identity(novel, locked_novel)
        logger.exception(
            "chapter_generation crashed novel_id=%s chapter_no=%s",
            log_novel_id,
            log_chapter_no,
        )
        _record_generation_failure(
            db,
            novel,
            previous_status=previous_status,
            chapter_no=log_chapter_no,
            stage="chapter_generation",
            message="章节生成流程出现未识别异常，已中止本次生成。",
            details={"error_type": type(exc).__name__},
        )
        raise
    finally:
        clear_llm_trace()
