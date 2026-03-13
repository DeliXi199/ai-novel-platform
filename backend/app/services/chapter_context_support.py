from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.services.hard_fact_guard import compact_hard_fact_guard
from app.services.story_architecture import ensure_story_architecture


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



def _tail_paragraphs(content: str, count: int = 2) -> list[str]:
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    if not blocks:
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if lines:
            blocks = [" ".join(lines)]
    return [_truncate_text(block, 220) for block in blocks[-count:]]



def _compact_scene_card(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw or {}
    card = {
        "main_scene": _truncate_text(payload.get("main_scene"), 42),
        "opening": _truncate_text(payload.get("opening") or payload.get("opening_beat"), 60),
        "middle": _truncate_text(payload.get("middle") or payload.get("mid_turn"), 60),
        "ending": _truncate_text(payload.get("ending") or payload.get("closing_image") or payload.get("ending_hook"), 60),
        "chapter_hook": _truncate_text(payload.get("chapter_hook") or payload.get("ending_hook"), 60),
        "supporting_character_focus": _truncate_text(payload.get("supporting_character_focus"), 24),
    }
    return {key: value for key, value in card.items() if value}



def _extract_continuity_bridge(last_chapter: Chapter, protagonist_name: str | None = None) -> dict[str, Any]:
    generation_meta = last_chapter.generation_meta or {}
    existing = generation_meta.get("continuity_bridge") if isinstance(generation_meta, dict) else None
    if isinstance(existing, dict) and existing.get("source_chapter_no") == last_chapter.chapter_no:
        bridge = dict(existing)
        bridge["source_chapter_no"] = int(last_chapter.chapter_no)
        bridge["title"] = _truncate_text(last_chapter.title, 30)
        bridge["tail_excerpt"] = _truncate_text(bridge.get("tail_excerpt") or last_chapter.content[-settings.chapter_last_excerpt_chars :], settings.chapter_last_excerpt_chars)
        bridge["last_two_paragraphs"] = [_truncate_text(item, 220) for item in (bridge.get("last_two_paragraphs") or [])[:2]]
        bridge["last_scene_card"] = _compact_scene_card(bridge.get("last_scene_card"))
        bridge["unresolved_action_chain"] = _truncate_list(bridge.get("unresolved_action_chain"), max_items=3, item_limit=64)
        bridge["carry_over_clues"] = _truncate_list(bridge.get("carry_over_clues"), max_items=3, item_limit=56)
        bridge["onstage_characters"] = _truncate_list(bridge.get("onstage_characters"), max_items=5, item_limit=20)
        bridge["next_opening_instruction"] = _truncate_text(bridge.get("next_opening_instruction"), 72)
        bridge["opening_anchor"] = _truncate_text(bridge.get("opening_anchor"), 120)
        return bridge

    chapter_plan = generation_meta.get("chapter_plan") if isinstance(generation_meta, dict) else {}
    summary = getattr(last_chapter, "summary", None)
    tail_excerpt = _truncate_text(last_chapter.content[-settings.chapter_last_excerpt_chars :], settings.chapter_last_excerpt_chars)
    last_two_paragraphs = _tail_paragraphs(last_chapter.content, count=2)
    onstage_characters: list[str] = []
    for candidate in [protagonist_name, chapter_plan.get("supporting_character_focus") if isinstance(chapter_plan, dict) else None]:
        text_value = _truncate_text(candidate, 20)
        if text_value and text_value not in onstage_characters:
            onstage_characters.append(text_value)
    if summary is not None:
        character_updates = getattr(summary, "character_updates", None) or {}
        if isinstance(character_updates, dict):
            for name in list(character_updates.keys())[:4]:
                if str(name).strip() == "notes":
                    continue
                text_value = _truncate_text(name, 20)
                if text_value and text_value not in onstage_characters:
                    onstage_characters.append(text_value)
    unresolved = _truncate_list(getattr(summary, "open_hooks", []) if summary is not None else [], max_items=3, item_limit=64)
    carry_over_clues = _truncate_list(getattr(summary, "new_clues", []) if summary is not None else [], max_items=3, item_limit=56)
    opening_instruction = _truncate_text(
        (chapter_plan.get("opening_beat") if isinstance(chapter_plan, dict) else None) or "下一章开头必须承接上一章最后动作、对话或局势变化。",
        72,
    )
    return {
        "source_chapter_no": int(last_chapter.chapter_no),
        "title": _truncate_text(last_chapter.title, 30),
        "tail_excerpt": tail_excerpt,
        "last_two_paragraphs": last_two_paragraphs,
        "last_scene_card": _compact_scene_card(chapter_plan if isinstance(chapter_plan, dict) else {}),
        "unresolved_action_chain": unresolved,
        "carry_over_clues": carry_over_clues,
        "onstage_characters": onstage_characters[:5],
        "next_opening_instruction": opening_instruction,
        "opening_anchor": _truncate_text(last_two_paragraphs[-1] if last_two_paragraphs else tail_excerpt, 120),
    }



def _serialize_last_chapter(last_chapter: Chapter | None, protagonist_name: str | None = None) -> dict:
    if not last_chapter:
        return {}
    continuity_bridge = _extract_continuity_bridge(last_chapter, protagonist_name=protagonist_name)
    return {
        "chapter_no": last_chapter.chapter_no,
        "title": _truncate_text(last_chapter.title, 30),
        "tail_excerpt": continuity_bridge.get("tail_excerpt") or _truncate_text(
            last_chapter.content[-settings.chapter_last_excerpt_chars :],
            settings.chapter_last_excerpt_chars,
        ),
        "continuity_bridge": continuity_bridge,
        "last_two_paragraphs": continuity_bridge.get("last_two_paragraphs", []),
        "last_scene_card": continuity_bridge.get("last_scene_card", {}),
        "unresolved_action_chain": continuity_bridge.get("unresolved_action_chain", []),
        "onstage_characters": continuity_bridge.get("onstage_characters", []),
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



def _published_and_stock_facts(story_bible: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger = (story_bible.get("fact_ledger") or {}) if isinstance(story_bible, dict) else {}
    published = ledger.get("published_facts") if isinstance(ledger.get("published_facts"), list) else []
    stock = ledger.get("stock_facts") if isinstance(ledger.get("stock_facts"), list) else []
    return published[-8:], stock[-6:]



def _validate_fact_ledger_state(story_bible: dict[str, Any], next_chapter_no: int) -> None:
    from app.services.generation_exceptions import ErrorCodes, GenerationError

    long_term_state = (story_bible.get("long_term_state") or {}) if isinstance(story_bible, dict) else {}
    release_state = (long_term_state.get("chapter_release_state") or {}) if isinstance(long_term_state, dict) else {}
    published_through = int(release_state.get("published_through", 0) or 0)
    latest_generated = int(release_state.get("latest_generated_chapter", 0) or 0)
    ledger = (story_bible.get("fact_ledger") or {}) if isinstance(story_bible, dict) else {}
    published_facts = ledger.get("published_facts") if isinstance(ledger.get("published_facts"), list) else []
    if published_facts:
        published_max = max(int(item.get("chapter_no", 0) or 0) for item in published_facts)
        if published_max < published_through:
            raise GenerationError(
                code=ErrorCodes.PLANNING_DOC_MISSING,
                message=f"第 {next_chapter_no} 章生成前，已发布事实索引未覆盖到第 {published_through} 章。",
                stage="fact_ledger_validation",
                retryable=True,
                http_status=409,
                details={"chapter_no": next_chapter_no, "published_through": published_through, "published_fact_max": published_max},
            )
    if latest_generated and latest_generated < published_through:
        raise GenerationError(
            code=ErrorCodes.PLANNING_DOC_MISSING,
            message=f"第 {next_chapter_no} 章生成前，发布状态层与已生成章节号不一致。",
            stage="fact_ledger_validation",
            retryable=False,
            http_status=409,
            details={"chapter_no": next_chapter_no, "latest_generated": latest_generated, "published_through": published_through},
        )



def _serialize_novel_context(novel: Novel, next_no: int, recent_summaries: list[dict[str, Any]]) -> dict:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    if settings.chapter_context_mode.lower() != "light":
        return {
            "context_mode": "full",
            "novel_id": novel.id,
            "title": novel.title,
            "genre": novel.genre,
            "premise": novel.premise,
            "protagonist_name": novel.protagonist_name,
            "style_preferences": novel.style_preferences,
            "story_bible": story_bible,
            "current_chapter_no": novel.current_chapter_no,
            "target_chapter_no": next_no,
        }

    style_preferences = _compact_value(novel.style_preferences or {}, text_limit=50)
    global_direction = _select_outline_window(story_bible.get("global_outline", {}), next_no)
    active_arc = _compact_arc(story_bible.get("active_arc"))
    live_hooks = _collect_live_hooks(recent_summaries)
    console = story_bible.get("control_console") or {}
    protagonist_state = _compact_value(console.get("protagonist_state", {}), text_limit=56)
    current_volume = _compact_value(
        next((card for card in story_bible.get("volume_cards", []) if int(card.get("start_chapter", 0) or 0) <= next_no <= int(card.get("end_chapter", 0) or 10**9)), {}),
        text_limit=70,
    )
    project_card = _compact_value(story_bible.get("project_card", {}), text_limit=70)
    near_outline = _compact_value(console.get("near_7_chapter_outline", []), text_limit=64)
    recent_progress = _compact_value((console.get("recent_progress") or [])[-3:], text_limit=72)
    recent_retrospectives = _compact_value((console.get("chapter_retrospectives") or [])[-2:], text_limit=72)
    character_cards = console.get("character_cards") or {}
    character_roster = []
    if isinstance(character_cards, dict):
        for idx, card in enumerate(character_cards.values()):
            if idx >= 4 or not isinstance(card, dict):
                break
            character_roster.append(
                {
                    "name": _truncate_text(card.get("name"), 16),
                    "role_archetype": _truncate_text(card.get("role_archetype"), 16),
                    "speech_style": _truncate_text(card.get("speech_style"), 44),
                    "small_tell": _truncate_text(card.get("small_tell"), 30),
                    "taboo": _truncate_text(card.get("taboo"), 30),
                }
            )
    foreshadowing = _compact_value([item for item in (console.get("foreshadowing") or []) if item.get("status") != "closed"][:6], text_limit=64)
    daily_workbench = _compact_value(console.get("daily_workbench", {}), text_limit=72)
    release_state = _compact_value((((story_bible.get("long_term_state") or {}).get("chapter_release_state") or {})), text_limit=64)
    serial_rules = _compact_value((story_bible.get("serial_rules") or {}), text_limit=64)
    published_facts, stock_facts = _published_and_stock_facts(story_bible)
    fact_ledger = _compact_value({"published_facts": published_facts, "stock_facts": stock_facts}, text_limit=74)
    hard_fact_guard = _compact_value(compact_hard_fact_guard(story_bible.get("hard_fact_guard", {}), max_items=3), text_limit=76)
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
            "continuity_rules": _truncate_list(story_bible.get("continuity_rules"), max_items=5, item_limit=42),
            "characterization_rules": _truncate_list(story_bible.get("characterization_rules"), max_items=4, item_limit=42),
            "language_rules": _truncate_list(story_bible.get("language_rules"), max_items=4, item_limit=42),
            "antagonist_rules": _truncate_list(story_bible.get("antagonist_rules"), max_items=3, item_limit=42),
            "protagonist_emotion_rules": _truncate_list(story_bible.get("protagonist_emotion_rules"), max_items=3, item_limit=42),
            "ending_rules": _truncate_list(story_bible.get("ending_rules"), max_items=4, item_limit=42),
            "global_direction": global_direction,
            "active_arc": active_arc,
            "live_hooks": live_hooks,
            "project_card": project_card,
            "current_volume_card": current_volume,
            "protagonist_state": protagonist_state,
            "near_7_chapter_outline": near_outline,
            "recent_progress": recent_progress,
            "recent_retrospectives": recent_retrospectives,
            "character_roster": character_roster,
            "foreshadowing": foreshadowing,
            "daily_workbench": daily_workbench,
            "serial_rules": serial_rules,
            "fact_ledger": fact_ledger,
            "hard_fact_guard": hard_fact_guard,
            "chapter_release_state": release_state,
            "workflow_runtime": {
                "stage": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("stage")), 24),
                "note": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("note")), 72),
                "failed_stage": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("failed_stage")), 24),
                "last_error_message": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("last_error_message")), 72),
                "retry_feedback": _compact_value(((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("retry_feedback")) or {}), text_limit=64),
            },
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
        bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else None
        if bridge is not None:
            bridge["tail_excerpt"] = serialized_last["tail_excerpt"]

    if total_size() > budget and isinstance(serialized_last.get("last_two_paragraphs"), list) and len(serialized_last["last_two_paragraphs"]) > 1:
        serialized_last["last_two_paragraphs"] = serialized_last["last_two_paragraphs"][-1:]
        bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else None
        if bridge is not None:
            bridge["last_two_paragraphs"] = list(serialized_last["last_two_paragraphs"])

    if total_size() > budget and isinstance(serialized_last.get("unresolved_action_chain"), list) and len(serialized_last["unresolved_action_chain"]) > 2:
        serialized_last["unresolved_action_chain"] = serialized_last["unresolved_action_chain"][:2]
        bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else None
        if bridge is not None:
            bridge["unresolved_action_chain"] = list(serialized_last["unresolved_action_chain"])

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
        "continuity_bridge_chars": _json_size(serialized_last.get("continuity_bridge", {})) if serialized_last.get("continuity_bridge") else 0,
    }
    return novel_context, recent_summaries, serialized_last, serialized_active, stats



def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a[:1500], b[:1500]).ratio()
