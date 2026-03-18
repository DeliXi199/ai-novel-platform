from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.task import AsyncTaskCleanupResponse, AsyncTaskEventListResponse, AsyncTaskListResponse, AsyncTaskResponse
from app.schemas.chapter import SerialModeResponse, SerialModeUpdateRequest
from app.schemas.story_workspace import StoryWorkspaceResponse
from app.schemas.story_studio import StoryStudioResponse
from app.services.async_tasks import cleanup_terminal_tasks, get_task, list_task_events, list_tasks, request_task_cancel, retry_task, serialize_task
from app.services.chapter_generation import prepare_next_planning_window
from app.services.story_workspace_archive import archive_story_workspace_snapshot, list_story_workspace_archives, read_story_workspace_archive
from app.services.generation_exceptions import GenerationError
from app.services.story_architecture import ensure_story_architecture, set_delivery_mode, sync_long_term_state
from app.services.story_state import ensure_serial_runtime

from .novel_common import (
    build_fresh_snapshot,
    build_live_runtime_payload,
    build_story_studio_payload,
    ensure_bootstrap_not_running,
    raise_http_from_generation_error,
    require_novel,
    sync_novel_serial_layers,
)

router = APIRouter(prefix="/novels", tags=["novels"])


@router.get("/{novel_id}/tasks/{task_id}", response_model=AsyncTaskResponse)
def get_async_task_status(novel_id: int, task_id: int, db: Session = Depends(get_db)):
    require_novel(db, novel_id)
    task = get_task(db, novel_id=novel_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize_task(task)




@router.get("/{novel_id}/tasks/{task_id}/events", response_model=AsyncTaskEventListResponse)
def get_async_task_events(novel_id: int, task_id: int, limit: int = Query(40, ge=1, le=200), db: Session = Depends(get_db)):
    require_novel(db, novel_id)
    task = get_task(db, novel_id=novel_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    items = list_task_events(db, novel_id=novel_id, task_id=task_id, limit=limit)
    return {"novel_id": novel_id, "task_id": task_id, "total": len(items), "items": items}


@router.get("/{novel_id}/tasks", response_model=AsyncTaskListResponse)
def get_async_tasks(novel_id: int, status: str | None = Query(None), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    require_novel(db, novel_id)
    tasks = list_tasks(db, novel_id=novel_id, status=status, limit=limit)
    return {"novel_id": novel_id, "total": len(tasks), "items": [serialize_task(task) for task in tasks]}




@router.post("/{novel_id}/tasks/{task_id}/cancel", response_model=AsyncTaskResponse)
def cancel_async_task(novel_id: int, task_id: int, db: Session = Depends(get_db)):
    require_novel(db, novel_id)
    try:
        task = request_task_cancel(db, novel_id=novel_id, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return serialize_task(task)


@router.post("/{novel_id}/tasks/{task_id}/retry", response_model=AsyncTaskResponse, status_code=202)
def retry_async_task(novel_id: int, task_id: int, db: Session = Depends(get_db)):
    require_novel(db, novel_id)
    try:
        task, reused_existing = retry_task(db, novel_id=novel_id, task_id=task_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 409
        raise HTTPException(status_code=status_code, detail=message)
    return serialize_task(task, reused_existing=reused_existing)


@router.post("/{novel_id}/tasks/cleanup", response_model=AsyncTaskCleanupResponse)
def cleanup_async_tasks(
    novel_id: int,
    keep_latest: int = Query(30, ge=0, le=200),
    older_than_days: int | None = Query(14, ge=0, le=3650),
    db: Session = Depends(get_db),
):
    require_novel(db, novel_id)
    return cleanup_terminal_tasks(db, novel_id=novel_id, keep_latest=keep_latest, older_than_days=older_than_days)


@router.get("/{novel_id}/story-studio", response_model=StoryStudioResponse)
def get_story_studio(novel_id: int, desired_chapter_no: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    return build_story_studio_payload(db, novel, desired_chapter_no=desired_chapter_no)


@router.get("/{novel_id}/planning-state")
def get_planning_state(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
    return {
        "novel_id": novel.id,
        "current_chapter_no": novel.current_chapter_no,
        "planning_layers": snapshot.get("planning_layers", {}),
        "planning_state": snapshot.get("planning_state", {}),
        "planning_status": snapshot.get("story_workspace", {}).get("planning_status", {}),
        "chapter_card_queue": snapshot.get("story_workspace", {}).get("chapter_card_queue", []),
    }


@router.post("/{novel_id}/prepare-next-window")
def create_next_planning_window(novel_id: int, force: bool = Query(False), db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="规划窗口刷新")
    try:
        return prepare_next_planning_window(db, novel, force=force)
    except GenerationError as exc:
        db.rollback()
        raise_http_from_generation_error(exc)


@router.post("/{novel_id}/refresh-serial-state")
def refresh_serial_state(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    novel = sync_novel_serial_layers(db, novel, persist=True)
    db.commit()
    db.refresh(novel)
    _, snapshot = build_fresh_snapshot(db, novel)
    return {"novel_id": novel.id, "status": "refreshed", "serial_runtime": snapshot.get("serial_runtime", {})}


@router.get("/{novel_id}/live-runtime")
def get_live_runtime(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    return build_live_runtime_payload(db, novel)


@router.get("/{novel_id}/story-workspace", response_model=StoryWorkspaceResponse)
def get_story_workspace(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
    return snapshot


@router.get("/{novel_id}/story-workspace-archives")
def get_story_workspace_archives(
    novel_id: int,
    chapter_no: int | None = Query(None, ge=1),
    limit: int = Query(40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    require_novel(db, novel_id)
    return list_story_workspace_archives(novel_id=novel_id, chapter_no=chapter_no, limit=limit)


@router.get("/{novel_id}/story-workspace-archives/content")
def get_story_workspace_archive_content(
    novel_id: int,
    relative_path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    require_novel(db, novel_id)
    try:
        payload = read_story_workspace_archive(novel_id=novel_id, relative_path=relative_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archive file not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid archive path")
    return payload


@router.post("/{novel_id}/story-workspace-archives/snapshot")
def create_manual_story_workspace_archive(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    next_chapter_no = int(novel.current_chapter_no or 0) + 1
    path = archive_story_workspace_snapshot(
        novel,
        chapter_no=next_chapter_no,
        phase="manual",
        stage="manual_snapshot",
        note="手动导出的 Story Workspace 快照。",
    )
    return {
        "novel_id": novel.id,
        "chapter_no": next_chapter_no,
        "saved": bool(path),
        "path": path,
    }


@router.get("/{novel_id}/serial-state")
def get_serial_state(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
    return {
        "novel_id": novel.id,
        "serial_rules": snapshot.get("serial_rules", {}),
        "serial_runtime": snapshot.get("serial_runtime", {}),
        "fact_ledger": snapshot.get("fact_ledger", {}),
        "hard_fact_guard": snapshot.get("hard_fact_guard", {}),
        "long_term_state": snapshot.get("long_term_state", {}),
        "initialization_packet": snapshot.get("initialization_packet", {}),
        "story_state": snapshot.get("story_state", {}),
    }


@router.get("/{novel_id}/facts")
def get_fact_ledger(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
    fact_ledger = snapshot.get("fact_ledger", {})
    return {
        "novel_id": novel.id,
        "fact_ledger": fact_ledger,
        "published_fact_count": len(fact_ledger.get("published_facts", [])) if isinstance(fact_ledger, dict) else 0,
        "stock_fact_count": len(fact_ledger.get("stock_facts", [])) if isinstance(fact_ledger, dict) else 0,
    }


@router.get("/{novel_id}/hard-facts")
def get_hard_fact_guard(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
    hard_fact_guard = snapshot.get("hard_fact_guard", {})
    return {
        "novel_id": novel.id,
        "hard_fact_guard": hard_fact_guard,
        "last_conflict_report": (hard_fact_guard or {}).get("last_conflict_report")
        if isinstance(hard_fact_guard, dict)
        else None,
    }


@router.post("/{novel_id}/serial-mode", response_model=SerialModeResponse)
def update_serial_mode(novel_id: int, payload: SerialModeUpdateRequest, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="连载模式切换")
    if novel.status == "generating":
        raise HTTPException(status_code=409, detail="当前小说正在生成中，不能切换连载模式")
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    story_bible = set_delivery_mode(story_bible, payload.delivery_mode)
    novel.story_bible = sync_long_term_state(story_bible, novel)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return {
        "novel_id": novel.id,
        "delivery_mode": payload.delivery_mode,
        "serial_runtime": ensure_serial_runtime(novel.story_bible or {}),
    }
