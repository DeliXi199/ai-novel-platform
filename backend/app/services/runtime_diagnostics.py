from __future__ import annotations

from typing import Any

from app.services.chapter_generation_report import compact_generation_pipeline_report




def _get_planning_status(story_bible: dict[str, Any]) -> dict[str, Any]:
    workspace = story_bible.get("story_workspace") or {}
    return workspace.get("planning_status") or {}


def _get_current_pipeline(story_bible: dict[str, Any]) -> dict[str, Any]:
    workflow = story_bible.get("workflow_state") or {}
    return workflow.get("current_pipeline") or {}


def _get_live_runtime(story_bible: dict[str, Any]) -> dict[str, Any]:
    workflow = story_bible.get("workflow_state") or {}
    return workflow.get("live_runtime") or {}


def _get_live_runtime_events(story_bible: dict[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
    workflow = story_bible.get("workflow_state") or {}
    events = [item for item in (workflow.get("live_runtime_events") or []) if isinstance(item, dict)]
    if isinstance(limit, int) and limit >= 0:
        return events[-limit:]
    return events


def _get_chapter_card_queue(story_bible: dict[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
    workspace = story_bible.get("story_workspace") or {}
    queue = [item for item in (workspace.get("chapter_card_queue") or []) if isinstance(item, dict)]
    if isinstance(limit, int) and limit >= 0:
        return queue[:limit]
    return queue

def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _truncate(value: Any, limit: int = 80) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def _compact_value(value: Any, *, text_limit: int = 60, max_items: int = 5) -> Any:
    if isinstance(value, str):
        return _truncate(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, text_limit=text_limit, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                break
            compact[str(key)] = _compact_value(item, text_limit=text_limit, max_items=max_items)
        return compact
    return _truncate(value, text_limit)


def _compact_runtime_event(event: dict[str, Any]) -> dict[str, Any]:
    summary = event.get("summary") or {}
    return {
        "updated_at": event.get("updated_at"),
        "target_chapter_no": _safe_int(event.get("target_chapter_no"), 0),
        "stage": _text(event.get("stage")),
        "note": _truncate(event.get("note"), 120),
        "summary": _compact_value(summary, text_limit=56, max_items=6),
    }


def _book_profile_summary(story_bible: dict[str, Any]) -> dict[str, Any]:
    profile = story_bible.get("book_execution_profile") or {}
    rhythm = profile.get("rhythm_bias") or {}
    return {
        "positioning_summary": _truncate(profile.get("positioning_summary"), 120),
        "flow_high": list((profile.get("flow_family_priority") or {}).get("high") or [])[:4],
        "payoff_high": list((profile.get("payoff_priority") or {}).get("high") or [])[:4],
        "foreshadowing_primary": list((profile.get("foreshadowing_priority") or {}).get("primary") or [])[:4],
        "writing_high": list((profile.get("writing_strategy_priority") or {}).get("high") or [])[:4],
        "rhythm_bias": _compact_value(rhythm, text_limit=32, max_items=6),
        "demotion_rules": list(profile.get("demotion_rules") or [])[:4],
    }


def _window_bias_summary(story_bible: dict[str, Any]) -> dict[str, Any]:
    workspace = story_bible.get("story_workspace") or {}
    bias = workspace.get("window_execution_bias") or {}
    return {
        "window_mode": _text(bias.get("window_mode")),
        "focus": _truncate(bias.get("focus"), 96),
        "payoff_bias": list(bias.get("payoff_bias") or [])[:3],
        "foreshadowing_bias": list(bias.get("foreshadowing_bias") or [])[:3],
        "notes": list(bias.get("notes") or [])[:4],
    }


def _queue_preview(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    queue = _get_chapter_card_queue(story_bible, limit=4)
    return [
        {
            "chapter_no": _safe_int(item.get("chapter_no"), 0),
            "title": _truncate(item.get("title"), 28),
            "goal": _truncate(item.get("goal"), 68),
            "event_type": _truncate(item.get("event_type"), 20),
            "payoff_or_pressure": _truncate(item.get("payoff_or_pressure"), 72),
        }
        for item in queue
        if isinstance(item, dict)
    ]


def build_runtime_diagnostics(story_bible: dict[str, Any] | None, *, active_tasks: list[dict[str, Any]] | None = None, recent_tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = story_bible or {}
    planning_status = _get_planning_status(payload)
    current_pipeline = _get_current_pipeline(payload)
    live_runtime = _get_live_runtime(payload)
    live_events = [_compact_runtime_event(item) for item in _get_live_runtime_events(payload, limit=10)]
    workspace = payload.get("story_workspace") or {}
    latest_report = workspace.get("last_generation_report") if isinstance(workspace.get("last_generation_report"), dict) else {}
    history_rows = workspace.get("generation_report_history") if isinstance(workspace.get("generation_report_history"), list) else []
    report_payload = {**latest_report, "history": history_rows} if latest_report and history_rows else latest_report
    generation_report = compact_generation_pipeline_report(report_payload) if report_payload else {}
    latest_alerts = ((generation_report.get("alerts") or {}).get("items") or [])[:4] if generation_report else []
    latest_delivery = _text((generation_report.get("payoff_delivery") or {}).get("delivery_level"))
    if not latest_alerts and latest_delivery.lower() == "low":
        latest_alerts = [{
            "code": "latest_delivery_low",
            "severity": "medium",
            "title": "最近一章兑现偏弱",
            "message": "最近一章的兑现等级为 low，下一章应提高兑现优先级或减少继续蓄压。",
        }]
    active_task_rows = [item for item in (active_tasks or []) if isinstance(item, dict)]
    recent_task_rows = [item for item in (recent_tasks or []) if isinstance(item, dict)]
    return {
        "overview": {
            "target_chapter_no": _safe_int(live_runtime.get("target_chapter_no") or current_pipeline.get("target_chapter_no"), 0),
            "current_stage": _text(live_runtime.get("stage") or current_pipeline.get("last_live_stage")),
            "current_note": _truncate(live_runtime.get("note") or current_pipeline.get("last_live_note"), 120),
            "planned_until": _safe_int(planning_status.get("planned_until"), 0),
            "ready_card_count": len(planning_status.get("ready_chapter_cards") or []),
            "queue_size": len((workspace.get("chapter_card_queue") or [])),
            "active_task_count": len(active_task_rows),
        },
        "book_profile": _book_profile_summary(payload),
        "window_bias": _window_bias_summary(payload),
        "queue_preview": _queue_preview(payload),
        "timeline": live_events,
        "latest_generation": {
            "chapter_no": _safe_int(generation_report.get("chapter_no"), 0),
            "delivery_level": _text((generation_report.get("payoff_delivery") or {}).get("delivery_level")),
            "delivery_score": _safe_int((generation_report.get("payoff_delivery") or {}).get("delivery_score"), 0),
            "duration_ms": _safe_int(generation_report.get("duration_ms"), 0),
            "selected_outputs": _compact_value(generation_report.get("selected_outputs") or {}, text_limit=40, max_items=6),
            "summary_line": _truncate(generation_report.get("summary_line"), 120),
        },
        "alerts": {
            "count": len(latest_alerts),
            "items": [
                {
                    "code": _text(item.get("code")),
                    "severity": _text(item.get("severity")),
                    "title": _truncate(item.get("title"), 40),
                    "message": _truncate(item.get("message"), 120),
                }
                for item in latest_alerts
                if isinstance(item, dict)
            ],
        },
        "tasks": {
            "active": [
                {
                    "id": _safe_int(item.get("id"), 0),
                    "task_type": _text(item.get("task_type")),
                    "status": _text(item.get("status")),
                    "chapter_no": _safe_int(item.get("chapter_no"), 0),
                    "progress_message": _truncate(item.get("progress_message"), 72),
                }
                for item in active_task_rows[:4]
            ],
            "recent": [
                {
                    "id": _safe_int(item.get("id"), 0),
                    "task_type": _text(item.get("task_type")),
                    "status": _text(item.get("status")),
                    "chapter_no": _safe_int(item.get("chapter_no"), 0),
                }
                for item in recent_task_rows[:6]
            ],
        },
    }


def build_runtime_diagnostics_brief(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = build_runtime_diagnostics(story_bible)
    overview = diagnostics.get("overview") or {}
    alerts = diagnostics.get("alerts") or {}
    return {
        "target_chapter_no": _safe_int(overview.get("target_chapter_no"), 0),
        "current_stage": _text(overview.get("current_stage")),
        "queue_size": _safe_int(overview.get("queue_size"), 0),
        "planned_until": _safe_int(overview.get("planned_until"), 0),
        "book_positioning": _truncate(((diagnostics.get("book_profile") or {}).get("positioning_summary")), 80),
        "window_mode": _text((diagnostics.get("window_bias") or {}).get("window_mode")),
        "timeline": [
            {
                "stage": _text(item.get("stage")),
                "note": _truncate(item.get("note"), 72),
            }
            for item in (diagnostics.get("timeline") or [])[-4:]
            if isinstance(item, dict)
        ],
        "alert_count": _safe_int(alerts.get("count"), 0),
    }
