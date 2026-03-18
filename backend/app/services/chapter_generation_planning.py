from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.novel import Novel
from app.services.chapter_generation_progress import emit_progress
from app.services.chapter_generation_support import _arc_remaining, _generate_and_store_pending_arc
from app.services.chapter_planning_support import _ensure_outline_state, _promote_pending_arc_if_needed
from app.services.chapter_runtime_support import _planning_runtime_meta
from app.services.story_architecture import ensure_story_architecture, refresh_planning_views


def pending_arc_window_preview(story_bible: dict[str, Any], *, current_chapter_no: int) -> tuple[int, int, int]:
    state = _ensure_outline_state(story_bible)
    active_arc = story_bible.get("active_arc")
    if not active_arc:
        start = current_chapter_no + 1
    else:
        start = int(active_arc.get("end_chapter", 0) or 0) + 1
    end = start + settings.arc_outline_size - 1
    arc_no = int(state.get("next_arc_no", 1) or 1)
    return start, end, arc_no


def auto_prepare_future_planning(
    db: Session,
    novel: Novel,
    *,
    current_chapter_no: int,
    recent_summaries: list[dict[str, Any]],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    _ensure_outline_state(story_bible)
    _promote_pending_arc_if_needed(story_bible, current_chapter_no + 1)
    story_bible = refresh_planning_views(story_bible, current_chapter_no)
    novel.story_bible = story_bible

    workspace_state = story_bible.get("story_workspace") or {}
    queue = workspace_state.get("chapter_card_queue") or []
    active_arc = story_bible.get("active_arc")
    pending_arc = story_bible.get("pending_arc")
    remaining = _arc_remaining(active_arc, current_chapter_no)
    planned_until = int((((story_bible or {}).get("outline_state") or {}).get("planned_until", 0) or 0))
    need_prefetch = not pending_arc and (
        remaining <= settings.arc_prefetch_threshold
        or len(queue) < settings.planning_window_size
    )

    emit_progress(
        progress_callback,
        {
            "stage": "planning_refresh_check",
            "stage_label": "近5章规划检查",
            "message": (
                f"正在检查近{settings.arc_outline_size}章规划：当前已规划到第{planned_until}章，"
                f"队列有{len(queue)}张章节卡。"
            ),
            "target_chapter_no": current_chapter_no + 1,
            "current_chapter_no": current_chapter_no,
            "queue_size": len(queue),
            "ready_cards": [int(item.get("chapter_no", 0) or 0) for item in queue[: settings.planning_window_size]],
            "arc_remaining": remaining,
            "planned_until": planned_until,
            "need_refresh": bool(need_prefetch),
            "pending_arc_exists": bool(pending_arc),
        },
    )

    auto_prefetched = False
    refresh_summary: dict[str, Any] = {
        "triggered": False,
        "reason": "planning_window_already_ready",
        "queue_size_before": len(queue),
        "queue_size_after": len(queue),
        "ready_cards_before": [int(item.get("chapter_no", 0) or 0) for item in queue[: settings.planning_window_size]],
        "ready_cards_after": [int(item.get("chapter_no", 0) or 0) for item in queue[: settings.planning_window_size]],
        "pending_arc_exists": bool(pending_arc),
    }
    if need_prefetch:
        start_preview, end_preview, arc_no_preview = pending_arc_window_preview(story_bible, current_chapter_no=current_chapter_no)
        reason = "queue_low" if len(queue) < settings.planning_window_size else "active_arc_nearly_exhausted"
        emit_progress(
            progress_callback,
            {
                "stage": "planning_refresh_running",
                "stage_label": "近5章规划刷新",
                "message": f"正在刷新近{settings.arc_outline_size}章规划：准备补到第{start_preview}-{end_preview}章。",
                "target_chapter_no": current_chapter_no + 1,
                "refresh_reason": reason,
                "queue_size_before": len(queue),
                "arc_no": arc_no_preview,
                "start_chapter": start_preview,
                "end_chapter": end_preview,
                "ready_cards_before": [int(item.get("chapter_no", 0) or 0) for item in queue[: settings.planning_window_size]],
            },
        )
        bundle_meta = _generate_and_store_pending_arc(
            db,
            novel,
            recent_summaries,
            replace_existing=False,
        )
        story_bible = novel.story_bible or {}
        _promote_pending_arc_if_needed(story_bible, current_chapter_no + 1)
        story_bible = refresh_planning_views(story_bible, current_chapter_no)
        novel.story_bible = story_bible
        queue_after = (((story_bible or {}).get("story_workspace") or {}).get("chapter_card_queue") or [])
        refresh_summary = {
            **(bundle_meta or {}),
            "triggered": True,
            "reason": reason,
            "queue_size_before": len(queue),
            "queue_size_after": len(queue_after),
            "ready_cards_before": [int(item.get("chapter_no", 0) or 0) for item in queue[: settings.planning_window_size]],
            "ready_cards_after": [int(item.get("chapter_no", 0) or 0) for item in queue_after[: settings.planning_window_size]],
        }
        emit_progress(
            progress_callback,
            {
                "stage": "planning_refresh_completed",
                "stage_label": "近5章规划已更新",
                "message": (
                    f"近{settings.arc_outline_size}章规划已更新：新增第{int((bundle_meta or {}).get('start_chapter', start_preview) or start_preview)}"
                    f"-{int((bundle_meta or {}).get('end_chapter', end_preview) or end_preview)}章，"
                    f"当前可用章节卡覆盖到第{int((queue_after[-1].get('chapter_no', 0) if queue_after else end_preview) or end_preview)}章。"
                ),
                "target_chapter_no": current_chapter_no + 1,
                "refresh_reason": reason,
                **refresh_summary,
            },
        )
        auto_prefetched = True
    else:
        emit_progress(
            progress_callback,
            {
                "stage": "planning_refresh_ready",
                "stage_label": "近5章规划就绪",
                "message": (
                    f"近{settings.arc_outline_size}章规划已就绪：下一章直接承接现有规划，"
                    f"当前章节卡覆盖到第{int((queue[-1].get('chapter_no', 0) if queue else planned_until) or planned_until)}章。"
                ),
                "target_chapter_no": current_chapter_no + 1,
                **refresh_summary,
            },
        )

    db.add(novel)
    return {
        **_planning_runtime_meta(novel.story_bible or {}),
        "auto_prefetched": auto_prefetched,
        "arc_remaining": remaining,
        "planning_refresh": refresh_summary,
    }
