from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.chapter_context_common import _compact_value
from app.services.chapter_context_support import _compact_scene_card, _tail_paragraphs
from app.services.chapter_generation_persistence import _load_recent_titles
from app.services.chapter_generation_postprocess import serial_delivery_mode as _serial_delivery_mode
from app.services.chapter_generation_support import _truncate_list, _truncate_text
from app.services.chapter_generation_types import DraftPhaseResult
from app.services.chapter_runtime_support import (
    _commit_runtime_snapshot,
    _compute_llm_timeout_seconds,
    _ensure_generation_runtime_budget,
    _planning_runtime_meta,
)
from app.services.chapter_title_service import build_cooled_terms, normalize_title, refine_generated_chapter_title_from_candidates
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.hard_fact_guard import HardFactConflict, validate_and_register_chapter
from app.services.openai_story_engine_summary import generate_chapter_summary_and_title_package
from app.services.scene_templates import build_scene_handoff_card
from app.services.story_architecture import sync_character_registry, sync_monster_registry, update_story_architecture_after_chapter


@dataclass(slots=True)
class FinalizationSnapshot:
    locked_novel: Any
    next_no: int
    title: str
    content: str
    used_plan: dict[str, Any]
    payoff_delivery: dict[str, Any]
    summary: Any
    title_refinement_meta: dict[str, Any] | None
    chapter_fact_entries: list[dict[str, Any]]
    chapter_hard_facts: list[dict[str, Any]]
    chapter_hard_fact_report: dict[str, Any]
    continuity_bridge: dict[str, Any]
    generation_duration_ms: int


def prepare_finalization_snapshot(
    db: Session,
    draft: DraftPhaseResult,
    *,
    chapter_started_at: float,
) -> FinalizationSnapshot:
    prepared = draft.prepared
    locked_novel = prepared.locked_novel
    next_no = prepared.next_no
    title = draft.title
    content = draft.content
    used_plan = draft.used_plan
    payoff_delivery = draft.payoff_delivery

    recent_titles = _load_recent_titles(db, locked_novel.id)
    title_refinement_meta: dict[str, Any] | None = None
    locked_novel = _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="title_refinement",
        note=f"第 {next_no} 章正文已定稿，正在进行 AI 摘要与联合标题精修。",
        extra={
            **_planning_runtime_meta(locked_novel.story_bible or {}),
            "draft_title": title,
        },
    )
    _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_summary_title_package", chapter_no=next_no)
    package_timeout = _compute_llm_timeout_seconds(
        started_at=chapter_started_at,
        chapter_no=next_no,
        stage="chapter_summary_title_package",
        reserve_seconds=6,
    )
    recent_clean = [normalize_title(item) for item in recent_titles if normalize_title(item)]
    recent_window = max(int(getattr(settings, "chapter_title_recent_window", 20) or 20), 5)
    recent_window_titles = recent_clean[-recent_window:]
    cooled_terms = build_cooled_terms(recent_window_titles)
    summary_title_package = generate_chapter_summary_and_title_package(
        chapter_no=next_no,
        title=title,
        content=content,
        chapter_plan=used_plan,
        recent_titles=recent_window_titles,
        cooled_terms=cooled_terms,
        candidate_count=max(int(getattr(settings, "chapter_title_refinement_candidate_count", 5) or 5), 3),
        request_timeout_seconds=package_timeout,
    )
    summary = summary_title_package.summary
    raw_title_candidates: list[dict[str, Any]] = []
    if summary_title_package.title_refinement.recommended_title:
        raw_title_candidates.append(
            {
                "title": summary_title_package.title_refinement.recommended_title,
                "title_type": "推荐标题",
                "angle": "模型推荐",
                "reason": "联合后处理中模型最推荐的标题。",
                "source": "ai_recommended",
            }
        )
    for item in summary_title_package.title_refinement.candidates:
        raw_title_candidates.append(
            {
                "title": item.title,
                "title_type": item.title_type,
                "angle": item.angle,
                "reason": item.reason,
                "source": "ai",
            }
        )
    refinement_result = refine_generated_chapter_title_from_candidates(
        chapter_no=next_no,
        original_title=title,
        plan=used_plan,
        recent_titles=recent_titles,
        summary=summary.model_dump(mode="python"),
        raw_candidates=raw_title_candidates,
        ai_attempted=True,
        ai_succeeded=bool(raw_title_candidates),
        ai_error=None,
    )
    refined_title = refinement_result.final_title or title
    title_refinement_meta = {
        "enabled": True,
        "joint_call": True,
        "source_stage": "chapter_summary_title_package",
        "original_title": refinement_result.original_title,
        "final_title": refined_title,
        "ai_attempted": refinement_result.ai_attempted,
        "ai_succeeded": refinement_result.ai_succeeded,
        "ai_error": refinement_result.ai_error,
        "recent_titles": refinement_result.recent_titles,
        "cooled_terms": refinement_result.cooled_terms,
        "candidates": [
            {
                "title": item.title,
                "score": item.total_score,
                "duplicate_risk": item.duplicate_risk,
                "source": item.source,
                "title_type": item.title_type,
                "angle": item.angle,
                "reason": item.reason,
                "notes": item.notes,
            }
            for item in refinement_result.candidates[:8]
        ],
    }
    title = refined_title
    used_plan["original_planned_title"] = refinement_result.original_title
    used_plan["title"] = refined_title
    delivery_mode_for_guard = _serial_delivery_mode(locked_novel.story_bible or {})
    guard_serial_stage = "published" if delivery_mode_for_guard == "live_publish" else "stock"
    try:
        locked_novel.story_bible, chapter_hard_facts, chapter_hard_fact_report = validate_and_register_chapter(
            locked_novel.story_bible or {},
            protagonist_name=locked_novel.protagonist_name,
            chapter_no=next_no,
            chapter_title=title,
            content=content,
            plan=used_plan,
            summary=summary,
            serial_stage=guard_serial_stage,
            reference_mode="stock",
            raise_on_conflict=True,
        )
    except HardFactConflict as exc:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_HARD_FACT_CONFLICT,
            message=f"第 {next_no} 章与前文硬事实冲突，已拒绝入库，请调整后重试。",
            stage="hard_fact_validation",
            retryable=True,
            http_status=409,
            details=exc.report,
        ) from exc
    locked_novel.story_bible = update_story_architecture_after_chapter(
        story_bible=locked_novel.story_bible or {},
        novel=locked_novel,
        chapter_no=next_no,
        chapter_title=title,
        plan=used_plan,
        summary=summary,
        last_chapter_tail=prepared.serialized_last.get("tail_excerpt", ""),
        chapter_content=content,
        payoff_delivery=payoff_delivery,
    )
    sync_character_registry(
        db,
        locked_novel,
        story_bible=locked_novel.story_bible or {},
        plan=used_plan,
        summary=summary,
    )
    sync_monster_registry(
        db,
        locked_novel,
        story_bible=locked_novel.story_bible or {},
        plan=used_plan,
        summary=summary,
    )
    locked_novel = _commit_runtime_snapshot(
        db,
        locked_novel,
        next_chapter_no=next_no,
        stage="state_updated",
        note=f"第 {next_no} 章摘要、角色状态、伏笔状态与长期状态层已更新。",
        extra={
            **_planning_runtime_meta(locked_novel.story_bible or {}),
            "history_summary_count": len((((locked_novel.story_bible or {}).get("long_term_state") or {}).get("history_summaries") or [])),
        },
    )

    fact_entries = ((locked_novel.story_bible or {}).get("fact_ledger") or {})
    chapter_fact_entries = [
        item
        for item in ((fact_entries.get("published_facts") or []) + (fact_entries.get("stock_facts") or []))
        if int(item.get("chapter_no", 0) or 0) == next_no
    ]

    scene_card = ((prepared.execution_brief or {}).get("scene_execution_card") or {}) if isinstance(prepared.execution_brief, dict) else {}
    scene_outline = ((prepared.execution_brief or {}).get("scene_outline") or []) if isinstance(prepared.execution_brief, dict) else []
    scene_handoff_card = build_scene_handoff_card(
        story_bible=locked_novel.story_bible or {},
        plan=used_plan,
        scene_runtime={
            "scene_execution_card": scene_card,
            "scene_sequence_plan": ((prepared.execution_brief or {}).get("scene_sequence_plan") or []) if isinstance(prepared.execution_brief, dict) else [],
        },
        summary=summary,
        content=content,
        protagonist_name=locked_novel.protagonist_name,
    )
    continuity_bridge = {
        "source_chapter_no": next_no,
        "title": _truncate_text(title, 30),
        "tail_excerpt": _truncate_text(content[-settings.chapter_last_excerpt_chars :], settings.chapter_last_excerpt_chars),
        "last_two_paragraphs": _tail_paragraphs(content, count=2),
        "last_scene_card": _compact_scene_card(used_plan),
        "scene_execution_card": {
            "scene_count": int(scene_card.get("scene_count", 0) or 0),
            "transition_mode": _truncate_text(scene_card.get("transition_mode"), 24),
            "must_continue_same_scene": bool(scene_card.get("must_continue_same_scene")),
            "first_scene_focus": _truncate_text(scene_card.get("first_scene_focus"), 28),
            "sequence_note": _truncate_text(scene_card.get("sequence_note"), 84),
        },
        "scene_outline": _compact_value(scene_outline, text_limit=72),
        "scene_handoff_card": scene_handoff_card,
        "unresolved_action_chain": _truncate_list(summary.open_hooks, max_items=3, item_limit=64),
        "carry_over_clues": _truncate_list(summary.new_clues, max_items=3, item_limit=56),
        "onstage_characters": _truncate_list(
            [locked_novel.protagonist_name, used_plan.get("supporting_character_focus")]
            + [
                str(key).strip()
                for key in list((summary.character_updates or {}).keys())
                if str(key).strip() and str(key).strip() != "notes" and not str(key).strip().startswith("__")
            ],
            max_items=5,
            item_limit=20,
        ),
        "next_opening_instruction": _truncate_text(used_plan.get("opening_beat") or "下一章开头必须承接这一章最后动作、对话或局势变化。", 72),
        "opening_anchor": _truncate_text((_tail_paragraphs(content, count=1) or [content[-160:]])[-1], 120),
    }
    story_bible_runtime = (locked_novel.story_bible or {}).setdefault("serial_runtime", {})
    story_bible_runtime["previous_chapter_bridge"] = continuity_bridge
    story_bible_runtime["continuity_mode"] = "strong_bridge"
    locked_novel.story_bible = locked_novel.story_bible or {}
    (locked_novel.story_bible.setdefault("serial_runtime", {})).update(story_bible_runtime)
    console_state = (locked_novel.story_bible.setdefault("story_workspace", {}))
    scene_report = console_state.get("last_generated_scene_report") if isinstance(console_state.get("last_generated_scene_report"), dict) else {}
    if scene_report:
        scene_report["handoff_hint"] = {
            "scene_status_at_end": _truncate_text(scene_handoff_card.get("scene_status_at_end"), 16),
            "must_continue_same_scene": bool(scene_handoff_card.get("must_continue_same_scene")),
            "next_opening_anchor": _truncate_text(scene_handoff_card.get("next_opening_anchor"), 96),
        }
        console_state["last_generated_scene_report"] = scene_report

    generation_duration_ms = int(round((time.monotonic() - chapter_started_at) * 1000))
    return FinalizationSnapshot(
        locked_novel=locked_novel,
        next_no=next_no,
        title=title,
        content=content,
        used_plan=used_plan,
        payoff_delivery=payoff_delivery,
        summary=summary,
        title_refinement_meta=title_refinement_meta,
        chapter_fact_entries=chapter_fact_entries,
        chapter_hard_facts=chapter_hard_facts,
        chapter_hard_fact_report=chapter_hard_fact_report,
        continuity_bridge=continuity_bridge,
        generation_duration_ms=generation_duration_ms,
    )
