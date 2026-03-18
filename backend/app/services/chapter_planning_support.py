from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.chapter_context_common import _compact_value, _truncate_text
from app.services.chapter_context_serialization import _serialize_recent_summaries
from app.services.chapter_runtime_support import _planning_runtime_meta, _set_live_runtime, _ensure_generation_runtime_budget
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.novel_bootstrap import generate_arc_outline_bundle
from app.services.openai_story_engine_selection import review_stage_characters
from app.services.story_character_support import _text
from app.services.story_workspace_archive import archive_story_workspace_snapshot
from app.services.stage_review_support import (
    build_stage_character_review_snapshot,
    should_run_stage_character_review,
    store_stage_character_review,
)
from app.services.story_architecture import (
    build_execution_brief,
    ensure_story_architecture,
    refresh_planning_views,
    set_pipeline_target,
)

logger = logging.getLogger(__name__)


def _load_novel_or_404(db: Session, novel_id: int) -> Novel:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise GenerationError(
            code="NOVEL_NOT_FOUND",
            message="小说不存在。",
            stage="chapter_generation_lock",
            retryable=False,
            http_status=404,
            details={"novel_id": novel_id},
        )
    return novel



def _acquire_generation_slot(db: Session, novel_id: int) -> str:
    novel = _load_novel_or_404(db, novel_id)
    if novel.status == "generating":
        raise GenerationError(
            code=ErrorCodes.CHAPTER_ALREADY_GENERATING,
            message="当前这本书已经有一个生成任务在进行中，请稍后再试。",
            stage="chapter_generation_lock",
            retryable=True,
            http_status=409,
            details={"novel_id": novel_id},
        )

    previous_status = novel.status or ("planning_ready" if novel.current_chapter_no <= 0 else "active")
    updated = (
        db.query(Novel)
        .filter(Novel.id == novel_id, Novel.status != "generating")
        .update({Novel.status: "generating"}, synchronize_session=False)
    )
    db.commit()
    if updated != 1:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_ALREADY_GENERATING,
            message="当前这本书已经有一个生成任务在进行中，请稍后再试。",
            stage="chapter_generation_lock",
            retryable=True,
            http_status=409,
            details={"novel_id": novel_id},
        )
    return previous_status



def _release_generation_slot(db: Session, novel_id: int, restore_status: str) -> None:
    db.query(Novel).filter(Novel.id == novel_id).update({Novel.status: restore_status}, synchronize_session=False)
    db.commit()



def _persist_generation_failure_snapshot(
    db: Session,
    *,
    novel_id: int,
    restore_status: str,
    next_chapter_no: int,
    stage: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        return
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    retry_feedback: dict[str, Any] = {}
    if "主动性不足" in str(message or ""):
        retry_feedback = {
            "problem": "上一版草稿主角偏被动",
            "correction": "开头就让主角先手试探，中段受阻后再追一步，结尾落在主角行动造成的后果上。",
            "forbidden": ["站着听", "只是观察", "压下念头", "没有立刻行动"],
        }
    story_bible = _set_live_runtime(
        story_bible,
        next_chapter_no=next_chapter_no,
        stage="failed",
        note=message,
        extra={
            **_planning_runtime_meta(story_bible),
            "failed_stage": stage,
            "last_error_message": _truncate_text(message, 180),
            "last_error_code": _text((details or {}).get("code")),
            "last_error_retryable": bool((details or {}).get("retryable")),
            "last_error_trace_id": _text((details or {}).get("trace_id")),
            "last_error_details": _compact_value(details or {}, text_limit=80),
            "retry_feedback": retry_feedback,
        },
    )
    novel.story_bible = story_bible
    novel.status = restore_status
    db.add(novel)
    db.commit()
    db.refresh(novel)
    archive_story_workspace_snapshot(
        novel,
        chapter_no=next_chapter_no,
        phase="failed",
        stage=stage,
        note=message,
        extra={"error_details": details or {}, "restore_status": restore_status},
    )



def _validate_required_planning_docs(story_bible: dict[str, Any], next_chapter_no: int) -> None:
    required = {
        "project_card": story_bible.get("project_card"),
        "world_bible": story_bible.get("world_bible"),
        "cultivation_system": story_bible.get("cultivation_system"),
        "volume_cards": story_bible.get("volume_cards"),
        "global_outline": story_bible.get("global_outline"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise GenerationError(
            code=ErrorCodes.PLANNING_DOC_MISSING,
            message=f"第 {next_chapter_no} 章生成前缺少规划文档：{', '.join(missing)}。",
            stage="planning_validation",
            retryable=False,
            http_status=409,
            details={"chapter_no": next_chapter_no, "missing": missing},
        )



def _save_pipeline_execution_packet(
    *,
    novel: Novel,
    story_bible: dict[str, Any],
    next_chapter_no: int,
    plan: dict[str, Any],
    last_chapter_tail: str,
) -> dict[str, Any]:
    execution_brief = build_execution_brief(
        story_bible=story_bible,
        next_chapter_no=next_chapter_no,
        plan=plan,
        last_chapter_tail=last_chapter_tail,
    )
    story_bible = set_pipeline_target(
        story_bible,
        next_chapter_no=next_chapter_no,
        execution_brief=execution_brief,
        stage="chapter_execution_card",
        last_completed_chapter_no=novel.current_chapter_no,
    )
    novel.story_bible = story_bible
    return execution_brief



def _run_stage_character_review_if_needed(
    *,
    story_bible: dict[str, Any],
    current_chapter_no: int,
    recent_summaries: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not should_run_stage_character_review(story_bible, current_chapter_no=current_chapter_no):
        return None
    snapshot = build_stage_character_review_snapshot(
        story_bible,
        current_chapter_no=current_chapter_no,
        recent_summaries=recent_summaries,
    )
    review = review_stage_characters(snapshot=snapshot)
    return store_stage_character_review(story_bible, review.model_dump(mode="python"), current_chapter_no=current_chapter_no)


def prepare_next_planning_window(db: Session, novel: Novel, *, force: bool = False) -> dict[str, Any]:
    previous_status = _acquire_generation_slot(db, novel.id)
    chapter_started_at = time.monotonic()
    try:
        locked_novel = _load_novel_or_404(db, novel.id)
        next_no = locked_novel.current_chapter_no + 1
        _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_planning_prepare", chapter_no=next_no)
        story_bible = ensure_story_architecture(locked_novel.story_bible or {}, locked_novel)
        recent_summaries = _serialize_recent_summaries(db, locked_novel.id)
        _run_stage_character_review_if_needed(
            story_bible=story_bible,
            current_chapter_no=locked_novel.current_chapter_no,
            recent_summaries=recent_summaries,
        )
        locked_novel.story_bible = story_bible

        _ensure_outline_state(story_bible)
        _promote_pending_arc_if_needed(story_bible, next_no)
        locked_novel.story_bible = refresh_planning_views(story_bible, locked_novel.current_chapter_no)

        queue = ((locked_novel.story_bible or {}).get("story_workspace") or {}).get("chapter_card_queue") or []
        ready_for_next = bool(queue and int(queue[0].get("chapter_no", 0) or 0) == next_no)
        if force or not ready_for_next or len(queue) < settings.planning_window_size:
            _generate_and_store_pending_arc(
                db,
                locked_novel,
                recent_summaries,
                replace_existing=force,
            )
            story_bible = locked_novel.story_bible or {}
            _promote_pending_arc_if_needed(story_bible, next_no)
            locked_novel.story_bible = refresh_planning_views(story_bible, locked_novel.current_chapter_no)

        queue = ((locked_novel.story_bible or {}).get("story_workspace") or {}).get("chapter_card_queue") or []
        if not queue or int(queue[0].get("chapter_no", 0) or 0) != next_no:
            raise GenerationError(
                code=ErrorCodes.PLANNING_STAGE_NOT_READY,
                message=f"第 {next_no} 章的近纲/章节卡尚未就绪，不能进入正文生成。",
                stage="prepare_next_window",
                retryable=True,
                http_status=409,
                details={"chapter_no": next_no, "ready_cards": [int(item.get('chapter_no', 0) or 0) for item in queue[:7]]},
            )

        locked_novel.status = previous_status
        db.add(locked_novel)
        db.commit()
        db.refresh(locked_novel)
        return {
            "novel_id": locked_novel.id,
            "current_chapter_no": locked_novel.current_chapter_no,
            "next_chapter_no": next_no,
            "workflow_state": (locked_novel.story_bible or {}).get("workflow_state", {}),
            "planning_status": ((locked_novel.story_bible or {}).get("story_workspace") or {}).get("planning_status", {}),
            "chapter_card_queue": ((locked_novel.story_bible or {}).get("story_workspace") or {}).get("chapter_card_queue", []),
        }
    except Exception:
        db.rollback()
        _release_generation_slot(db, novel.id, previous_status)
        raise



def _story_bible_payload_to_novel_create(novel: Novel) -> NovelCreate:
    return NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )



def _ensure_outline_state(story_bible: dict[str, Any]) -> dict[str, Any]:
    state = story_bible.setdefault("outline_state", {})
    state.setdefault("planned_until", 0)
    state.setdefault("next_arc_no", 1)
    state.setdefault("bootstrap_generated_until", 0)
    return state



def _arc_remaining(active_arc: dict[str, Any] | None, current_chapter_no: int) -> int:
    if not active_arc:
        return 0
    return int(active_arc.get("end_chapter", 0)) - current_chapter_no



def _promote_pending_arc_if_needed(story_bible: dict[str, Any], next_no: int) -> None:
    active_arc = story_bible.get("active_arc")
    pending_arc = story_bible.get("pending_arc")
    if active_arc and next_no <= int(active_arc.get("end_chapter", 0)):
        return
    if pending_arc and next_no >= int(pending_arc.get("start_chapter", 0)):
        story_bible["active_arc"] = pending_arc
        story_bible["pending_arc"] = None



def _generate_and_store_pending_arc(
    db: Session,
    novel: Novel,
    recent_summaries: list[dict[str, Any]],
    *,
    start_chapter: int | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    story_bible = novel.story_bible or {}
    state = _ensure_outline_state(story_bible)
    active_arc = story_bible.get("active_arc")
    pending_arc = story_bible.get("pending_arc")
    if pending_arc and not replace_existing:
        return {
            "arc_no": int(pending_arc.get("arc_no", 0) or 0),
            "start_chapter": int(pending_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(pending_arc.get("end_chapter", 0) or 0),
            "focus": _text(pending_arc.get("focus")),
            "chapter_nos": [int(item.get("chapter_no", 0) or 0) for item in (pending_arc.get("chapters") or [])],
            "chapter_titles": [_text(item.get("title")) for item in (pending_arc.get("chapters") or [])[:5] if _text(item.get("title"))],
            "reused_existing": True,
        }

    if start_chapter is None:
        if not active_arc:
            start = novel.current_chapter_no + 1
        else:
            start = int(active_arc.get("end_chapter", 0)) + 1
    else:
        start = start_chapter
    end = start + settings.arc_outline_size - 1
    arc_no = int(state.get("next_arc_no", 1))

    _run_stage_character_review_if_needed(
        story_bible=story_bible,
        current_chapter_no=novel.current_chapter_no,
        recent_summaries=recent_summaries,
    )
    payload = _story_bible_payload_to_novel_create(novel)
    bundle = generate_arc_outline_bundle(
        payload=payload,
        story_bible=story_bible,
        global_outline=story_bible.get("global_outline", {}),
        start_chapter=start,
        end_chapter=end,
        arc_no=arc_no,
        recent_summaries=recent_summaries,
    )
    story_bible["pending_arc"] = bundle
    state["planned_until"] = end
    state["next_arc_no"] = arc_no + 1
    novel.story_bible = refresh_planning_views(story_bible, novel.current_chapter_no)
    db.add(novel)
    return {
        "arc_no": int(bundle.get("arc_no", 0) or arc_no),
        "start_chapter": int(bundle.get("start_chapter", 0) or start),
        "end_chapter": int(bundle.get("end_chapter", 0) or end),
        "focus": _text(bundle.get("focus")),
        "bridge_note": _text(bundle.get("bridge_note")),
        "chapter_nos": [int(item.get("chapter_no", 0) or 0) for item in (bundle.get("chapters") or [])],
        "chapter_titles": [_text(item.get("title")) for item in (bundle.get("chapters") or [])[:5] if _text(item.get("title"))],
        "reused_existing": False,
    }



def _get_plan_for_chapter(novel: Novel, chapter_no: int) -> dict[str, Any]:
    story_bible = novel.story_bible or {}
    for arc_key in ["active_arc", "pending_arc"]:
        arc = story_bible.get(arc_key)
        if not arc:
            continue
        for chapter in arc.get("chapters", []):
            if int(chapter.get("chapter_no", 0)) == chapter_no:
                return chapter
    raise GenerationError(
        code=ErrorCodes.CHAPTER_PLAN_MISSING,
        message=f"第 {chapter_no} 章没有对应拍表，无法生成正文。",
        stage="chapter_plan_lookup",
        retryable=True,
        http_status=409,
        details={"chapter_no": chapter_no},
    )



def _ensure_plan_for_chapter(
    db: Session,
    novel: Novel,
    chapter_no: int,
    recent_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        return _get_plan_for_chapter(novel, chapter_no)
    except GenerationError as exc:
        if exc.code != ErrorCodes.CHAPTER_PLAN_MISSING:
            raise

    logger.info("chapter %s missing plan, generating arc just-in-time for novel=%s", chapter_no, novel.id)
    _generate_and_store_pending_arc(
        db,
        novel,
        recent_summaries,
        start_chapter=chapter_no,
        replace_existing=True,
    )
    story_bible = novel.story_bible or {}
    _promote_pending_arc_if_needed(story_bible, chapter_no)
    novel.story_bible = story_bible
    db.add(novel)
    return _get_plan_for_chapter(novel, chapter_no)
