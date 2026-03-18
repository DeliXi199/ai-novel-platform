from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.chapter_generation_types import DraftPhaseResult, PreparedChapterState
from app.services.chapter_quality import assess_payoff_delivery, review_payoff_delivery_with_ai
from app.services.chapter_retry_support import _attempt_generate_validated_chapter
from app.services.chapter_runtime_support import _commit_runtime_snapshot, _planning_runtime_meta
from app.services.chapter_generation_postprocess import (
    runtime_payoff_delivery_extra as _runtime_payoff_delivery_extra,
    runtime_payoff_extra as _runtime_payoff_extra,
    runtime_stage_casting_extra as _runtime_stage_casting_extra,
)


def draft_chapter_content(db: Session, prepared: PreparedChapterState, *, chapter_started_at: float) -> DraftPhaseResult:
    title, content, draft_payload, used_plan, length_targets, attempt_meta = _attempt_generate_validated_chapter(
        novel_context=prepared.novel_context,
        plan=prepared.plan,
        serialized_last=prepared.serialized_last,
        recent_summaries=prepared.recent_summaries,
        serialized_active=prepared.serialized_active,
        recent_full_texts=prepared.recent_full_texts,
        recent_plan_meta=prepared.recent_plan_meta,
        execution_brief=prepared.execution_brief,
        chapter_no=prepared.next_no,
        started_at=chapter_started_at,
        novel_ref=prepared.locked_novel,
    )
    local_payoff_delivery = assess_payoff_delivery(
        title=title,
        content=content,
        chapter_plan=used_plan,
    )
    payoff_delivery = review_payoff_delivery_with_ai(
        title=title,
        content=content,
        chapter_plan=used_plan,
        local_review=local_payoff_delivery,
    )
    used_plan["_payoff_delivery"] = {
        "delivery_level": payoff_delivery.get("delivery_level"),
        "delivery_score": payoff_delivery.get("delivery_score"),
        "verdict": payoff_delivery.get("verdict"),
        "should_compensate_next_chapter": payoff_delivery.get("should_compensate_next_chapter"),
        "compensation_priority": payoff_delivery.get("compensation_priority"),
        "compensation_note": payoff_delivery.get("compensation_note"),
    }
    _commit_runtime_snapshot(
        db,
        prepared.locked_novel,
        next_chapter_no=prepared.next_no,
        stage="quality_check",
        note=f"第 {prepared.next_no} 章正文与结尾检查通过，正在生成摘要与标题精修。",
        extra={
            **_planning_runtime_meta(prepared.locked_novel.story_bible or {}),
            **_runtime_stage_casting_extra(prepared.execution_brief),
            **_runtime_payoff_extra(prepared.execution_brief),
            **_runtime_payoff_delivery_extra(payoff_delivery),
            "validated": True,
            "target_visible_chars_min": int(length_targets["target_visible_chars_min"]),
            "target_visible_chars_max": int(length_targets["target_visible_chars_max"]),
        },
    )
    return DraftPhaseResult(
        prepared=prepared,
        title=title,
        content=content,
        draft_payload=draft_payload,
        used_plan=used_plan,
        length_targets=length_targets,
        attempt_meta=attempt_meta,
        payoff_delivery=payoff_delivery,
    )




