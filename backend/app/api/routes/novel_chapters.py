from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db.session import create_session, get_db
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.schemas.chapter import (
    ChapterBatchGenerateRequest,
    ChapterBatchResponse,
    ChapterDeleteTailRequest,
    ChapterDeleteTailResponse,
    ChapterListResponse,
    ChapterPublishBatchRequest,
    ChapterPublishBatchResponse,
    ChapterResponse,
    ChapterTtsGenerateRequest,
    ChapterTtsStatusResponse,
)
from app.services.chapter_generation import generate_next_chapter, generate_next_chapters_batch
from app.services.edge_tts_service import (
    EdgeTtsBadRequestError,
    EdgeTtsBusyError,
    EdgeTtsError,
    EdgeTtsUnavailableError,
    generate_chapter_tts,
    get_chapter_tts_status,
)
from app.services.export_service import export_novel_bytes
from app.services.generation_exceptions import GenerationError
from app.services.hard_fact_guard import validate_and_register_chapter
from app.services.novel_lifecycle import BOOTSTRAP_STATUS_RUNNING, sync_story_bible_snapshot
from app.services.story_architecture import promote_stock_fact_entries

from .novel_common import (
    batch_payload,
    chapter_preview,
    ensure_bootstrap_not_running,
    raise_http_from_generation_error,
    require_novel,
    resolve_tail_chapters_to_delete,
    sse_payload,
    sync_novel_serial_layers,
)

router = APIRouter(prefix="/novels", tags=["novels"])


def _require_chapter(db: Session, novel_id: int, chapter_no: int) -> Chapter:
    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_no == chapter_no)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter



@router.get("/{novel_id}/chapters", response_model=ChapterListResponse)
def list_chapters(novel_id: int, db: Session = Depends(get_db)):
    require_novel(db, novel_id)
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
                "content_preview": chapter_preview(item.content),
                "char_count": len(item.content or ""),
                "serial_stage": item.serial_stage,
                "is_published": item.is_published,
                "locked_from_edit": item.locked_from_edit,
                "published_at": item.published_at,
                "created_at": item.created_at,
            }
            for item in items
        ],
    }


@router.post("/{novel_id}/chapters/publish-batch", response_model=ChapterPublishBatchResponse)
def publish_stock_chapters(novel_id: int, payload: ChapterPublishBatchRequest, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="发布章节")
    if novel.status == "generating":
        raise HTTPException(status_code=409, detail="当前小说正在生成中，不能执行发布操作")

    chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_no.asc())
        .all()
    )
    unpublished = [chapter for chapter in chapters if not chapter.is_published]
    if not unpublished:
        raise HTTPException(status_code=400, detail="当前没有库存章节可发布")

    target = unpublished[: payload.count]
    expected = list(range(target[0].chapter_no, target[0].chapter_no + len(target)))
    actual = [chapter.chapter_no for chapter in target]
    if actual != expected:
        raise HTTPException(status_code=409, detail="库存章节必须按顺序连续发布，中间不能跳章")

    temp_story_bible = sync_story_bible_snapshot(novel=novel, story_bible=novel.story_bible or {}, chapters=chapters)
    published_nos: list[int] = []
    published_titles: list[str] = []

    for chapter in target:
        meta = chapter.generation_meta or {}
        plan = meta.get("chapter_plan") if isinstance(meta, dict) else {}
        summary_text = ((meta.get("summary") or {}) if isinstance(meta, dict) else {}).get("event_summary")
        try:
            temp_story_bible, hard_facts, hard_fact_report = validate_and_register_chapter(
                temp_story_bible,
                protagonist_name=novel.protagonist_name,
                chapter_no=chapter.chapter_no,
                chapter_title=chapter.title,
                content=chapter.content,
                plan=plan if isinstance(plan, dict) else None,
                summary=summary_text,
                serial_stage="published",
                reference_mode="published",
                raise_on_conflict=True,
            )
        except Exception as exc:
            if isinstance(exc, GenerationError):
                raise
            from app.services.hard_fact_guard import HardFactConflict

            if isinstance(exc, HardFactConflict):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CHAPTER_HARD_FACT_CONFLICT",
                        "message": f"第 {chapter.chapter_no} 章与已发布硬事实冲突，不能发布。",
                        "details": exc.report,
                    },
                )
            raise

        chapter.serial_stage = "published"
        chapter.is_published = True
        chapter.locked_from_edit = True
        chapter.published_at = chapter.published_at or chapter.created_at
        meta = chapter.generation_meta or {}
        meta["serial_delivery"] = {
            **(meta.get("serial_delivery") or {}),
            "delivery_mode": "stockpile",
            "serial_stage": "published",
            "is_published": True,
            "locked_from_edit": True,
            "published_at": chapter.published_at.isoformat(timespec="seconds") + "Z" if chapter.published_at else None,
        }
        meta["hard_fact_report"] = {**hard_fact_report, "facts": hard_facts}
        chapter.generation_meta = meta
        db.add(chapter)
        published_nos.append(chapter.chapter_no)
        published_titles.append(chapter.title)

    story_bible = promote_stock_fact_entries(temp_story_bible, published_nos)
    runtime = story_bible.setdefault("serial_runtime", {})
    runtime["last_publish_action"] = {
        "published_chapter_nos": published_nos,
        "delivery_mode": runtime.get("delivery_mode", "stockpile"),
    }
    novel.story_bible = story_bible
    novel = sync_novel_serial_layers(db, novel, persist=True)
    db.commit()
    db.refresh(novel)
    published_through = int(
        (((((novel.story_bible or {}).get("long_term_state") or {}).get("chapter_release_state") or {}).get("published_through", 0)) or 0)
    )
    return {
        "novel_id": novel.id,
        "published_count": len(published_nos),
        "published_chapter_nos": published_nos,
        "published_titles": published_titles,
        "published_through": published_through,
        "delivery_mode": ((novel.story_bible or {}).get("serial_runtime") or {}).get("delivery_mode", "stockpile"),
    }


@router.post("/{novel_id}/chapters/delete-tail", response_model=ChapterDeleteTailResponse)
def delete_tail_chapters(novel_id: int, payload: ChapterDeleteTailRequest, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="删稿")
    deleted_chapters = resolve_tail_chapters_to_delete(novel, db, payload)
    deleted_nos = [chapter.chapter_no for chapter in deleted_chapters]
    deleted_titles = [chapter.title for chapter in deleted_chapters]
    deleted_no_set = set(deleted_nos)
    remaining_chapter_no = max(
        (
            chapter.chapter_no
            for chapter in db.query(Chapter).filter(Chapter.novel_id == novel.id).all()
            if chapter.chapter_no not in deleted_no_set
        ),
        default=0,
    )

    for chapter in deleted_chapters:
        db.delete(chapter)

    novel.current_chapter_no = remaining_chapter_no
    if isinstance(novel.story_bible, dict):
        workflow_state = novel.story_bible.setdefault("workflow_state", {})
        workflow_state["last_deleted_chapter_nos"] = deleted_nos
    novel = sync_novel_serial_layers(db, novel, persist=True)
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
    return _require_chapter(db, novel_id, chapter_no)




@router.get("/{novel_id}/chapters/{chapter_no}/tts", response_model=ChapterTtsStatusResponse)
def get_chapter_tts(
    novel_id: int,
    chapter_no: int,
    voice: str | None = Query(None),
    db: Session = Depends(get_db),
):
    chapter = _require_chapter(db, novel_id, chapter_no)
    return get_chapter_tts_status(chapter, {"voice": voice} if voice else None)


@router.post("/{novel_id}/chapters/{chapter_no}/tts/generate", response_model=ChapterTtsStatusResponse)
def generate_chapter_tts_audio(
    novel_id: int,
    chapter_no: int,
    payload: ChapterTtsGenerateRequest,
    db: Session = Depends(get_db),
):
    chapter = _require_chapter(db, novel_id, chapter_no)
    try:
        status = generate_chapter_tts(
            chapter,
            {
                "voice": payload.voice,
                "rate": payload.rate,
                "volume": payload.volume,
                "pitch": payload.pitch,
            },
            force_regenerate=payload.force_regenerate,
        )
    except EdgeTtsUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EdgeTtsBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except EdgeTtsBadRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EdgeTtsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return status


@router.get("/{novel_id}/export")
def export_novel(
    novel_id: int,
    export_format: str = Query("txt", alias="format", pattern="^(txt|md|docx|pdf)$"),
    db: Session = Depends(get_db),
):
    ensure_bootstrap_not_running(require_novel(db, novel_id), action="导出")
    buffer, filename, media_type = export_novel_bytes(db, novel_id, export_format)

    ascii_fallback = f"novel_{novel_id}.{export_format}"
    quoted_filename = quote(filename)
    headers = {
        "Content-Disposition": f'attachment; filename="{ascii_fallback}"; ' f"filename*=UTF-8''{quoted_filename}"
    }
    return StreamingResponse(buffer, media_type=media_type, headers=headers)


@router.post("/{novel_id}/next-chapter", response_model=ChapterResponse)
def create_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="生成章节")

    try:
        chapter = generate_next_chapter(db, novel)
        return chapter
    except GenerationError as exc:
        db.rollback()
        raise_http_from_generation_error(exc)


@router.post("/{novel_id}/next-chapters", response_model=ChapterBatchResponse)
def create_next_chapters(novel_id: int, payload: ChapterBatchGenerateRequest, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="批量生成章节")

    progress: list[dict] = []
    started_from = novel.current_chapter_no + 1

    def _progress(event: dict) -> None:
        progress.append(event)

    try:
        chapters = generate_next_chapters_batch(db, novel_id=novel_id, count=payload.count, progress_callback=_progress)
        return batch_payload(chapters, payload.count, started_from, progress)
    except GenerationError as exc:
        db.rollback()
        raise_http_from_generation_error(exc)


@router.post("/{novel_id}/next-chapters/stream")
def stream_next_chapters(novel_id: int, payload: ChapterBatchGenerateRequest):
    def event_stream():
        db = create_session()
        try:
            novel = db.query(Novel).filter(Novel.id == novel_id).first()
            if not novel:
                yield sse_payload("error", {"code": "NOVEL_NOT_FOUND", "message": "Novel not found", "novel_id": novel_id})
                return
            if novel.status == BOOTSTRAP_STATUS_RUNNING:
                yield sse_payload(
                    "error", {"code": "BOOTSTRAP_RUNNING", "message": "Novel bootstrap still running", "novel_id": novel_id}
                )
                return

            total = payload.count
            started_from = novel.current_chapter_no + 1
            yield sse_payload(
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
                    yield sse_payload("error", {"code": "NOVEL_NOT_FOUND", "message": "Novel not found", "novel_id": novel_id})
                    return
                next_no = novel.current_chapter_no + 1
                yield sse_payload(
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
                    yield sse_payload(
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
                yield sse_payload(
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
            yield sse_payload(
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
