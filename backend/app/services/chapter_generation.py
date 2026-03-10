from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.chapter_context import (
    fit_chapter_payload_budget,
    load_recent_chapters,
    serialize_active_interventions,
    serialize_last_chapter,
    serialize_novel_context,
    serialize_recent_summaries,
)
from app.services.chapter_quality import validate_chapter_content
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.instruction_parser import parse_reader_instruction as _parse_reader_instruction
from app.services.novel_bootstrap import generate_arc_outline_bundle
from app.services.openai_story_engine import (
    begin_llm_trace,
    clear_llm_trace,
    extend_chapter_text,
    generate_chapter_from_plan,
    get_llm_trace,
    summarize_chapter,
)

logger = logging.getLogger(__name__)


def parse_reader_instruction(raw_instruction: str) -> dict[str, Any]:
    return _parse_reader_instruction(raw_instruction)


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


def _lock_novel_for_generation(db: Session, novel_id: int) -> Novel:
    try:
        locked = db.query(Novel).filter(Novel.id == novel_id).with_for_update(nowait=True).first()
    except OperationalError as exc:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_ALREADY_GENERATING,
            message="当前这本书已经有一个章节生成任务在进行中，请稍后再试。",
            stage="chapter_generation_lock",
            retryable=True,
            http_status=409,
            details={"novel_id": novel_id},
        ) from exc

    if not locked:
        raise GenerationError(
            code="NOVEL_NOT_FOUND",
            message="小说不存在。",
            stage="chapter_generation_lock",
            retryable=False,
            http_status=404,
            details={"novel_id": novel_id},
        )
    return locked


def _story_bible_payload_to_novel_create(novel: Novel) -> NovelCreate:
    return NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )


def _ensure_outline_state(story_bible: dict[str, Any]) -> dict[str, Any]:
    state = story_bible.setdefault("outline_state", {})
    state.setdefault("planned_until", 0)
    state.setdefault("next_arc_no", 1)
    state.setdefault("bootstrap_generated_until", 0)
    return state


def _promote_pending_arc_if_needed(story_bible: dict[str, Any], next_no: int) -> None:
    active_arc = story_bible.get("active_arc")
    pending_arc = story_bible.get("pending_arc")
    if active_arc and next_no <= int(active_arc.get("end_chapter", 0)):
        return
    if pending_arc and next_no >= int(pending_arc.get("start_chapter", 0)):
        story_bible["active_arc"] = pending_arc
        story_bible["pending_arc"] = None


def _generate_and_store_pending_arc(
    db: Session,
    novel: Novel,
    recent_summaries: list[dict[str, Any]],
    *,
    start_chapter: int | None = None,
    replace_existing: bool = False,
) -> None:
    story_bible = novel.story_bible or {}
    state = _ensure_outline_state(story_bible)
    active_arc = story_bible.get("active_arc")
    pending_arc = story_bible.get("pending_arc")
    if pending_arc and not replace_existing:
        return

    if start_chapter is None:
        start = novel.current_chapter_no + 1 if not active_arc else int(active_arc.get("end_chapter", 0)) + 1
    else:
        start = start_chapter
    end = start + settings.arc_outline_size - 1
    arc_no = int(state.get("next_arc_no", 1))

    payload = _story_bible_payload_to_novel_create(novel)
    bundle = generate_arc_outline_bundle(
        payload=payload,
        story_bible=story_bible,
        global_outline=story_bible.get("global_outline", {}),
        start_chapter=start,
        end_chapter=end,
        arc_no=arc_no,
        recent_summaries=recent_summaries,
    )
    story_bible["pending_arc"] = bundle
    state["planned_until"] = end
    state["next_arc_no"] = arc_no + 1
    novel.story_bible = story_bible
    db.add(novel)


def _get_plan_for_chapter(novel: Novel, chapter_no: int) -> dict[str, Any]:
    story_bible = novel.story_bible or {}
    for arc_key in ["active_arc", "pending_arc"]:
        arc = story_bible.get(arc_key)
        if not arc:
            continue
        for chapter in arc.get("chapters", []):
            if int(chapter.get("chapter_no", 0)) == chapter_no:
                return chapter
    raise GenerationError(
        code=ErrorCodes.CHAPTER_PLAN_MISSING,
        message=f"第 {chapter_no} 章没有对应拍表，无法生成正文。",
        stage="chapter_plan_lookup",
        retryable=True,
        http_status=409,
        details={"chapter_no": chapter_no},
    )


def _ensure_plan_for_chapter(
    db: Session,
    novel: Novel,
    chapter_no: int,
    recent_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        return _get_plan_for_chapter(novel, chapter_no)
    except GenerationError as exc:
        if exc.code != ErrorCodes.CHAPTER_PLAN_MISSING:
            raise

    logger.info("chapter %s missing plan, generating arc just-in-time for novel=%s", chapter_no, novel.id)
    _generate_and_store_pending_arc(db, novel, recent_summaries, start_chapter=chapter_no, replace_existing=True)
    story_bible = novel.story_bible or {}
    _promote_pending_arc_if_needed(story_bible, chapter_no)
    novel.story_bible = story_bible
    db.add(novel)
    return _get_plan_for_chapter(novel, chapter_no)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a[:1500], b[:1500]).ratio()


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
    novel.current_chapter_no = chapter_no
    db.add(novel)
    return chapter


def _chapter_length_targets(plan: dict[str, Any]) -> dict[str, int | str]:
    chapter_type = str(plan.get("chapter_type") or "").strip().lower()
    if chapter_type not in {"probe", "progress", "turning_point"}:
        goal_text = f"{plan.get('goal') or ''} {plan.get('conflict') or ''} {plan.get('ending_hook') or ''}"
        if any(token in goal_text for token in ["追", "逃", "转折", "对峙", "揭示", "伏击", "矿"]):
            chapter_type = "turning_point"
        elif any(token in goal_text for token in ["查", "换", "买", "谈", "坊市", "交易", "跟踪"]):
            chapter_type = "progress"
        else:
            chapter_type = "probe"

    if chapter_type == "turning_point":
        target_min = settings.chapter_turning_point_target_min_visible_chars
        target_max = settings.chapter_turning_point_target_max_visible_chars
    elif chapter_type == "progress":
        target_min = settings.chapter_progress_target_min_visible_chars
        target_max = settings.chapter_progress_target_max_visible_chars
    else:
        target_min = settings.chapter_probe_target_min_visible_chars
        target_max = settings.chapter_probe_target_max_visible_chars

    if int(plan.get("target_visible_chars_min") or 0) > 0:
        target_min = int(plan["target_visible_chars_min"])
    if int(plan.get("target_visible_chars_max") or 0) > 0:
        target_max = int(plan["target_visible_chars_max"])

    hard_min = min(settings.chapter_hard_min_visible_chars, target_min)
    target_words = max(settings.chapter_target_words, int((target_min + target_max) / 2 * 0.9))
    return {
        "chapter_type": chapter_type,
        "target_visible_chars_min": target_min,
        "target_visible_chars_max": target_max,
        "hard_min_visible_chars": hard_min,
        "target_words": target_words,
    }


def _append_extension(base: str, addition: str) -> str:
    base_text = (base or "").rstrip()
    extra = (addition or "").strip()
    if not extra:
        return base_text
    if not base_text:
        return extra
    if extra in base_text[-max(len(extra) + 20, 200) :]:
        return base_text
    separator = "\n\n" if not base_text.endswith("\n") else "\n"
    return f"{base_text}{separator}{extra}".strip()


def _repair_short_or_incomplete_chapter(
    *,
    title: str,
    content: str,
    plan: dict[str, Any],
    exc: GenerationError,
    targets: dict[str, int | str],
) -> str | None:
    if not isinstance(exc.details, dict):
        return None
    if exc.code not in {ErrorCodes.CHAPTER_TOO_SHORT, ErrorCodes.CHAPTER_ENDING_INCOMPLETE}:
        return None
    reason = "补足篇幅并自然收尾" if exc.code == ErrorCodes.CHAPTER_TOO_SHORT else "补齐截断结尾并自然收束"
    addition = extend_chapter_text(
        chapter_plan=plan,
        existing_content=content,
        reason=reason,
        target_visible_chars_min=int(targets["target_visible_chars_min"]),
        target_visible_chars_max=int(targets["target_visible_chars_max"]),
    )
    merged = _append_extension(content, addition)
    return merged if merged != content else None


def _build_attempt_plans(plan: dict[str, Any]) -> list[dict[str, Any]]:
    max_attempts = max(int(settings.chapter_draft_max_attempts), 1)
    attempts: list[dict[str, Any]] = [dict(plan)]
    if max_attempts <= 1:
        return attempts

    base_note = (plan.get("writing_note") or "").strip()
    variants = [
        "进一步拉开与最近章节的句式距离，换开场动作、换感官、换结尾方式，减少‘不是错觉/心跳快了/若有若无/温凉/微弱’这类高频表达，并至少写出一两句更有棱角的具体句子。",
        "把配角写得更像人：给重复出现的人物一个职业习惯、说话方式或顾虑，不要只让他负责抛信息。若有反派或帮众，要补一处让人记住的危险细节。",
        "这次章末可以平稳过渡或余味收束，不必硬留悬念，但必须有结果落地或人物选择。",
        "对话和动作链要更分人，避免所有角色都用同一种冷硬叙述腔；林玄在离别、损失、抉择处，情绪再沉半层，但通过动作和停顿去表现。",
    ]

    for index, extra in enumerate(variants, start=1):
        variant = dict(plan)
        variant["writing_note"] = f"{base_note}；{extra}" if base_note else extra
        if index >= 3 and variant.get("hook_style") not in {"平稳过渡", "余味收束"}:
            variant["hook_style"] = "平稳过渡"
            if variant.get("ending_hook"):
                variant["ending_hook"] = f"{variant['ending_hook']}（也可改为自然过渡收束）"
        attempts.append(variant)
        if len(attempts) >= max_attempts:
            break
    return attempts[:max_attempts]


def _make_too_short_retry_plan(plan: dict[str, Any], *, visible_chars: int, target_min: int, target_max: int) -> dict[str, Any]:
    note = (plan.get("writing_note") or "").strip()
    retry_note = (
        f"上一篇草稿只有约 {visible_chars} 个可见字符，明显偏短。"
        f"这次必须补足到完整一章的体量，尽量写到 {target_min}-{target_max} 个可见中文字符左右。"
        "务必补出开场动作、一次中段受阻、一次具体发现和一个结尾钩子，"
        "把人物试探、对话、动作因果和场景细节写完整，不要匆忙收尾。"
    )
    retry_plan = dict(plan)
    retry_plan["writing_note"] = f"{note}；{retry_note}" if note else retry_note
    retry_plan["length_retry"] = {"reason": "too_short", "previous_visible_chars": visible_chars}
    return retry_plan


def _attempt_generate_validated_chapter(
    *,
    novel_context: dict[str, Any],
    plan: dict[str, Any],
    serialized_last: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    serialized_active: list[dict[str, Any]],
    recent_full_texts: list[str],
) -> tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    attempts = _build_attempt_plans(plan)
    last_error: Exception | None = None
    too_short_retries_left = max(int(settings.chapter_too_short_retry_attempts), 0)
    tail_fix_retries_left = max(int(settings.chapter_tail_fix_attempts), 0)
    idx = 0
    while idx < len(attempts):
        attempt_plan = attempts[idx]
        targets = _chapter_length_targets(attempt_plan)
        draft = generate_chapter_from_plan(
            novel_context=novel_context,
            chapter_plan=attempt_plan,
            last_chapter=serialized_last,
            recent_summaries=recent_summaries,
            active_interventions=serialized_active,
            target_words=int(targets["target_words"]),
            target_visible_chars_min=int(targets["target_visible_chars_min"]),
            target_visible_chars_max=int(targets["target_visible_chars_max"]),
        )
        title = draft.title or attempt_plan["title"]
        content = draft.content
        try:
            validate_chapter_content(
                title=title,
                content=content,
                min_visible_chars=int(targets["target_visible_chars_min"]),
                hard_min_visible_chars=int(targets["hard_min_visible_chars"]),
                recent_chapter_texts=recent_full_texts,
                similarity_checker=_similarity,
                max_similarity=settings.chapter_similarity_threshold,
                target_visible_chars_max=int(targets["target_visible_chars_max"]),
                hook_style=str(attempt_plan.get("hook_style") or ""),
            )
            return title, content, draft.model_dump(mode="python"), attempt_plan, targets
        except GenerationError as exc:
            last_error = exc
            if exc.code in {ErrorCodes.CHAPTER_TOO_SHORT, ErrorCodes.CHAPTER_ENDING_INCOMPLETE}:
                repaired = _repair_short_or_incomplete_chapter(
                    title=title,
                    content=content,
                    plan=attempt_plan,
                    exc=exc,
                    targets=targets,
                )
                if repaired:
                    if exc.code == ErrorCodes.CHAPTER_ENDING_INCOMPLETE:
                        tail_fix_retries_left -= 1
                        delay_ms = max(int(settings.chapter_tail_fix_delay_ms), 0)
                    else:
                        too_short_retries_left -= 1
                        delay_ms = max(int(settings.chapter_too_short_retry_delay_ms), 0)
                    if delay_ms:
                        time.sleep(delay_ms / 1000.0)
                    try:
                        validate_chapter_content(
                            title=title,
                            content=repaired,
                            min_visible_chars=int(targets["target_visible_chars_min"]),
                            hard_min_visible_chars=int(targets["hard_min_visible_chars"]),
                            recent_chapter_texts=recent_full_texts,
                            similarity_checker=_similarity,
                            max_similarity=settings.chapter_similarity_threshold,
                            target_visible_chars_max=int(targets["target_visible_chars_max"]),
                            hook_style=str(attempt_plan.get("hook_style") or ""),
                        )
                        patched_payload = draft.model_dump(mode="python")
                        patched_payload["content"] = repaired
                        return title, repaired, patched_payload, attempt_plan, targets
                    except GenerationError as repair_exc:
                        last_error = repair_exc

            if exc.code == ErrorCodes.CHAPTER_TOO_SHORT and too_short_retries_left > 0 and isinstance(exc.details, dict):
                too_short_retries_left -= 1
                visible_chars = int(exc.details.get("visible_chars") or 0)
                attempts.insert(
                    idx + 1,
                    _make_too_short_retry_plan(
                        attempt_plan,
                        visible_chars=visible_chars,
                        target_min=int(targets["target_visible_chars_min"]),
                        target_max=int(targets["target_visible_chars_max"]),
                    ),
                )
                delay_ms = max(int(settings.chapter_too_short_retry_delay_ms), 0)
                if delay_ms:
                    time.sleep(delay_ms / 1000.0)
                idx += 1
                continue
            if idx >= len(attempts) - 1:
                raise last_error or exc
        idx += 1
    if last_error:
        raise last_error
    raise RuntimeError("chapter generation unexpectedly exited without result")


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
    locked_novel = _lock_novel_for_generation(db, novel.id)
    trace_id = begin_llm_trace(f"novel-{locked_novel.id}-chapter-{locked_novel.current_chapter_no + 1}")
    try:
        next_no = locked_novel.current_chapter_no + 1
        existing = db.query(Chapter).filter(Chapter.novel_id == locked_novel.id, Chapter.chapter_no == next_no).first()
        if existing:
            return existing

        recent_chapters = load_recent_chapters(db, locked_novel.id, limit=3)
        last_chapter = recent_chapters[-1] if recent_chapters else None
        recent_full_texts = [item.content for item in recent_chapters]
        recent_summaries = serialize_recent_summaries(db, locked_novel.id)
        story_bible = locked_novel.story_bible or {}
        _ensure_outline_state(story_bible)
        _promote_pending_arc_if_needed(story_bible, next_no)
        locked_novel.story_bible = story_bible
        db.add(locked_novel)

        plan = _ensure_plan_for_chapter(db, locked_novel, next_no, recent_summaries)
        active_interventions = collect_active_interventions(db, locked_novel.id, next_no)
        serialized_active = serialize_active_interventions(active_interventions)
        serialized_last = serialize_last_chapter(last_chapter)
        novel_context = serialize_novel_context(locked_novel, next_no, recent_summaries)
        novel_context, recent_summaries, serialized_last, serialized_active, context_stats = fit_chapter_payload_budget(
            novel_context=novel_context,
            recent_summaries=recent_summaries,
            serialized_last=serialized_last,
            serialized_active=serialized_active,
        )

        title, content, draft_payload, used_plan, length_targets = _attempt_generate_validated_chapter(
            novel_context=novel_context,
            plan=plan,
            serialized_last=serialized_last,
            recent_summaries=recent_summaries,
            serialized_active=serialized_active,
            recent_full_texts=recent_full_texts,
        )

        summary = summarize_chapter(title, content)
        generation_meta = {
            "generator": "chat_completions_api" if settings.llm_provider == "deepseek" else "responses_api",
            "provider": settings.llm_provider,
            "trace_id": trace_id,
            "based_on_chapter": last_chapter.chapter_no if last_chapter else None,
            "active_interventions": [i.id for i in active_interventions],
            "chapter_plan": used_plan,
            "quality_validated": True,
            "length_targets": length_targets,
            "context_stats": context_stats,
            "summary_mode_configured": settings.chapter_summary_mode,
            **({"draft_payload": draft_payload} if settings.return_draft_payload_in_meta else {}),
            "llm_call_trace": get_llm_trace(),
            "serial_generation_guard": {
                "novel_row_lock": True,
                "llm_call_min_interval_ms": settings.llm_call_min_interval_ms,
                "chapter_draft_max_attempts": settings.chapter_draft_max_attempts,
                "arc_prefetch_threshold": settings.arc_prefetch_threshold,
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

        for item in active_interventions:
            item.applied = True
            db.add(item)

        db.commit()
        db.refresh(chapter)
        return chapter
    finally:
        clear_llm_trace()
