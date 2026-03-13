from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.services.chapter_retry_support import (
    _attempt_generate_validated_chapter,
    _build_attempt_plans,
    _chapter_length_targets,
    _enrich_plan_agency,
)
from app.services.chapter_runtime_support import (
    _commit_runtime_snapshot,
    _compute_llm_timeout_seconds,
    _ensure_generation_runtime_budget,
    _planning_runtime_meta,
    _set_live_runtime,
)
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.hard_fact_guard import HardFactConflict, compact_hard_fact_guard, validate_and_register_chapter
from app.services.novel_bootstrap import generate_arc_outline_bundle
from app.services.story_architecture import (
    build_execution_brief,
    ensure_story_architecture,
    refresh_planning_views,
    set_pipeline_target,
    sync_character_registry,
    sync_long_term_state,
    update_story_architecture_after_chapter,
)
from app.services.openai_story_engine import (
    begin_llm_trace,
    clear_llm_trace,
    get_llm_trace,
    parse_instruction_with_openai,
    summarize_chapter,
)
from app.services.llm_runtime import current_timeout

logger = logging.getLogger(__name__)


def parse_reader_instruction(raw_instruction: str) -> dict:
    try:
        return parse_instruction_with_openai(raw_instruction).model_dump(mode="python")
    except Exception:
        lowered = raw_instruction.lower()
        parsed = {
            "character_focus": {},
            "tone": None,
            "pace": None,
            "protected_characters": [],
            "relationship_direction": None,
        }
        if "轻松" in raw_instruction or "温柔" in raw_instruction:
            parsed["tone"] = "lighter"
        if "压抑" in raw_instruction or "黑暗" in raw_instruction:
            parsed["tone"] = "darker"
        if "快一点" in raw_instruction or "节奏快" in raw_instruction or "faster" in lowered:
            parsed["pace"] = "faster"
        if "慢一点" in raw_instruction or "慢热" in raw_instruction or "slower" in lowered:
            parsed["pace"] = "slower"
        return parsed


def collect_active_interventions(db: Session, novel_id: int, next_chapter_no: int) -> list[Intervention]:
    interventions = (
        db.query(Intervention)
        .filter(Intervention.novel_id == novel_id)
        .order_by(Intervention.created_at.asc())
        .all()
    )
    active: list[Intervention] = []
    for item in interventions:
        start = item.chapter_no + 1
        end = item.chapter_no + item.effective_chapter_span
        if start <= next_chapter_no <= end:
            active.append(item)
    return active

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
from app.services.chapter_context_support import _compact_scene_card, _tail_paragraphs


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
    chapter = Chapter(
        novel_id=novel.id,
        chapter_no=chapter_no,
        title=chapter_title,
        content=content,
        generation_meta=generation_meta,
    )
    db.add(chapter)
    db.flush()

    summary = ChapterSummary(
        chapter_id=chapter.id,
        event_summary=event_summary,
        character_updates=character_updates,
        new_clues=new_clues,
        open_hooks=open_hooks,
        closed_hooks=closed_hooks,
    )
    db.add(summary)
    db.flush()
    novel.current_chapter_no = chapter_no
    db.add(novel)
    return chapter


def _auto_prepare_future_planning(
    db: Session,
    novel: Novel,
    *,
    current_chapter_no: int,
    recent_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    _ensure_outline_state(story_bible)
    _promote_pending_arc_if_needed(story_bible, current_chapter_no + 1)
    story_bible = refresh_planning_views(story_bible, current_chapter_no)
    novel.story_bible = story_bible

    console = story_bible.get("control_console") or {}
    queue = console.get("chapter_card_queue") or []
    active_arc = story_bible.get("active_arc")
    pending_arc = story_bible.get("pending_arc")
    remaining = _arc_remaining(active_arc, current_chapter_no)
    need_prefetch = not pending_arc and (
        remaining <= settings.arc_prefetch_threshold
        or len(queue) < settings.planning_window_size
    )

    auto_prefetched = False
    if need_prefetch:
        _generate_and_store_pending_arc(
            db,
            novel,
            recent_summaries,
            replace_existing=False,
        )
        story_bible = novel.story_bible or {}
        _promote_pending_arc_if_needed(story_bible, current_chapter_no + 1)
        story_bible = refresh_planning_views(story_bible, current_chapter_no)
        novel.story_bible = story_bible
        auto_prefetched = True

    db.add(novel)
    return {
        **_planning_runtime_meta(novel.story_bible or {}),
        "auto_prefetched": auto_prefetched,
        "arc_remaining": remaining,
    }


def _serial_delivery_mode(story_bible: dict[str, Any]) -> str:
    runtime = (story_bible or {}).get("serial_runtime") or {}
    mode = str(runtime.get("delivery_mode") or "live_publish").strip()
    return mode if mode in {"live_publish", "stockpile"} else "live_publish"


def _chapter_serial_stage_for_mode(delivery_mode: str) -> tuple[str, bool, bool]:
    if delivery_mode == "stockpile":
        return "stock", False, False
    return "published", True, True


def _refresh_serial_layers_from_db(db: Session, novel: Novel) -> Novel:
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


def _mark_generated_chapter_delivery(db: Session, novel: Novel, chapter: Chapter) -> tuple[Novel, dict[str, Any]]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    delivery_mode = _serial_delivery_mode(story_bible)
    serial_stage, is_published, locked_from_edit = _chapter_serial_stage_for_mode(delivery_mode)
    chapter.serial_stage = serial_stage
    chapter.is_published = is_published
    chapter.locked_from_edit = locked_from_edit
    chapter.published_at = datetime.now(UTC).replace(tzinfo=None) if is_published else None
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
    novel = _refresh_serial_layers_from_db(db, novel)
    return novel, {
        "delivery_mode": delivery_mode,
        "serial_stage": serial_stage,
        "is_published": is_published,
        "locked_from_edit": locked_from_edit,
        "published_at": chapter.published_at.isoformat(timespec="seconds") + "Z" if chapter.published_at else None,
    }


def generate_next_chapters_batch(
    db: Session,
    novel_id: int,
    count: int,
    progress_callback=None,
) -> list[Chapter]:
    total = max(int(count), 1)
    chapters: list[Chapter] = []
    started_from_chapter: int | None = None
    if progress_callback:
        progress_callback({"event": "batch_started", "novel_id": novel_id, "requested_count": total})

    for index in range(total):
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            raise GenerationError(
                code="NOVEL_NOT_FOUND",
                message="Novel not found",
                stage="batch_generation",
                retryable=False,
                http_status=404,
                details={"novel_id": novel_id},
            )
        next_no = novel.current_chapter_no + 1
        started_from_chapter = started_from_chapter or next_no
        if progress_callback:
            progress_callback(
                {
                    "event": "chapter_started",
                    "novel_id": novel_id,
                    "index": index + 1,
                    "total": total,
                    "chapter_no": next_no,
                    "message": f"开始生成第 {next_no} 章（{index + 1}/{total}）",
                }
            )
        started_at = time.monotonic()
        try:
            chapter = generate_next_chapter(db, novel)
        except GenerationError as exc:
            if progress_callback:
                progress_callback(
                    {
                        "event": "chapter_failed",
                        "novel_id": novel_id,
                        "index": index + 1,
                        "total": total,
                        "chapter_no": next_no,
                        "code": exc.code,
                        "stage": exc.stage,
                        "message": exc.message,
                        "retryable": exc.retryable,
                        "details": exc.details or {},
                    }
                )
            raise
        duration_ms = int(round((time.monotonic() - started_at) * 1000))
        chapters.append(chapter)
        if progress_callback:
            progress_callback(
                {
                    "event": "chapter_succeeded",
                    "novel_id": novel_id,
                    "index": index + 1,
                    "total": total,
                    "chapter_no": chapter.chapter_no,
                    "title": chapter.title,
                    "duration_ms": duration_ms,
                    "message": f"第 {chapter.chapter_no} 章生成完成：{chapter.title}",
                }
            )

    if progress_callback:
        progress_callback(
            {
                "event": "batch_completed",
                "novel_id": novel_id,
                "requested_count": total,
                "generated_count": len(chapters),
                "started_from_chapter": started_from_chapter,
                "ended_at_chapter": chapters[-1].chapter_no if chapters else None,
            }
        )
    return chapters


def generate_next_chapter(db: Session, novel: Novel) -> Chapter:
    previous_status = _acquire_generation_slot(db, novel.id)
    locked_novel = _load_novel_or_404(db, novel.id)
    trace_id = begin_llm_trace(f"novel-{locked_novel.id}-chapter-{locked_novel.current_chapter_no + 1}")
    chapter_started_at = time.monotonic()
    try:
        next_no = locked_novel.current_chapter_no + 1
        logger.info("chapter_generation start novel_id=%s chapter_no=%s trace=%s", locked_novel.id, next_no, trace_id)
        existing = (
            db.query(Chapter)
            .filter(Chapter.novel_id == locked_novel.id, Chapter.chapter_no == next_no)
            .first()
        )
        if existing:
            _release_generation_slot(db, novel.id, previous_status)
            return existing

        recent_chapters = _load_recent_chapters(db, locked_novel.id, limit=3)
        last_chapter = recent_chapters[-1] if recent_chapters else None
        recent_full_texts = [item.content for item in recent_chapters]
        recent_plan_meta = [
            ((item.generation_meta or {}).get("chapter_plan") or {})
            for item in recent_chapters
            if isinstance(item.generation_meta, dict)
        ]
        recent_summaries = _serialize_recent_summaries(db, locked_novel.id)

        story_bible = ensure_story_architecture(locked_novel.story_bible or {}, locked_novel)
        _ensure_outline_state(story_bible)
        _validate_required_planning_docs(story_bible, next_no)
        _validate_fact_ledger_state(story_bible, next_no)
        _promote_pending_arc_if_needed(story_bible, next_no)
        story_bible = refresh_planning_views(story_bible, locked_novel.current_chapter_no)
        locked_novel.story_bible = story_bible
        db.add(locked_novel)

        _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_planning_prefetch", chapter_no=next_no)
        planning_meta = _auto_prepare_future_planning(
            db,
            locked_novel,
            current_chapter_no=locked_novel.current_chapter_no,
            recent_summaries=recent_summaries,
        )
        locked_novel = _commit_runtime_snapshot(
            db,
            locked_novel,
            next_chapter_no=next_no,
            stage="reading_state",
            note=("第 {0} 章已完成定位、读状态与补规划准备。".format(next_no)),
            extra=planning_meta,
        )

        _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_plan_prepare", chapter_no=next_no)
        plan = _ensure_plan_for_chapter(db, locked_novel, next_no, recent_summaries)
        plan = _enrich_plan_agency(locked_novel, plan, recent_plan_meta=recent_plan_meta)
        story_bible = ensure_story_architecture(locked_novel.story_bible or {}, locked_novel)
        story_bible = refresh_planning_views(story_bible, locked_novel.current_chapter_no)
        locked_novel.story_bible = story_bible
        db.add(locked_novel)

        active_interventions = collect_active_interventions(db, locked_novel.id, next_no)
        serialized_active = _serialize_active_interventions(active_interventions)
        serialized_last = _serialize_last_chapter(last_chapter, protagonist_name=locked_novel.protagonist_name)
        execution_brief = _save_pipeline_execution_packet(
            novel=locked_novel,
            story_bible=story_bible,
            next_chapter_no=next_no,
            plan=plan,
            last_chapter_tail=serialized_last.get("tail_excerpt", ""),
        )
        locked_novel = _commit_runtime_snapshot(
            db,
            locked_novel,
            next_chapter_no=next_no,
            stage="chapter_outline_ready",
            note=f"第 {next_no} 章章纲已确定，准备落场景与正文。",
            extra={
                "chapter_title": plan.get("title") or f"第{next_no}章",
                "chapter_goal": _truncate_text(plan.get("goal"), 80),
                **_planning_runtime_meta(locked_novel.story_bible or {}),
            },
        )
        locked_novel = _commit_runtime_snapshot(
            db,
            locked_novel,
            next_chapter_no=next_no,
            stage="scene_outline_ready",
            note=f"第 {next_no} 章场景顺序已固定，将按场景推进正文。",
            extra={
                "scene_outline": _compact_value((execution_brief or {}).get("scene_outline", []), text_limit=68),
                **_planning_runtime_meta(locked_novel.story_bible or {}),
            },
        )

        novel_context = _serialize_novel_context(locked_novel, next_no, recent_summaries)
        novel_context.setdefault("story_memory", {})["execution_brief"] = _compact_value(execution_brief, text_limit=78)
        novel_context, recent_summaries, serialized_last, serialized_active, context_stats = _fit_chapter_payload_budget(
            novel_context=novel_context,
            recent_summaries=recent_summaries,
            serialized_last=serialized_last,
            serialized_active=serialized_active,
        )

        locked_novel = _commit_runtime_snapshot(
            db,
            locked_novel,
            next_chapter_no=next_no,
            stage="drafting",
            note=f"第 {next_no} 章正文生成中，控制台与目录会自动刷新。",
            extra={
                **_planning_runtime_meta(locked_novel.story_bible or {}),
                "context_mode": novel_context.get("context_mode", settings.chapter_context_mode),
            },
        )

        title, content, draft_payload, used_plan, length_targets, attempt_meta = _attempt_generate_validated_chapter(
            novel_context=novel_context,
            plan=plan,
            serialized_last=serialized_last,
            recent_summaries=recent_summaries,
            serialized_active=serialized_active,
            recent_full_texts=recent_full_texts,
            recent_plan_meta=recent_plan_meta,
            chapter_no=next_no,
            started_at=chapter_started_at,
            novel_ref=locked_novel,
        )

        locked_novel = _commit_runtime_snapshot(
            db,
            locked_novel,
            next_chapter_no=next_no,
            stage="quality_check",
            note=f"第 {next_no} 章正文与结尾检查通过，正在生成摘要与状态更新。",
            extra={
                **_planning_runtime_meta(locked_novel.story_bible or {}),
                "validated": True,
                "target_visible_chars_min": int(length_targets["target_visible_chars_min"]),
                "target_visible_chars_max": int(length_targets["target_visible_chars_max"]),
            },
        )

        _ensure_generation_runtime_budget(started_at=chapter_started_at, stage="chapter_summary_generation", chapter_no=next_no)
        summary_timeout = _compute_llm_timeout_seconds(
            started_at=chapter_started_at,
            chapter_no=next_no,
            stage="chapter_summary_generation",
            reserve_seconds=4,
        )
        summary = summarize_chapter(title, content, request_timeout_seconds=summary_timeout)
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
            last_chapter_tail=serialized_last.get("tail_excerpt", ""),
        )
        sync_character_registry(
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

        continuity_bridge = {
            "source_chapter_no": next_no,
            "title": _truncate_text(title, 30),
            "tail_excerpt": _truncate_text(content[-settings.chapter_last_excerpt_chars :], settings.chapter_last_excerpt_chars),
            "last_two_paragraphs": _tail_paragraphs(content, count=2),
            "last_scene_card": _compact_scene_card(used_plan),
            "unresolved_action_chain": _truncate_list(summary.open_hooks, max_items=3, item_limit=64),
            "carry_over_clues": _truncate_list(summary.new_clues, max_items=3, item_limit=56),
            "onstage_characters": _truncate_list([locked_novel.protagonist_name, used_plan.get("supporting_character_focus")] + list((summary.character_updates or {}).keys()), max_items=5, item_limit=20),
            "next_opening_instruction": _truncate_text(used_plan.get("opening_beat") or "下一章开头必须承接这一章最后动作、对话或局势变化。", 72),
            "opening_anchor": _truncate_text((_tail_paragraphs(content, count=1) or [content[-160:]])[-1], 120),
        }
        story_bible_runtime = (locked_novel.story_bible or {}).setdefault("serial_runtime", {})
        story_bible_runtime["previous_chapter_bridge"] = continuity_bridge
        story_bible_runtime["continuity_mode"] = "strong_bridge"
        locked_novel.story_bible = locked_novel.story_bible or {}
        (locked_novel.story_bible.setdefault("serial_runtime", {})).update(story_bible_runtime)

        generation_meta = {
            "generator": "chat_completions_api" if settings.llm_provider.lower() in ("deepseek", "groq") else "responses_api",
            "provider": settings.llm_provider,
            "trace_id": trace_id,
            "based_on_chapter": last_chapter.chapter_no if last_chapter else None,
            "based_on_published_through": int((((locked_novel.story_bible or {}).get("long_term_state") or {}).get("chapter_release_state") or {}).get("published_through", 0) or 0),
            "active_interventions": [i.id for i in active_interventions],
            "chapter_plan": used_plan,
            "quality_validated": True,
            "length_targets": length_targets,
            "context_stats": context_stats,
            "manual_framework": {
                "project_card_enabled": True,
                "volume_card_enabled": True,
                "control_console_enabled": True,
                "daily_workbench_enabled": True,
                "strict_document_first_pipeline": True,
                "bootstrap_generated_text": False,
                "pipeline_steps": ["定位", "读状态", "章纲", "场景", "正文", "检查", "摘要", "状态更新", "发布状态标记", "下一章入口"],
            },
            **({"draft_payload": draft_payload} if settings.return_draft_payload_in_meta else {}),
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
            "fact_entries": chapter_fact_entries,
            "hard_fact_report": {**chapter_hard_fact_report, "facts": chapter_hard_facts},
            "continuity_bridge": continuity_bridge,
            "attempt_meta": attempt_meta,
            "quality_rejections": (attempt_meta or {}).get("quality_rejections", []),
            "structural_signals": {
                "event_type": used_plan.get("event_type"),
                "progress_kind": used_plan.get("progress_kind"),
                "proactive_move": used_plan.get("proactive_move"),
                "payoff_or_pressure": used_plan.get("payoff_or_pressure"),
                "hook_kind": used_plan.get("hook_kind"),
                "agency_mode": used_plan.get("agency_mode"),
                "agency_mode_label": used_plan.get("agency_mode_label"),
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
        chapter.generation_meta = {
            **(chapter.generation_meta or {}),
            "serial_delivery": serial_delivery,
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
                "serial_delivery": serial_delivery,
            },
        )

        for item in active_interventions:
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
                "last_generated_chapter_no": next_no,
                "last_generated_title": title,
                "delivery_mode": _serial_delivery_mode(locked_novel.story_bible or {}),
            },
        )

        locked_novel.status = previous_status
        db.add(locked_novel)
        db.commit()
        db.refresh(chapter)
        logger.info("chapter_generation success novel_id=%s chapter_no=%s duration_ms=%s", locked_novel.id, next_no, int((time.monotonic() - chapter_started_at) * 1000))
        return chapter
    except GenerationError as exc:
        logger.warning("chapter_generation failed novel_id=%s chapter_no=%s stage=%s code=%s details=%s", novel.id, locals().get("next_no", novel.current_chapter_no + 1), exc.stage, exc.code, exc.details)
        db.rollback()
        _persist_generation_failure_snapshot(
            db,
            novel_id=novel.id,
            restore_status=previous_status,
            next_chapter_no=locals().get("next_no", novel.current_chapter_no + 1),
            stage=exc.stage,
            message=exc.message,
            details=exc.details or {},
        )
        raise
    except Exception as exc:
        logger.exception("chapter_generation crashed novel_id=%s chapter_no=%s", novel.id, locals().get("next_no", novel.current_chapter_no + 1))
        db.rollback()
        _persist_generation_failure_snapshot(
            db,
            novel_id=novel.id,
            restore_status=previous_status,
            next_chapter_no=locals().get("next_no", novel.current_chapter_no + 1),
            stage="chapter_generation",
            message="章节生成流程出现未识别异常，已中止本次生成。",
            details={"error_type": type(exc).__name__},
        )
        raise
    finally:
        clear_llm_trace()
