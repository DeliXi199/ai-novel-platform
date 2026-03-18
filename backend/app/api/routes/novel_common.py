import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.schemas.chapter import ChapterDeleteTailRequest
from app.services.ai_capability_audit import build_story_bible_ai_audit
from app.services.async_tasks import list_active_tasks, list_recent_tasks, serialize_task
from app.services.chapter_generation_report import compact_generation_pipeline_report
from app.services.chapter_quality import build_quality_feedback
from app.services.generation_exceptions import GenerationError
from app.services.novel_lifecycle import BOOTSTRAP_STATUS_RUNNING, sync_story_bible_snapshot
from app.services.runtime_snapshot_cache import (
    build_runtime_snapshot_cache_key,
    get_runtime_snapshot,
    store_runtime_snapshot,
)
from app.services.story_architecture import build_story_workspace_snapshot
from app.services.story_state import get_chapter_card_queue, get_current_pipeline, get_live_runtime, get_planning_status




def _truncate_text(value: Any, limit: int = 72) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def _compact_value(value: Any, *, text_limit: int = 60) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, text_limit=text_limit) for item in value[:6]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 8:
                break
            compact[str(key)] = _compact_value(item, text_limit=text_limit)
        return compact
    return _truncate_text(value, text_limit)


def _safe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _compact_scene_handoff_card(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    compact = {
        "scene_status_at_end": _truncate_text(payload.get("scene_status_at_end"), 16),
        "must_continue_same_scene": bool(payload.get("must_continue_same_scene")),
        "allowed_transition": _truncate_text(payload.get("allowed_transition"), 16),
        "next_opening_anchor": _truncate_text(payload.get("next_opening_anchor"), 96),
        "final_scene_name": _truncate_text(payload.get("final_scene_name"), 24),
        "final_scene_role": _truncate_text(payload.get("final_scene_role"), 16),
        "carry_over_items": _safe_list(payload.get("carry_over_items"))[:4],
        "carry_over_people": _safe_list(payload.get("carry_over_people"))[:5],
        "unfinished_actions": _safe_list(payload.get("unfinished_actions"))[:4],
        "forbidden_openings": _safe_list(payload.get("forbidden_openings"))[:3],
        "handoff_note": _truncate_text(payload.get("handoff_note"), 96),
        "next_scene_candidates": [
            {
                "scene_template_id": _truncate_text(item.get("scene_template_id"), 32),
                "scene_name": _truncate_text(item.get("scene_name"), 24),
                "score": round(float(item.get("score", 0.0) or 0.0), 2),
                "reason": _truncate_text(item.get("reason"), 56),
            }
            for item in (payload.get("next_scene_candidates") or [])[:3]
            if isinstance(item, dict) and (item.get("scene_template_id") or item.get("scene_name"))
        ],
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_execution_packet(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    chapter_card = (payload.get("chapter_execution_card") or {}) if isinstance(payload.get("chapter_execution_card"), dict) else {}
    outline = payload.get("scene_outline") or payload.get("daily_workbench", {}).get("scene_sequence_plan") or []
    scene_outline = [
        {
            "scene_no": int(item.get("scene_no", index + 1) or (index + 1)),
            "scene_name": _truncate_text(item.get("scene_name"), 24),
            "scene_role": _truncate_text(item.get("scene_role"), 16),
            "purpose": _truncate_text(item.get("purpose"), 72),
        }
        for index, item in enumerate(outline[:3])
        if isinstance(item, dict)
    ] if isinstance(outline, list) else []
    compact = {
        "for_chapter_no": int(payload.get("for_chapter_no", 0) or 0),
        "packet_phase": _truncate_text(payload.get("packet_phase"), 24),
        "packet_label": _truncate_text(payload.get("packet_label"), 36),
        "chapter_function": _truncate_text(chapter_card.get("chapter_function"), 96),
        "opening": _truncate_text(chapter_card.get("opening"), 96),
        "middle": _truncate_text(chapter_card.get("middle"), 96),
        "ending": _truncate_text(chapter_card.get("ending"), 96),
        "scene_outline": scene_outline,
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}



def _compact_realized_scene_report(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    actual_slots = payload.get("actual_scene_slots") or []
    compact = {
        "chapter_no": int(payload.get("chapter_no", 0) or 0),
        "chapter_title": _truncate_text(payload.get("chapter_title"), 28),
        "event_summary": _truncate_text(payload.get("event_summary"), 120),
        "preview_lines": [_truncate_text(item, 120) for item in (payload.get("preview_lines") or [])[:6] if str(item or "").strip()],
        "actual_scene_slots": [
            {
                "slot": _truncate_text(item.get("slot"), 16),
                "planned": _truncate_text(item.get("planned"), 72),
                "actual": _truncate_text(item.get("actual"), 120),
            }
            for item in actual_slots[:3]
            if isinstance(item, dict)
        ],
        "new_clues": _safe_list(payload.get("new_clues"))[:3],
        "open_hooks": _safe_list(payload.get("open_hooks"))[:3],
        "closed_hooks": _safe_list(payload.get("closed_hooks"))[:3],
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_generation_report_payload(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    payload = story_bible or {}
    workspace_state = payload.get("story_workspace") or {}
    report = workspace_state.get("last_generation_report") if isinstance(workspace_state.get("last_generation_report"), dict) else {}
    compact = compact_generation_pipeline_report(report)
    history_rows = workspace_state.get("generation_report_history") or []
    if isinstance(history_rows, list):
        compact["history"] = [
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "chapter_title": _truncate_text(item.get("chapter_title"), 24),
                "final_title": _truncate_text(item.get("final_title"), 24),
                "delivery_level": _truncate_text(item.get("delivery_level"), 12),
                "duration_ms": int(item.get("duration_ms", 0) or 0),
                "llm_calls": int(item.get("llm_calls", 0) or 0),
                "delivery_score": int(item.get("delivery_score", 0) or 0),
            }
            for item in history_rows[-5:]
            if isinstance(item, dict)
        ]
        compact = compact_generation_pipeline_report({**report, "history": history_rows, "trends": report.get("trends")})
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_scene_debug_payload(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    payload = story_bible or {}
    workflow_state = payload.get("workflow_state") or {}
    live_runtime = workflow_state.get("live_runtime") or {}
    pipeline = workflow_state.get("current_pipeline") or {}
    workspace_state = payload.get("story_workspace") or {}
    target_chapter_no = int(live_runtime.get("target_chapter_no") or pipeline.get("target_chapter_no") or workspace_state.get("entry_target_chapter_no") or 0)
    current_packet = workspace_state.get("current_execution_packet") if isinstance(workspace_state.get("current_execution_packet"), dict) else {}
    if not current_packet and isinstance(workspace_state.get("next_chapter_preview_packet"), dict):
        current_packet = workspace_state.get("next_chapter_preview_packet") or {}
    current_target = int(current_packet.get("for_chapter_no", 0) or 0)
    planning_packet = current_packet if current_packet and (not target_chapter_no or current_target in {0, target_chapter_no}) else {}
    last_completed_packet = workspace_state.get("last_completed_execution_packet") if isinstance(workspace_state.get("last_completed_execution_packet"), dict) else {}
    realized_report = workspace_state.get("last_generated_scene_report") if isinstance(workspace_state.get("last_generated_scene_report"), dict) else {}
    serial_runtime = payload.get("serial_runtime") or {}
    previous_bridge = serial_runtime.get("previous_chapter_bridge") or {}
    handoff = previous_bridge.get("scene_handoff_card") if isinstance(previous_bridge, dict) else {}

    scene_outline = []
    raw_outline = planning_packet.get("scene_outline") or planning_packet.get("daily_workbench", {}).get("scene_sequence_plan") or []
    if isinstance(raw_outline, list):
        scene_outline = [
            {
                "scene_no": int(item.get("scene_no", index + 1) or (index + 1)),
                "scene_name": _truncate_text(item.get("scene_name"), 24),
                "scene_role": _truncate_text(item.get("scene_role"), 16),
                "purpose": _truncate_text(item.get("purpose"), 72),
                "target_result": _truncate_text(item.get("target_result"), 56),
                "transition_in": _truncate_text(item.get("transition_in"), 40),
                "must_carry_over": _safe_list(item.get("must_carry_over"))[:3],
            }
            for index, item in enumerate(raw_outline[:3])
            if isinstance(item, dict)
        ]

    scene_execution = planning_packet.get("scene_execution_card") or {}
    compact_scene_execution = {
        "scene_count": int(scene_execution.get("scene_count", len(scene_outline)) or len(scene_outline) or 0),
        "scene_transition_mode": _truncate_text(scene_execution.get("scene_transition_mode") or scene_execution.get("transition_mode"), 20),
        "must_continue_same_scene": bool(scene_execution.get("must_continue_same_scene")),
        "scene_opening_anchor": _truncate_text(scene_execution.get("scene_opening_anchor") or scene_execution.get("opening_anchor"), 96),
        "scene_first_focus": _truncate_text(scene_execution.get("scene_first_focus") or scene_execution.get("first_scene_focus"), 56),
        "scene_must_carry_over": _safe_list(scene_execution.get("scene_must_carry_over") or scene_execution.get("must_carry_over"))[:4],
        "scene_sequence_note": _truncate_text(scene_execution.get("scene_sequence_note") or scene_execution.get("sequence_note"), 96),
    }
    compact_scene_execution = {key: value for key, value in compact_scene_execution.items() if value not in (None, "", [], {})}

    details = live_runtime.get("last_error_details") if isinstance(live_runtime.get("last_error_details"), dict) else {}
    quality_feedback = details.get("quality_feedback") if isinstance(details.get("quality_feedback"), dict) else {}
    continuity_issue = str(details.get("scene_continuity_issue") or quality_feedback.get("metrics", {}).get("scene_continuity_issue") or "").strip()
    continuity_diagnostic = {
        "status": "issue" if continuity_issue else ("idle" if not compact_scene_execution and not handoff else "ok"),
        "issue": continuity_issue or None,
        "message": _truncate_text(quality_feedback.get("display_message") or quality_feedback.get("message") or live_runtime.get("last_error_message"), 120) if continuity_issue else "",
        "failed_stage": _truncate_text(live_runtime.get("failed_stage"), 24) if continuity_issue else "",
        "updated_at": live_runtime.get("updated_at") if continuity_issue else None,
        "retry_feedback": _compact_value(live_runtime.get("retry_feedback") or {}, text_limit=56) if continuity_issue else {},
    }
    continuity_diagnostic = {key: value for key, value in continuity_diagnostic.items() if value not in (None, "", [], {})}

    compact = {
        "packet_target_chapter_no": target_chapter_no,
        "planning_packet": _compact_execution_packet(planning_packet),
        "last_completed_packet": _compact_execution_packet(last_completed_packet),
        "realized_scene_report": _compact_realized_scene_report(realized_report),
        "scene_execution_card": compact_scene_execution,
        "scene_outline": scene_outline,
        "scene_handoff_card": _compact_scene_handoff_card(handoff if isinstance(handoff, dict) else {}),
        "continuity_diagnostic": continuity_diagnostic,
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}

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
    snapshot = build_story_workspace_snapshot(snapshot_novel(novel, story_bible=synced_story_bible))
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


def build_story_studio_payload(db: Session, novel: Novel, *, desired_chapter_no: int | None = None) -> dict:
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
    ai_policy_audit = build_story_bible_ai_audit(synced_story_bible)
    return {
        "novel": novel,
        "chapters": {
            "novel_id": novel.id,
            "total": len(chapters),
            "items": _chapter_list_items(chapters),
        },
        "story_workspace": snapshot,
        "planning_data": {
            "novel_id": novel.id,
            "current_chapter_no": novel.current_chapter_no,
            "planning_layers": snapshot.get("planning_layers", {}),
            "planning_state": snapshot.get("planning_state", {}),
            "planning_status": snapshot.get("story_workspace", {}).get("planning_status", {}),
            "chapter_card_queue": snapshot.get("story_workspace", {}).get("chapter_card_queue", []),
            "scene_debug": _compact_scene_debug_payload(synced_story_bible),
            "generation_report": _compact_generation_report_payload(synced_story_bible),
            "ai_policy_audit": ai_policy_audit,
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
    ai_policy_audit = build_story_bible_ai_audit(story_bible)
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
        "ai_policy_audit": ai_policy_audit,
        "scene_debug": _compact_scene_debug_payload(story_bible),
        "generation_report": _compact_generation_report_payload(story_bible),
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
                "progress_kind": item.get("progress_kind"),
                "payoff_or_pressure": item.get("payoff_or_pressure"),
                "payoff_mode": item.get("payoff_mode"),
                "payoff_compensation_note": (item.get("payoff_compensation") or {}).get("note"),
                "payoff_compensation_priority": (item.get("payoff_compensation") or {}).get("priority"),
                "payoff_window_bias": item.get("payoff_window_bias") or (item.get("payoff_compensation") or {}).get("window_role"),
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
