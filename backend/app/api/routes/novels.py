import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db.session import SessionLocal, get_db
from app.models.chapter import Chapter
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.schemas.chapter import (
    ChapterBatchGenerateRequest,
    ChapterBatchResponse,
    ChapterDeleteTailRequest,
    ChapterDeleteTailResponse,
    ChapterListResponse,
    ChapterResponse,
)
from app.schemas.control_console import ControlConsoleResponse
from app.schemas.intervention import InterventionCreate, InterventionListResponse, InterventionResponse
from app.schemas.novel import NovelCreate, NovelDeleteResponse, NovelListResponse, NovelResponse
from app.services.chapter_generation import (
    generate_next_chapter,
    generate_next_chapters_batch,
    parse_reader_instruction,
    prepare_next_planning_window,
)
from app.services.export_service import export_novel_bytes
from app.services.generation_exceptions import GenerationError
from app.services.novel_bootstrap import (
    build_base_story_bible,
    build_story_bible,
    generate_arc_outline_bundle,
    generate_global_story_outline,
    generate_title,
)
from app.services.story_architecture import build_control_console_snapshot

router = APIRouter(prefix="/novels", tags=["novels"])


def _raise_http_from_generation_error(exc: GenerationError) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail={
            "code": exc.code,
            "stage": exc.stage,
            "message": exc.message,
            "retryable": exc.retryable,
            "provider": exc.provider,
            "details": exc.details or {},
        },
    )


def _batch_payload(chapters: list[Chapter], requested_count: int, started_from_chapter: int, progress: list[dict]) -> dict:
    return {
        "novel_id": chapters[0].novel_id if chapters else None,
        "requested_count": requested_count,
        "generated_count": len(chapters),
        "started_from_chapter": started_from_chapter,
        "ended_at_chapter": chapters[-1].chapter_no if chapters else None,
        "chapters": chapters,
        "progress": progress,
    }


def _require_novel(db: Session, novel_id: int) -> Novel:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


def _chapter_preview(text: str, limit: int = 70) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "…"


def _resolve_tail_chapters_to_delete(novel: Novel, db: Session, payload: ChapterDeleteTailRequest) -> list[Chapter]:
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
    return deleted


@router.get("", response_model=NovelListResponse)
def list_novels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="按书名/题材/主角关键词过滤"),
    db: Session = Depends(get_db),
):
    query = db.query(Novel)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            Novel.title.ilike(pattern) | Novel.genre.ilike(pattern) | Novel.protagonist_name.ilike(pattern)
        )
    total = query.with_entities(func.count(Novel.id)).scalar() or 0
    items = query.order_by(Novel.updated_at.desc(), Novel.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.post("", response_model=NovelResponse, status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelCreate, db: Session = Depends(get_db)):
    try:
        title = generate_title(payload)
        base_story_bible = build_base_story_bible(payload)

        global_outline = generate_global_story_outline(payload, base_story_bible)
        base_story_bible["global_outline"] = global_outline

        first_arc = generate_arc_outline_bundle(
            payload=payload,
            story_bible=base_story_bible,
            global_outline=global_outline,
            start_chapter=1,
            end_chapter=base_story_bible["outline_engine"]["arc_outline_size"],
            arc_no=1,
            recent_summaries=[],
        )

        story_bible = build_story_bible(payload, title, global_outline, first_arc)
        story_bible["global_outline"] = global_outline
        story_bible["active_arc"] = first_arc
        story_bible["pending_arc"] = None
        story_bible["outline_state"] = {
            "planned_until": first_arc["end_chapter"],
            "next_arc_no": 2,
            "bootstrap_generated_until": first_arc["end_chapter"],
        }

        novel = Novel(
            title=title,
            genre=payload.genre,
            premise=payload.premise,
            protagonist_name=payload.protagonist_name,
            style_preferences=payload.style_preferences,
            story_bible=story_bible,
            current_chapter_no=0,
            status="planning_ready",
        )
        db.add(novel)
        db.commit()
        db.refresh(novel)
        return novel
    except GenerationError as exc:
        db.rollback()
        _raise_http_from_generation_error(exc)


@router.get("/{novel_id}", response_model=NovelResponse)
def get_novel(novel_id: int, db: Session = Depends(get_db)):
    return _require_novel(db, novel_id)


@router.delete("/{novel_id}", response_model=NovelDeleteResponse)
def delete_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)
    if novel.status == "generating":
        raise HTTPException(status_code=409, detail="当前小说正在生成中，不能删除整本书")
    deleted_novel_id = novel.id
    deleted_title = novel.title
    deleted_chapter_count = len(novel.chapters)
    db.delete(novel)
    db.commit()
    return {
        "deleted_novel_id": deleted_novel_id,
        "deleted_title": deleted_title,
        "deleted_chapter_count": deleted_chapter_count,
    }


@router.get("/{novel_id}/planning-state")
def get_planning_state(novel_id: int, db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)
    snapshot = build_control_console_snapshot(novel)
    return {
        "novel_id": novel.id,
        "current_chapter_no": novel.current_chapter_no,
        "planning_layers": snapshot.get("planning_layers", {}),
        "planning_state": snapshot.get("planning_state", {}),
        "planning_status": snapshot.get("control_console", {}).get("planning_status", {}),
        "chapter_card_queue": snapshot.get("control_console", {}).get("chapter_card_queue", []),
    }


@router.post("/{novel_id}/prepare-next-window")
def create_next_planning_window(novel_id: int, force: bool = Query(False), db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)
    try:
        return prepare_next_planning_window(db, novel, force=force)
    except GenerationError as exc:
        db.rollback()
        _raise_http_from_generation_error(exc)


@router.get("/{novel_id}/control-console", response_model=ControlConsoleResponse)
def get_control_console(novel_id: int, db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)
    return build_control_console_snapshot(novel)


@router.get("/{novel_id}/chapters", response_model=ChapterListResponse)
def list_chapters(novel_id: int, db: Session = Depends(get_db)):
    _require_novel(db, novel_id)
    items = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.asc())
        .all()
    )
    return {
        "novel_id": novel_id,
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "chapter_no": item.chapter_no,
                "title": item.title,
                "content_preview": _chapter_preview(item.content),
                "char_count": len(item.content or ""),
                "created_at": item.created_at,
            }
            for item in items
        ],
    }


@router.post("/{novel_id}/chapters/delete-tail", response_model=ChapterDeleteTailResponse)
def delete_tail_chapters(novel_id: int, payload: ChapterDeleteTailRequest, db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)
    deleted_chapters = _resolve_tail_chapters_to_delete(novel, db, payload)
    deleted_nos = [chapter.chapter_no for chapter in deleted_chapters]
    deleted_titles = [chapter.title for chapter in deleted_chapters]
    deleted_no_set = set(deleted_nos)
    remaining_chapter_no = max(
        (chapter.chapter_no for chapter in db.query(Chapter).filter(Chapter.novel_id == novel.id).all() if chapter.chapter_no not in deleted_no_set),
        default=0,
    )

    for chapter in deleted_chapters:
        db.delete(chapter)

    novel.current_chapter_no = remaining_chapter_no
    if isinstance(novel.story_bible, dict):
        workflow_state = novel.story_bible.setdefault("workflow_state", {})
        workflow_state["last_deleted_chapter_nos"] = deleted_nos
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return {
        "novel_id": novel.id,
        "deleted_count": len(deleted_nos),
        "deleted_chapter_nos": deleted_nos,
        "deleted_titles": deleted_titles,
        "current_chapter_no": novel.current_chapter_no,
    }


@router.get("/{novel_id}/chapters/{chapter_no}", response_model=ChapterResponse)
def get_chapter(novel_id: int, chapter_no: int, db: Session = Depends(get_db)):
    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_no == chapter_no)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.get("/{novel_id}/export")
def export_novel(
    novel_id: int,
    export_format: str = Query("txt", alias="format", pattern="^(txt|md|docx|pdf)$"),
    db: Session = Depends(get_db),
):
    buffer, filename, media_type = export_novel_bytes(db, novel_id, export_format)

    ascii_fallback = f"novel_{novel_id}.{export_format}"
    quoted_filename = quote(filename)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_fallback}"; ' f"filename*=UTF-8''{quoted_filename}"
        )
    }
    return StreamingResponse(buffer, media_type=media_type, headers=headers)


@router.get("/{novel_id}/interventions", response_model=InterventionListResponse)
def list_interventions(novel_id: int, db: Session = Depends(get_db)):
    _require_novel(db, novel_id)
    items = (
        db.query(Intervention)
        .filter(Intervention.novel_id == novel_id)
        .order_by(Intervention.created_at.desc(), Intervention.id.desc())
        .all()
    )
    return {"novel_id": novel_id, "total": len(items), "items": items}


@router.post("/{novel_id}/interventions", response_model=InterventionResponse, status_code=status.HTTP_201_CREATED)
def create_intervention(novel_id: int, payload: InterventionCreate, db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)

    parsed = parse_reader_instruction(payload.raw_instruction)
    intervention = Intervention(
        novel_id=novel_id,
        chapter_no=payload.chapter_no,
        raw_instruction=payload.raw_instruction,
        parsed_constraints=parsed,
        effective_chapter_span=payload.effective_chapter_span,
    )
    db.add(intervention)
    db.commit()
    db.refresh(intervention)
    return intervention


@router.post("/{novel_id}/next-chapter", response_model=ChapterResponse)
def create_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    novel = _require_novel(db, novel_id)

    try:
        chapter = generate_next_chapter(db, novel)
        return chapter
    except GenerationError as exc:
        db.rollback()
        _raise_http_from_generation_error(exc)


@router.post("/{novel_id}/next-chapters", response_model=ChapterBatchResponse)
def create_next_chapters(novel_id: int, payload: ChapterBatchGenerateRequest, db: Session = Depends(get_db)):
    _require_novel(db, novel_id)
    novel = _require_novel(db, novel_id)

    progress: list[dict] = []
    started_from = novel.current_chapter_no + 1

    def _progress(event: dict) -> None:
        progress.append(event)

    try:
        chapters = generate_next_chapters_batch(db, novel_id=novel_id, count=payload.count, progress_callback=_progress)
        return _batch_payload(chapters, payload.count, started_from, progress)
    except GenerationError as exc:
        db.rollback()
        _raise_http_from_generation_error(exc)


@router.post("/{novel_id}/next-chapters/stream")
def stream_next_chapters(novel_id: int, payload: ChapterBatchGenerateRequest):
    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def event_stream():
        db = SessionLocal()
        try:
            novel = db.query(Novel).filter(Novel.id == novel_id).first()
            if not novel:
                yield _sse("error", {"code": "NOVEL_NOT_FOUND", "message": "Novel not found", "novel_id": novel_id})
                return

            total = payload.count
            started_from = novel.current_chapter_no + 1
            yield _sse(
                "batch_started",
                {
                    "novel_id": novel_id,
                    "requested_count": total,
                    "started_from_chapter": started_from,
                    "message": f"准备连续生成 {total} 章",
                },
            )

            generated_titles: list[str] = []
            for index in range(total):
                novel = db.query(Novel).filter(Novel.id == novel_id).first()
                if not novel:
                    yield _sse("error", {"code": "NOVEL_NOT_FOUND", "message": "Novel not found", "novel_id": novel_id})
                    return
                next_no = novel.current_chapter_no + 1
                yield _sse(
                    "chapter_started",
                    {
                        "novel_id": novel_id,
                        "index": index + 1,
                        "total": total,
                        "chapter_no": next_no,
                        "message": f"开始生成第 {next_no} 章（{index + 1}/{total}）",
                    },
                )
                try:
                    chapter = generate_next_chapter(db, novel)
                except GenerationError as exc:
                    db.rollback()
                    yield _sse(
                        "error",
                        {
                            "code": exc.code,
                            "stage": exc.stage,
                            "message": exc.message,
                            "retryable": exc.retryable,
                            "provider": exc.provider,
                            "details": exc.details or {},
                            "novel_id": novel_id,
                            "index": index + 1,
                            "total": total,
                            "chapter_no": next_no,
                        },
                    )
                    return
                generated_titles.append(chapter.title)
                yield _sse(
                    "chapter_succeeded",
                    {
                        "novel_id": novel_id,
                        "index": index + 1,
                        "total": total,
                        "chapter_no": chapter.chapter_no,
                        "title": chapter.title,
                        "message": f"第 {chapter.chapter_no} 章生成完成：{chapter.title}",
                    },
                )

            final_novel = db.query(Novel).filter(Novel.id == novel_id).first()
            yield _sse(
                "completed",
                {
                    "novel_id": novel_id,
                    "requested_count": total,
                    "generated_count": len(generated_titles),
                    "started_from_chapter": started_from,
                    "ended_at_chapter": final_novel.current_chapter_no if final_novel else None,
                    "titles": generated_titles,
                },
            )
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
