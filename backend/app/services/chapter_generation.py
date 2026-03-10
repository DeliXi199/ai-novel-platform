from __future__ import annotations

import json
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
from app.services.chapter_quality import validate_chapter_content
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.novel_bootstrap import generate_arc_outline_bundle
from app.services.openai_story_engine import (
    begin_llm_trace,
    clear_llm_trace,
    generate_chapter_from_plan,
    extend_chapter_text,
    get_llm_trace,
    parse_instruction_with_openai,
    summarize_chapter,
)

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



def _lock_novel_for_generation(db: Session, novel_id: int) -> Novel:
    try:
        locked = (
            db.query(Novel)
            .filter(Novel.id == novel_id)
            .with_for_update(nowait=True)
            .first()
        )
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



def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"



def _truncate_list(values: list[Any] | None, *, max_items: int, item_limit: int) -> list[str]:
    result: list[str] = []
    for item in values or []:
        text = _truncate_text(item, item_limit)
        if text:
            result.append(text)
        if len(result) >= max_items:
            break
    return result



def _compact_value(value: Any, *, text_limit: int = 60) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, text_limit=text_limit) for item in value[:6]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 8:
                break
            compact[str(key)] = _compact_value(item, text_limit=text_limit)
        return compact
    return _truncate_text(value, text_limit)



def _normalize_hook(hook: Any) -> str:
    return "".join(str(hook or "").split())



def _json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False))



def _serialize_recent_summaries(db: Session, novel_id: int) -> list[dict]:
    rows = (
        db.query(Chapter, ChapterSummary)
        .join(ChapterSummary, ChapterSummary.chapter_id == Chapter.id)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.desc())
        .limit(settings.chapter_recent_summary_limit)
        .all()
    )
    serialized = []
    for chapter, summary in reversed(rows):
        serialized.append(
            {
                "chapter_no": chapter.chapter_no,
                "chapter_title": _truncate_text(chapter.title, 30),
                "event_summary": _truncate_text(summary.event_summary, settings.chapter_recent_summary_chars),
                "open_hooks": _truncate_list(summary.open_hooks, max_items=3, item_limit=48),
                "closed_hooks": _truncate_list(summary.closed_hooks, max_items=2, item_limit=48),
            }
        )
    return serialized



def _load_recent_chapters(db: Session, novel_id: int, limit: int = 3) -> list[Chapter]:
    rows = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))



def _serialize_active_interventions(active_interventions: list[Intervention]) -> list[dict]:
    serialized: list[dict[str, Any]] = []
    for item in active_interventions:
        constraints = item.parsed_constraints or {}
        compact: dict[str, Any] = {}
        if constraints.get("character_focus"):
            compact["character_focus"] = {
                str(name): float(weight)
                for name, weight in list((constraints.get("character_focus") or {}).items())[:4]
            }
        if constraints.get("tone"):
            compact["tone"] = constraints["tone"]
        if constraints.get("pace"):
            compact["pace"] = constraints["pace"]
        if constraints.get("protected_characters"):
            compact["protected_characters"] = _truncate_list(
                constraints.get("protected_characters"), max_items=4, item_limit=20
            )
        if constraints.get("relationship_direction"):
            compact["relationship_direction"] = constraints["relationship_direction"]
        if compact:
            serialized.append(
                {
                    "id": item.id,
                    "constraints": compact,
                    "effective_chapter_span": item.effective_chapter_span,
                }
            )
    return serialized



def _serialize_last_chapter(last_chapter: Chapter | None) -> dict:
    if not last_chapter:
        return {}
    return {
        "chapter_no": last_chapter.chapter_no,
        "title": _truncate_text(last_chapter.title, 30),
        "tail_excerpt": _truncate_text(
            last_chapter.content[-settings.chapter_last_excerpt_chars :],
            settings.chapter_last_excerpt_chars,
        ),
    }



def _select_outline_window(global_outline: dict[str, Any], target_chapter_no: int) -> list[dict[str, Any]]:
    acts = global_outline.get("acts", []) if isinstance(global_outline, dict) else []
    if not acts:
        return []
    current_idx = len(acts) - 1
    for idx, act in enumerate(acts):
        target_end = int(act.get("target_chapter_end", 0) or 0)
        if target_chapter_no <= target_end or target_end == 0:
            current_idx = idx
            break
    selected = acts[current_idx : current_idx + 2]
    compact: list[dict[str, Any]] = []
    for act in selected:
        compact.append(
            {
                "act_no": int(act.get("act_no", 0) or 0),
                "title": _truncate_text(act.get("title"), 24),
                "purpose": _truncate_text(act.get("purpose"), 60),
                "summary": _truncate_text(act.get("summary"), 90),
                "target_chapter_end": int(act.get("target_chapter_end", 0) or 0),
            }
        )
    return compact



def _compact_arc(arc: dict[str, Any] | None) -> dict[str, Any]:
    if not arc:
        return {}
    return {
        "arc_no": int(arc.get("arc_no", 0) or 0),
        "start_chapter": int(arc.get("start_chapter", 0) or 0),
        "end_chapter": int(arc.get("end_chapter", 0) or 0),
        "focus": _truncate_text(arc.get("focus"), 70),
        "bridge_note": _truncate_text(arc.get("bridge_note"), 90),
    }



def _phase_rule(story_bible: dict[str, Any], next_no: int) -> str:
    pacing_rules = story_bible.get("pacing_rules", {}) if isinstance(story_bible, dict) else {}
    if next_no <= 3 and pacing_rules.get("first_three_chapters"):
        return _truncate_text(pacing_rules["first_three_chapters"], 80)
    if next_no <= 12 and pacing_rules.get("first_twelve_chapters"):
        return _truncate_text(pacing_rules["first_twelve_chapters"], 80)
    return _truncate_text(pacing_rules.get("overall"), 80)



def _collect_live_hooks(recent_summaries: list[dict[str, Any]]) -> list[str]:
    closed = {
        _normalize_hook(hook)
        for summary in recent_summaries
        for hook in summary.get("closed_hooks", [])
        if _normalize_hook(hook)
    }
    live_hooks: list[str] = []
    seen: set[str] = set()
    for summary in reversed(recent_summaries):
        for hook in summary.get("open_hooks", []):
            norm = _normalize_hook(hook)
            if not norm or norm in closed or norm in seen:
                continue
            seen.add(norm)
            live_hooks.append(_truncate_text(hook, 48))
            if len(live_hooks) >= settings.chapter_live_hook_limit:
                return live_hooks
    return live_hooks



def _serialize_novel_context(novel: Novel, next_no: int, recent_summaries: list[dict[str, Any]]) -> dict:
    if settings.chapter_context_mode.lower() != "light":
        return {
            "context_mode": "full",
            "novel_id": novel.id,
            "title": novel.title,
            "genre": novel.genre,
            "premise": novel.premise,
            "protagonist_name": novel.protagonist_name,
            "style_preferences": novel.style_preferences,
            "story_bible": novel.story_bible,
            "current_chapter_no": novel.current_chapter_no,
            "target_chapter_no": next_no,
        }

    story_bible = novel.story_bible or {}
    style_preferences = _compact_value(novel.style_preferences or {}, text_limit=50)
    global_direction = _select_outline_window(story_bible.get("global_outline", {}), next_no)
    active_arc = _compact_arc(story_bible.get("active_arc"))
    live_hooks = _collect_live_hooks(recent_summaries)
    return {
        "context_mode": "light",
        "novel_id": novel.id,
        "title": _truncate_text(novel.title, 40),
        "genre": _truncate_text(novel.genre, 20),
        "premise": _truncate_text(novel.premise, 180),
        "protagonist_name": _truncate_text(novel.protagonist_name, 20),
        "style_preferences": style_preferences,
        "current_chapter_no": novel.current_chapter_no,
        "target_chapter_no": next_no,
        "story_memory": {
            "narrative_style": _truncate_text(story_bible.get("narrative_style"), 40),
            "core_conflict": _truncate_text(story_bible.get("core_conflict"), 110),
            "phase_rule": _phase_rule(story_bible, next_no),
            "forbidden_rules": _truncate_list(story_bible.get("forbidden_rules"), max_items=5, item_limit=28),
            "continuity_rules": [
                "核心线索物件的形态与规模要稳定，除非本章明确解释变化。",
                "如果时间推进超过一天，开头两段必须写明过渡。",
                "结尾必须自然收束，不能停在半句。",
            ],
            "characterization_rules": _truncate_list(story_bible.get("characterization_rules"), max_items=4, item_limit=42),
            "language_rules": _truncate_list(story_bible.get("language_rules"), max_items=4, item_limit=42),
            "antagonist_rules": _truncate_list(story_bible.get("antagonist_rules"), max_items=3, item_limit=42),
            "protagonist_emotion_rules": _truncate_list(story_bible.get("protagonist_emotion_rules"), max_items=3, item_limit=42),
            "ending_rules": _truncate_list(story_bible.get("ending_rules"), max_items=4, item_limit=42),
            "global_direction": global_direction,
            "active_arc": active_arc,
            "live_hooks": live_hooks,
        },
    }



def _fit_chapter_payload_budget(
    novel_context: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    serialized_last: dict[str, Any],
    serialized_active: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    budget = settings.chapter_prompt_max_chars
    before = _json_size(novel_context) + _json_size(recent_summaries) + _json_size(serialized_last) + _json_size(serialized_active)

    def total_size() -> int:
        return _json_size(novel_context) + _json_size(recent_summaries) + _json_size(serialized_last) + _json_size(serialized_active)

    if total_size() > budget and serialized_last.get("tail_excerpt"):
        serialized_last["tail_excerpt"] = _truncate_text(serialized_last["tail_excerpt"], min(260, settings.chapter_last_excerpt_chars))

    if total_size() > budget and len(recent_summaries) > 1:
        recent_summaries = recent_summaries[-1:]

    if total_size() > budget and len(serialized_active) > 1:
        serialized_active = serialized_active[-1:]

    story_memory = novel_context.get("story_memory") if isinstance(novel_context, dict) else None
    if total_size() > budget and isinstance(story_memory, dict):
        if isinstance(story_memory.get("global_direction"), list) and len(story_memory["global_direction"]) > 1:
            story_memory["global_direction"] = story_memory["global_direction"][:1]
        if isinstance(story_memory.get("live_hooks"), list) and len(story_memory["live_hooks"]) > 3:
            story_memory["live_hooks"] = story_memory["live_hooks"][:3]
        if isinstance(story_memory.get("core_conflict"), str):
            story_memory["core_conflict"] = _truncate_text(story_memory["core_conflict"], 80)
        if isinstance(story_memory.get("phase_rule"), str):
            story_memory["phase_rule"] = _truncate_text(story_memory["phase_rule"], 60)

    if total_size() > budget:
        novel_context["premise"] = _truncate_text(novel_context.get("premise"), 120)

    stats = {
        "context_mode": novel_context.get("context_mode", settings.chapter_context_mode),
        "payload_chars_before": before,
        "payload_chars_after": total_size(),
        "budget": budget,
        "recent_summary_count": len(recent_summaries),
        "active_intervention_count": len(serialized_active),
        "last_excerpt_chars": len(serialized_last.get("tail_excerpt", "")),
    }
    return novel_context, recent_summaries, serialized_last, serialized_active, stats



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



def _arc_remaining(active_arc: dict[str, Any] | None, current_chapter_no: int) -> int:
    if not active_arc:
        return 0
    return int(active_arc.get("end_chapter", 0)) - current_chapter_no



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
        if not active_arc:
            start = novel.current_chapter_no + 1
        else:
            start = int(active_arc.get("end_chapter", 0)) + 1
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
    _generate_and_store_pending_arc(
        db,
        novel,
        recent_summaries,
        start_chapter=chapter_no,
        replace_existing=True,
    )
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
    if extra in base_text[-max(len(extra) + 20, 200):]:
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

    for i, extra in enumerate(variants, start=1):
        variant = dict(plan)
        merged = f"{base_note}；{extra}" if base_note else extra
        variant["writing_note"] = merged
        if i >= 3 and variant.get("hook_style") not in {"平稳过渡", "余味收束"}:
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
    merged_note = f"{note}；{retry_note}" if note else retry_note
    retry_plan = dict(plan)
    retry_plan["writing_note"] = merged_note
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
    too_short_retries_left = max(int(getattr(settings, "chapter_too_short_retry_attempts", 0)), 0)
    tail_fix_retries_left = max(int(getattr(settings, "chapter_tail_fix_attempts", 0)), 0)
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
            repaired: str | None = None
            if exc.code in {ErrorCodes.CHAPTER_TOO_SHORT, ErrorCodes.CHAPTER_ENDING_INCOMPLETE}:
                can_repair = (exc.code == ErrorCodes.CHAPTER_ENDING_INCOMPLETE and tail_fix_retries_left > 0) or (exc.code == ErrorCodes.CHAPTER_TOO_SHORT and too_short_retries_left > 0)
                if can_repair:
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
                            delay_ms = max(int(getattr(settings, "chapter_tail_fix_delay_ms", 0)), 0)
                        else:
                            too_short_retries_left -= 1
                            delay_ms = max(int(getattr(settings, "chapter_too_short_retry_delay_ms", 0)), 0)
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
            if (
                exc.code == ErrorCodes.CHAPTER_TOO_SHORT
                and too_short_retries_left > 0
                and isinstance(exc.details, dict)
            ):
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
                delay_ms = max(int(getattr(settings, "chapter_too_short_retry_delay_ms", 0)), 0)
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
        existing = (
            db.query(Chapter)
            .filter(Chapter.novel_id == locked_novel.id, Chapter.chapter_no == next_no)
            .first()
        )
        if existing:
            return existing

        recent_chapters = _load_recent_chapters(db, locked_novel.id, limit=3)
        last_chapter = recent_chapters[-1] if recent_chapters else None
        recent_full_texts = [item.content for item in recent_chapters]
        recent_summaries = _serialize_recent_summaries(db, locked_novel.id)
        story_bible = locked_novel.story_bible or {}
        _ensure_outline_state(story_bible)
        _promote_pending_arc_if_needed(story_bible, next_no)
        locked_novel.story_bible = story_bible
        db.add(locked_novel)

        plan = _ensure_plan_for_chapter(db, locked_novel, next_no, recent_summaries)
        active_interventions = collect_active_interventions(db, locked_novel.id, next_no)
        serialized_active = _serialize_active_interventions(active_interventions)
        serialized_last = _serialize_last_chapter(last_chapter)
        novel_context = _serialize_novel_context(locked_novel, next_no, recent_summaries)
        novel_context, recent_summaries, serialized_last, serialized_active, context_stats = _fit_chapter_payload_budget(
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
            "generator": "chat_completions_api" if settings.llm_provider.lower() == "deepseek" else "responses_api",
            "provider": settings.llm_provider,
            "trace_id": trace_id,
            "based_on_chapter": last_chapter.chapter_no if last_chapter else None,
            "active_interventions": [i.id for i in active_interventions],
            "chapter_plan": used_plan,
            "quality_validated": True,
            "length_targets": length_targets,
            "context_stats": context_stats,
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
