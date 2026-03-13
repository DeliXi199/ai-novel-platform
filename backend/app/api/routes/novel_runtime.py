from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chapter import SerialModeResponse, SerialModeUpdateRequest
from app.schemas.control_console import ControlConsoleResponse
from app.services.chapter_generation import prepare_next_planning_window
from app.services.generation_exceptions import GenerationError
from app.services.story_architecture import ensure_story_architecture, set_delivery_mode, sync_long_term_state
from app.services.story_state import ensure_serial_runtime

from .novel_common import (
    build_fresh_snapshot,
    build_live_runtime_payload,
    ensure_bootstrap_not_running,
    raise_http_from_generation_error,
    require_novel,
    sync_novel_serial_layers,
)

router = APIRouter(prefix="/novels", tags=["novels"])


@router.get("/{novel_id}/planning-state")
def get_planning_state(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
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


@router.get("/{novel_id}/control-console", response_model=ControlConsoleResponse)
def get_control_console(novel_id: int, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    _, snapshot = build_fresh_snapshot(db, novel)
    return snapshot


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
