from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.novel import Novel
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import current_timeout
from app.services.story_architecture import ensure_story_architecture


def _chapter_wall_clock_limit_seconds() -> int:
    return max(int(getattr(settings, "chapter_generation_wall_clock_limit_seconds", 0) or 0), 0)



def _remaining_generation_budget_seconds(*, started_at: float) -> int | None:
    limit = _chapter_wall_clock_limit_seconds()
    if limit <= 0:
        return None
    elapsed = time.monotonic() - started_at
    return max(int(limit - elapsed), 0)



def _minimum_llm_timeout_seconds_for_stage(stage: str) -> tuple[int, int | None]:
    base_minimum = max(int(getattr(settings, "chapter_runtime_min_llm_timeout_seconds", 25) or 25), 5)
    if stage == "chapter_extension":
        hard_minimum = max(int(getattr(settings, "chapter_extension_min_llm_timeout_seconds", 20) or 20), 8)
        soft_minimum = max(int(getattr(settings, "chapter_extension_soft_min_timeout_seconds", 12) or 12), 8)
        return hard_minimum, min(soft_minimum, hard_minimum)
    return base_minimum, None



def _compute_llm_timeout_seconds(
    *,
    started_at: float,
    chapter_no: int,
    stage: str,
    reserve_seconds: int = 0,
    attempt_no: int | None = None,
) -> int | None:
    remaining = _remaining_generation_budget_seconds(started_at=started_at)
    if remaining is None:
        return None
    budget = remaining - max(int(reserve_seconds or 0), 0)
    minimum, soft_minimum = _minimum_llm_timeout_seconds_for_stage(stage)
    if budget < minimum:
        details = {
            "chapter_no": chapter_no,
            "remaining_seconds": remaining,
            "reserve_seconds": reserve_seconds,
            "required_timeout_seconds": minimum,
            "wall_clock_limit_seconds": _chapter_wall_clock_limit_seconds(),
        }
        if soft_minimum is not None:
            details["soft_timeout_floor_seconds"] = soft_minimum
            if budget >= soft_minimum:
                return max(min(int(current_timeout(stage)), budget), soft_minimum)
        if attempt_no is not None:
            details["attempt_no"] = attempt_no
        raise GenerationError(
            code=ErrorCodes.CHAPTER_PIPELINE_TIMEOUT,
            message=f"第 {chapter_no} 章剩余时间不足，已停止继续尝试，避免整章超时。",
            stage=stage,
            retryable=True,
            http_status=504,
            details=details,
        )
    return max(min(int(current_timeout(stage)), budget), minimum)



def _should_stop_retrying_for_budget(*, started_at: float, attempt_no: int) -> bool:
    if attempt_no <= 1:
        return False
    remaining = _remaining_generation_budget_seconds(started_at=started_at)
    if remaining is None:
        return False
    threshold = max(int(getattr(settings, "chapter_runtime_min_remaining_for_retry_seconds", 45) or 45), 10)
    return remaining < threshold



def _ensure_generation_runtime_budget(*, started_at: float, stage: str, chapter_no: int, attempt_no: int | None = None) -> None:
    limit = _chapter_wall_clock_limit_seconds()
    if limit <= 0:
        return
    elapsed = time.monotonic() - started_at
    if elapsed <= limit:
        return
    details = {
        "chapter_no": chapter_no,
        "elapsed_seconds": int(round(elapsed)),
        "wall_clock_limit_seconds": limit,
    }
    if attempt_no is not None:
        details["attempt_no"] = attempt_no
    raise GenerationError(
        code=ErrorCodes.CHAPTER_PIPELINE_TIMEOUT,
        message=f"第 {chapter_no} 章生成耗时过长，已主动中止，请直接重试这一章。",
        stage=stage,
        retryable=True,
        http_status=504,
        details=details,
    )



def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")



def _planning_runtime_meta(story_bible: dict[str, Any]) -> dict[str, Any]:
    console = (story_bible or {}).get("control_console") or {}
    planning_status = console.get("planning_status") or {}
    queue = console.get("chapter_card_queue") or []
    pending_arc = planning_status.get("pending_arc") or {}
    active_arc = planning_status.get("active_arc") or {}
    return {
        "planned_until": int((((story_bible or {}).get("outline_state") or {}).get("planned_until", 0) or 0)),
        "ready_cards": [int(item.get("chapter_no", 0) or 0) for item in queue[:7]],
        "queue_size": len(queue),
        "active_arc_no": int((active_arc.get("arc_no", 0) or 0)),
        "pending_arc_no": int((pending_arc.get("arc_no", 0) or 0)) if pending_arc else None,
    }



def _set_live_runtime(
    story_bible: dict[str, Any],
    *,
    next_chapter_no: int,
    stage: str,
    note: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow_state = story_bible.setdefault("workflow_state", {})
    pipeline = workflow_state.setdefault("current_pipeline", {})
    runtime = workflow_state.setdefault("live_runtime", {})
    runtime.update(
        {
            "stage": stage,
            "note": note,
            "updated_at": _utc_now_iso(),
            "target_chapter_no": next_chapter_no,
        }
    )
    if extra:
        runtime.update(extra)
    pipeline["target_chapter_no"] = next_chapter_no
    pipeline["last_live_stage"] = stage
    pipeline["last_live_note"] = note
    workflow_state["current_pipeline"] = pipeline
    workflow_state["live_runtime"] = runtime
    story_bible["workflow_state"] = workflow_state
    return story_bible



def _commit_runtime_snapshot(
    db: Session,
    novel: Novel,
    *,
    next_chapter_no: int,
    stage: str,
    note: str,
    extra: dict[str, Any] | None = None,
) -> Novel:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    story_bible = _set_live_runtime(
        story_bible,
        next_chapter_no=next_chapter_no,
        stage=stage,
        note=note,
        extra=extra,
    )
    novel.story_bible = story_bible
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return novel
