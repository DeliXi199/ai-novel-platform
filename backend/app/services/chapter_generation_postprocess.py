from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.services.chapter_generation_support import _compact_value, _truncate_text
from app.services.payoff_compensation_support import _text, apply_payoff_window_event_bias_to_plan
from app.services.story_architecture import ensure_story_architecture, sync_long_term_state


def runtime_stage_casting_extra(execution_brief: dict[str, Any] | None) -> dict[str, Any]:
    daily = (execution_brief or {}).get("daily_workbench") or {}
    runtime = daily.get("chapter_stage_casting_runtime") or {}
    return {
        "stage_casting_runtime": _compact_value(runtime, text_limit=72),
        "stage_casting_runtime_note": _truncate_text(daily.get("chapter_stage_casting_runtime_note"), 96),
        "stage_casting_display_lines": _compact_value(runtime.get("display_lines") or [], text_limit=72),
    }



def runtime_payoff_extra(execution_brief: dict[str, Any] | None) -> dict[str, Any]:
    chapter_card = (execution_brief or {}).get("chapter_execution_card") or {}
    daily = (execution_brief or {}).get("daily_workbench") or {}
    diagnostics = (daily.get("payoff_diagnostics") or chapter_card.get("payoff_diagnostics") or {}) if isinstance(daily, dict) else {}
    summary_lines = diagnostics.get("summary_lines") or []
    return {
        "selected_payoff_card_id": _truncate_text(chapter_card.get("payoff_card_id") or chapter_card.get("payoff_mode"), 48),
        "payoff_mode": _truncate_text(chapter_card.get("payoff_mode"), 32),
        "payoff_level": _truncate_text(chapter_card.get("payoff_level"), 16),
        "payoff_visibility": _truncate_text(chapter_card.get("payoff_visibility"), 20),
        "reader_payoff": _truncate_text(chapter_card.get("reader_payoff"), 96),
        "new_pressure": _truncate_text(chapter_card.get("new_pressure"), 96),
        "payoff_debt_score": diagnostics.get("pressure_debt_score"),
        "payoff_debt_level": diagnostics.get("pressure_debt_level"),
        "payoff_repeat_risk": diagnostics.get("repeat_risk"),
        "payoff_recommended_level": diagnostics.get("recommended_level"),
        "payoff_runtime_note": _truncate_text(daily.get("payoff_runtime_note") or (summary_lines[2] if len(summary_lines) >= 3 else ""), 96),
        "payoff_summary_lines": _compact_value(summary_lines[:4], text_limit=72),
    }



def runtime_payoff_delivery_extra(payoff_delivery: dict[str, Any] | None) -> dict[str, Any]:
    delivery = payoff_delivery or {}
    summary_lines = delivery.get("summary_lines") or []
    return {
        "payoff_delivery_score": delivery.get("delivery_score"),
        "payoff_delivery_level": _truncate_text(delivery.get("delivery_level"), 16),
        "payoff_delivery_verdict": _truncate_text(delivery.get("verdict"), 32),
        "payoff_delivery_note": _truncate_text(delivery.get("runtime_note") or (summary_lines[2] if len(summary_lines) >= 3 else ""), 96),
        "payoff_delivery_summary_lines": _compact_value(summary_lines[:4], text_limit=72),
        "payoff_delivery_review_source": _truncate_text(delivery.get("review_source"), 20),
        "payoff_next_compensation": _truncate_text(delivery.get("compensation_note"), 96),
        "payoff_next_compensation_priority": _truncate_text(delivery.get("compensation_priority"), 16),
    }



def apply_pending_payoff_compensation_to_plan(story_bible: dict[str, Any], plan: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    updated = dict(plan or {})
    existing = (updated.get("payoff_compensation") or {}) if isinstance(updated, dict) else {}
    if isinstance(existing, dict) and int(existing.get("target_chapter_no", 0) or 0) == int(chapter_no or 0):
        pending = existing
    else:
        retrospective_state = (story_bible or {}).get("retrospective_state") or {}
        payload = retrospective_state.get("pending_payoff_compensation") or {}
        pending = {}
        if isinstance(payload, dict) and payload and bool(payload.get("enabled", True)):
            for item in (payload.get("chapter_biases") or []):
                if not isinstance(item, dict):
                    continue
                if int(item.get("chapter_no", 0) or 0) == int(chapter_no or 0):
                    pending = {
                        "enabled": True,
                        "source_chapter_no": int(payload.get("source_chapter_no", 0) or 0),
                        "target_chapter_no": chapter_no,
                        "priority": _text(item.get("priority") or payload.get("priority"), "medium"),
                        "note": _text(item.get("note") or payload.get("note") or payload.get("reason"), "上一章兑现偏虚，这章优先追回一次明确回报。"),
                        "window_role": _text(item.get("bias") or item.get("window_role"), "primary_repay"),
                        "window_end_chapter_no": int(payload.get("window_end_chapter_no", 0) or 0),
                        "should_reduce_pressure": bool(payload.get("should_reduce_pressure", True)),
                    }
                    break
            if not pending and int(payload.get("target_chapter_no", 0) or 0) == int(chapter_no or 0):
                pending = {
                    "enabled": True,
                    "source_chapter_no": int(payload.get("source_chapter_no", 0) or 0),
                    "target_chapter_no": chapter_no,
                    "priority": _text(payload.get("priority"), "medium"),
                    "note": _text(payload.get("note") or payload.get("reason"), "上一章兑现偏虚，这章优先追回一次明确回报。"),
                    "window_role": "primary_repay",
                    "window_end_chapter_no": int(payload.get("window_end_chapter_no", 0) or 0),
                    "should_reduce_pressure": bool(payload.get("should_reduce_pressure", True)),
                }
    if not pending:
        return updated
    priority = _text(pending.get("priority"), "medium").lower()
    role = _text(pending.get("window_role"), "primary_repay")
    note = _text(pending.get("note") or pending.get("reason"), "上一章兑现偏虚，这章优先追回一次明确回报。")
    compensation = {
        "source_chapter_no": int(pending.get("source_chapter_no", 0) or 0),
        "target_chapter_no": int(pending.get("target_chapter_no", chapter_no) or chapter_no),
        "priority": priority,
        "note": note,
        "window_role": role,
        "window_end_chapter_no": int(pending.get("window_end_chapter_no", 0) or 0),
        "should_reduce_pressure": bool(pending.get("should_reduce_pressure", True)),
    }
    updated["payoff_compensation"] = compensation
    current_level = _text(updated.get("payoff_level"), "medium").lower()
    if priority == "high" and role == "primary_repay":
        updated["payoff_level"] = "strong"
    elif current_level not in {"medium", "strong"}:
        updated["payoff_level"] = "medium"
    payoff_line = _text(updated.get("payoff_or_pressure"))
    primary_line = "本章必须补一次明确回报落袋，不要继续只蓄压。"
    follow_line = "本章至少保留一次可感回收，不要重新连续两章只抬压力。"
    target_line = primary_line if role == "primary_repay" else follow_line
    if target_line not in payoff_line:
        updated["payoff_or_pressure"] = _truncate_text((payoff_line + "；" if payoff_line else "") + target_line, 120)
    if role == "primary_repay":
        if not _text(updated.get("reader_payoff")):
            updated["reader_payoff"] = "本章必须让主角追回一次读者看得见的实在回报。"
        if not _text(updated.get("new_pressure")):
            updated["new_pressure"] = "回报落袋后立刻带出新的盯防、追查或代价。"
    writing_note = _text(updated.get("writing_note"))
    if note and note not in writing_note:
        updated["writing_note"] = _truncate_text((writing_note + "；" if writing_note else "") + note, 120)
    recent_event_types = []
    for item in (((story_bible or {}).get("serial_runtime") or {}).get("recent_event_types") or [])[-2:]:
        value = _text(item)
        if value:
            recent_event_types.append(value)
    updated = apply_payoff_window_event_bias_to_plan(
        updated,
        role=role,
        priority=priority,
        note=note,
        recent_event_types=recent_event_types,
    )
    return updated



def serial_delivery_mode(story_bible: dict[str, Any]) -> str:
    runtime = (story_bible or {}).get("serial_runtime") or {}
    mode = str(runtime.get("delivery_mode") or "live_publish").strip()
    return mode if mode in {"live_publish", "stockpile"} else "live_publish"



def chapter_serial_stage_for_mode(delivery_mode: str) -> tuple[str, bool, bool]:
    if delivery_mode == "stockpile":
        return "stock", False, False
    return "published", True, True



def refresh_serial_layers_from_db(db: Session, novel: Novel) -> Novel:
    chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_no.asc())
        .all()
    )
    story_bible = sync_long_term_state(ensure_story_architecture(novel.story_bible or {}, novel), novel, chapters=chapters)
    novel.story_bible = story_bible
    db.add(novel)
    return novel



def mark_generated_chapter_delivery(db: Session, novel: Novel, chapter: Chapter) -> tuple[Novel, dict[str, Any]]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    delivery_mode = serial_delivery_mode(story_bible)
    serial_stage, is_published, locked_from_edit = chapter_serial_stage_for_mode(delivery_mode)
    chapter.serial_stage = serial_stage
    chapter.is_published = is_published
    chapter.locked_from_edit = locked_from_edit
    chapter.published_at = datetime.now().replace(tzinfo=None) if is_published else None
    db.add(chapter)

    story_bible = ensure_story_architecture(story_bible, novel)
    runtime = story_bible.setdefault("serial_runtime", {})
    runtime["delivery_mode"] = delivery_mode
    runtime["last_publish_action"] = {
        "chapter_no": chapter.chapter_no,
        "serial_stage": serial_stage,
        "published": is_published,
        "published_at": chapter.published_at.isoformat(timespec="seconds") + "Z" if chapter.published_at else None,
    }
    novel.story_bible = story_bible
    novel = refresh_serial_layers_from_db(db, novel)
    return novel, {
        "delivery_mode": delivery_mode,
        "serial_stage": serial_stage,
        "is_published": is_published,
        "locked_from_edit": locked_from_edit,
        "published_at": chapter.published_at.isoformat(timespec="seconds") + "Z" if chapter.published_at else None,
    }
