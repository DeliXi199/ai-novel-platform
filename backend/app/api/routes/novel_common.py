import json
from copy import deepcopy
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.schemas.chapter import ChapterDeleteTailRequest
from app.services.async_tasks import list_active_tasks, list_recent_tasks, serialize_task
from app.services.chapter_quality import build_quality_feedback
from app.services.generation_exceptions import GenerationError
from app.services.novel_lifecycle import BOOTSTRAP_STATUS_RUNNING, sync_story_bible_snapshot
from app.services.runtime_snapshot_cache import (
    build_runtime_snapshot_cache_key,
    get_runtime_snapshot,
    store_runtime_snapshot,
)
from app.services.story_architecture import build_control_console_snapshot
from app.services.story_state import get_chapter_card_queue, get_current_pipeline, get_live_runtime, get_planning_status


def raise_http_from_generation_error(exc: GenerationError, *, extra_detail: dict | None = None) -> None:
    details = exc.details or {}
    detail = {
        "code": exc.code,
        "stage": exc.stage,
        "message": exc.message,
        "retryable": exc.retryable,
        "provider": exc.provider,
        "details": details,
    }
    if exc.stage == "chapter_quality" or (isinstance(details, dict) and details.get("quality_feedback")):
        detail["quality_feedback"] = details.get("quality_feedback") or build_quality_feedback(exc)
        if details.get("quality_rejections"):
            detail["quality_rejections"] = details.get("quality_rejections")
    if extra_detail:
        detail.update(extra_detail)
    raise HTTPException(status_code=exc.http_status, detail=detail)


def batch_payload(chapters: list[Chapter], requested_count: int, started_from_chapter: int, progress: list[dict]) -> dict:
    return {
        "novel_id": chapters[0].novel_id if chapters else None,
        "requested_count": requested_count,
        "generated_count": len(chapters),
        "started_from_chapter": started_from_chapter,
        "ended_at_chapter": chapters[-1].chapter_no if chapters else None,
        "chapters": chapters,
        "progress": progress,
    }


def require_novel(db: Session, novel_id: int) -> Novel:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


def ensure_bootstrap_not_running(novel: Novel, *, action: str) -> None:
    if novel.status == BOOTSTRAP_STATUS_RUNNING:
        raise HTTPException(status_code=409, detail=f"当前小说仍在初始化中，暂时不能执行{action}。")


def chapter_preview(text: str, limit: int = 70) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "…"


def snapshot_novel(novel: Novel, *, story_bible: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=novel.id,
        title=novel.title,
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=deepcopy(novel.style_preferences or {}),
        story_bible=deepcopy(story_bible or {}),
        current_chapter_no=novel.current_chapter_no,
    )


def _load_chapters_for_novel(db: Session, novel_id: int) -> list[Chapter]:
    return (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.asc())
        .all()
    )


def _chapter_cache_state_from_rows(chapters: list[Chapter]) -> tuple[int, object | None]:
    latest = max((item.updated_at or item.created_at for item in chapters), default=None)
    return len(chapters), latest


def _chapter_cache_state_from_db(db: Session, novel_id: int) -> tuple[int, object | None]:
    count, latest = (
        db.query(func.count(Chapter.id), func.max(func.coalesce(Chapter.updated_at, Chapter.created_at)))
        .filter(Chapter.novel_id == novel_id)
        .one()
    )
    return int(count or 0), latest


def _runtime_snapshot_cache_key(novel: Novel, *, chapter_count: int, chapter_last_updated_at) -> str:
    return build_runtime_snapshot_cache_key(
        novel_id=novel.id,
        title=novel.title,
        genre=novel.genre,
        protagonist_name=novel.protagonist_name,
        current_chapter_no=novel.current_chapter_no,
        novel_updated_at=novel.updated_at,
        story_bible=novel.story_bible or {},
        chapter_count=chapter_count,
        chapter_last_updated_at=chapter_last_updated_at,
    )


def _build_runtime_snapshot(novel: Novel, chapters: list[Chapter]) -> tuple[dict, dict]:
    synced_story_bible = sync_story_bible_snapshot(novel=novel, story_bible=novel.story_bible or {}, chapters=chapters)
    snapshot = build_control_console_snapshot(snapshot_novel(novel, story_bible=synced_story_bible))
    return synced_story_bible, snapshot


def build_fresh_snapshot(db: Session, novel: Novel) -> tuple[dict, dict]:
    chapter_count, chapter_last_updated_at = _chapter_cache_state_from_db(db, novel.id)
    cache_key = _runtime_snapshot_cache_key(
        novel,
        chapter_count=chapter_count,
        chapter_last_updated_at=chapter_last_updated_at,
    )
    cached = get_runtime_snapshot(cache_key)
    if cached is not None:
        return cached

    chapters = _load_chapters_for_novel(db, novel.id)
    chapter_count, chapter_last_updated_at = _chapter_cache_state_from_rows(chapters)
    cache_key = _runtime_snapshot_cache_key(
        novel,
        chapter_count=chapter_count,
        chapter_last_updated_at=chapter_last_updated_at,
    )
    cached = get_runtime_snapshot(cache_key)
    if cached is not None:
        return cached

    synced_story_bible, snapshot = _build_runtime_snapshot(novel, chapters)
    store_runtime_snapshot(cache_key, synced_story_bible, snapshot)
    return synced_story_bible, snapshot


def _chapter_list_items(chapters: list[Chapter]) -> list[dict]:
    return [
        {
            "id": item.id,
            "chapter_no": item.chapter_no,
            "title": item.title,
            "content_preview": chapter_preview(item.content),
            "char_count": len(item.content or ""),
            "serial_stage": item.serial_stage,
            "is_published": item.is_published,
            "locked_from_edit": item.locked_from_edit,
            "published_at": item.published_at,
            "created_at": item.created_at,
        }
        for item in chapters
    ]


def _intervention_payload(novel_id: int, items: list[Intervention]) -> dict:
    return {"novel_id": novel_id, "total": len(items), "items": items}


def resolve_workspace_selected_chapter(chapters: list[Chapter], desired_chapter_no: int | None = None) -> Chapter | None:
    if not chapters:
        return None
    if desired_chapter_no is not None:
        for item in chapters:
            if item.chapter_no == desired_chapter_no:
                return item
    return chapters[-1]


def build_workspace_payload(db: Session, novel: Novel, *, desired_chapter_no: int | None = None) -> dict:
    chapters = _load_chapters_for_novel(db, novel.id)
    interventions = (
        db.query(Intervention)
        .filter(Intervention.novel_id == novel.id)
        .order_by(Intervention.created_at.desc(), Intervention.id.desc())
        .all()
    )
    chapter_count, chapter_last_updated_at = _chapter_cache_state_from_rows(chapters)
    cache_key = _runtime_snapshot_cache_key(
        novel,
        chapter_count=chapter_count,
        chapter_last_updated_at=chapter_last_updated_at,
    )
    cached = get_runtime_snapshot(cache_key)
    if cached is not None:
        synced_story_bible, snapshot = cached
    else:
        synced_story_bible, snapshot = _build_runtime_snapshot(novel, chapters)
        store_runtime_snapshot(cache_key, synced_story_bible, snapshot)
    selected_chapter = resolve_workspace_selected_chapter(chapters, desired_chapter_no=desired_chapter_no)
    active_tasks = [serialize_task(task) for task in list_active_tasks(db, novel_id=novel.id)]
    recent_tasks = [serialize_task(task) for task in list_recent_tasks(db, novel_id=novel.id, limit=8)]
    return {
        "novel": novel,
        "chapters": {
            "novel_id": novel.id,
            "total": len(chapters),
            "items": _chapter_list_items(chapters),
        },
        "console_data": snapshot,
        "planning_data": {
            "novel_id": novel.id,
            "current_chapter_no": novel.current_chapter_no,
            "planning_layers": snapshot.get("planning_layers", {}),
            "planning_state": snapshot.get("planning_state", {}),
            "planning_status": snapshot.get("control_console", {}).get("planning_status", {}),
            "chapter_card_queue": snapshot.get("control_console", {}).get("chapter_card_queue", []),
        },
        "interventions": _intervention_payload(novel.id, interventions),
        "selected_chapter": selected_chapter,
        "selected_chapter_no": selected_chapter.chapter_no if selected_chapter else None,
        "active_tasks": active_tasks,
        "recent_tasks": recent_tasks,
    }

def build_live_runtime_payload(db: Session, novel: Novel) -> dict:
    story_bible = novel.story_bible or {}
    live_runtime = get_live_runtime(story_bible)
    current_pipeline = get_current_pipeline(story_bible)
    planning_status = get_planning_status(story_bible)
    queue = get_chapter_card_queue(story_bible, limit=6)
    latest_chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_no.desc())
        .first()
    )
    return {
        "novel": {
            "id": novel.id,
            "title": novel.title,
            "genre": novel.genre,
            "protagonist_name": novel.protagonist_name,
            "current_chapter_no": novel.current_chapter_no,
            "status": novel.status,
            "updated_at": novel.updated_at,
            "created_at": novel.created_at,
        },
        "live_runtime": live_runtime,
        "current_pipeline": current_pipeline,
        "planning_status": {
            "planned_until": planning_status.get("planned_until"),
            "ready_chapter_cards": planning_status.get("ready_chapter_cards") or [],
            "active_arc": planning_status.get("active_arc") or {},
            "pending_arc": planning_status.get("pending_arc") or {},
            "active_arc_casting_layout_review": planning_status.get("active_arc_casting_layout_review") or {},
            "pending_arc_casting_layout_review": planning_status.get("pending_arc_casting_layout_review") or {},
        },
        "queue_preview": [
            {
                "chapter_no": item.get("chapter_no"),
                "title": item.get("title"),
                "goal": item.get("goal"),
                "stage_casting_action": item.get("stage_casting_action"),
                "stage_casting_target": item.get("stage_casting_target"),
                "stage_casting_note": item.get("stage_casting_note") or item.get("stage_casting_review_note"),
            }
            for item in queue
            if isinstance(item, dict)
        ],
        "latest_chapter": {
            "chapter_no": latest_chapter.chapter_no,
            "title": latest_chapter.title,
            "created_at": latest_chapter.created_at,
        }
        if latest_chapter
        else None,
    }


def sync_novel_serial_layers(db: Session, novel: Novel, *, persist: bool = True) -> Novel:
    chapters = _load_chapters_for_novel(db, novel.id)
    novel.story_bible = sync_story_bible_snapshot(novel=novel, story_bible=novel.story_bible or {}, chapters=chapters)
    if persist:
        db.add(novel)
    return novel


def resolve_tail_chapters_to_delete(novel: Novel, db: Session, payload: ChapterDeleteTailRequest) -> list[Chapter]:
    chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_no.asc())
        .all()
    )
    if not chapters:
        raise HTTPException(status_code=400, detail="当前没有可删除的章节")

    last_chapter_no = chapters[-1].chapter_no

    if novel.status == "generating":
        raise HTTPException(status_code=409, detail="当前小说正在生成中，不能执行删除操作")

    if payload.count is not None:
        if payload.count > len(chapters):
            raise HTTPException(status_code=400, detail="删除数量超过现有章节数")
        target_nos = list(range(last_chapter_no - payload.count + 1, last_chapter_no + 1))
    elif payload.from_chapter_no is not None:
        if payload.from_chapter_no > last_chapter_no:
            raise HTTPException(status_code=400, detail="起始章节号超过当前最后一章")
        target_nos = list(range(payload.from_chapter_no, last_chapter_no + 1))
    else:
        normalized = sorted(set(payload.chapter_nos))
        if not normalized:
            raise HTTPException(status_code=400, detail="没有提供有效的章节删除目标")
        expected = list(range(normalized[0], last_chapter_no + 1))
        if normalized != expected:
            raise HTTPException(status_code=400, detail="只能删除从最后一章往前连续的一段章节")
        target_nos = normalized

    deleted = [chapter for chapter in chapters if chapter.chapter_no in set(target_nos)]
    if len(deleted) != len(target_nos):
        raise HTTPException(status_code=400, detail="请求删除的章节不存在或不连续")
    locked = [
        chapter.chapter_no
        for chapter in deleted
        if chapter.is_published or chapter.locked_from_edit or chapter.serial_stage == "published"
    ]
    if locked:
        raise HTTPException(status_code=409, detail=f"已发布章节不可删除或回改：{locked}")
    return deleted


def sse_payload(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
