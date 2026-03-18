from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.generation_exceptions import GenerationError
from app.services.story_workspace_archive import archive_story_workspace_snapshot
from app.services.novel_bootstrap import (
    build_base_story_bible,
    build_story_bible,
    generate_arc_outline_bundle,
    generate_global_story_outline,
    generate_story_engine_strategy_bundle,
    generate_title,
)
from app.services.story_architecture import ensure_story_architecture, sync_long_term_state
from app.services.story_state import ensure_workflow_state, workflow_bootstrap_view


BOOTSTRAP_STATUS_READY = "planning_ready"
BOOTSTRAP_STATUS_RUNNING = "bootstrapping"
BOOTSTRAP_STATUS_FAILED = "bootstrap_failed"


BOOTSTRAP_STAGE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "stage": "initial_story_seed",
        "label": "初始化底稿",
        "description": "准备基础世界设定、主角信息与风格底稿。",
        "step_index": 1,
        "step_total": 6,
    },
    {
        "stage": "story_engine_strategy_generation",
        "label": "题材推进引擎",
        "description": "分析题材结构，生成前 30 章推进引擎与策略卡。",
        "step_index": 2,
        "step_total": 6,
    },
    {
        "stage": "global_outline_generation",
        "label": "全书总纲",
        "description": "生成全书总纲，明确主线、阶段目标与长期矛盾。",
        "step_index": 3,
        "step_total": 6,
    },
    {
        "stage": "title_generation",
        "label": "作品包装",
        "description": "生成书名并校准作品对外包装信息。",
        "step_index": 4,
        "step_total": 6,
    },
    {
        "stage": "arc_outline_generation",
        "label": "首段剧情弧",
        "description": "生成首个剧情弧与近期章节卡，搭好开局节奏。",
        "step_index": 5,
        "step_total": 6,
    },
    {
        "stage": "story_bible_finalize",
        "label": "Story Bible 收口",
        "description": "整理 Story Bible、长期状态、模板与 Story Workspace 快照。",
        "step_index": 6,
        "step_total": 6,
    },
]
BOOTSTRAP_STAGE_INDEX = {item["stage"]: item for item in BOOTSTRAP_STAGE_DEFINITIONS}


def bootstrap_stage_meta(stage: str) -> dict[str, Any]:
    item = BOOTSTRAP_STAGE_INDEX.get(stage, {})
    return {
        "stage": stage,
        "label": item.get("label") or stage,
        "description": item.get("description") or "",
        "step_index": int(item.get("step_index") or 0),
        "step_total": int(item.get("step_total") or len(BOOTSTRAP_STAGE_DEFINITIONS) or 0),
    }


def build_bootstrap_progress_payload(*, stage: str, message: str, status: str = "running", novel_id: int | None = None, title: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = bootstrap_stage_meta(stage)
    step_total = meta.get("step_total") or 0
    step_index = meta.get("step_index") or 0
    percent = int(round(step_index / step_total * 100)) if step_total and status == "running" else 100 if status == "completed" else 0
    payload = {
        "phase": "bootstrap",
        "status": status,
        "stage": stage,
        "stage_label": meta.get("label") or stage,
        "stage_description": meta.get("description") or "",
        "message": message,
        "step_index": step_index,
        "step_total": step_total,
        "percent": max(0, min(percent, 100)),
    }
    if novel_id is not None:
        payload["novel_id"] = novel_id
    if title:
        payload["title"] = title
    if extra:
        payload.update(extra)
    return payload


def _emit_bootstrap_progress(progress_callback: Callable[[dict[str, Any]], None] | None, *, stage: str, message: str, status: str = "running", novel: Novel | None = None, title: str | None = None, extra: dict[str, Any] | None = None) -> None:
    if not progress_callback:
        return
    progress_callback(
        build_bootstrap_progress_payload(
            stage=stage,
            message=message,
            status=status,
            novel_id=novel.id if novel is not None else None,
            title=title or (novel.title if novel is not None else None),
            extra=extra,
        )
    )



class BootstrapLifecycleError(GenerationError):
    novel_id: int | None = None


def _bootstrap_placeholder_title(payload: NovelCreate) -> str:
    return f"待初始化作品：{payload.protagonist_name.strip()[:20] or '未命名主角'}"


def _bootstrap_state(
    *,
    stage: str,
    status: str,
    message: str,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "phase": "bootstrap",
        "status": status,
        "stage": stage,
        "message": message,
        "retryable": bool(error.get("retryable", True)) if isinstance(error, dict) else True,
        "error": error or None,
    }
    return payload


def _merge_workflow_state(story_bible: dict[str, Any], **updates: Any) -> dict[str, Any]:
    workflow = ensure_workflow_state(story_bible)
    workflow.update(updates)
    return story_bible


def build_bootstrap_seed_story_bible(payload: NovelCreate) -> dict[str, Any]:
    story_bible = build_base_story_bible(payload)
    return _merge_workflow_state(
        story_bible,
        bootstrap_state=_bootstrap_state(
            stage="queued",
            status="running",
            message="小说已创建，正在准备初始化文档。",
        ),
        bootstrap_error=None,
        bootstrap_retry_count=0,
        bootstrap_completed=False,
    )


def create_bootstrap_placeholder_novel(payload: NovelCreate) -> Novel:
    return Novel(
        title=_bootstrap_placeholder_title(payload),
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences,
        story_bible=build_bootstrap_seed_story_bible(payload),
        current_chapter_no=0,
        status=BOOTSTRAP_STATUS_RUNNING,
    )


def mark_bootstrap_progress(
    db: Session,
    *,
    novel: Novel,
    stage: str,
    message: str,
    story_bible: dict[str, Any] | None = None,
    title: str | None = None,
) -> Novel:
    payload = deepcopy(story_bible if story_bible is not None else (novel.story_bible or {}))
    payload = _merge_workflow_state(
        payload,
        bootstrap_state=_bootstrap_state(stage=stage, status="running", message=message),
        bootstrap_error=None,
    )
    novel.story_bible = payload
    novel.status = BOOTSTRAP_STATUS_RUNNING
    if title:
        novel.title = title
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return novel


def mark_bootstrap_success(db: Session, *, novel: Novel, story_bible: dict[str, Any], title: str) -> Novel:
    payload = deepcopy(story_bible or {})
    payload = _merge_workflow_state(
        payload,
        bootstrap_state=_bootstrap_state(
            stage="completed",
            status="completed",
            message="初始化完成，可以开始生成章节。",
        ),
        bootstrap_error=None,
        bootstrap_completed=True,
    )
    novel.title = title
    novel.story_bible = payload
    novel.status = BOOTSTRAP_STATUS_READY
    db.add(novel)
    db.commit()
    db.refresh(novel)
    archive_story_workspace_snapshot(
        novel,
        chapter_no=1,
        phase="after",
        stage="bootstrap_completed",
        note="小说初始化完成后的 Story Workspace 快照。",
        extra={"bootstrap": True},
    )
    return novel


def mark_bootstrap_failure(db: Session, *, novel: Novel, exc: GenerationError) -> Novel:
    story_bible = deepcopy(novel.story_bible or {})
    workflow = ensure_workflow_state(story_bible)
    retry_count = int(workflow.get("bootstrap_retry_count", 0) or 0)
    error_payload = {
        "code": exc.code,
        "stage": exc.stage,
        "message": exc.message,
        "provider": exc.provider,
        "retryable": exc.retryable,
        "details": exc.details or {},
    }
    story_bible = _merge_workflow_state(
        story_bible,
        bootstrap_state=_bootstrap_state(
            stage=exc.stage,
            status="failed",
            message=exc.message,
            error=error_payload,
        ),
        bootstrap_error=error_payload,
        bootstrap_retry_count=retry_count + 1,
        bootstrap_completed=False,
    )
    novel.story_bible = story_bible
    novel.status = BOOTSTRAP_STATUS_FAILED
    db.add(novel)
    db.commit()
    db.refresh(novel)
    archive_story_workspace_snapshot(
        novel,
        chapter_no=1,
        phase="failed",
        stage=exc.stage,
        note=exc.message,
        extra={"bootstrap": True, "error": error_payload},
    )
    return novel


def build_bootstrap_error_detail(novel: Novel, exc: GenerationError) -> dict[str, Any]:
    workflow = workflow_bootstrap_view(novel.story_bible if isinstance(novel.story_bible, dict) else {})
    return {
        "code": exc.code,
        "stage": exc.stage,
        "message": exc.message,
        "retryable": exc.retryable,
        "provider": exc.provider,
        "details": exc.details or {},
        "novel": {
            "id": novel.id,
            "title": novel.title,
            "status": novel.status,
            "bootstrap_state": workflow.get("bootstrap_state"),
        },
    }


def run_bootstrap_pipeline(
    db: Session,
    *,
    novel: Novel,
    payload: NovelCreate,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Novel:
    archive_story_workspace_snapshot(
        novel,
        chapter_no=1,
        phase="before",
        stage="bootstrap_started",
        note="小说初始化开始前的 Story Workspace 快照。",
        extra={"bootstrap": True},
    )
    _emit_bootstrap_progress(
        progress_callback,
        stage="initial_story_seed",
        message="正在准备基础设定、主角信息与风格底稿。",
        novel=novel,
    )
    base_story_bible = build_base_story_bible(payload)
    novel = mark_bootstrap_progress(
        db,
        novel=novel,
        stage="story_engine_strategy_generation",
        message="正在分析题材类型并生成前30章推进引擎。",
        story_bible=base_story_bible,
    )
    _emit_bootstrap_progress(
        progress_callback,
        stage="story_engine_strategy_generation",
        message="正在分析题材类型并生成前30章推进引擎。",
        novel=novel,
    )
    current_story_bible = deepcopy(novel.story_bible or base_story_bible)
    story_engine_diagnosis, story_strategy_card = generate_story_engine_strategy_bundle(payload, current_story_bible)
    current_story_bible = build_base_story_bible(
        payload,
        story_engine_diagnosis=story_engine_diagnosis,
        story_strategy_card=story_strategy_card,
    )

    novel = mark_bootstrap_progress(
        db,
        novel=novel,
        stage="global_outline_generation",
        message="正在生成全书总纲。",
        story_bible=current_story_bible,
    )
    _emit_bootstrap_progress(
        progress_callback,
        stage="global_outline_generation",
        message="正在生成全书总纲。",
        novel=novel,
    )
    current_story_bible = deepcopy(novel.story_bible or current_story_bible)
    global_outline = generate_global_story_outline(payload, current_story_bible)
    current_story_bible["global_outline"] = global_outline
    novel = mark_bootstrap_progress(
        db,
        novel=novel,
        stage="title_generation",
        message="正在生成书名并校准作品包装信息。",
        story_bible=current_story_bible,
    )
    _emit_bootstrap_progress(
        progress_callback,
        stage="title_generation",
        message="正在生成书名并校准作品包装信息。",
        novel=novel,
    )
    title = generate_title(payload)
    novel = mark_bootstrap_progress(
        db,
        novel=novel,
        stage="arc_outline_generation",
        message="正在生成首个剧情弧与近期章节卡。",
        story_bible=current_story_bible,
        title=title,
    )

    _emit_bootstrap_progress(
        progress_callback,
        stage="arc_outline_generation",
        message="正在生成首个剧情弧与近期章节卡。",
        novel=novel,
        title=title,
    )

    first_arc = generate_arc_outline_bundle(
        payload=payload,
        story_bible=current_story_bible,
        global_outline=global_outline,
        start_chapter=1,
        end_chapter=current_story_bible["outline_engine"]["arc_outline_size"],
        arc_no=1,
        recent_summaries=[],
    )

    novel = mark_bootstrap_progress(
        db,
        novel=novel,
        stage="story_bible_finalize",
        message="正在整理 Story Bible、模板与长期状态。",
        story_bible=current_story_bible,
        title=title,
    )
    _emit_bootstrap_progress(
        progress_callback,
        stage="story_bible_finalize",
        message="正在整理 Story Bible、模板与长期状态。",
        novel=novel,
        title=title,
    )

    story_bible = build_story_bible(
        payload,
        title,
        global_outline,
        first_arc,
        story_engine_diagnosis=story_engine_diagnosis,
        story_strategy_card=story_strategy_card,
    )
    story_bible["story_engine_diagnosis"] = story_engine_diagnosis
    story_bible["story_strategy_card"] = story_strategy_card
    story_bible["global_outline"] = global_outline
    story_bible["active_arc"] = first_arc
    story_bible["pending_arc"] = None
    story_bible["outline_state"] = {
        "planned_until": first_arc["end_chapter"],
        "next_arc_no": 2,
        "bootstrap_generated_until": first_arc["end_chapter"],
    }
    story_bible = sync_story_bible_snapshot(novel=novel, story_bible=story_bible, chapters=[])
    result = mark_bootstrap_success(db, novel=novel, story_bible=story_bible, title=title)
    _emit_bootstrap_progress(
        progress_callback,
        stage="completed",
        message="初始化完成，可以开始生成章节。",
        status="completed",
        novel=result,
        title=title,
        extra={"percent": 100, "step_index": len(BOOTSTRAP_STAGE_DEFINITIONS), "step_total": len(BOOTSTRAP_STAGE_DEFINITIONS)},
    )
    return result


def bootstrap_novel(db: Session, *, payload: NovelCreate) -> Novel:
    novel = create_bootstrap_placeholder_novel(payload)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    try:
        return run_bootstrap_pipeline(db, novel=novel, payload=payload)
    except GenerationError as exc:
        db.rollback()
        novel = db.query(Novel).filter(Novel.id == novel.id).first() or novel
        mark_bootstrap_failure(db, novel=novel, exc=exc)
        raise


def retry_bootstrap_novel(db: Session, *, novel: Novel) -> Novel:
    payload = NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )
    try:
        return run_bootstrap_pipeline(db, novel=novel, payload=payload)
    except GenerationError as exc:
        db.rollback()
        novel = db.query(Novel).filter(Novel.id == novel.id).first() or novel
        mark_bootstrap_failure(db, novel=novel, exc=exc)
        raise


def sync_story_bible_snapshot(*, novel: Novel, story_bible: dict[str, Any], chapters: list[Any] | None = None) -> dict[str, Any]:
    return sync_long_term_state(ensure_story_architecture(deepcopy(story_bible or {}), novel), novel, chapters=chapters)
