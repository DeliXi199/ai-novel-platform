from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.chapter_context_serialization import _serialize_recent_summaries
from app.services.chapter_generation_finalize_prepare import FinalizationSnapshot
from app.services.chapter_generation_persistence import _persist_chapter_and_summary
from app.services.chapter_generation_postprocess import (
    mark_generated_chapter_delivery as _mark_generated_chapter_delivery,
    runtime_payoff_delivery_extra as _runtime_payoff_delivery_extra,
    runtime_payoff_extra as _runtime_payoff_extra,
    serial_delivery_mode as _serial_delivery_mode,
)
from app.services.chapter_generation_planning import auto_prepare_future_planning as _auto_prepare_future_planning_impl
from app.services.chapter_generation_report import attach_generation_pipeline_report, build_generation_pipeline_report
from app.services.chapter_generation_types import DraftPhaseResult
from app.services.chapter_runtime_support import _commit_runtime_snapshot, _planning_runtime_meta, _set_live_runtime
from app.services.openai_story_engine import get_llm_trace
from app.services.story_architecture import ensure_story_architecture
from app.services.story_workspace_archive import archive_story_workspace_snapshot

logger = logging.getLogger(__name__)


def _auto_prepare_future_planning(
    db: Session,
    novel,
    *,
    current_chapter_no: int,
    recent_summaries: list[dict[str, Any]],
    progress_callback=None,
) -> dict[str, Any]:
    return _auto_prepare_future_planning_impl(
        db,
        novel,
        current_chapter_no=current_chapter_no,
        recent_summaries=recent_summaries,
        progress_callback=progress_callback,
    )


def commit_finalized_chapter(
    db: Session,
    draft: DraftPhaseResult,
    snapshot: FinalizationSnapshot,
    *,
    trace_id: str,
    previous_status: str,
) -> Any:
    prepared = draft.prepared
    locked_novel = snapshot.locked_novel
    next_no = snapshot.next_no
    title = snapshot.title
    content = snapshot.content
    used_plan = snapshot.used_plan
    payoff_delivery = snapshot.payoff_delivery
    summary = snapshot.summary

    generation_meta = {
        "generator": "chat_completions_api" if settings.llm_provider.lower() in ("deepseek", "groq") else "responses_api",
        "provider": settings.llm_provider,
        "trace_id": trace_id,
        "based_on_chapter": prepared.last_chapter.chapter_no if prepared.last_chapter else None,
        "based_on_published_through": int((((locked_novel.story_bible or {}).get("long_term_state") or {}).get("chapter_release_state") or {}).get("published_through", 0) or 0),
        "active_interventions": [i.id for i in prepared.active_interventions],
        "chapter_plan": used_plan,
        "chapter_plan_packet": used_plan.get("planning_packet", {}),
        "quality_validated": True,
        "length_targets": draft.length_targets,
        "context_stats": prepared.context_stats,
        "manual_framework": {
            "project_card_enabled": True,
            "volume_card_enabled": True,
            "story_workspace_enabled": True,
            "daily_workbench_enabled": True,
            "strict_document_first_pipeline": True,
            "bootstrap_generated_text": False,
            "pipeline_steps": ["定位", "读状态", "章纲", "场景", "正文", "检查", "摘要", "状态更新", "发布状态标记", "下一章入口"],
        },
        **({"draft_payload": draft.draft_payload} if settings.return_draft_payload_in_meta else {}),
        "llm_call_trace": get_llm_trace(),
        "serial_generation_guard": {
            "generation_slot_status": "generating",
            "llm_call_min_interval_ms": settings.llm_call_min_interval_ms,
            "chapter_draft_max_attempts": settings.chapter_draft_max_attempts,
            "chapter_total_llm_attempt_cap": getattr(settings, "chapter_total_llm_attempt_cap", 2),
            "arc_prefetch_threshold": settings.arc_prefetch_threshold,
            "state_refresh_each_chapter": True,
            "parallel_batch_generation_disabled": True,
        },
        "fact_entries": snapshot.chapter_fact_entries,
        "hard_fact_report": {**snapshot.chapter_hard_fact_report, "facts": snapshot.chapter_hard_facts},
        "continuity_bridge": snapshot.continuity_bridge,
        "attempt_meta": draft.attempt_meta,
        "title_refinement": snapshot.title_refinement_meta,
        "quality_rejections": (draft.attempt_meta or {}).get("quality_rejections", []),
        "payoff_delivery": payoff_delivery,
        "structural_signals": {
            "event_type": used_plan.get("event_type"),
            "progress_kind": used_plan.get("progress_kind"),
            "proactive_move": used_plan.get("proactive_move"),
            "payoff_or_pressure": used_plan.get("payoff_or_pressure"),
            "payoff_mode": used_plan.get("payoff_mode"),
            "payoff_level": used_plan.get("payoff_level"),
            "payoff_visibility": used_plan.get("payoff_visibility"),
            "reader_payoff": used_plan.get("reader_payoff"),
            "new_pressure": used_plan.get("new_pressure"),
            "hook_kind": used_plan.get("hook_kind"),
            "flow_card": used_plan.get("flow_template_name") or used_plan.get("flow_template_tag") or used_plan.get("flow_template_id"),
            "writing_card_selection_note": ((used_plan.get("planning_packet") or {}).get("writing_card_selection") or {}).get("selection_note"),
        },
    }

    chapter = _persist_chapter_and_summary(
        db=db,
        novel=locked_novel,
        chapter_no=next_no,
        chapter_title=title,
        content=content,
        generation_meta=generation_meta,
        event_summary=summary.event_summary,
        character_updates=summary.character_updates,
        new_clues=summary.new_clues,
        open_hooks=summary.open_hooks,
        closed_hooks=summary.closed_hooks,
    )
    locked_novel, serial_delivery = _mark_generated_chapter_delivery(db, locked_novel, chapter)
    generation_report = build_generation_pipeline_report(
        chapter_no=next_no,
        chapter_title=title,
        content=content,
        plan=used_plan,
        chapter_plan_packet=prepared.chapter_plan_packet,
        execution_brief=prepared.execution_brief,
        context_stats=prepared.context_stats,
        attempt_meta=draft.attempt_meta,
        length_targets=draft.length_targets,
        payoff_delivery=payoff_delivery,
        title_refinement=snapshot.title_refinement_meta,
        serial_delivery=serial_delivery,
        llm_trace=get_llm_trace(),
        duration_ms=snapshot.generation_duration_ms,
        summary=summary,
    )
    locked_novel.story_bible = attach_generation_pipeline_report(locked_novel.story_bible or {}, generation_report)
    chapter.generation_meta = {
        **(chapter.generation_meta or {}),
        "serial_delivery": serial_delivery,
        "generation_report": generation_report,
    }
    db.add(chapter)
    locked_novel = _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="publish_mark",
        note=(f"第 {next_no} 章已立即发布并锁定。" if serial_delivery.get("is_published") else f"第 {next_no} 章已写入库存，等待后续发布。"),
        extra={
            **_planning_runtime_meta(locked_novel.story_bible or {}),
            **_runtime_payoff_delivery_extra(payoff_delivery),
            "serial_delivery": serial_delivery,
        },
    )

    for item in prepared.active_interventions:
        item.applied = True
        db.add(item)

    recent_summaries_after = _serialize_recent_summaries(db, locked_novel.id)
    planning_meta_after = _auto_prepare_future_planning(
        db,
        locked_novel,
        current_chapter_no=next_no,
        recent_summaries=recent_summaries_after,
    )

    locked_novel.story_bible = _set_live_runtime(
        ensure_story_architecture(locked_novel.story_bible or {}, locked_novel),
        next_chapter_no=next_no + 1,
        stage="next_entry_ready",
        note=f"第 {next_no} 章已完成，下一章入口、主控台与后续规划均已刷新。",
        extra={
            **planning_meta_after,
            **_runtime_payoff_delivery_extra(payoff_delivery),
            **_runtime_payoff_extra(prepared.execution_brief),
            "last_generated_chapter_no": next_no,
            "last_generated_title": title,
            "delivery_mode": _serial_delivery_mode(locked_novel.story_bible or {}),
            "generation_report": {
                "chapter_no": next_no,
                "duration_ms": snapshot.generation_duration_ms,
                "llm_calls": (generation_report.get("llm_trace") or {}).get("total_calls", 0),
                "delivery_level": ((generation_report.get("payoff_delivery") or {}).get("delivery_level")),
            },
        },
    )

    locked_novel.status = previous_status
    db.add(locked_novel)
    db.commit()
    db.refresh(chapter)
    db.refresh(locked_novel)
    archive_story_workspace_snapshot(
        locked_novel,
        chapter_no=next_no,
        phase="after",
        stage="next_entry_ready",
        note=f"第 {next_no} 章生成完成后的 Story Workspace 快照。",
        extra={"chapter_title": title, "trace_id": trace_id, "serial_delivery": serial_delivery},
    )
    logger.info(
        "chapter_generation success novel_id=%s chapter_no=%s duration_ms=%s",
        locked_novel.id,
        next_no,
        snapshot.generation_duration_ms,
    )
    return chapter
