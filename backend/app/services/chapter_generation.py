from __future__ import annotations

import logging
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.services.card_indexing import apply_card_selection_to_packet, apply_soft_card_ranking_to_packet as _apply_soft_card_ranking_to_packet_impl
from app.services.chapter_context_support import (
    _compact_scene_card,
    _tail_paragraphs,
    build_chapter_plan_packet,
    serialize_local_novel_context,
)
from app.services.chapter_generation_persistence import (
    collect_active_interventions as _collect_active_interventions_impl,
    load_recent_titles as _load_recent_titles_impl,
    persist_chapter_and_summary as _persist_chapter_and_summary_impl,
)
from app.services.chapter_generation_postprocess import (
    apply_pending_payoff_compensation_to_plan as _apply_pending_payoff_compensation_to_plan_impl,
    chapter_serial_stage_for_mode as _chapter_serial_stage_for_mode_impl,
    mark_generated_chapter_delivery as _mark_generated_chapter_delivery_impl,
    refresh_serial_layers_from_db as _refresh_serial_layers_from_db_impl,
    runtime_payoff_delivery_extra as _runtime_payoff_delivery_extra_impl,
    runtime_payoff_extra as _runtime_payoff_extra_impl,
    runtime_stage_casting_extra as _runtime_stage_casting_extra_impl,
    serial_delivery_mode as _serial_delivery_mode_impl,
)
from app.services.chapter_generation_entry import (
    generate_next_chapter as _entry_generate_next_chapter,
    generate_next_chapters_batch as _entry_generate_next_chapters_batch,
)
from app.services.chapter_generation_stages import (
    auto_prepare_future_planning as _auto_prepare_future_planning_impl,
    emit_progress as _emit_progress_impl,
    pending_arc_window_preview as _pending_arc_window_preview_impl,
    run_chapter_generation,
)
from app.services.chapter_generation_support import (
    _acquire_generation_slot,
    _arc_remaining,
    _compact_arc,
    _compact_value,
    _ensure_outline_state,
    _ensure_plan_for_chapter,
    _extract_continuity_bridge,
    _fit_chapter_payload_budget,
    _generate_and_store_pending_arc,
    _json_size,
    _load_novel_or_404,
    _load_recent_chapters,
    _normalize_hook,
    _persist_generation_failure_snapshot,
    _promote_pending_arc_if_needed,
    _published_and_stock_facts,
    _release_generation_slot,
    _save_pipeline_execution_packet,
    _select_outline_window,
    _serialize_active_interventions,
    _serialize_last_chapter,
    _serialize_novel_context,
    _serialize_recent_summaries,
    _story_bible_payload_to_novel_create,
    _truncate_list,
    _truncate_text,
    _validate_fact_ledger_state,
    _validate_required_planning_docs,
    prepare_next_planning_window,
)
from app.services.chapter_quality import assess_payoff_delivery, review_payoff_delivery_with_ai
from app.services.chapter_retry_support import (
    _attempt_generate_validated_chapter,
    _build_attempt_plans,
    _chapter_length_targets,
    _enrich_plan_agency,
)
from app.services.llm_runtime import current_timeout, is_openai_enabled as _llm_is_openai_enabled
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.chapter_runtime_support import (
    _chapter_wall_clock_limit_seconds,
    _commit_runtime_snapshot,
    _compute_llm_timeout_seconds as _runtime_compute_llm_timeout_seconds,
    _ensure_generation_runtime_budget,
    _minimum_llm_timeout_seconds_for_stage,
    _planning_runtime_meta,
    _remaining_generation_budget_seconds as _runtime_remaining_generation_budget_seconds,
    _set_live_runtime,
)
from app.services.hard_fact_guard import HardFactConflict, compact_hard_fact_guard, validate_and_register_chapter
from app.services.openai_story_engine import (
    begin_llm_trace,
    clear_llm_trace,
    get_llm_trace,
    generate_chapter_summary_and_title_package,
    parse_instruction_with_openai,
    summarize_chapter as _summarize_chapter_impl,
)
from app.services.openai_story_engine_selection import (
    apply_schedule_review_to_packet,
    review_character_relation_schedule_and_select_cards,
    run_chapter_preparation_selection,
)
from app.services.scene_templates import build_scene_handoff_card, realize_scene_sequence_from_selection
from app.services.story_architecture import (
    build_execution_brief,
    ensure_story_architecture,
    prepare_story_workspace_for_chapter_entry,
    refresh_planning_views,
    set_pipeline_target,
    sync_character_registry,
    sync_long_term_state,
    update_story_architecture_after_chapter,
)
from app.services.payoff_cards import realize_payoff_selection_from_index
from app.services.prompt_strategy_library import apply_prompt_strategy_selection_to_packet

from app.services.chapter_title_service import (
    build_cooled_terms,
    normalize_title,
    refine_generated_chapter_title_from_candidates,
)

import app.services.chapter_generation_prepare as _cg_prepare_module
import app.services.chapter_generation_draft as _cg_draft_module
import app.services.chapter_generation_finalize_prepare as _cg_finalize_prepare_module
import app.services.chapter_generation_finalize_commit as _cg_finalize_commit_module
import app.services.chapter_context_support as _cg_context_support_module
import app.services.resource_card_support as _cg_resource_card_support_module
import app.services.openai_story_engine_selection as _cg_selection_boundary_module
import app.services.openai_story_engine_summary as _cg_summary_module

logger = logging.getLogger(__name__)



def _remaining_generation_budget_seconds(*, started_at: float) -> int | None:
    return _runtime_remaining_generation_budget_seconds(started_at=started_at)



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



def _emit_progress(progress_callback: Callable[[dict[str, Any]], None] | None, snapshot: dict[str, Any] | None) -> None:
    _emit_progress_impl(progress_callback, snapshot)



def _pending_arc_window_preview(story_bible: dict[str, Any], *, current_chapter_no: int) -> tuple[int, int, int]:
    return _pending_arc_window_preview_impl(story_bible, current_chapter_no=current_chapter_no)





def apply_soft_card_ranking_to_packet(packet: dict[str, Any], *, chapter_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    return _apply_soft_card_ranking_to_packet_impl(packet, chapter_plan=chapter_plan)


def summarize_chapter(title: str, content: str, request_timeout_seconds: int | None = None):
    return _summarize_chapter_impl(title=title, content=content, request_timeout_seconds=request_timeout_seconds)


def _run_constraint_reasoning_for_generation(original_fn: Callable[..., dict[str, Any]], *args, **kwargs) -> dict[str, Any]:
    filtered_kwargs = {key: value for key, value in kwargs.items() if key != "allow_ai"}
    if bool(_llm_is_openai_enabled()):
        return original_fn(*args, allow_ai=True, **filtered_kwargs)
    baseline_builder = filtered_kwargs.get("baseline_builder")
    packet = {
        "task_type": filtered_kwargs.get("task_type"),
        "scope": filtered_kwargs.get("scope"),
        "chapter_no": int(filtered_kwargs.get("chapter_no", 0) or 0),
        "local_context": filtered_kwargs.get("local_context") or {},
        "hard_constraints": list(filtered_kwargs.get("hard_constraints") or []),
        "soft_goals": list(filtered_kwargs.get("soft_goals") or []),
        "output_contract": filtered_kwargs.get("output_contract") or {},
    }
    baseline_result = baseline_builder(packet) if callable(baseline_builder) else {}
    return {
        "result": baseline_result or {},
        "used_ai": False,
        "reason": "generation_compat_baseline",
        "confidence": "fallback",
        "constraint_checks": ["generation_compat_baseline"],
    }


def _heuristic_run_chapter_preparation_selection(*, chapter_plan: dict[str, Any], planning_packet: dict[str, Any], request_timeout_seconds: int | None = None):
    schedule_review = _cg_selection_boundary_module.review_character_relation_schedule(chapter_plan=chapter_plan, planning_packet=planning_packet)
    card_ids = [
        str(item.get("card_id") or "").strip()
        for item in (((planning_packet or {}).get("card_index") or {}).get("entries") or [])
        if isinstance(item, dict) and str(item.get("card_id") or "").strip()
    ][:12]
    payoff_candidates = [item for item in (((planning_packet or {}).get("payoff_candidate_index") or {}).get("candidates") or []) if isinstance(item, dict)]
    payoff_id = str((payoff_candidates[0] or {}).get("card_id") or "").strip() if payoff_candidates else None
    scene_candidates = [item for item in (((planning_packet or {}).get("scene_template_index") or {}).get("candidates") or []) if isinstance(item, dict)]
    if not scene_candidates:
        raw_templates = ((planning_packet or {}).get("scene_template_index") or {}).get("templates") or []
        scene_candidates = [item for item in raw_templates if isinstance(item, dict)]
    scene_ids = [str(item.get("template_id") or item.get("scene_template_id") or item.get("id") or "").strip() for item in scene_candidates if str(item.get("template_id") or item.get("scene_template_id") or item.get("id") or "").strip()][:3]
    flow_templates = [item for item in ((planning_packet or {}).get("flow_template_index") or []) if isinstance(item, dict)]
    flow_id = str(chapter_plan.get("flow_template_id") or (flow_templates[0].get("template_id") if flow_templates else "") or "").strip() or None
    prompt_strategies = [item for item in ((planning_packet or {}).get("prompt_strategy_index") or []) if isinstance(item, dict)]
    strategy_ids = [str(item.get("strategy_id") or item.get("id") or "").strip() for item in prompt_strategies if str(item.get("strategy_id") or item.get("id") or "").strip()][:3]
    return _cg_selection_boundary_module.ChapterPreparationSelectionResult(
        schedule_review=schedule_review,
        card_selection=_cg_selection_boundary_module.ChapterCardSelectionPayload(selected_card_ids=card_ids, selection_note="AI 不可用，已使用兼容启发式选卡。"),
        payoff_selection=_cg_selection_boundary_module.PayoffSelectionPayload(selected_card_id=payoff_id, selection_note="AI 不可用，已使用兼容启发式爽点选卡。"),
        scene_selection=_cg_selection_boundary_module.SceneTemplateSelectionPayload(selected_scene_template_ids=scene_ids, selection_note="AI 不可用，已使用兼容启发式场景链。"),
        prompt_strategy_selection=_cg_selection_boundary_module.PromptStrategySelectionPayload(selected_flow_template_id=flow_id, selected_strategy_ids=strategy_ids, selection_note="AI 不可用，已使用兼容启发式 prompt 策略。"),
        selection_trace={"selection_scope": {"mode": "generation_compat_heuristic", "request_timeout_seconds": request_timeout_seconds}},
    )


def _review_payoff_delivery_for_generation(*, title: str, content: str, chapter_plan: dict[str, Any], local_review: dict[str, Any]) -> dict[str, Any]:
    if bool(_llm_is_openai_enabled()):
        return _cg_draft_module.review_payoff_delivery_with_ai(title=title, content=content, chapter_plan=chapter_plan, local_review=local_review)
    return dict(local_review or {})


def _summary_title_package_for_generation(**kwargs):
    if bool(_llm_is_openai_enabled()):
        return _cg_summary_module.generate_chapter_summary_and_title_package(**kwargs)
    summary_obj = summarize_chapter(kwargs.get("title") or "", kwargs.get("content") or "", request_timeout_seconds=kwargs.get("request_timeout_seconds"))
    if hasattr(summary_obj, "model_dump"):
        summary_data = summary_obj.model_dump(mode="python")
    elif hasattr(summary_obj, "dict"):
        summary_data = summary_obj.dict()
    elif hasattr(summary_obj, "__dict__"):
        summary_data = dict(summary_obj.__dict__)
    else:
        summary_data = dict(summary_obj or {})
    summary = _cg_summary_module.ChapterSummaryPayload.model_validate(summary_data)
    title_text = str(kwargs.get("title") or (kwargs.get("chapter_plan") or {}).get("title") or "未命名章节").strip() or "未命名章节"
    refinement = _cg_summary_module.ChapterTitleRefinementPayload(recommended_title=title_text, candidates=[])
    return _cg_summary_module.ChapterSummaryTitlePackagePayload(summary=summary, title_refinement=refinement)


def _runtime_stage_casting_extra(execution_brief: dict[str, Any] | None) -> dict[str, Any]:
    return _runtime_stage_casting_extra_impl(execution_brief)



def _runtime_payoff_extra(execution_brief: dict[str, Any] | None) -> dict[str, Any]:
    return _runtime_payoff_extra_impl(execution_brief)



def _runtime_payoff_delivery_extra(payoff_delivery: dict[str, Any] | None) -> dict[str, Any]:
    return _runtime_payoff_delivery_extra_impl(payoff_delivery)



def _apply_pending_payoff_compensation_to_plan(story_bible: dict[str, Any], plan: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    return _apply_pending_payoff_compensation_to_plan_impl(story_bible, plan, chapter_no=chapter_no)



def parse_reader_instruction(raw_instruction: str) -> dict:
    return parse_instruction_with_openai(raw_instruction).model_dump(mode="python")



def collect_active_interventions(db: Session, novel_id: int, next_chapter_no: int) -> list[Intervention]:
    return _collect_active_interventions_impl(db, novel_id, next_chapter_no)



def _load_recent_titles(db: Session, novel_id: int, *, limit: int | None = None) -> list[str]:
    return _load_recent_titles_impl(db, novel_id, limit=limit)



def _persist_chapter_and_summary(
    db: Session,
    novel: Novel,
    chapter_no: int,
    chapter_title: str,
    content: str,
    generation_meta: dict[str, Any],
    event_summary: str,
    character_updates: dict[str, Any],
    new_clues: list[str],
    open_hooks: list[str],
    closed_hooks: list[str],
) -> Chapter:
    return _persist_chapter_and_summary_impl(
        db=db,
        novel=novel,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        content=content,
        generation_meta=generation_meta,
        event_summary=event_summary,
        character_updates=character_updates,
        new_clues=new_clues,
        open_hooks=open_hooks,
        closed_hooks=closed_hooks,
    )



def _auto_prepare_future_planning(
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

    _emit_progress(progress_callback, {
        "stage": "planning_refresh_check",
        "stage_label": "近5章规划检查",
        "message": f"正在检查近{settings.arc_outline_size}章规划：当前已规划到第{planned_until}章，队列有{len(queue)}张章节卡。",
        "target_chapter_no": current_chapter_no + 1,
        "current_chapter_no": current_chapter_no,
        "queue_size": len(queue),
        "ready_cards": [int(item.get("chapter_no", 0) or 0) for item in queue[: settings.planning_window_size]],
        "arc_remaining": remaining,
        "planned_until": planned_until,
        "need_refresh": bool(need_prefetch),
        "pending_arc_exists": bool(pending_arc),
    })

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
        start_preview, end_preview, arc_no_preview = _pending_arc_window_preview(story_bible, current_chapter_no=current_chapter_no)
        reason = "queue_low" if len(queue) < settings.planning_window_size else "active_arc_nearly_exhausted"
        _emit_progress(progress_callback, {
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
        })
        bundle_meta = _generate_and_store_pending_arc(db, novel, recent_summaries, replace_existing=False)
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
        _emit_progress(progress_callback, {
            "stage": "planning_refresh_completed",
            "stage_label": "近5章规划已更新",
            "message": f"近{settings.arc_outline_size}章规划已更新：新增第{int((bundle_meta or {}).get('start_chapter', start_preview) or start_preview)}-{int((bundle_meta or {}).get('end_chapter', end_preview) or end_preview)}章。",
            "target_chapter_no": current_chapter_no + 1,
            "refresh_reason": reason,
            **refresh_summary,
        })
        auto_prefetched = True
    else:
        _emit_progress(progress_callback, {
            "stage": "planning_refresh_ready",
            "stage_label": "近5章规划就绪",
            "message": f"近{settings.arc_outline_size}章规划已就绪：下一章直接承接现有规划，当前章节卡覆盖到第{int((queue[-1].get('chapter_no', 0) if queue else planned_until) or planned_until)}章。",
            "target_chapter_no": current_chapter_no + 1,
            **refresh_summary,
        })

    db.add(novel)
    return {
        **_planning_runtime_meta(novel.story_bible or {}),
        "auto_prefetched": auto_prefetched,
        "arc_remaining": remaining,
        "planning_refresh": refresh_summary,
    }


def _serial_delivery_mode(story_bible: dict[str, Any]) -> str:
    return _serial_delivery_mode_impl(story_bible)



def _chapter_serial_stage_for_mode(delivery_mode: str) -> str:
    return _chapter_serial_stage_for_mode_impl(delivery_mode)



def _refresh_serial_layers_from_db(db: Session, novel: Novel) -> Novel:
    return _refresh_serial_layers_from_db_impl(db, novel)



def _mark_generated_chapter_delivery(db: Session, novel: Novel, chapter: Chapter) -> tuple[Novel, dict[str, Any]]:
    return _mark_generated_chapter_delivery_impl(db, novel, chapter)




def _sync_split_generation_compat() -> None:
    # Keep legacy monkeypatch-based tests and callers working after module splits.
    _cg_prepare_module._validate_required_planning_docs = _validate_required_planning_docs
    _cg_prepare_module._validate_fact_ledger_state = _validate_fact_ledger_state
    _cg_prepare_module._promote_pending_arc_if_needed = _promote_pending_arc_if_needed
    _cg_prepare_module._ensure_outline_state = _ensure_outline_state
    _cg_prepare_module.ensure_story_architecture = ensure_story_architecture
    _cg_prepare_module.refresh_planning_views = refresh_planning_views
    _cg_prepare_module.collect_active_interventions = collect_active_interventions
    _cg_prepare_module._serialize_active_interventions = _serialize_active_interventions
    _cg_prepare_module._serialize_last_chapter = _serialize_last_chapter
    _cg_prepare_module.build_chapter_plan_packet = build_chapter_plan_packet
    _cg_prepare_module.run_chapter_preparation_selection = run_chapter_preparation_selection
    _cg_prepare_module.apply_schedule_review_to_packet = apply_schedule_review_to_packet
    _cg_prepare_module.apply_card_selection_to_packet = apply_card_selection_to_packet
    _cg_prepare_module.serialize_local_novel_context = serialize_local_novel_context
    _cg_prepare_module._fit_chapter_payload_budget = _fit_chapter_payload_budget
    _cg_prepare_module._save_pipeline_execution_packet = _save_pipeline_execution_packet
    _cg_prepare_module._enrich_plan_agency = _enrich_plan_agency
    _cg_prepare_module._ensure_plan_for_chapter = _ensure_plan_for_chapter
    _cg_prepare_module.auto_prepare_future_planning = _auto_prepare_future_planning

    _cg_draft_module._attempt_generate_validated_chapter = _attempt_generate_validated_chapter

    _cg_finalize_prepare_module.generate_chapter_summary_and_title_package = generate_chapter_summary_and_title_package
    _cg_finalize_prepare_module.validate_and_register_chapter = validate_and_register_chapter
    _cg_finalize_prepare_module.update_story_architecture_after_chapter = update_story_architecture_after_chapter
    _cg_finalize_prepare_module.sync_character_registry = sync_character_registry

    _cg_finalize_commit_module._mark_generated_chapter_delivery = _mark_generated_chapter_delivery
    _cg_finalize_commit_module._auto_prepare_future_planning_impl = _auto_prepare_future_planning


def generate_next_chapter(db: Session, novel: Novel | int) -> Chapter:
    _sync_split_generation_compat()
    original_allow_ai = getattr(_cg_context_support_module, "_planning_importance_allow_ai", None)
    original_constraint_reasoning = getattr(_cg_resource_card_support_module, "run_local_constraint_reasoning", None)
    original_selection_runner = getattr(_cg_prepare_module, "run_chapter_preparation_selection", None)
    original_payoff_review = getattr(_cg_draft_module, "review_payoff_delivery_with_ai", None)
    original_summary_package = getattr(_cg_finalize_prepare_module, "generate_chapter_summary_and_title_package", None)
    _cg_context_support_module._planning_importance_allow_ai = lambda story_bible, *, chapter_no: bool(_llm_is_openai_enabled())
    if original_constraint_reasoning is not None:
        _cg_resource_card_support_module.run_local_constraint_reasoning = lambda *args, **kwargs: _run_constraint_reasoning_for_generation(original_constraint_reasoning, *args, **kwargs)
    if not bool(_llm_is_openai_enabled()):
        if original_selection_runner is not None:
            _cg_prepare_module.run_chapter_preparation_selection = _heuristic_run_chapter_preparation_selection
        if original_payoff_review is not None:
            _cg_draft_module.review_payoff_delivery_with_ai = _review_payoff_delivery_for_generation
        if original_summary_package is not None and getattr(original_summary_package, "__module__", "").startswith("app.services.openai_story_engine"):
            _cg_finalize_prepare_module.generate_chapter_summary_and_title_package = _summary_title_package_for_generation
    try:
        return _entry_generate_next_chapter(db, novel)
    finally:
        if original_allow_ai is not None:
            _cg_context_support_module._planning_importance_allow_ai = original_allow_ai
        if original_constraint_reasoning is not None:
            _cg_resource_card_support_module.run_local_constraint_reasoning = original_constraint_reasoning
        if original_selection_runner is not None:
            _cg_prepare_module.run_chapter_preparation_selection = original_selection_runner
        if original_payoff_review is not None:
            _cg_draft_module.review_payoff_delivery_with_ai = original_payoff_review
        if original_summary_package is not None:
            _cg_finalize_prepare_module.generate_chapter_summary_and_title_package = original_summary_package


def generate_next_chapters_batch(db: Session, novel: Novel | int, *, count: int = 1) -> list[Chapter]:
    _sync_split_generation_compat()
    original_allow_ai = getattr(_cg_context_support_module, "_planning_importance_allow_ai", None)
    original_constraint_reasoning = getattr(_cg_resource_card_support_module, "run_local_constraint_reasoning", None)
    original_selection_runner = getattr(_cg_prepare_module, "run_chapter_preparation_selection", None)
    original_payoff_review = getattr(_cg_draft_module, "review_payoff_delivery_with_ai", None)
    original_summary_package = getattr(_cg_finalize_prepare_module, "generate_chapter_summary_and_title_package", None)
    _cg_context_support_module._planning_importance_allow_ai = lambda story_bible, *, chapter_no: bool(_llm_is_openai_enabled())
    if original_constraint_reasoning is not None:
        _cg_resource_card_support_module.run_local_constraint_reasoning = lambda *args, **kwargs: _run_constraint_reasoning_for_generation(original_constraint_reasoning, *args, **kwargs)
    if not bool(_llm_is_openai_enabled()):
        if original_selection_runner is not None:
            _cg_prepare_module.run_chapter_preparation_selection = _heuristic_run_chapter_preparation_selection
        if original_payoff_review is not None:
            _cg_draft_module.review_payoff_delivery_with_ai = _review_payoff_delivery_for_generation
        if original_summary_package is not None and getattr(original_summary_package, "__module__", "").startswith("app.services.openai_story_engine"):
            _cg_finalize_prepare_module.generate_chapter_summary_and_title_package = _summary_title_package_for_generation
    try:
        return _entry_generate_next_chapters_batch(db, novel, count=count)
    finally:
        if original_allow_ai is not None:
            _cg_context_support_module._planning_importance_allow_ai = original_allow_ai
        if original_constraint_reasoning is not None:
            _cg_resource_card_support_module.run_local_constraint_reasoning = original_constraint_reasoning
        if original_selection_runner is not None:
            _cg_prepare_module.run_chapter_preparation_selection = original_selection_runner
        if original_payoff_review is not None:
            _cg_draft_module.review_payoff_delivery_with_ai = original_payoff_review
        if original_summary_package is not None:
            _cg_finalize_prepare_module.generate_chapter_summary_and_title_package = original_summary_package
