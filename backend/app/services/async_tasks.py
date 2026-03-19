from __future__ import annotations

import inspect
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_session
from app.models.async_task import AsyncTask
from app.models.async_task_event import AsyncTaskEvent
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.models.time_utils import utcnow_naive
from app.services.chapter_generation import generate_next_chapter
from app.services.edge_tts_service import (
    EdgeTtsBadRequestError,
    EdgeTtsBusyError,
    EdgeTtsError,
    EdgeTtsUnavailableError,
    generate_chapter_tts,
    get_chapter_tts_status,
    normalize_tts_options,
)
from app.schemas.novel import NovelCreate
from app.services.generation_exceptions import GenerationError
from app.services.novel_lifecycle import (
    BOOTSTRAP_STATUS_FAILED,
    BOOTSTRAP_STATUS_RUNNING,
    build_bootstrap_progress_payload,
    create_bootstrap_placeholder_novel,
    mark_bootstrap_failure,
    run_bootstrap_pipeline,
)
from app.services.story_state import ensure_workflow_state, workflow_bootstrap_view
from app.services.runtime_diagnostics import build_runtime_diagnostics_brief

logger = logging.getLogger(__name__)

TASK_TYPE_NEXT_CHAPTER = "generate_next_chapter"
TASK_TYPE_NEXT_CHAPTER_BATCH = "generate_next_chapters_batch"
TASK_TYPE_CHAPTER_TTS = "generate_chapter_tts"
TASK_TYPE_NOVEL_BOOTSTRAP = "bootstrap_novel"
GENERATION_TASK_TYPES = {TASK_TYPE_NEXT_CHAPTER, TASK_TYPE_NEXT_CHAPTER_BATCH}
ACTIVE_TASK_STATUSES = {"queued", "running"}
TERMINAL_TASK_STATUSES = {"succeeded", "failed", "cancelled"}
TASK_CANCELLED_CODE = "TASK_CANCELLED"
TASK_ORPHANED_CODE = "TASK_ORPHANED"

_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, int(getattr(settings, "async_task_max_workers", 2) or 2)))


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _chapter_task_progress_payload(
    *,
    novel: Novel,
    target_chapter_no: int,
    stage: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "stage": stage,
        "message": message,
        "novel_id": novel.id,
        "title": novel.title,
        "target_chapter_no": target_chapter_no,
    }
    diagnostics = build_runtime_diagnostics_brief(novel.story_bible or {})
    if diagnostics:
        payload["runtime_diagnostics"] = diagnostics
    if extra:
        payload.update(extra)
    return payload


def _invoke_generate_next_chapter(db: Session, novel: Novel, *, progress_callback: Callable[[dict[str, Any]], None] | None = None):
    generator = generate_next_chapter
    try:
        signature = inspect.signature(generator)
        if "progress_callback" in signature.parameters:
            return generator(db, novel, progress_callback=progress_callback)
    except (TypeError, ValueError):
        pass
    return generator(db, novel)


def _supports_cancel(task: AsyncTask) -> bool:
    if task.task_type == TASK_TYPE_NOVEL_BOOTSTRAP:
        return False
    if task.status == "queued":
        return True
    return task.status == "running" and task.task_type in {TASK_TYPE_NEXT_CHAPTER_BATCH, TASK_TYPE_CHAPTER_TTS, TASK_TYPE_NEXT_CHAPTER}


def _is_retryable_status(task: AsyncTask) -> bool:
    return task.status in {"failed", "cancelled"}


def serialize_task(task: AsyncTask, *, reused_existing: bool = False) -> dict[str, Any]:
    error_payload = task.error_payload or {}
    retryable_flag = bool(error_payload.get("retryable")) if task.status == "failed" else task.status == "cancelled"
    can_retry = _is_retryable_status(task)
    can_cancel = _supports_cancel(task) and not task.cancel_requested_at and task.status in ACTIVE_TASK_STATUSES
    duration_seconds = None
    if task.started_at and task.finished_at:
        duration_seconds = max(0.0, (task.finished_at - task.started_at).total_seconds())
    elif task.started_at and task.status in ACTIVE_TASK_STATUSES:
        duration_seconds = max(0.0, (_utcnow() - task.started_at).total_seconds())
    wait_seconds = None
    if task.status == "queued":
        wait_seconds = max(0.0, (_utcnow() - task.created_at).total_seconds())
    return {
        "id": task.id,
        "novel_id": task.novel_id,
        "chapter_no": task.chapter_no,
        "task_type": task.task_type,
        "status": task.status,
        "reused_existing": reused_existing,
        "owner_key": task.owner_key,
        "request_payload": task.request_payload or {},
        "progress_message": task.progress_message,
        "progress_payload": task.progress_payload or {},
        "result_payload": task.result_payload or {},
        "error_payload": error_payload,
        "retry_of_task_id": task.retry_of_task_id,
        "cancel_requested_at": task.cancel_requested_at,
        "cancelled_at": task.cancelled_at,
        "retryable": retryable_flag,
        "can_cancel": can_cancel,
        "can_retry": can_retry,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "duration_seconds": duration_seconds,
        "queue_wait_seconds": wait_seconds,
        "status_url": f"/api/v1/novels/{task.novel_id}/tasks/{task.id}",
        "events_url": f"/api/v1/novels/{task.novel_id}/tasks/{task.id}/events",
    }


def _task_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, GenerationError):
        details = exc.details or {}
        payload = {
            "code": exc.code,
            "stage": exc.stage,
            "message": exc.message,
            "retryable": exc.retryable,
            "provider": exc.provider,
            "details": details,
        }
        if exc.stage == "chapter_quality" or (isinstance(details, dict) and details.get("quality_feedback")):
            payload["quality_feedback"] = details.get("quality_feedback")
            if details.get("quality_rejections"):
                payload["quality_rejections"] = details.get("quality_rejections")
        return payload
    if isinstance(exc, EdgeTtsUnavailableError):
        return {"code": "TTS_UNAVAILABLE", "message": str(exc), "retryable": True}
    if isinstance(exc, EdgeTtsBusyError):
        return {"code": "TTS_BUSY", "message": str(exc), "retryable": True}
    if isinstance(exc, EdgeTtsBadRequestError):
        return {"code": "TTS_BAD_REQUEST", "message": str(exc), "retryable": False}
    if isinstance(exc, EdgeTtsError):
        return {"code": "TTS_ERROR", "message": str(exc), "retryable": True}
    return {"code": "TASK_EXECUTION_FAILED", "message": str(exc) or type(exc).__name__, "retryable": True}


def _task_cancelled_payload(message: str = "任务已取消。", *, partial_result: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"code": TASK_CANCELLED_CODE, "message": message, "retryable": True}
    if partial_result:
        payload["partial_result"] = partial_result
    return payload


def _task_orphaned_payload(message: str = "任务在服务重启后失联，已标记为失败。") -> dict[str, Any]:
    return {"code": TASK_ORPHANED_CODE, "message": message, "retryable": True}


def _record_task_event(
    db: Session,
    *,
    task: AsyncTask,
    event_type: str,
    message: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
    dedupe_same_message: bool = False,
) -> None:
    if dedupe_same_message:
        last_event = (
            db.query(AsyncTaskEvent)
            .filter(AsyncTaskEvent.task_id == task.id)
            .order_by(AsyncTaskEvent.created_at.desc(), AsyncTaskEvent.id.desc())
            .first()
        )
        if last_event and last_event.event_type == event_type and last_event.message == message:
            return
    event = AsyncTaskEvent(
        task_id=task.id,
        novel_id=task.novel_id,
        event_type=event_type,
        level=level,
        message=message,
        payload=payload or {},
    )
    db.add(event)


def list_task_events(db: Session, *, novel_id: int, task_id: int, limit: int = 50) -> list[AsyncTaskEvent]:
    return (
        db.query(AsyncTaskEvent)
        .filter(AsyncTaskEvent.novel_id == novel_id, AsyncTaskEvent.task_id == task_id)
        .order_by(AsyncTaskEvent.created_at.desc(), AsyncTaskEvent.id.desc())
        .limit(max(1, min(int(limit or 50), 200)))
        .all()
    )


def recover_orphaned_tasks_on_startup(db: Session) -> dict[str, Any]:
    tasks = (
        db.query(AsyncTask)
        .filter(AsyncTask.status.in_(tuple(ACTIVE_TASK_STATUSES)))
        .order_by(AsyncTask.created_at.asc(), AsyncTask.id.asc())
        .all()
    )
    if not tasks:
        return {"recovered_count": 0, "task_ids": []}

    now = utcnow_naive()
    recovered_ids: list[int] = []
    for task in tasks:
        previous_status = task.status
        task.status = "failed"
        task.finished_at = now
        task.progress_message = "任务因服务重启中断，已结束。"
        task.error_payload = _task_orphaned_payload()
        if task.cancel_requested_at and not task.cancelled_at:
            task.cancelled_at = now
        db.add(task)
        _record_task_event(
            db,
            task=task,
            event_type="recovered_orphaned",
            level="warning",
            message="检测到未完成任务在服务启动时失联，已标记为失败。",
            payload={"status_before_recovery": previous_status, "recovered_at": now.isoformat()},
        )
        recovered_ids.append(task.id)
    db.commit()
    return {"recovered_count": len(recovered_ids), "task_ids": recovered_ids}


def _mark_task_running(task_id: int, *, progress_message: str | None = None, progress_payload: dict[str, Any] | None = None) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task or task.status == "cancelled":
            return
        task.status = "running"
        task.started_at = task.started_at or utcnow_naive()
        task.progress_message = progress_message or task.progress_message
        task.progress_payload = progress_payload or task.progress_payload or {}
        db.add(task)
        _record_task_event(
            db,
            task=task,
            event_type="running",
            message=task.progress_message or "任务开始执行。",
            payload=task.progress_payload or {},
            dedupe_same_message=True,
        )
        db.commit()
    finally:
        db.close()


def _update_task_progress(task_id: int, *, progress_message: str | None = None, progress_payload: dict[str, Any] | None = None) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task or task.status in TERMINAL_TASK_STATUSES:
            return
        if progress_message is not None:
            task.progress_message = progress_message
        if progress_payload is not None:
            task.progress_payload = progress_payload
        db.add(task)
        if progress_message:
            _record_task_event(
                db,
                task=task,
                event_type="progress",
                message=progress_message,
                payload=progress_payload or task.progress_payload or {},
                dedupe_same_message=True,
            )
        db.commit()
    finally:
        db.close()


def _mark_task_succeeded(task_id: int, *, result_payload: dict[str, Any], progress_message: str | None = None) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        task.status = "succeeded"
        task.finished_at = utcnow_naive()
        task.progress_message = progress_message or task.progress_message
        task.result_payload = result_payload or {}
        task.error_payload = {}
        db.add(task)
        _record_task_event(
            db,
            task=task,
            event_type="succeeded",
            message=task.progress_message or "任务执行完成。",
            payload=task.result_payload or {},
        )
        db.commit()
    finally:
        db.close()


def _mark_task_failed(task_id: int, *, error_payload: dict[str, Any], progress_message: str | None = None) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        task.status = "failed"
        task.finished_at = utcnow_naive()
        task.progress_message = progress_message or task.progress_message
        task.error_payload = error_payload or {}
        db.add(task)
        _record_task_event(
            db,
            task=task,
            event_type="failed",
            level="error",
            message=task.progress_message or (task.error_payload or {}).get("message") or "任务执行失败。",
            payload=task.error_payload or {},
        )
        db.commit()
    finally:
        db.close()


def _mark_task_cancelled(
    task_id: int,
    *,
    progress_message: str | None = None,
    error_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        now = utcnow_naive()
        task.status = "cancelled"
        task.cancel_requested_at = task.cancel_requested_at or now
        task.cancelled_at = task.cancelled_at or now
        task.finished_at = task.finished_at or now
        task.progress_message = progress_message or task.progress_message or "任务已取消。"
        task.error_payload = error_payload or task.error_payload or _task_cancelled_payload(task.progress_message or "任务已取消。")
        if result_payload is not None:
            task.result_payload = result_payload
        db.add(task)
        _record_task_event(
            db,
            task=task,
            event_type="cancelled",
            level="warning",
            message=task.progress_message or "任务已取消。",
            payload=(task.error_payload or {}) if isinstance(task.error_payload, dict) else {},
        )
        db.commit()
    finally:
        db.close()


def _submit_background_task(task_id: int, runner: Callable[[int], None]) -> None:
    _EXECUTOR.submit(runner, task_id)


def _active_task_query(db: Session, *, novel_id: int, task_type: str, owner_key: str | None = None):
    query = db.query(AsyncTask).filter(
        AsyncTask.novel_id == novel_id,
        AsyncTask.task_type == task_type,
        AsyncTask.status.in_(tuple(ACTIVE_TASK_STATUSES)),
    )
    if owner_key is not None:
        query = query.filter(AsyncTask.owner_key == owner_key)
    return query.order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())


def get_task(db: Session, *, novel_id: int, task_id: int) -> AsyncTask | None:
    return db.query(AsyncTask).filter(AsyncTask.id == task_id, AsyncTask.novel_id == novel_id).first()


def list_tasks(db: Session, *, novel_id: int, status: str | None = None, limit: int = 20) -> list[AsyncTask]:
    query = db.query(AsyncTask).filter(AsyncTask.novel_id == novel_id)
    if status == "active":
        query = query.filter(AsyncTask.status.in_(tuple(ACTIVE_TASK_STATUSES)))
    elif status == "terminal":
        query = query.filter(AsyncTask.status.in_(tuple(TERMINAL_TASK_STATUSES)))
    elif status == "recent":
        pass
    elif status:
        query = query.filter(AsyncTask.status == status)
    return query.order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc()).limit(max(1, min(int(limit or 20), 100))).all()


def list_recent_tasks(db: Session, *, novel_id: int, limit: int = 8) -> list[AsyncTask]:
    return list_tasks(db, novel_id=novel_id, status="recent", limit=limit)


def list_active_tasks(db: Session, *, novel_id: int) -> list[AsyncTask]:
    return list_tasks(db, novel_id=novel_id, status="active", limit=20)


def find_active_task(
    db: Session,
    *,
    novel_id: int,
    task_type: str,
    owner_key: str | None = None,
    chapter_no: int | None = None,
) -> AsyncTask | None:
    query = _active_task_query(db, novel_id=novel_id, task_type=task_type, owner_key=owner_key)
    if chapter_no is not None:
        query = query.filter(AsyncTask.chapter_no == chapter_no)
    return query.first()


def find_active_generation_task(db: Session, *, novel_id: int) -> AsyncTask | None:
    return (
        db.query(AsyncTask)
        .filter(
            AsyncTask.novel_id == novel_id,
            AsyncTask.task_type.in_(tuple(GENERATION_TASK_TYPES)),
            AsyncTask.status.in_(tuple(ACTIVE_TASK_STATUSES)),
        )
        .order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
        .first()
    )


def _create_task(
    db: Session,
    *,
    novel_id: int,
    chapter_no: int | None,
    task_type: str,
    owner_key: str,
    request_payload: dict[str, Any] | None = None,
    progress_message: str | None = None,
    retry_of_task_id: int | None = None,
) -> AsyncTask:
    task = AsyncTask(
        novel_id=novel_id,
        chapter_no=chapter_no,
        task_type=task_type,
        owner_key=owner_key,
        status="queued",
        request_payload=request_payload or {},
        progress_message=progress_message,
        progress_payload={},
        result_payload={},
        error_payload={},
        retry_of_task_id=retry_of_task_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _record_task_event(
        db,
        task=task,
        event_type="queued",
        message=task.progress_message or "任务已进入队列。",
        payload=task.request_payload or {},
    )
    db.commit()
    return task


def _cancel_requested(db: Session, task_id: int) -> bool:
    task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
    return bool(task and (task.status == "cancelled" or task.cancel_requested_at))


def _payload_to_novel_create(payload: dict[str, Any]) -> NovelCreate:
    return NovelCreate(
        genre=str((payload or {}).get("genre") or "").strip(),
        premise=str((payload or {}).get("premise") or "").strip(),
        protagonist_name=str((payload or {}).get("protagonist_name") or "").strip(),
        style_preferences=dict((payload or {}).get("style_preferences") or {}),
    )


def _novel_to_bootstrap_payload(novel: Novel) -> NovelCreate:
    return NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )


def _bootstrap_task_progress_payload(
    *,
    stage: str,
    message: str,
    novel: Novel,
    status: str = "running",
    title: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_bootstrap_progress_payload(
        stage=stage,
        message=message,
        status=status,
        novel_id=novel.id,
        title=title or novel.title,
        extra=extra,
    )
    payload["bootstrap_status"] = BOOTSTRAP_STATUS_RUNNING if status == "running" else status
    return payload


def _mark_bootstrap_task_novel_failed(
    db: Session,
    *,
    novel: Novel,
    stage: str,
    message: str,
    error_payload: dict[str, Any],
) -> Novel:
    story_bible = dict(novel.story_bible or {}) if isinstance(novel.story_bible, dict) else {}
    workflow = ensure_workflow_state(story_bible)
    retry_count = int(workflow.get("bootstrap_retry_count", 0) or 0)
    workflow["bootstrap_state"] = {
        "phase": "bootstrap",
        "status": "failed",
        "stage": stage,
        "message": message,
        "retryable": bool((error_payload or {}).get("retryable", True)),
        "error": error_payload or None,
    }
    workflow["bootstrap_error"] = error_payload or None
    workflow["bootstrap_retry_count"] = retry_count + 1
    workflow["bootstrap_completed"] = False
    novel.story_bible = story_bible
    novel.status = BOOTSTRAP_STATUS_FAILED
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return novel


def submit_novel_bootstrap_task(
    db: Session,
    *,
    payload: NovelCreate | None = None,
    novel: Novel | None = None,
    retry_of_task_id: int | None = None,
) -> tuple[AsyncTask, bool]:
    if novel is None and payload is None:
        raise ValueError("Novel payload is required")
    if novel is None:
        novel = create_bootstrap_placeholder_novel(payload)
        db.add(novel)
        db.commit()
        db.refresh(novel)
    payload = payload or _novel_to_bootstrap_payload(novel)
    owner_key = f"novel:{novel.id}:bootstrap"
    existing = find_active_task(db, novel_id=novel.id, task_type=TASK_TYPE_NOVEL_BOOTSTRAP, owner_key=owner_key)
    if existing is not None:
        return existing, True

    task = _create_task(
        db,
        novel_id=novel.id,
        chapter_no=None,
        task_type=TASK_TYPE_NOVEL_BOOTSTRAP,
        owner_key=owner_key,
        request_payload=payload.model_dump(),
        progress_message=f"已进入队列，准备初始化《{novel.title}》。",
        retry_of_task_id=retry_of_task_id,
    )
    _submit_background_task(task.id, _run_novel_bootstrap_task)
    db.expire(task)
    db.refresh(task)
    return task, False


def submit_next_chapter_task(db: Session, novel: Novel, *, retry_of_task_id: int | None = None) -> tuple[AsyncTask, bool]:
    owner_key = f"novel:{novel.id}:next-chapter"
    active_generation_task = find_active_generation_task(db, novel_id=novel.id)
    if active_generation_task is not None:
        return active_generation_task, True

    task = _create_task(
        db,
        novel_id=novel.id,
        chapter_no=None,
        task_type=TASK_TYPE_NEXT_CHAPTER,
        owner_key=owner_key,
        progress_message=f"已进入队列，准备生成《{novel.title}》下一章。",
        retry_of_task_id=retry_of_task_id,
    )
    _submit_background_task(task.id, _run_next_chapter_task)
    db.expire(task)
    db.refresh(task)
    return task, False


def submit_next_chapters_batch_task(db: Session, novel: Novel, *, count: int, retry_of_task_id: int | None = None) -> tuple[AsyncTask, bool]:
    owner_key = f"novel:{novel.id}:next-chapters-batch"
    active_generation_task = find_active_generation_task(db, novel_id=novel.id)
    if active_generation_task is not None:
        return active_generation_task, True

    safe_count = int(max(1, count))
    task = _create_task(
        db,
        novel_id=novel.id,
        chapter_no=None,
        task_type=TASK_TYPE_NEXT_CHAPTER_BATCH,
        owner_key=owner_key,
        request_payload={"count": safe_count},
        progress_message=f"已进入队列，准备连续生成 {safe_count} 章。",
        retry_of_task_id=retry_of_task_id,
    )
    _submit_background_task(task.id, _run_next_chapters_batch_task)
    db.expire(task)
    db.refresh(task)
    return task, False


def _run_novel_bootstrap_task(task_id: int) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        novel = db.query(Novel).filter(Novel.id == task.novel_id).first()
        if not novel:
            raise RuntimeError("小说不存在，无法继续执行初始化任务。")
        if task.status == "cancelled" or task.cancel_requested_at:
            _mark_bootstrap_task_novel_failed(
                db,
                novel=novel,
                stage="queued",
                message="初始化任务已取消。",
                error_payload=_task_cancelled_payload("初始化任务已取消。"),
            )
            _mark_task_cancelled(task_id, progress_message="初始化任务已取消。")
            return

        request_payload = dict(task.request_payload or {})
        payload = _payload_to_novel_create(request_payload)
        _mark_task_running(
            task_id,
            progress_message=f"正在初始化《{novel.title}》。",
            progress_payload=_bootstrap_task_progress_payload(
                stage="initial_story_seed",
                message="正在准备基础设定、主角信息与风格底稿。",
                novel=novel,
            ),
        )

        def _on_bootstrap_progress(snapshot: dict[str, Any]) -> None:
            stage = str(snapshot.get("stage") or "bootstrap")
            message = str(snapshot.get("message") or snapshot.get("progress_message") or f"正在初始化《{novel.title}》。")
            title = snapshot.get("title") if isinstance(snapshot.get("title"), str) else None
            extra = dict(snapshot)
            extra.pop("message", None)
            progress_payload = _bootstrap_task_progress_payload(
                stage=stage,
                message=message,
                novel=novel,
                status=str(snapshot.get("status") or "running"),
                title=title,
                extra=extra,
            )
            _update_task_progress(task_id, progress_message=message, progress_payload=progress_payload)

        result_novel = run_bootstrap_pipeline(db, novel=novel, payload=payload, progress_callback=_on_bootstrap_progress)
        _mark_task_succeeded(
            task_id,
            progress_message=f"《{result_novel.title}》初始化完成。",
            result_payload={
                "novel_id": result_novel.id,
                "title": result_novel.title,
                "status": result_novel.status,
                "current_chapter_no": result_novel.current_chapter_no,
            },
        )
    except GenerationError as exc:  # pragma: no cover - real execution path
        logger.exception("async bootstrap task failed task_id=%s", task_id)
        db.rollback()
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        novel = db.query(Novel).filter(Novel.id == (task.novel_id if task else None)).first() if task else None
        if novel is not None:
            novel = mark_bootstrap_failure(db, novel=novel, exc=exc)
            error_payload = {**_task_error_payload(exc), "novel": {"id": novel.id, "title": novel.title, "status": novel.status, "bootstrap_state": workflow_bootstrap_view(novel.story_bible).get("bootstrap_state")}}
        else:
            error_payload = _task_error_payload(exc)
        _mark_task_failed(
            task_id,
            progress_message="初始化失败。",
            error_payload=error_payload,
        )
    except Exception as exc:  # pragma: no cover - real execution path
        logger.exception("async bootstrap task crashed task_id=%s", task_id)
        db.rollback()
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        novel = db.query(Novel).filter(Novel.id == (task.novel_id if task else None)).first() if task else None
        error_payload = _task_error_payload(exc)
        if novel is not None:
            novel = _mark_bootstrap_task_novel_failed(db, novel=novel, stage="bootstrap_pipeline", message=str(exc) or "初始化失败。", error_payload=error_payload)
            error_payload = {**error_payload, "novel": {"id": novel.id, "title": novel.title, "status": novel.status, "bootstrap_state": workflow_bootstrap_view(novel.story_bible).get("bootstrap_state")}}
        _mark_task_failed(task_id, progress_message="初始化失败。", error_payload=error_payload)
    finally:
        db.close()


def _run_next_chapter_task(task_id: int) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        if task.status == "cancelled" or task.cancel_requested_at:
            _mark_task_cancelled(task_id, progress_message="章节生成已取消。")
            return
        novel = db.query(Novel).filter(Novel.id == task.novel_id).first()
        if not novel:
            raise RuntimeError("小说不存在，无法继续执行任务。")
        target_chapter_no = int(novel.current_chapter_no or 0) + 1
        _mark_task_running(
            task_id,
            progress_message=f"正在生成《{novel.title}》下一章。",
            progress_payload=_chapter_task_progress_payload(
                novel=novel,
                target_chapter_no=target_chapter_no,
                stage="drafting",
                message=f"正在生成《{novel.title}》下一章。",
            ),
        )
        if _cancel_requested(db, task_id):
            _mark_task_cancelled(task_id, progress_message="章节生成已取消。")
            return

        def _on_chapter_progress(snapshot: dict[str, Any]) -> None:
            message = str((snapshot or {}).get("message") or f"正在生成《{novel.title}》第 {target_chapter_no} 章。")
            stage = str((snapshot or {}).get("stage") or "drafting")
            payload = _chapter_task_progress_payload(
                novel=novel,
                target_chapter_no=int((snapshot or {}).get("target_chapter_no") or target_chapter_no),
                stage=stage,
                message=message,
                extra=dict(snapshot or {}),
            )
            _update_task_progress(task_id, progress_message=message, progress_payload=payload)

        chapter = _invoke_generate_next_chapter(db, novel, progress_callback=_on_chapter_progress)
        _mark_task_succeeded(
            task_id,
            progress_message=f"第 {chapter.chapter_no} 章已生成完成。",
            result_payload={
                "chapter_id": chapter.id,
                "chapter_no": chapter.chapter_no,
                "title": chapter.title,
                "novel_current_chapter_no": chapter.chapter_no,
            },
        )
    except Exception as exc:  # pragma: no cover - real execution path
        logger.exception("async next chapter task failed task_id=%s", task_id)
        _mark_task_failed(task_id, progress_message="章节生成失败。", error_payload=_task_error_payload(exc))
    finally:
        db.close()


def _run_next_chapters_batch_task(task_id: int) -> None:
    db = create_session()
    generated: list[dict[str, Any]] = []
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        if task.status == "cancelled" or task.cancel_requested_at:
            _mark_task_cancelled(task_id, progress_message="批量生成任务已取消。")
            return
        novel = db.query(Novel).filter(Novel.id == task.novel_id).first()
        if not novel:
            raise RuntimeError("小说不存在，无法继续执行批量生成任务。")
        requested_count = int((task.request_payload or {}).get("count") or 1)
        started_from_chapter = int(novel.current_chapter_no or 0) + 1
        _mark_task_running(
            task_id,
            progress_message=f"正在准备连续生成 {requested_count} 章。",
            progress_payload={
                "stage": "batch_drafting",
                "requested_count": requested_count,
                "generated_count": 0,
                "started_from_chapter": started_from_chapter,
            },
        )
        for index in range(requested_count):
            if _cancel_requested(db, task_id):
                partial = {
                    "generated_count": len(generated),
                    "chapters": generated,
                    "ended_at_chapter": generated[-1]["chapter_no"] if generated else started_from_chapter - 1,
                }
                _mark_task_cancelled(
                    task_id,
                    progress_message=f"批量生成已取消，已完成 {len(generated)}/{requested_count} 章。",
                    error_payload=_task_cancelled_payload("批量生成已取消。", partial_result=partial),
                    result_payload=partial,
                )
                return
            novel = db.query(Novel).filter(Novel.id == task.novel_id).first()
            if not novel:
                raise RuntimeError("小说不存在，批量生成任务已中断。")
            next_chapter_no = int(novel.current_chapter_no or 0) + 1
            _update_task_progress(
                task_id,
                progress_message=f"正在生成第 {next_chapter_no} 章（{index + 1}/{requested_count}）。",
                progress_payload={
                    "stage": "batch_drafting",
                    "requested_count": requested_count,
                    "generated_count": len(generated),
                    "started_from_chapter": started_from_chapter,
                    "current_index": index + 1,
                    "target_chapter_no": next_chapter_no,
                    "generated_chapters": generated,
                },
            )

            def _on_batch_chapter_progress(snapshot: dict[str, Any]) -> None:
                message = str((snapshot or {}).get("message") or f"正在生成第 {next_chapter_no} 章（{index + 1}/{requested_count}）。")
                payload = {
                    "stage": str((snapshot or {}).get("stage") or "batch_drafting"),
                    "requested_count": requested_count,
                    "generated_count": len(generated),
                    "started_from_chapter": started_from_chapter,
                    "current_index": index + 1,
                    "target_chapter_no": int((snapshot or {}).get("target_chapter_no") or next_chapter_no),
                    "generated_chapters": generated,
                    **dict(snapshot or {}),
                }
                _update_task_progress(task_id, progress_message=message, progress_payload=payload)

            chapter = _invoke_generate_next_chapter(db, novel, progress_callback=_on_batch_chapter_progress)
            chapter_payload = {
                "chapter_id": chapter.id,
                "chapter_no": chapter.chapter_no,
                "title": chapter.title,
            }
            generated.append(chapter_payload)
            _update_task_progress(
                task_id,
                progress_message=f"第 {chapter.chapter_no} 章已生成完成（{len(generated)}/{requested_count}）。",
                progress_payload={
                    "stage": "batch_drafting",
                    "requested_count": requested_count,
                    "generated_count": len(generated),
                    "started_from_chapter": started_from_chapter,
                    "last_generated_chapter_no": chapter.chapter_no,
                    "last_generated_title": chapter.title,
                    "generated_chapters": generated,
                },
            )
        _mark_task_succeeded(
            task_id,
            progress_message=f"批量生成完成，共新增 {len(generated)} 章。",
            result_payload={
                "requested_count": requested_count,
                "generated_count": len(generated),
                "started_from_chapter": started_from_chapter,
                "ended_at_chapter": generated[-1]["chapter_no"] if generated else started_from_chapter - 1,
                "chapters": generated,
                "titles": [item["title"] for item in generated],
            },
        )
    except Exception as exc:  # pragma: no cover - real execution path
        logger.exception("async batch generation task failed task_id=%s", task_id)
        error_payload = _task_error_payload(exc)
        if generated:
            error_payload["partial_result"] = {
                "generated_count": len(generated),
                "chapters": generated,
                "ended_at_chapter": generated[-1]["chapter_no"],
            }
        _mark_task_failed(task_id, progress_message="批量生成失败。", error_payload=error_payload)
    finally:
        db.close()


def _tts_owner_key(novel_id: int, chapter_no: int, voice: str) -> str:
    return f"novel:{novel_id}:chapter:{chapter_no}:tts:{voice}"


def submit_chapter_tts_task(
    db: Session,
    chapter: Chapter,
    payload: dict[str, Any] | None = None,
    *,
    force_regenerate: bool = False,
    retry_of_task_id: int | None = None,
) -> tuple[AsyncTask, bool]:
    options = normalize_tts_options(payload)
    owner_key = _tts_owner_key(chapter.novel_id, chapter.chapter_no, options["voice"])
    existing = find_active_task(
        db,
        novel_id=chapter.novel_id,
        task_type=TASK_TYPE_CHAPTER_TTS,
        owner_key=owner_key,
        chapter_no=chapter.chapter_no,
    )
    if existing is not None:
        return existing, True

    status = get_chapter_tts_status(chapter, options)
    if status.get("ready") and not force_regenerate:
        task = _create_task(
            db,
            novel_id=chapter.novel_id,
            chapter_no=chapter.chapter_no,
            task_type=TASK_TYPE_CHAPTER_TTS,
            owner_key=owner_key,
            request_payload={**options, "force_regenerate": False},
            progress_message=f"{options['voice']} 版本已存在，直接复用。",
            retry_of_task_id=retry_of_task_id,
        )
        task.status = "succeeded"
        task.started_at = task.created_at
        task.finished_at = task.created_at
        task.result_payload = status
        db.add(task)
        _record_task_event(
            db,
            task=task,
            event_type="reused_existing_result",
            message=f"{options['voice']} 版本已存在，直接复用已有音频。",
            payload=status,
        )
        db.commit()
        db.refresh(task)
        return task, False

    task = _create_task(
        db,
        novel_id=chapter.novel_id,
        chapter_no=chapter.chapter_no,
        task_type=TASK_TYPE_CHAPTER_TTS,
        owner_key=owner_key,
        request_payload={**options, "force_regenerate": bool(force_regenerate)},
        progress_message=f"第 {chapter.chapter_no} 章 {options['voice']} 朗读已进入队列。",
        retry_of_task_id=retry_of_task_id,
    )
    _submit_background_task(task.id, _run_chapter_tts_task)
    db.expire(task)
    db.refresh(task)
    return task, False


def _run_chapter_tts_task(task_id: int) -> None:
    db = create_session()
    try:
        task = db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if not task:
            return
        if task.status == "cancelled" or task.cancel_requested_at:
            _mark_task_cancelled(task_id, progress_message="朗读任务已取消。")
            return
        chapter = (
            db.query(Chapter)
            .filter(Chapter.novel_id == task.novel_id, Chapter.chapter_no == task.chapter_no)
            .first()
        )
        if not chapter:
            raise RuntimeError("章节不存在，无法继续生成朗读音频。")
        options = dict(task.request_payload or {})
        _mark_task_running(
            task_id,
            progress_message=f"正在生成第 {chapter.chapter_no} 章朗读音频。",
            progress_payload={"voice": options.get("voice"), "chapter_no": chapter.chapter_no},
        )
        if _cancel_requested(db, task_id):
            _mark_task_cancelled(task_id, progress_message="朗读任务已取消。")
            return
        status = generate_chapter_tts(chapter, options, force_regenerate=bool(options.get("force_regenerate")))
        db.add(chapter)
        db.commit()
        db.refresh(chapter)
        _mark_task_succeeded(
            task_id,
            progress_message=f"第 {chapter.chapter_no} 章朗读音频已生成。",
            result_payload=status,
        )
    except Exception as exc:  # pragma: no cover - real execution path
        logger.exception("async chapter tts task failed task_id=%s", task_id)
        _mark_task_failed(task_id, progress_message="朗读生成失败。", error_payload=_task_error_payload(exc))
    finally:
        db.close()


def request_task_cancel(db: Session, *, novel_id: int, task_id: int) -> AsyncTask:
    task = get_task(db, novel_id=novel_id, task_id=task_id)
    if task is None:
        raise ValueError("Task not found")
    if task.status in TERMINAL_TASK_STATUSES:
        return task
    now = utcnow_naive()
    if task.status == "queued":
        task.status = "cancelled"
        task.cancel_requested_at = now
        task.cancelled_at = now
        task.finished_at = now
        task.progress_message = "任务已取消。"
        task.error_payload = _task_cancelled_payload()
        event_type = "cancelled"
        event_level = "warning"
    else:
        task.cancel_requested_at = task.cancel_requested_at or now
        task.progress_message = "已请求取消，将在安全点停止。"
        event_type = "cancel_requested"
        event_level = "warning"
    db.add(task)
    _record_task_event(
        db,
        task=task,
        event_type=event_type,
        level=event_level,
        message=task.progress_message or "任务已收到取消请求。",
        payload={"cancel_requested_at": task.cancel_requested_at.isoformat() if task.cancel_requested_at else None},
    )
    db.commit()
    db.refresh(task)
    return task


def retry_task(db: Session, *, novel_id: int, task_id: int) -> tuple[AsyncTask, bool]:
    task = get_task(db, novel_id=novel_id, task_id=task_id)
    if task is None:
        raise ValueError("Task not found")
    if task.status not in {"failed", "cancelled"}:
        raise ValueError("Only failed or cancelled tasks can be retried")

    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is None:
        raise ValueError("Novel not found")

    _record_task_event(
        db,
        task=task,
        event_type="retry_requested",
        message="已为该任务创建重试请求。",
        payload={"task_type": task.task_type},
    )
    db.commit()

    if task.task_type == TASK_TYPE_NEXT_CHAPTER:
        return submit_next_chapter_task(db, novel, retry_of_task_id=task.id)
    if task.task_type == TASK_TYPE_NEXT_CHAPTER_BATCH:
        count = int((task.request_payload or {}).get("count") or 1)
        return submit_next_chapters_batch_task(db, novel, count=count, retry_of_task_id=task.id)
    if task.task_type == TASK_TYPE_CHAPTER_TTS:
        chapter = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.chapter_no == task.chapter_no)
            .first()
        )
        if chapter is None:
            raise ValueError("Chapter not found")
        payload = dict(task.request_payload or {})
        return submit_chapter_tts_task(
            db,
            chapter,
            payload,
            force_regenerate=bool(payload.get("force_regenerate")),
            retry_of_task_id=task.id,
        )
    if task.task_type == TASK_TYPE_NOVEL_BOOTSTRAP:
        payload = _payload_to_novel_create(dict(task.request_payload or {}) or _novel_to_bootstrap_payload(novel).model_dump())
        return submit_novel_bootstrap_task(db, novel=novel, payload=payload, retry_of_task_id=task.id)
    raise ValueError("Unsupported task type")


def cleanup_terminal_tasks(
    db: Session,
    *,
    novel_id: int,
    keep_latest: int = 30,
    older_than_days: int | None = None,
) -> dict[str, Any]:
    keep_latest = max(0, min(int(keep_latest or 0), 200))
    query = (
        db.query(AsyncTask)
        .filter(AsyncTask.novel_id == novel_id, AsyncTask.status.in_(tuple(TERMINAL_TASK_STATUSES)))
        .order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
    )
    tasks = query.all()
    if not tasks:
        return {"novel_id": novel_id, "keep_latest": keep_latest, "deleted_count": 0, "deleted_task_ids": []}
    cutoff = _utcnow() - timedelta(days=max(0, int(older_than_days))) if older_than_days is not None else None
    preserved_ids = {task.id for task in tasks[:keep_latest]}
    to_delete = []
    for task in tasks:
        if task.id in preserved_ids:
            continue
        if cutoff is not None and (task.finished_at or task.updated_at or task.created_at) > cutoff:
            continue
        to_delete.append(task)
    deleted_ids = [task.id for task in to_delete]
    for task in to_delete:
        db.delete(task)
    db.commit()
    return {
        "novel_id": novel_id,
        "keep_latest": keep_latest,
        "deleted_count": len(deleted_ids),
        "deleted_task_ids": deleted_ids,
    }
