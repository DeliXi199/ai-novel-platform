from __future__ import annotations

from copy import deepcopy
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
from app.services.importance_evaluator import evaluate_story_elements_importance, sort_entities_by_importance
from app.services.resource_card_support import build_resource_capability_plan, build_resource_card, ensure_resource_card_structure, infer_resource_plan_entry
from app.services.story_architecture import ensure_story_architecture
from app.services.core_cast_support import bind_character_to_core_slot, core_cast_guidance_for_chapter
from app.services.character_schedule_support import (
    build_character_relation_schedule_guidance,
    sort_character_names_by_schedule,
    sort_relation_names_by_schedule,
)
from app.services.card_indexing import apply_card_selection_to_packet, build_card_index_payload, ensure_card_id
from app.services.stage_review_support import build_chapter_stage_casting_hint
from app.services.story_character_support import apply_character_template_defaults, character_template_prompt_brief, pick_character_template


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


def _resolve_opening_reveal_guidance(story_bible: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    opening_constraints = (story_bible or {}).get("opening_constraints") or {}
    chapter_range = opening_constraints.get("opening_phase_chapter_range") or [1, 20]
    if not isinstance(chapter_range, list) or len(chapter_range) < 2:
        chapter_range = [1, 20]
    start_no = int(chapter_range[0] or 1)
    end_no = int(chapter_range[1] or 20)
    foundation_schedule = opening_constraints.get("foundation_reveal_schedule") or []
    power_schedule = opening_constraints.get("power_system_reveal_plan") or []

    def _pick_window(items: list[Any]) -> dict[str, Any]:
        for item in items:
            if not isinstance(item, dict):
                continue
            window = item.get("window") or []
            if isinstance(window, list) and len(window) >= 2:
                left = int(window[0] or 0)
                right = int(window[1] or 0)
                if left <= chapter_no <= right:
                    return item
        return items[0] if items and isinstance(items[0], dict) else {}

    foundation = _pick_window(foundation_schedule)
    power = _pick_window(power_schedule)
    in_opening = start_no <= int(chapter_no or 0) <= end_no
    guidance = {
        "in_opening_phase": in_opening,
        "chapter_range": [start_no, end_no],
        "current_window": foundation.get("window") or power.get("window") or [],
        "must_gradually_explain": _truncate_list(opening_constraints.get("must_gradually_explain"), max_items=5, item_limit=36),
        "foundation_focus": _truncate_list(foundation.get("focus"), max_items=4, item_limit=28),
        "foundation_delivery_rule": _truncate_text(foundation.get("delivery_rule"), 88),
        "power_system_focus": _truncate_list(power.get("reveal_topics") or foundation.get("power_system_focus"), max_items=4, item_limit=30),
        "reader_visible_goal": _truncate_text(power.get("reader_visible_goal"), 88),
    }
    return {key: value for key, value in guidance.items() if value not in ("", [], {}, None)}



def _build_character_template_guidance(
    story_bible: dict[str, Any],
    *,
    characters: dict[str, Any],
    candidate_names: list[str],
    focus_name: str,
    protagonist_name: str,
) -> dict[str, Any]:
    ordered_names = _unique_texts([protagonist_name, focus_name, *candidate_names], limit=6, item_limit=20)
    roster: list[dict[str, Any]] = []
    for name in ordered_names:
        card = deepcopy((characters or {}).get(name) or {})
        role_hint = _truncate_text(card.get("role_type") or card.get("role_archetype") or ("protagonist" if name == protagonist_name else "supporting"), 20)
        relation_hint = _truncate_text(card.get("protagonist_relation_level") or card.get("attitude_to_protagonist"), 20)
        note = _truncate_text(card.get("current_goal") or card.get("current_desire") or "", 72)
        template = character_template_prompt_brief(
            story_bible,
            template_id=_truncate_text(card.get("behavior_template_id"), 40),
            fallback=pick_character_template(
                story_bible,
                name=name,
                note=note,
                role_hint=role_hint,
                relation_hint=relation_hint,
                fallback_id="starter_cautious_observer" if name == protagonist_name else "starter_hard_shell_soft_core",
            ),
        )
        enriched = apply_character_template_defaults(card, template)
        roster.append(
            {
                "name": name,
                "role_type": role_hint,
                "relation_level": relation_hint,
                "behavior_template_id": _truncate_text(enriched.get("behavior_template_id"), 40),
                "template_name": _truncate_text(template.get("name"), 18),
                "personality": _truncate_list(template.get("personality"), max_items=4, item_limit=10),
                "speech_style": _truncate_text(enriched.get("speech_style"), 64),
                "behavior_mode": _truncate_text(enriched.get("behavior_mode") or enriched.get("work_style"), 64),
                "core_value": _truncate_text(enriched.get("core_value"), 40),
                "decision_logic": _truncate_text(enriched.get("decision_logic"), 56),
                "pressure_response": _truncate_text(enriched.get("pressure_response"), 48),
                "small_tell": _truncate_text(enriched.get("small_tell"), 28),
                "taboo": _truncate_text(enriched.get("taboo"), 28),
            }
        )
    return {"characters": [item for item in roster if item.get("name")]}



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
    latest_stage_review = _compact_value(console.get("latest_stage_character_review", {}), text_limit=72)
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
    opening_reveal_guidance = _compact_value(_resolve_opening_reveal_guidance(story_bible, chapter_no=next_no), text_limit=72)
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
            "latest_stage_character_review": latest_stage_review,
            "character_roster": character_roster,
            "foreshadowing": foreshadowing,
            "daily_workbench": daily_workbench,
            "serial_rules": serial_rules,
            "fact_ledger": fact_ledger,
            "hard_fact_guard": hard_fact_guard,
            "opening_reveal_guidance": opening_reveal_guidance,
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


def _unique_texts(values: list[Any] | None, *, limit: int, item_limit: int = 32) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _truncate_text(value, item_limit)
        if not text:
            continue
        norm = "".join(text.split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        items.append(text)
        if len(items) >= limit:
            break
    return items



def _plan_text_blob(plan: dict[str, Any]) -> str:
    parts = [
        plan.get("title"),
        plan.get("goal"),
        plan.get("conflict"),
        plan.get("ending_hook"),
        plan.get("main_scene"),
        plan.get("opening_beat"),
        plan.get("mid_turn"),
        plan.get("discovery"),
        plan.get("closing_image"),
        plan.get("supporting_character_note"),
    ]
    parts.extend(_planned_name_list(plan.get("new_resources"), limit=4, item_limit=24))
    parts.extend(_planned_name_list(plan.get("new_factions"), limit=3, item_limit=24))
    for item in _planned_relation_hints(plan.get("new_relations"), limit=3):
        parts.extend([item.get("subject"), item.get("target"), item.get("relation_type"), item.get("status"), item.get("recent_trigger")])
    return "\n".join(str(item or "") for item in parts if str(item or "").strip())



def _planned_name_list(value: Any, *, limit: int, item_limit: int = 24) -> list[str]:
    if isinstance(value, list):
        return _unique_texts(value, limit=limit, item_limit=item_limit)
    if isinstance(value, str):
        parts = [item.strip() for item in value.replace("；", "，").replace(";", "，").split("，")]
        return _unique_texts(parts, limit=limit, item_limit=item_limit)
    return []


def _planned_relation_hints(value: Any, *, limit: int = 3) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        subject = _truncate_text(item.get("subject"), 20)
        target = _truncate_text(item.get("target"), 20)
        if not subject or not target:
            continue
        results.append(
            {
                "subject": subject,
                "target": target,
                "relation_type": _truncate_text(item.get("relation_type"), 24),
                "level": _truncate_text(item.get("level"), 20),
                "status": _truncate_text(item.get("status"), 24),
                "recent_trigger": _truncate_text(item.get("recent_trigger"), 48),
            }
        )
        if len(results) >= limit:
            break
    return results

def _compact_domain_card(card: dict[str, Any] | None, *, entity_type: str) -> dict[str, Any]:
    payload = card or {}
    if entity_type == "character":
        compact = {
            "card_id": _truncate_text(payload.get("card_id"), 16),
            "name": _truncate_text(payload.get("name"), 20),
            "role_type": _truncate_text(payload.get("role_type") or payload.get("role_archetype"), 16),
            "importance_tier": _truncate_text(payload.get("importance_tier"), 16),
            "relation_level": _truncate_text(payload.get("protagonist_relation_level") or payload.get("attitude_to_protagonist"), 20),
            "current_goal": _truncate_text(payload.get("current_goal") or payload.get("current_desire"), 60),
            "behavior_template_id": _truncate_text(payload.get("behavior_template_id"), 40),
            "speech_style": _truncate_text(payload.get("speech_style"), 56),
            "behavior_mode": _truncate_text(payload.get("behavior_mode") or payload.get("work_style") or payload.get("behavior_logic"), 56),
            "core_value": _truncate_text(payload.get("core_value"), 32),
            "decision_logic": _truncate_text(payload.get("decision_logic"), 48),
            "pressure_response": _truncate_text(payload.get("pressure_response"), 40),
            "small_tell": _truncate_text(payload.get("small_tell"), 26),
            "taboo": _truncate_text(payload.get("taboo"), 26),
            "resource_refs": _truncate_list(payload.get("resource_refs"), max_items=4, item_limit=20),
            "faction_refs": _truncate_list(payload.get("faction_refs"), max_items=3, item_limit=20),
            "importance_score": int(payload.get("importance_score") or 0) if payload.get("importance_score") is not None else 0,
            "importance_mainline_rank_score": float(payload.get("importance_mainline_rank_score") or payload.get("importance_soft_rank_score") or 0.0),
            "importance_activation_rank_score": float(payload.get("importance_activation_rank_score") or 0.0),
            "importance_exploration_score": float(payload.get("importance_exploration_score") or 0.0),
            "importance_hint_summary": _truncate_text(payload.get("importance_hint_summary"), 96),
            "tracking_level": _truncate_text(payload.get("tracking_level"), 14),
            "core_cast_slot_id": _truncate_text(payload.get("core_cast_slot_id"), 8),
            "entry_phase": _truncate_text(payload.get("entry_phase"), 12),
            "appearance_frequency": _truncate_text(payload.get("appearance_frequency"), 8),
            "binding_pattern": _truncate_text(payload.get("binding_pattern"), 14),
            "first_entry_mission": _truncate_text(payload.get("first_entry_mission"), 36),
            "long_term_relation_line": _truncate_text(payload.get("long_term_relation_line"), 40),
            "appearance_due_status": _truncate_text(payload.get("appearance_due_status"), 12),
            "appearance_schedule_grade": _truncate_text(payload.get("appearance_schedule_grade"), 12),
        }
    elif entity_type == "resource":
        normalized = ensure_resource_card_structure(payload, fallback_name=_truncate_text(payload.get("name"), 24))
        compact = {
            "card_id": _truncate_text(normalized.get("card_id"), 16),
            "name": _truncate_text(normalized.get("name"), 24),
            "display_name": _truncate_text(normalized.get("display_name"), 24),
            "resource_type": _truncate_text(normalized.get("resource_type"), 18),
            "owner": _truncate_text(normalized.get("owner"), 20),
            "status": _truncate_text(normalized.get("status"), 28),
            "rarity": _truncate_text(normalized.get("rarity"), 20),
            "quantity": int(normalized.get("quantity") or 0),
            "unit": _truncate_text(normalized.get("unit"), 8),
            "stackable": bool(normalized.get("stackable")),
            "quantity_mode": _truncate_text(normalized.get("quantity_mode"), 12),
            "quantity_note": _truncate_text(normalized.get("quantity_note"), 42),
            "resource_scope": _truncate_text(normalized.get("resource_scope"), 14),
            "resource_kind": _truncate_text(normalized.get("resource_kind"), 16),
            "ability_summary": _truncate_text(normalized.get("ability_summary"), 56),
            "core_functions": _truncate_list(normalized.get("core_functions"), max_items=3, item_limit=18),
            "activation_rules": _truncate_list(normalized.get("activation_rules"), max_items=2, item_limit=28),
            "usage_limits": _truncate_list(normalized.get("usage_limits"), max_items=2, item_limit=28),
            "costs": _truncate_list(normalized.get("costs"), max_items=2, item_limit=24),
            "unlock_level": _truncate_text(((normalized.get("unlock_state") or {}).get("level")), 16),
            "exposure_risk": _truncate_text(normalized.get("exposure_risk"), 42),
            "narrative_role": _truncate_text(normalized.get("narrative_role"), 56),
            "importance_tier": _truncate_text(normalized.get("importance_tier") or normalized.get("resource_tier"), 16),
            "importance_score": int(normalized.get("importance_score") or 0),
            "importance_mainline_rank_score": float(normalized.get("importance_mainline_rank_score") or normalized.get("importance_soft_rank_score") or 0.0),
            "importance_activation_rank_score": float(normalized.get("importance_activation_rank_score") or 0.0),
            "importance_exploration_score": float(normalized.get("importance_exploration_score") or 0.0),
            "importance_hint_summary": _truncate_text(normalized.get("importance_hint_summary"), 96),
            "tracking_level": _truncate_text(normalized.get("tracking_level"), 14),
        }
    elif entity_type == "faction":
        compact = {
            "card_id": _truncate_text(payload.get("card_id"), 16),
            "name": _truncate_text(payload.get("name"), 24),
            "faction_level": _truncate_text(payload.get("faction_level"), 20),
            "faction_type": _truncate_text(payload.get("faction_type"), 18),
            "relation_to_protagonist": _truncate_text(payload.get("relation_to_protagonist"), 22),
            "core_goal": _truncate_text(payload.get("core_goal"), 56),
            "resource_control": _truncate_list(payload.get("resource_control"), max_items=4, item_limit=20),
            "key_characters": _truncate_list(payload.get("key_characters"), max_items=4, item_limit=20),
            "importance_tier": _truncate_text(payload.get("importance_tier") or payload.get("faction_importance_tier"), 16),
            "importance_score": int(payload.get("importance_score") or 0),
            "importance_mainline_rank_score": float(payload.get("importance_mainline_rank_score") or payload.get("importance_soft_rank_score") or 0.0),
            "importance_activation_rank_score": float(payload.get("importance_activation_rank_score") or 0.0),
            "importance_exploration_score": float(payload.get("importance_exploration_score") or 0.0),
            "importance_hint_summary": _truncate_text(payload.get("importance_hint_summary"), 96),
        }
    else:
        compact = {
            "card_id": _truncate_text(payload.get("card_id"), 16),
            "relation_id": _truncate_text(payload.get("relation_id"), 48),
            "subject": _truncate_text(payload.get("subject"), 20),
            "target": _truncate_text(payload.get("target"), 20),
            "relation_type": _truncate_text(payload.get("relation_type") or payload.get("change"), 26),
            "level": _truncate_text(payload.get("level") or payload.get("current_level"), 20),
            "status": _truncate_text(payload.get("status") or payload.get("direction"), 32),
            "recent_trigger": _truncate_text(payload.get("recent_trigger") or payload.get("change"), 56),
            "importance_tier": _truncate_text(payload.get("importance_tier") or payload.get("relation_importance_tier"), 16),
            "importance_score": int(payload.get("importance_score") or 0),
            "importance_mainline_rank_score": float(payload.get("importance_mainline_rank_score") or payload.get("importance_soft_rank_score") or 0.0),
            "importance_activation_rank_score": float(payload.get("importance_activation_rank_score") or 0.0),
            "importance_exploration_score": float(payload.get("importance_exploration_score") or 0.0),
            "importance_hint_summary": _truncate_text(payload.get("importance_hint_summary"), 96),
            "interaction_depth": _truncate_text(payload.get("interaction_depth"), 12),
            "push_direction": _truncate_text(payload.get("relation_push_direction"), 12),
            "relation_due_status": _truncate_text(payload.get("relation_due_status"), 12),
        }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}



def _ensure_planned_character_card(
    story_bible: dict[str, Any],
    *,
    name: str,
    protagonist_name: str,
    chapter_no: int,
    note: str | None = None,
) -> bool:
    clean_name = _truncate_text(name, 20)
    if not clean_name:
        return False
    domains = story_bible.setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    console = story_bible.setdefault("control_console", {})
    cards = console.setdefault("character_cards", {})
    created = False
    template = pick_character_template(
        story_bible,
        name=clean_name,
        note=_truncate_text(note, 72),
        role_hint="protagonist" if clean_name == protagonist_name else "supporting",
        relation_hint="self" if clean_name == protagonist_name else "待观察",
        fallback_id="starter_cautious_observer" if clean_name == protagonist_name else "starter_hard_shell_soft_core",
    )
    if clean_name not in characters:
        characters[clean_name] = apply_character_template_defaults(
            {
                "name": clean_name,
                "entity_type": "character",
                "role_type": "supporting" if clean_name != protagonist_name else "protagonist",
                "importance_tier": "重要配角" if clean_name != protagonist_name else "核心主角",
                "protagonist_relation_level": "待观察" if clean_name != protagonist_name else "self",
                "narrative_priority": 72 if clean_name != protagonist_name else 100,
                "current_goal": _truncate_text(note or "在当前局势里保住自身利益并观察主角。", 64),
                "relationship_index": {},
                "resource_refs": [],
                "faction_refs": [],
                "status": "planned",
                "first_planned_chapter": chapter_no,
            },
            template,
        )
        if note and len(str(note).strip()) >= 8:
            characters[clean_name]["speech_style"] = _truncate_text(note, 56)
        created = True
    else:
        characters[clean_name].setdefault("status", "active")
        characters[clean_name].setdefault("first_planned_chapter", chapter_no)
    if clean_name not in cards:
        cards[clean_name] = apply_character_template_defaults(
            {
                "name": clean_name,
                "role_type": "supporting" if clean_name != protagonist_name else "protagonist",
                "current_desire": _truncate_text(note or "先保住眼前利益，再看是否靠近主角。", 56),
                "attitude_to_protagonist": "待观察" if clean_name != protagonist_name else "self",
            },
            template,
        )
        if note and len(str(note).strip()) >= 8:
            cards[clean_name]["speech_style"] = _truncate_text(note, 56)
        created = True
    if clean_name != protagonist_name:
        bind_character_to_core_slot(
            story_bible,
            character_name=clean_name,
            chapter_no=chapter_no,
            note=_truncate_text(note, 48),
            protagonist_name=protagonist_name,
        )
    return created



def _ensure_planned_resource_card(
    story_bible: dict[str, Any],
    *,
    name: str,
    protagonist_name: str,
    chapter_no: int,
) -> str | None:
    clean_name = _truncate_text(name, 24)
    if not clean_name:
        return None
    domains = story_bible.setdefault("story_domains", {})
    resources = domains.setdefault("resources", {})
    existing = resources.get(clean_name)
    if isinstance(existing, dict):
        existing.setdefault("status", "planned")
        existing.setdefault("first_planned_chapter", chapter_no)
        return None
    resource_name, resource_card = build_resource_card(
        clean_name,
        owner=protagonist_name or "待观察",
        resource_type="本章新引入资源",
        status="planned",
        rarity="待判定",
        exposure_risk="待观察",
        narrative_role="本章规划阶段预登记的新资源，正文需按卡片信息落地。",
        recent_change=f"第{chapter_no}章规划预登记。",
        source="chapter_plan",
    )
    if not resource_name:
        return None
    resource_card["first_planned_chapter"] = chapter_no
    resources[resource_name] = resource_card
    return resource_name



def _ensure_planned_faction_card(
    story_bible: dict[str, Any],
    *,
    name: str,
    protagonist_name: str,
    chapter_no: int,
) -> str | None:
    clean_name = _truncate_text(name, 24)
    if not clean_name:
        return None
    domains = story_bible.setdefault("story_domains", {})
    factions = domains.setdefault("factions", {})
    existing = factions.get(clean_name)
    if isinstance(existing, dict):
        existing.setdefault("first_planned_chapter", chapter_no)
        return None
    factions[clean_name] = {
        "name": clean_name,
        "entity_type": "faction",
        "faction_level": "待细化",
        "faction_type": "本章新引入势力",
        "territory": "待后续章节补充",
        "core_goal": "先围绕当前事件行动，后续再细化长期目标。",
        "relation_to_protagonist": "待观察",
        "resource_control": [],
        "key_characters": [protagonist_name] if protagonist_name else [],
        "importance_tier": "阶段级",
        "importance_score": 54,
        "first_planned_chapter": chapter_no,
    }
    return clean_name



def _ensure_planned_relation_card(
    story_bible: dict[str, Any],
    *,
    subject: str,
    target: str,
    chapter_no: int,
    relation_type: str | None = None,
    level: str | None = None,
    status: str | None = None,
    recent_trigger: str | None = None,
) -> str | None:
    clean_subject = _truncate_text(subject, 20)
    clean_target = _truncate_text(target, 20)
    if not clean_subject or not clean_target:
        return None
    relation_id = _truncate_text(f"{clean_subject}::{clean_target}", 48)
    domains = story_bible.setdefault("story_domains", {})
    relations = domains.setdefault("relations", {})
    existing = relations.get(relation_id)
    if isinstance(existing, dict):
        existing.setdefault("first_planned_chapter", chapter_no)
        if relation_type and not existing.get("relation_type"):
            existing["relation_type"] = relation_type
        if level and not existing.get("level"):
            existing["level"] = level
        if status and not existing.get("status"):
            existing["status"] = status
        if recent_trigger and not existing.get("recent_trigger"):
            existing["recent_trigger"] = recent_trigger
        return None
    relations[relation_id] = {
        "relation_id": relation_id,
        "entity_type": "relation",
        "subject": clean_subject,
        "target": clean_target,
        "left": clean_subject,
        "right": clean_target,
        "relation_type": _truncate_text(relation_type, 24) or "待观察",
        "level": _truncate_text(level, 20) or "新建",
        "current_level": _truncate_text(level, 20) or "新建",
        "status": _truncate_text(status, 24) or "刚建立",
        "next_direction": "待后续发展",
        "recent_trigger": _truncate_text(recent_trigger, 48) or f"第{chapter_no}章规划首次挂接。",
        "first_planned_chapter": chapter_no,
        "last_updated_chapter": chapter_no,
        "importance_tier": "阶段级",
        "importance_score": 52,
    }
    return relation_id



def _infer_entities_from_text(text: str, candidates: dict[str, Any] | None, *, limit: int = 4) -> list[str]:
    source = str(text or "")
    matches: list[str] = []
    seen: set[str] = set()
    for key in (candidates or {}).keys():
        name = str(key or "").strip()
        if not name or len(name) <= 1:
            continue
        if name in source and name not in seen:
            seen.add(name)
            matches.append(_truncate_text(name, 24))
            if len(matches) >= limit:
                break
    return matches



def _collect_relevant_relations(relations: dict[str, Any], characters: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    selected_keys: list[str] = []
    selected_cards: list[dict[str, Any]] = []
    char_set = set(characters)
    for key, card in (relations or {}).items():
        if not isinstance(card, dict):
            continue
        subject = _truncate_text(card.get("subject"), 20)
        target = _truncate_text(card.get("target"), 20)
        if not subject or not target:
            continue
        if subject in char_set or target in char_set:
            selected_keys.append(_truncate_text(key, 32))
            selected_cards.append(_compact_domain_card(card, entity_type="relation"))
            if len(selected_keys) >= 4:
                break
    return selected_keys, selected_cards


def _combine_importance_lanes(
    container: dict[str, Any],
    names: list[str],
    *,
    base_limit: int,
    keep_names: list[str] | None = None,
    allow_exploration: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    ordered_names = [name for name in names if name in container]
    keep = [name for name in (keep_names or []) if name in ordered_names]
    mainline_ranked = sort_entities_by_importance(container, ordered_names, mode="mainline")
    activation_ranked = sort_entities_by_importance(container, ordered_names, mode="activation")
    exploration_ranked = [
        name
        for name in sort_entities_by_importance(container, ordered_names, mode="exploration")
        if bool((container.get(name) or {}).get("importance_exploration_candidate"))
    ]
    mainline_soft_cap = max(int(getattr(settings, "importance_eval_mainline_soft_cap", 4) or 4), 2)
    activation_slots = max(int(getattr(settings, "importance_eval_activation_slots", 1) or 1), 0)
    exploration_slots = max(int(getattr(settings, "importance_eval_exploration_slots", 1) or 1), 0) if allow_exploration else 0
    selected: list[str] = []
    lane_map = {"mainline": [], "activation": [], "exploration": [], "forced": []}

    def _append(candidates: list[str], lane: str, limit: int) -> None:
        if limit <= 0:
            return
        for name in candidates:
            if name in selected or name not in ordered_names:
                continue
            selected.append(name)
            lane_map[lane].append(name)
            if len(lane_map[lane]) >= limit or len(selected) >= base_limit:
                break

    _append(keep, "forced", max(len(keep), 0))
    remaining_slots = max(base_limit - len(selected), 0)
    _append(mainline_ranked, "mainline", min(mainline_soft_cap, remaining_slots))
    remaining_slots = max(base_limit - len(selected), 0)
    _append(activation_ranked, "activation", min(activation_slots, remaining_slots))
    remaining_slots = max(base_limit - len(selected), 0)
    _append(exploration_ranked, "exploration", min(exploration_slots, remaining_slots))
    remaining_slots = max(base_limit - len(selected), 0)
    if remaining_slots > 0:
        fallback = mainline_ranked + activation_ranked + exploration_ranked
        _append(fallback, "mainline", remaining_slots)

    meta = {
        "forced": keep,
        "mainline_top": mainline_ranked[: min(6, len(mainline_ranked))],
        "activation_top": activation_ranked[: min(6, len(activation_ranked))],
        "exploration_top": exploration_ranked[: min(4, len(exploration_ranked))],
        "selected_by_lane": lane_map,
    }
    return selected[:base_limit], meta



def _build_resource_plan(resources: dict[str, Any], selected_resources: list[str], plan_text: str) -> dict[str, Any]:
    plan_map: dict[str, Any] = {}
    for name in selected_resources:
        card = resources.get(name)
        if not isinstance(card, dict):
            continue
        normalized_card = ensure_resource_card_structure(card, fallback_name=name)
        plan_map[name] = infer_resource_plan_entry(name, normalized_card, plan_text)
    return plan_map


def _outline_entry_for_chapter(console: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    for source_key in ("chapter_card_queue", "near_7_chapter_outline"):
        for item in (console.get(source_key) or []):
            if int(item.get("chapter_no", 0) or 0) == chapter_no:
                return item
    return {}



def _build_recent_continuity_plan(
    *,
    story_bible: dict[str, Any],
    protagonist_name: str,
    plan: dict[str, Any],
    serialized_last: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    console = (story_bible.get("control_console") or {}) if isinstance(story_bible, dict) else {}
    chapter_no = int(plan.get("chapter_no", 0) or 0)
    bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else {}
    current_outline = _outline_entry_for_chapter(console, chapter_no)
    next_outline = _outline_entry_for_chapter(console, chapter_no + 1)
    next_two_outline = _outline_entry_for_chapter(console, chapter_no + 2)

    recent_progression: list[dict[str, Any]] = []
    for summary in recent_summaries[-3:]:
        if not isinstance(summary, dict):
            continue
        recent_progression.append(
            {
                "chapter_no": int(summary.get("chapter_no", 0) or 0),
                "event_summary": _truncate_text(summary.get("event_summary"), 72),
                "open_hooks": _truncate_list(summary.get("open_hooks"), max_items=2, item_limit=40),
                "closed_hooks": _truncate_list(summary.get("closed_hooks"), max_items=2, item_limit=40),
            }
        )

    unresolved = _unique_texts(
        list(bridge.get("unresolved_action_chain") or [])
        + list(bridge.get("carry_over_clues") or [])
        + [hook for summary in recent_summaries[-3:] for hook in (summary.get("open_hooks") or [])],
        limit=6,
        item_limit=56,
    )
    recently_closed = _unique_texts(
        [hook for summary in recent_summaries[-2:] for hook in (summary.get("closed_hooks") or [])],
        limit=4,
        item_limit=40,
    )
    carry_in = _unique_texts(
        [
            bridge.get("opening_anchor"),
            serialized_last.get("tail_excerpt"),
            plan.get("opening_beat"),
            plan.get("goal"),
        ]
        + list(bridge.get("carry_over_clues") or []),
        limit=5,
        item_limit=72,
    )

    focus_targets = _unique_texts(
        [
            protagonist_name,
            plan.get("supporting_character_focus"),
            *list(bridge.get("onstage_characters") or []),
        ],
        limit=5,
        item_limit=20,
    )

    handoff_targets = []
    for outline in (next_outline, next_two_outline):
        if not outline:
            continue
        handoff_targets.append(
            {
                "chapter_no": int(outline.get("chapter_no", 0) or 0),
                "title": _truncate_text(outline.get("title"), 24),
                "goal": _truncate_text(outline.get("goal"), 56),
                "hook": _truncate_text(outline.get("hook") or outline.get("ending") or outline.get("opening"), 48),
            }
        )

    continuity_tasks = _unique_texts(
        [
            f"先承接：{_truncate_text(bridge.get('opening_anchor') or serialized_last.get('tail_excerpt'), 56)}" if (bridge.get("opening_anchor") or serialized_last.get("tail_excerpt")) else "",
            f"本章必须回应：{unresolved[0]}" if unresolved else "",
            f"让{plan.get('supporting_character_focus')}继续释放态度变化。" if plan.get("supporting_character_focus") else "",
            f"把本章结果自然递给第{handoff_targets[0]['chapter_no']}章。" if handoff_targets else "",
        ],
        limit=4,
        item_limit=68,
    )

    preserve_for_next = _unique_texts(
        [
            plan.get("ending_hook"),
            plan.get("closing_image"),
            *(item.get("hook") for item in handoff_targets if isinstance(item, dict)),
        ],
        limit=4,
        item_limit=48,
    )

    return {
        "window_summary": {
            "recent_range": [item.get("chapter_no") for item in recent_progression if item.get("chapter_no")],
            "current_chapter_no": chapter_no,
            "lookahead_range": [item.get("chapter_no") for item in handoff_targets if item.get("chapter_no")],
        },
        "recent_progression": recent_progression,
        "carry_in": {
            "opening_anchor": _truncate_text(bridge.get("opening_anchor") or serialized_last.get("tail_excerpt"), 96),
            "carry_over_points": carry_in,
            "unresolved_hooks": unresolved,
            "recently_closed": recently_closed,
            "focus_targets": focus_targets,
        },
        "current_chapter_bridge": {
            "must_continue": unresolved[:3],
            "must_payoff": _unique_texts(
                list(unresolved[:2])
                + [plan.get("goal"), plan.get("conflict"), current_outline.get("goal")],
                limit=4,
                item_limit=56,
            ),
            "scene_entry": _truncate_text(
                current_outline.get("opening")
                or plan.get("opening_beat")
                or bridge.get("opening_anchor")
                or serialized_last.get("tail_excerpt"),
                88,
            ),
            "emotion_line": _truncate_text(
                bridge.get("opening_anchor")
                or plan.get("conflict")
                or plan.get("supporting_character_note"),
                72,
            ),
        },
        "lookahead_handoff": {
            "next_outline_beats": handoff_targets,
            "preserve_for_next": preserve_for_next,
            "handoff_rule": "这章收尾既要落结果，也要给后一两章留自然延续点，不要像断片。",
        },
        "continuity_tasks": continuity_tasks,
        "rhythm_guardrails": [
            "先接上一章动作与情绪，再推进本章新变化。",
            "最近两三章在追的线索，本章至少回应一项，不要整章失忆。",
            "结尾的后劲要能自然递给下一章入口，而不是重新起跑。",
        ],
    }


def build_chapter_plan_packet(
    *,
    story_bible: dict[str, Any],
    protagonist_name: str,
    plan: dict[str, Any],
    serialized_last: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    domains = story_bible.setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    resources = domains.setdefault("resources", {})
    factions = domains.setdefault("factions", {})
    relations = domains.setdefault("relations", {})
    planner_state = story_bible.setdefault("planner_state", {})
    selected_entities_by_chapter = planner_state.setdefault("selected_entities_by_chapter", {})
    resource_plan_cache = planner_state.setdefault("resource_plan_cache", {})
    resource_capability_plan_cache = planner_state.setdefault("resource_capability_plan_cache", {})
    continuity_packet_cache = planner_state.setdefault("continuity_packet_cache", {})

    chapter_no = int(plan.get("chapter_no", 0) or 0)
    focus_name = _truncate_text(plan.get("supporting_character_focus"), 20)
    note = _truncate_text(plan.get("supporting_character_note"), 64)
    bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else {}
    bridge_characters = _unique_texts(bridge.get("onstage_characters") or serialized_last.get("onstage_characters") or [], limit=4, item_limit=20)
    core_cast_guidance = core_cast_guidance_for_chapter(story_bible, chapter_no=chapter_no or 1, focus_name=focus_name)
    chapter_stage_casting_hint = build_chapter_stage_casting_hint(story_bible, chapter_no=chapter_no or 1, plan=plan)

    created_characters: list[str] = []
    created_resources: list[str] = []
    created_factions: list[str] = []
    created_relations: list[str] = []
    candidate_characters = _unique_texts([protagonist_name, focus_name, *bridge_characters], limit=6, item_limit=20)
    for name in candidate_characters:
        if _ensure_planned_character_card(
            story_bible,
            name=name,
            protagonist_name=protagonist_name,
            chapter_no=chapter_no,
            note=note if name == focus_name else None,
        ):
            created_characters.append(name)

    planned_new_resources = _planned_name_list(plan.get("new_resources"), limit=4, item_limit=24)
    planned_new_factions = _planned_name_list(plan.get("new_factions"), limit=3, item_limit=24)
    planned_new_relations = _planned_relation_hints(plan.get("new_relations"), limit=3)

    for name in planned_new_resources:
        created_name = _ensure_planned_resource_card(
            story_bible,
            name=name,
            protagonist_name=protagonist_name,
            chapter_no=chapter_no,
        )
        if created_name:
            created_resources.append(created_name)

    for name in planned_new_factions:
        created_name = _ensure_planned_faction_card(
            story_bible,
            name=name,
            protagonist_name=protagonist_name,
            chapter_no=chapter_no,
        )
        if created_name:
            created_factions.append(created_name)

    for relation in planned_new_relations:
        for endpoint in [relation.get("subject"), relation.get("target")]:
            endpoint_name = _truncate_text(endpoint, 20)
            if not endpoint_name or endpoint_name in (domains.get("factions") or {}):
                continue
            if _ensure_planned_character_card(
                story_bible,
                name=endpoint_name,
                protagonist_name=protagonist_name,
                chapter_no=chapter_no,
                note=None,
            ):
                created_characters.append(endpoint_name)
            candidate_characters = _unique_texts(list(candidate_characters) + [endpoint_name], limit=8, item_limit=20)
        relation_id = _ensure_planned_relation_card(
            story_bible,
            subject=relation.get("subject") or "",
            target=relation.get("target") or "",
            chapter_no=chapter_no,
            relation_type=relation.get("relation_type"),
            level=relation.get("level"),
            status=relation.get("status"),
            recent_trigger=relation.get("recent_trigger"),
        )
        if relation_id:
            created_relations.append(relation_id)

    plan_text = _plan_text_blob(plan)
    selected_resources = _unique_texts(
        planned_new_resources
        + _infer_entities_from_text(plan_text, resources, limit=4)
        + [item for name in candidate_characters for item in ((characters.get(name) or {}).get("resource_refs") or [])],
        limit=6,
        item_limit=24,
    )
    selected_factions = _unique_texts(
        planned_new_factions
        + _infer_entities_from_text(plan_text, factions, limit=4)
        + [item for name in candidate_characters for item in ((characters.get(name) or {}).get("faction_refs") or [])],
        limit=5,
        item_limit=24,
    )
    relation_keys, relation_cards = _collect_relevant_relations(relations, candidate_characters)
    relation_keys = _unique_texts(list(planned_new_relations and created_relations or []) + relation_keys, limit=5, item_limit=32)

    touched_entities = {
        "character": list(candidate_characters),
        "resource": _unique_texts(list(selected_resources) + [item for item in ((characters.get(protagonist_name) or {}).get("resource_refs") or [])], limit=8, item_limit=24),
        "faction": list(selected_factions),
        "relation": list(relation_keys),
    }
    importance_summary = evaluate_story_elements_importance(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        scope="planning",
        chapter_no=chapter_no,
        plan=plan,
        recent_summaries=recent_summaries,
        touched_entities=touched_entities,
        allow_ai=True,
    )

    priority_resources = []
    for item in ((characters.get(protagonist_name) or {}).get("resource_refs") or []):
        card = resources.get(item) or {}
        tier = _truncate_text(card.get("importance_tier") or card.get("resource_tier"), 16)
        score = int(card.get("importance_score") or 0)
        if tier in {"核心级", "重要级"} or score >= 72:
            priority_resources.append(item)
    selected_resources = _unique_texts(list(selected_resources) + priority_resources[:2], limit=6, item_limit=24)

    character_selection_lanes: dict[str, Any]
    resource_selection_lanes: dict[str, Any]
    faction_selection_lanes: dict[str, Any]
    relation_selection_lanes: dict[str, Any]
    candidate_characters, character_selection_lanes = _combine_importance_lanes(
        characters,
        candidate_characters,
        base_limit=6,
        keep_names=[protagonist_name, focus_name],
        allow_exploration=True,
    )
    selected_resources, resource_selection_lanes = _combine_importance_lanes(
        resources,
        selected_resources,
        base_limit=6,
        keep_names=priority_resources[:2],
        allow_exploration=True,
    )
    selected_factions, faction_selection_lanes = _combine_importance_lanes(
        factions,
        selected_factions,
        base_limit=5,
        keep_names=[],
        allow_exploration=True,
    )
    relation_force_keep = [f"{protagonist_name}::{focus_name}"] if protagonist_name and focus_name and f"{protagonist_name}::{focus_name}" in relation_keys else []
    relation_keys, relation_selection_lanes = _combine_importance_lanes(
        relations,
        relation_keys,
        base_limit=5,
        keep_names=relation_force_keep,
        allow_exploration=False,
    )

    character_relation_schedule = build_character_relation_schedule_guidance(
        story_bible,
        protagonist_name=protagonist_name,
        chapter_no=chapter_no or 1,
        focus_name=focus_name,
        plan=plan,
    )
    candidate_characters = sort_character_names_by_schedule(
        characters,
        candidate_characters,
        guidance=character_relation_schedule,
        protagonist_name=protagonist_name,
    )
    relation_keys = sort_relation_names_by_schedule(
        relations,
        relation_keys,
        guidance=character_relation_schedule,
    )

    for name in candidate_characters:
        card = characters.get(name)
        if isinstance(card, dict):
            ensure_card_id(story_bible, entity_type="character", entity_name=name, card=card)
    for name in selected_resources:
        card = resources.get(name)
        if isinstance(card, dict):
            ensure_card_id(story_bible, entity_type="resource", entity_name=name, card=card)
    for name in selected_factions:
        card = factions.get(name)
        if isinstance(card, dict):
            ensure_card_id(story_bible, entity_type="faction", entity_name=name, card=card)
    for name in relation_keys:
        card = relations.get(name)
        if isinstance(card, dict):
            ensure_card_id(story_bible, entity_type="relation", entity_name=name, card=card)

    relevant_cards = {
        "characters": {name: _compact_domain_card(characters.get(name), entity_type="character") for name in candidate_characters if characters.get(name)},
        "resources": {name: _compact_domain_card(resources.get(name), entity_type="resource") for name in selected_resources if resources.get(name)},
        "factions": {name: _compact_domain_card(factions.get(name), entity_type="faction") for name in selected_factions if factions.get(name)},
        "relations": [_compact_domain_card(relations.get(name), entity_type="relation") for name in relation_keys if relations.get(name)],
    }
    card_index = build_card_index_payload(relevant_cards)
    resource_plan = _build_resource_plan(resources, selected_resources, plan_text)
    resource_capability_plan = build_resource_capability_plan(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        plan=plan,
        resources=resources,
        selected_resources=selected_resources,
        recent_summaries=recent_summaries,
        serialized_last=serialized_last,
        allow_ai=True,
    )
    recent_continuity_plan = _build_recent_continuity_plan(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=recent_summaries,
    )
    opening_reveal_guidance = _resolve_opening_reveal_guidance(story_bible, chapter_no=chapter_no or 1)
    character_template_guidance = _build_character_template_guidance(
        story_bible,
        characters=characters,
        candidate_names=list(candidate_characters),
        focus_name=focus_name,
        protagonist_name=protagonist_name,
    )

    selected_entities_by_chapter[str(chapter_no)] = {
        "characters": list(candidate_characters),
        "resources": list(selected_resources),
        "factions": list(selected_factions),
        "relations": list(relation_keys),
    }

    resource_plan_cache[str(chapter_no)] = resource_plan
    resource_capability_plan_cache[str(chapter_no)] = resource_capability_plan
    continuity_packet_cache[str(chapter_no)] = recent_continuity_plan
    planner_state["last_continuity_review_chapter"] = chapter_no

    continuity_window = {
        "recent_chapter_summaries": _compact_value(recent_summaries[-3:], text_limit=72),
        "last_chapter_tail_excerpt": _truncate_text(serialized_last.get("tail_excerpt"), settings.chapter_last_excerpt_chars),
        "last_two_paragraphs": _truncate_list(serialized_last.get("last_two_paragraphs"), max_items=2, item_limit=220),
        "opening_anchor": _truncate_text((bridge or {}).get("opening_anchor"), 120),
        "unresolved_action_chain": _truncate_list((bridge or {}).get("unresolved_action_chain"), max_items=3, item_limit=64),
        "carry_over_clues": _truncate_list((bridge or {}).get("carry_over_clues"), max_items=3, item_limit=56),
        "onstage_characters": bridge_characters,
    }

    packet = {
        "chapter_identity": {
            "chapter_no": chapter_no,
            "title": _truncate_text(plan.get("title"), 30),
            "goal": _truncate_text(plan.get("goal"), 72),
            "conflict": _truncate_text(plan.get("conflict"), 72),
            "main_scene": _truncate_text(plan.get("main_scene"), 42),
            "hook_style": _truncate_text(plan.get("hook_style"), 16),
            "flow_template_id": _truncate_text(plan.get("flow_template_id"), 32),
            "flow_template_tag": _truncate_text(plan.get("flow_template_tag"), 12),
            "flow_template_name": _truncate_text(plan.get("flow_template_name"), 20),
        },
        "selected_elements": {
            "characters": candidate_characters,
            "focus_character": focus_name,
            "resources": selected_resources,
            "factions": selected_factions,
            "relations": relation_keys,
            "due_characters": list((character_relation_schedule.get("appearance_schedule") or {}).get("due_characters") or []),
            "due_relations": list((character_relation_schedule.get("relationship_schedule") or {}).get("due_relations") or []),
            "importance_mainline_characters": list(character_selection_lanes.get("selected_by_lane", {}).get("mainline") or []),
            "importance_activation_characters": list(character_selection_lanes.get("selected_by_lane", {}).get("activation") or []),
            "importance_exploration_characters": list(character_selection_lanes.get("selected_by_lane", {}).get("exploration") or []),
            "importance_activation_resources": list(resource_selection_lanes.get("selected_by_lane", {}).get("activation") or []),
            "importance_exploration_resources": list(resource_selection_lanes.get("selected_by_lane", {}).get("exploration") or []),
        },
        "core_cast_guidance": core_cast_guidance,
        "chapter_stage_casting_hint": chapter_stage_casting_hint,
        "character_relation_schedule": character_relation_schedule,
        "new_cards_created": {
            "characters": _unique_texts(created_characters, limit=8, item_limit=20),
            "resources": _unique_texts(created_resources, limit=4, item_limit=24),
            "factions": _unique_texts(created_factions, limit=3, item_limit=24),
            "relations": _unique_texts(created_relations, limit=4, item_limit=32),
        },
        "flow_plan": {
            "flow_template_id": _truncate_text(plan.get("flow_template_id"), 32),
            "flow_template_tag": _truncate_text(plan.get("flow_template_tag"), 12),
            "flow_template_name": _truncate_text(plan.get("flow_template_name"), 20),
            "turning_points": _truncate_list(plan.get("flow_turning_points"), max_items=4, item_limit=28),
            "variation_note": _truncate_text(plan.get("flow_variation_note"), 72),
        },
        "resource_plan": resource_plan,
        "resource_capability_plan": resource_capability_plan,
        "recent_continuity_plan": recent_continuity_plan,
        "opening_reveal_guidance": opening_reveal_guidance,
        "character_template_guidance": character_template_guidance,
        "importance_snapshot": importance_summary.get("evaluations") or {},
        "importance_runtime": {
            "used_ai": bool(importance_summary.get("used_ai")),
            "selection_lanes": {
                "characters": character_selection_lanes,
                "resources": resource_selection_lanes,
                "factions": faction_selection_lanes,
                "relations": relation_selection_lanes,
            },
        },
        "card_index": card_index,
        "relevant_cards": relevant_cards,
        "continuity_window": continuity_window,
        "open_loops": _unique_texts(
            list((bridge or {}).get("unresolved_action_chain") or [])
            + list((bridge or {}).get("carry_over_clues") or [])
            + [hook for summary in recent_summaries[-3:] for hook in (summary.get("open_hooks") or [])],
            limit=6,
            item_limit=64,
        ),
        "input_policy": {
            "write_from": ["chapter_plan", "recent_continuity_plan", "selected_story_cards", "resource_plan", "resource_capability_plan", "recent_chapter_summaries", "last_chapter_tail_excerpt"],
            "avoid": ["full_card_pool_dump", "whole_book_recap", "detached_scene_reset"],
            "continuity_priority": "先承接上一章末尾，再落实本章拍表，并兼顾最近几章的连续推进。",
            "resource_quantity_rule": "资源若带数量字段，正文必须保持前后数量一致，不得随意改写。",
            "resource_ability_rule": "资源若带能力档案，只能按 resource_capability_plan 和资源卡里的条件/代价/限制来写，不得突然无代价开新功能。",
            "stage_casting_rule": "若 chapter_stage_casting_hint 里的 final_should_execute_planned_action=true，就自然落实补新人或旧人换功能；若 final_do_not_force_action=true，则不要硬塞。",
            "importance_lane_rule": "优先落实推进榜对象，再给激活榜留补位口，同时保留少量探索槽位，让冷门但合适的对象有自然冒头机会。",
        },
    }
    return packet



def _pick_story_memory(base_story_memory: dict[str, Any]) -> dict[str, Any]:
    keep_keys = {
        "project_card",
        "current_volume_card",
        "protagonist_state",
        "recent_retrospectives",
        "hard_fact_guard",
        "opening_reveal_guidance",
        "workflow_runtime",
        "continuity_rules",
        "fact_ledger",
        "chapter_release_state",
    }
    return {key: value for key, value in (base_story_memory or {}).items() if key in keep_keys and value not in (None, "", [], {})}



def serialize_local_novel_context(
    *,
    novel: Novel,
    next_no: int,
    recent_summaries: list[dict[str, Any]],
    chapter_plan_packet: dict[str, Any],
    execution_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_context = _serialize_novel_context(novel, next_no, recent_summaries)
    if str(base_context.get("context_mode") or "").lower() == "full":
        base_context["context_mode"] = "planned_local"
        base_context["chapter_plan_packet"] = chapter_plan_packet
        if execution_brief is not None:
            base_context["execution_brief"] = execution_brief
        return base_context

    story_memory = _pick_story_memory(base_context.get("story_memory") or {})
    story_memory["execution_brief"] = _compact_value(execution_brief or {}, text_limit=78)
    story_memory["chapter_local_context"] = _compact_value(chapter_plan_packet, text_limit=84)
    story_memory["context_strategy"] = {
        "mode": "planned_local",
        "source_order": ["本章拍表", "近章承接规划", "本章规划包", "最近几章摘要", "上一章末尾正文片段"],
        "note": "正文先吃近几章滚动承接，再围绕本章相关卡片与连续性窗口写，不回看全量卡池。",
    }
    base_context["context_mode"] = "planned_local"
    base_context["story_memory"] = story_memory
    return base_context



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
