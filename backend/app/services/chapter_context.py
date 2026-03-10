from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel


def truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def truncate_list(values: list[Any] | None, *, max_items: int, item_limit: int) -> list[str]:
    result: list[str] = []
    for item in values or []:
        text = truncate_text(item, item_limit)
        if text:
            result.append(text)
        if len(result) >= max_items:
            break
    return result


def compact_value(value: Any, *, text_limit: int = 60) -> Any:
    if isinstance(value, str):
        return truncate_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [compact_value(item, text_limit=text_limit) for item in value[:6]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 8:
                break
            compact[str(key)] = compact_value(item, text_limit=text_limit)
        return compact
    return truncate_text(value, text_limit)


def normalize_hook(hook: Any) -> str:
    return "".join(str(hook or "").split())


def json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False))


def serialize_recent_summaries(db: Session, novel_id: int) -> list[dict[str, Any]]:
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
                "chapter_title": truncate_text(chapter.title, 30),
                "event_summary": truncate_text(summary.event_summary, settings.chapter_recent_summary_chars),
                "open_hooks": truncate_list(summary.open_hooks, max_items=3, item_limit=48),
                "closed_hooks": truncate_list(summary.closed_hooks, max_items=2, item_limit=48),
            }
        )
    return serialized


def load_recent_chapters(db: Session, novel_id: int, limit: int = 3) -> list[Chapter]:
    rows = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def serialize_active_interventions(active_interventions: list[Intervention]) -> list[dict[str, Any]]:
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
            compact["protected_characters"] = truncate_list(
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


def serialize_last_chapter(last_chapter: Chapter | None) -> dict[str, Any]:
    if not last_chapter:
        return {}
    return {
        "chapter_no": last_chapter.chapter_no,
        "title": truncate_text(last_chapter.title, 30),
        "tail_excerpt": truncate_text(
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
                "title": truncate_text(act.get("title"), 24),
                "purpose": truncate_text(act.get("purpose"), 60),
                "summary": truncate_text(act.get("summary"), 90),
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
        "focus": truncate_text(arc.get("focus"), 70),
        "bridge_note": truncate_text(arc.get("bridge_note"), 90),
    }


def _phase_rule(story_bible: dict[str, Any], next_no: int) -> str:
    pacing_rules = story_bible.get("pacing_rules", {}) if isinstance(story_bible, dict) else {}
    if next_no <= 3 and pacing_rules.get("first_three_chapters"):
        return truncate_text(pacing_rules["first_three_chapters"], 80)
    if next_no <= 12 and pacing_rules.get("first_twelve_chapters"):
        return truncate_text(pacing_rules["first_twelve_chapters"], 80)
    return truncate_text(pacing_rules.get("overall"), 80)


def _collect_live_hooks(recent_summaries: list[dict[str, Any]]) -> list[str]:
    closed = {
        normalize_hook(hook)
        for summary in recent_summaries
        for hook in summary.get("closed_hooks", [])
        if normalize_hook(hook)
    }
    live_hooks: list[str] = []
    seen: set[str] = set()
    for summary in reversed(recent_summaries):
        for hook in summary.get("open_hooks", []):
            normalized = normalize_hook(hook)
            if not normalized or normalized in closed or normalized in seen:
                continue
            seen.add(normalized)
            live_hooks.append(truncate_text(hook, 48))
            if len(live_hooks) >= settings.chapter_live_hook_limit:
                return live_hooks
    return live_hooks


def serialize_novel_context(novel: Novel, next_no: int, recent_summaries: list[dict[str, Any]]) -> dict[str, Any]:
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
    style_preferences = compact_value(novel.style_preferences or {}, text_limit=50)
    global_direction = _select_outline_window(story_bible.get("global_outline", {}), next_no)
    active_arc = _compact_arc(story_bible.get("active_arc"))
    live_hooks = _collect_live_hooks(recent_summaries)
    return {
        "context_mode": "light",
        "novel_id": novel.id,
        "title": truncate_text(novel.title, 40),
        "genre": truncate_text(novel.genre, 20),
        "premise": truncate_text(novel.premise, 180),
        "protagonist_name": truncate_text(novel.protagonist_name, 20),
        "style_preferences": style_preferences,
        "current_chapter_no": novel.current_chapter_no,
        "target_chapter_no": next_no,
        "story_memory": {
            "narrative_style": truncate_text(story_bible.get("narrative_style"), 40),
            "core_conflict": truncate_text(story_bible.get("core_conflict"), 110),
            "phase_rule": _phase_rule(story_bible, next_no),
            "forbidden_rules": truncate_list(story_bible.get("forbidden_rules"), max_items=5, item_limit=28),
            "continuity_rules": [
                "核心线索物件的形态与规模要稳定，除非本章明确解释变化。",
                "如果时间推进超过一天，开头两段必须写明过渡。",
                "结尾必须自然收束，不能停在半句。",
            ],
            "characterization_rules": truncate_list(story_bible.get("characterization_rules"), max_items=4, item_limit=42),
            "language_rules": truncate_list(story_bible.get("language_rules"), max_items=4, item_limit=42),
            "antagonist_rules": truncate_list(story_bible.get("antagonist_rules"), max_items=3, item_limit=42),
            "protagonist_emotion_rules": truncate_list(story_bible.get("protagonist_emotion_rules"), max_items=3, item_limit=42),
            "ending_rules": truncate_list(story_bible.get("ending_rules"), max_items=4, item_limit=42),
            "global_direction": global_direction,
            "active_arc": active_arc,
            "live_hooks": live_hooks,
        },
    }


def fit_chapter_payload_budget(
    novel_context: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    serialized_last: dict[str, Any],
    serialized_active: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    budget = settings.chapter_prompt_max_chars
    before = json_size(novel_context) + json_size(recent_summaries) + json_size(serialized_last) + json_size(serialized_active)

    def total_size() -> int:
        return json_size(novel_context) + json_size(recent_summaries) + json_size(serialized_last) + json_size(serialized_active)

    if total_size() > budget and serialized_last.get("tail_excerpt"):
        serialized_last["tail_excerpt"] = truncate_text(serialized_last["tail_excerpt"], min(260, settings.chapter_last_excerpt_chars))

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
            story_memory["core_conflict"] = truncate_text(story_memory["core_conflict"], 80)
        if isinstance(story_memory.get("phase_rule"), str):
            story_memory["phase_rule"] = truncate_text(story_memory["phase_rule"], 60)

    if total_size() > budget:
        novel_context["premise"] = truncate_text(novel_context.get("premise"), 120)

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
