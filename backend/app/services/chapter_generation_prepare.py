from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.novel import Novel
from app.services.card_indexing import apply_card_selection_to_packet
from app.services.chapter_context_serialization import _load_recent_chapters, _serialize_active_interventions, _serialize_last_chapter, _serialize_recent_summaries, _validate_fact_ledger_state, serialize_local_novel_context
from app.services.chapter_context_support import build_chapter_plan_packet
from app.services.chapter_generation_persistence import collect_active_interventions
from app.services.chapter_generation_postprocess import apply_pending_payoff_compensation_to_plan
from app.services.chapter_generation_planning import auto_prepare_future_planning
from app.services.chapter_generation_support import _compact_value, _save_pipeline_execution_packet, _truncate_text
from app.services.chapter_payload_budget import _fit_chapter_payload_budget
from app.services.chapter_generation_types import PreparedChapterState
from app.services.chapter_planning_support import _ensure_outline_state, _ensure_plan_for_chapter, _promote_pending_arc_if_needed, _validate_required_planning_docs
from app.services.chapter_preparation_selection import run_chapter_preparation_selection
from app.services.chapter_retry_support import _enrich_plan_agency
from app.services.chapter_runtime_support import _commit_runtime_snapshot, _ensure_generation_runtime_budget, _planning_runtime_meta, _runtime_payoff_extra, _runtime_stage_casting_extra
from app.services.openai_story_engine_selection import apply_schedule_review_to_packet
from app.services.payoff_cards import realize_payoff_selection_from_index
from app.services.preparation_diagnostics import build_preparation_diagnostics, build_preparation_runtime_extra
from app.services.prompt_strategy_library import apply_prompt_strategy_selection_to_packet
from app.services.scene_templates import realize_scene_sequence_from_selection
from app.services.story_architecture import ensure_story_architecture, refresh_planning_views


def load_recent_generation_state(db: Session, locked_novel: Novel) -> dict[str, Any]:
    recent_chapters = _load_recent_chapters(db, locked_novel.id, limit=3)
    last_chapter = recent_chapters[-1] if recent_chapters else None
    recent_full_texts = [item.content for item in recent_chapters]
    recent_plan_meta: list[dict[str, Any]] = []
    for item in recent_chapters:
        meta = item.generation_meta or {}
        if not isinstance(meta, dict):
            continue
        plan_meta = dict((meta.get("chapter_plan") or {}))
        payoff_meta = meta.get("payoff_delivery") or {}
        if isinstance(payoff_meta, dict) and payoff_meta:
            plan_meta["_payoff_delivery"] = {
                "delivery_level": payoff_meta.get("delivery_level"),
                "delivery_score": payoff_meta.get("delivery_score"),
                "verdict": payoff_meta.get("verdict"),
            }
        recent_plan_meta.append(plan_meta)
    return {
        "last_chapter": last_chapter,
        "recent_full_texts": recent_full_texts,
        "recent_plan_meta": recent_plan_meta,
        "recent_summaries": _serialize_recent_summaries(db, locked_novel.id),
    }


def refresh_story_bible_for_generation(
    db: Session,
    locked_novel: Novel,
    *,
    next_no: int,
    chapter_started_at: float,
    recent_summaries: list[dict[str, Any]],
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> tuple[Novel, dict[str, Any]]:
    story_bible = ensure_story_architecture(locked_novel.story_bible or {}, locked_novel)
    _ensure_outline_state(story_bible)
    _validate_required_planning_docs(story_bible, next_no)
    _validate_fact_ledger_state(story_bible, next_no)
    _promote_pending_arc_if_needed(story_bible, next_no)
    story_bible = refresh_planning_views(story_bible, locked_novel.current_chapter_no)
    locked_novel.story_bible = story_bible
    db.add(locked_novel)

    _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_planning_prefetch", chapter_no=next_no)
    planning_meta = auto_prepare_future_planning(
        db,
        locked_novel,
        current_chapter_no=locked_novel.current_chapter_no,
        recent_summaries=recent_summaries,
        progress_callback=progress_callback,
    )
    locked_novel = _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="reading_state",
        note=("第 {0} 章已完成定位、读状态与补规划准备。".format(next_no)),
        extra=planning_meta,
    )
    return locked_novel, story_bible


def build_plan_execution_bundle(
    db: Session,
    locked_novel: Novel,
    *,
    next_no: int,
    chapter_started_at: float,
    recent_summaries: list[dict[str, Any]],
    recent_plan_meta: list[dict[str, Any]],
    last_chapter: Any,
) -> dict[str, Any]:
    _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_plan_prepare", chapter_no=next_no)
    plan = _ensure_plan_for_chapter(db, locked_novel, next_no, recent_summaries)
    plan = _enrich_plan_agency(locked_novel, plan, recent_plan_meta=recent_plan_meta)
    plan = apply_pending_payoff_compensation_to_plan(locked_novel.story_bible or {}, plan, chapter_no=next_no)
    story_bible = ensure_story_architecture(locked_novel.story_bible or {}, locked_novel)
    story_bible = refresh_planning_views(story_bible, locked_novel.current_chapter_no)
    locked_novel.story_bible = story_bible
    db.add(locked_novel)

    active_interventions = collect_active_interventions(db, locked_novel.id, next_no)
    serialized_active = _serialize_active_interventions(active_interventions)
    serialized_last = _serialize_last_chapter(last_chapter, protagonist_name=locked_novel.protagonist_name)
    chapter_plan_packet = build_chapter_plan_packet(
        story_bible=story_bible,
        protagonist_name=locked_novel.protagonist_name,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=recent_summaries,
        recent_plan_meta=recent_plan_meta,
    )
    chapter_plan_packet["selection_runtime"] = {
        "preparation_stages": ["index_compress", "ai_shortlist", "parallel_selection", "merge", "assembly"],
        "selection_mode": "ai_multistage_compressed_selection",
        "parallel_enabled": bool(getattr(settings, "chapter_preparation_parallel_selection_enabled", True)),
        "selection_scope": ["schedule", "cards", "payoff", "scene_templates", "flow_templates", "prompt_strategies"],
        "assembly_rule": "本地只负责压缩、合法性校验与拼装；所有主筛选与统一仲裁均由 AI 完成，失败即停止生成。",
    }
    frontload_timeout = int(getattr(settings, "chapter_frontload_decision_timeout_seconds", 0) or 0)
    selection_result = run_chapter_preparation_selection(
        chapter_plan=plan,
        planning_packet=chapter_plan_packet,
        request_timeout_seconds=frontload_timeout or None,
    )
    chapter_plan_packet = apply_schedule_review_to_packet(chapter_plan_packet, selection_result.schedule_review)
    chapter_plan_packet = apply_card_selection_to_packet(
        chapter_plan_packet,
        selection_result.card_selection.selected_card_ids,
        selection_note=selection_result.card_selection.selection_note,
    )
    chapter_plan_packet = apply_prompt_strategy_selection_to_packet(
        chapter_plan_packet,
        selection_result.prompt_strategy_selection.selected_strategy_ids,
        selected_flow_template_id=selection_result.prompt_strategy_selection.selected_flow_template_id,
        selection_note=selection_result.prompt_strategy_selection.selection_note,
    )
    payoff_runtime = realize_payoff_selection_from_index(
        story_bible=story_bible,
        plan=plan,
        selected_card_id=selection_result.payoff_selection.selected_card_id,
        recent_summaries=recent_summaries,
        recent_plan_meta=recent_plan_meta,
        selection_note=selection_result.payoff_selection.selection_note,
    )
    chapter_plan_packet["payoff_runtime"] = payoff_runtime
    chapter_plan_packet["payoff_compensation"] = payoff_runtime.get("payoff_compensation") or plan.get("payoff_compensation") or {}
    chapter_plan_packet["selected_payoff_card"] = payoff_runtime.get("selected_payoff_card") or {}
    scene_runtime = realize_scene_sequence_from_selection(
        story_bible=story_bible,
        plan={
            **plan,
            "payoff_mode": ((payoff_runtime.get("selected_payoff_card") or {}).get("payoff_mode")) or plan.get("payoff_mode"),
        },
        serialized_last=serialized_last,
        recent_summaries=recent_summaries,
        selected_scene_template_ids=selection_result.scene_selection.selected_scene_template_ids,
    )
    chapter_plan_packet["scene_runtime"] = scene_runtime
    chapter_plan_packet["scene_sequence_plan"] = scene_runtime.get("scene_sequence_plan") or []
    chapter_plan_packet["scene_execution_card"] = scene_runtime.get("scene_execution_card") or {}
    selection_scope = (selection_result.selection_trace or {}).get("selection_scope") or {}
    preparation_diagnostics = build_preparation_diagnostics(
        planning_packet=chapter_plan_packet,
        selection_trace=selection_result.selection_trace,
    )
    chapter_plan_packet["preparation_selection"] = {
        "schedule_review": selection_result.schedule_review.model_dump(mode="python"),
        "card_selection": selection_result.card_selection.model_dump(mode="python"),
        "payoff_selection": selection_result.payoff_selection.model_dump(mode="python"),
        "scene_selection": selection_result.scene_selection.model_dump(mode="python"),
        "prompt_strategy_selection": selection_result.prompt_strategy_selection.model_dump(mode="python"),
        "selection_scope_stats": (selection_scope.get("stats") or {}),
        "selection_trace": selection_result.selection_trace,
        "diagnostics": preparation_diagnostics,
    }
    chapter_plan_packet["selection_runtime"] = {
        **(chapter_plan_packet.get("selection_runtime") or {}),
        "selection_scope_stats": selection_scope.get("stats") or {},
        "diagnostics": preparation_diagnostics,
        **build_preparation_runtime_extra(preparation_diagnostics),
    }
    selected_payoff_card = chapter_plan_packet.get("selected_payoff_card") or {}
    selected_flow_template = chapter_plan_packet.get("selected_flow_template") or {}
    plan = {
        **plan,
        "flow_template_id": selected_flow_template.get("flow_id") or chapter_plan_packet.get("chapter_identity", {}).get("flow_template_id") or plan.get("flow_template_id"),
        "flow_template_tag": selected_flow_template.get("quick_tag") or chapter_plan_packet.get("chapter_identity", {}).get("flow_template_tag") or plan.get("flow_template_tag"),
        "flow_template_name": selected_flow_template.get("name") or chapter_plan_packet.get("chapter_identity", {}).get("flow_template_name") or plan.get("flow_template_name"),
        "flow_turning_points": list(selected_flow_template.get("turning_points") or chapter_plan_packet.get("flow_plan", {}).get("turning_points") or plan.get("flow_turning_points") or [])[:4],
        "flow_variation_note": selected_flow_template.get("variation_notes") or chapter_plan_packet.get("flow_plan", {}).get("variation_note") or plan.get("flow_variation_note"),
        "planning_packet": chapter_plan_packet,
        "selected_story_elements": chapter_plan_packet.get("selected_elements", {}),
        "related_story_cards": chapter_plan_packet.get("relevant_cards", {}),
        "continuity_window": chapter_plan_packet.get("continuity_window", {}),
        "payoff_mode": selected_payoff_card.get("payoff_mode"),
        "payoff_level": selected_payoff_card.get("payoff_level"),
        "payoff_visibility": selected_payoff_card.get("payoff_visibility"),
        "reader_payoff": selected_payoff_card.get("reader_payoff"),
        "new_pressure": selected_payoff_card.get("new_pressure"),
    }
    locked_novel.story_bible = story_bible
    db.add(locked_novel)
    execution_brief = _save_pipeline_execution_packet(
        novel=locked_novel,
        story_bible=story_bible,
        next_chapter_no=next_no,
        plan=plan,
        last_chapter_tail=serialized_last.get("tail_excerpt", ""),
    )
    return {
        "story_bible": story_bible,
        "plan": plan,
        "chapter_plan_packet": chapter_plan_packet,
        "execution_brief": execution_brief,
        "active_interventions": active_interventions,
        "serialized_active": serialized_active,
        "serialized_last": serialized_last,
        "preparation_diagnostics": ((chapter_plan_packet.get("preparation_selection") or {}).get("diagnostics") or {}),
    }


def commit_outline_runtime(
    db: Session,
    locked_novel: Novel,
    *,
    next_no: int,
    plan: dict[str, Any],
    execution_brief: dict[str, Any],
) -> Novel:
    locked_novel = _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="chapter_outline_ready",
        note=f"第 {next_no} 章章纲已确定，准备落场景与正文。",
        extra={
            "chapter_title": plan.get("title") or f"第{next_no}章",
            "chapter_goal": _truncate_text(plan.get("goal"), 80),
            **_runtime_stage_casting_extra(execution_brief),
            **_runtime_payoff_extra(execution_brief),
            **_planning_runtime_meta(locked_novel.story_bible or {}),
        },
    )
    return _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="scene_outline_ready",
        note=f"第 {next_no} 章场景顺序已固定，将按场景推进正文。",
        extra={
            "scene_outline": _compact_value((execution_brief or {}).get("scene_outline", []), text_limit=68),
            **_runtime_stage_casting_extra(execution_brief),
            **_runtime_payoff_extra(execution_brief),
            **_planning_runtime_meta(locked_novel.story_bible or {}),
        },
    )


def assemble_draft_context(
    db: Session,
    locked_novel: Novel,
    *,
    next_no: int,
    recent_summaries: list[dict[str, Any]],
    chapter_plan_packet: dict[str, Any],
    execution_brief: dict[str, Any],
    serialized_last: dict[str, Any],
    serialized_active: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    novel_context = serialize_local_novel_context(
        novel=locked_novel,
        next_no=next_no,
        recent_summaries=recent_summaries,
        chapter_plan_packet=chapter_plan_packet,
        execution_brief=execution_brief,
    )
    return _fit_chapter_payload_budget(
        novel_context=novel_context,
        recent_summaries=recent_summaries,
        serialized_last=serialized_last,
        serialized_active=serialized_active,
    )


def prepare_generation_context(
    db: Session,
    locked_novel: Novel,
    *,
    next_no: int,
    chapter_started_at: float,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> PreparedChapterState:
    history = load_recent_generation_state(db, locked_novel)
    last_chapter = history["last_chapter"]
    recent_full_texts = history["recent_full_texts"]
    recent_plan_meta = history["recent_plan_meta"]
    recent_summaries = history["recent_summaries"]

    locked_novel, story_bible = refresh_story_bible_for_generation(
        db,
        locked_novel,
        next_no=next_no,
        chapter_started_at=chapter_started_at,
        recent_summaries=recent_summaries,
        progress_callback=progress_callback,
    )
    plan_bundle = build_plan_execution_bundle(
        db,
        locked_novel,
        next_no=next_no,
        chapter_started_at=chapter_started_at,
        recent_summaries=recent_summaries,
        recent_plan_meta=recent_plan_meta,
        last_chapter=last_chapter,
    )
    story_bible = plan_bundle["story_bible"]
    plan = plan_bundle["plan"]
    chapter_plan_packet = plan_bundle["chapter_plan_packet"]
    execution_brief = plan_bundle["execution_brief"]
    active_interventions = plan_bundle["active_interventions"]
    serialized_active = plan_bundle["serialized_active"]
    serialized_last = plan_bundle["serialized_last"]
    preparation_diagnostics = plan_bundle.get("preparation_diagnostics") or {}

    _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="chapter_preparation_selected",
        note=f"第 {next_no} 章准备筛选已完成，正在固定执行卡与场景链。",
        extra={
            **_planning_runtime_meta(locked_novel.story_bible or {}),
            **build_preparation_runtime_extra(preparation_diagnostics),
        },
    )

    locked_novel = commit_outline_runtime(
        db,
        locked_novel,
        next_no=next_no,
        plan=plan,
        execution_brief=execution_brief,
    )
    novel_context, recent_summaries, serialized_last, serialized_active, context_stats = assemble_draft_context(
        db,
        locked_novel,
        next_no=next_no,
        recent_summaries=recent_summaries,
        chapter_plan_packet=chapter_plan_packet,
        execution_brief=execution_brief,
        serialized_last=serialized_last,
        serialized_active=serialized_active,
    )

    _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="drafting",
        note=f"第 {next_no} 章正文生成中，Story Workspace 与目录会自动刷新。",
        extra={
            **_planning_runtime_meta(locked_novel.story_bible or {}),
            **_runtime_stage_casting_extra(execution_brief),
            **_runtime_payoff_extra(execution_brief),
            "context_mode": novel_context.get("context_mode", settings.chapter_context_mode),
        },
    )
    return PreparedChapterState(
        locked_novel=locked_novel,
        next_no=next_no,
        last_chapter=last_chapter,
        recent_full_texts=recent_full_texts,
        recent_plan_meta=recent_plan_meta,
        recent_summaries=recent_summaries,
        story_bible=story_bible,
        plan=plan,
        chapter_plan_packet=chapter_plan_packet,
        execution_brief=execution_brief,
        serialized_last=serialized_last,
        serialized_active=serialized_active,
        active_interventions=active_interventions,
        novel_context=novel_context,
        context_stats=context_stats,
    )
