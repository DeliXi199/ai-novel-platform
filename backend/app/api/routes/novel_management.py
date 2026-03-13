from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.novel import Novel
from app.schemas.novel import NovelCreate, NovelDeleteResponse, NovelListResponse, NovelResponse
from app.services.generation_exceptions import GenerationError
from app.services.novel_lifecycle import (
    BOOTSTRAP_STATUS_FAILED,
    BOOTSTRAP_STATUS_RUNNING,
    bootstrap_novel,
    build_bootstrap_error_detail,
    retry_bootstrap_novel,
)

from .novel_common import require_novel, raise_http_from_generation_error

router = APIRouter(prefix="/novels", tags=["novels"])


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
        return bootstrap_novel(db, payload=payload)
    except GenerationError as exc:
        novel_id = None
        try:
            latest = (
                db.query(Novel)
                .filter(
                    Novel.genre == payload.genre,
                    Novel.premise == payload.premise,
                    Novel.protagonist_name == payload.protagonist_name,
                )
                .order_by(Novel.id.desc())
                .first()
            )
            if latest:
                novel_id = latest.id
                raise HTTPException(
                    status_code=exc.http_status,
                    detail={**build_bootstrap_error_detail(latest, exc), "novel_id": novel_id},
                )
        except HTTPException:
            raise
        db.rollback()
        raise_http_from_generation_error(exc)


@router.post("/{novel_id}/bootstrap/retry", response_model=NovelResponse)
def retry_novel_bootstrap(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    if novel.current_chapter_no > 0:
        raise HTTPException(status_code=409, detail="这本小说已经开始生成章节，不需要重新初始化。")
    if novel.status not in {BOOTSTRAP_STATUS_FAILED, BOOTSTRAP_STATUS_RUNNING}:
        raise HTTPException(status_code=409, detail="当前状态无需重试初始化。")
    try:
        return retry_bootstrap_novel(db, novel=novel)
    except GenerationError as exc:
        latest = require_novel(db, novel_id)
        raise HTTPException(status_code=exc.http_status, detail=build_bootstrap_error_detail(latest, exc))


@router.get("/{novel_id}", response_model=NovelResponse)
def get_novel(novel_id: int, db: Session = Depends(get_db)):
    return require_novel(db, novel_id)


@router.delete("/{novel_id}", response_model=NovelDeleteResponse)
def delete_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
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
