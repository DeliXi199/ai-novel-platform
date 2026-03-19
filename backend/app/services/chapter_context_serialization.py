from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.services.chapter_context_common import (
    _collect_live_hooks,
    _compact_arc,
    _compact_scene_card,
    _compact_scene_handoff_card,
    _compact_value,
    _phase_rule,
    _published_and_stock_facts,
    _resolve_opening_reveal_guidance,
    _select_outline_window,
    _tail_paragraphs,
    _truncate_list,
    _truncate_text,
    _unique_texts,
)
from app.services.hard_fact_guard import compact_hard_fact_guard
from app.services.story_architecture import ensure_story_architecture


_SUMMARY_RESERVED_UPDATE_KEYS = {"notes", "__resource_updates__", "__monster_updates__", "__power_progress__"}


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
        bridge["scene_handoff_card"] = _compact_scene_handoff_card(bridge.get("scene_handoff_card"))
        bridge["unresolved_action_chain"] = _truncate_list(bridge.get("unresolved_action_chain"), max_items=3, item_limit=64)
        bridge["carry_over_clues"] = _truncate_list(bridge.get("carry_over_clues"), max_items=3, item_limit=56)
        bridge["onstage_characters"] = _truncate_list(bridge.get("onstage_characters"), max_items=5, item_limit=20)
        bridge["next_opening_instruction"] = _truncate_text(bridge.get("next_opening_instruction"), 72)
        bridge["opening_anchor"] = _truncate_text(bridge.get("opening_anchor"), 120)
        if isinstance(bridge.get("scene_execution_card"), dict):
            scene_card = dict(bridge.get("scene_execution_card") or {})
            scene_card["scene_count"] = int(scene_card.get("scene_count", 0) or 0)
            scene_card["transition_mode"] = _truncate_text(scene_card.get("transition_mode"), 24)
            scene_card["first_scene_focus"] = _truncate_text(scene_card.get("first_scene_focus"), 28)
            scene_card["sequence_note"] = _truncate_text(scene_card.get("sequence_note"), 84)
            bridge["scene_execution_card"] = scene_card
        bridge["scene_outline"] = _compact_value(bridge.get("scene_outline") or [], text_limit=72)
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
                clean_name = str(name).strip()
                if not clean_name or clean_name in _SUMMARY_RESERVED_UPDATE_KEYS or clean_name.startswith("__"):
                    continue
                text_value = _truncate_text(clean_name, 20)
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
        "scene_handoff_card": {},
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
        "scene_handoff_card": continuity_bridge.get("scene_handoff_card", {}),
        "unresolved_action_chain": continuity_bridge.get("unresolved_action_chain", []),
        "onstage_characters": continuity_bridge.get("onstage_characters", []),
    }



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
    active_arc_digest = _compact_value(
        story_bible.get("active_arc_digest") or ((story_bible.get("story_workspace") or {}).get("active_arc_digest") or {}),
        text_limit=72,
    )
    live_hooks = _collect_live_hooks(recent_summaries)
    workspace_state = story_bible.get("story_workspace") or {}
    protagonist_profile = _compact_value(workspace_state.get("protagonist_profile", {}), text_limit=56)
    current_volume = _compact_value(
        next((card for card in story_bible.get("volume_cards", []) if int(card.get("start_chapter", 0) or 0) <= next_no <= int(card.get("end_chapter", 0) or 10**9)), {}),
        text_limit=70,
    )
    project_card = _compact_value(story_bible.get("project_card", {}), text_limit=70)
    near_outline = _compact_value(workspace_state.get("near_7_chapter_outline", []), text_limit=64)
    recent_progress = _compact_value((workspace_state.get("recent_progress") or [])[-3:], text_limit=72)
    recent_retrospectives = _compact_value((workspace_state.get("chapter_retrospectives") or [])[-2:], text_limit=72)
    latest_stage_review = _compact_value(workspace_state.get("latest_stage_character_review", {}), text_limit=72)
    cast_cards = workspace_state.get("cast_cards") or {}
    character_roster = []
    if isinstance(cast_cards, dict):
        for idx, card in enumerate(cast_cards.values()):
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
    foreshadowing = _compact_value([item for item in (workspace_state.get("foreshadowing") or []) if item.get("status") != "closed"][:6], text_limit=64)
    monster_cards = workspace_state.get("monster_cards") or {}
    monster_roster = []
    if isinstance(monster_cards, dict):
        for idx, card in enumerate(monster_cards.values()):
            if idx >= 4 or not isinstance(card, dict):
                break
            monster_roster.append(
                {
                    "name": _truncate_text(card.get("name"), 16),
                    "species_type": _truncate_text(card.get("species_type"), 16),
                    "current_realm": _truncate_text(card.get("current_realm") or card.get("threat_level"), 16),
                    "threat_note": _truncate_text(card.get("threat_note"), 42),
                }
            )
    power_system_snapshot = _compact_value(
        {
            "strength_rank_table": (((story_bible.get("power_system") or {}).get("strength_rank_table")) or {}),
            "resource_quality_table": (((story_bible.get("power_system") or {}).get("resource_quality_table")) or {}),
            "power_ledger": workspace_state.get("power_ledger") or {},
        },
        text_limit=72,
    )
    daily_workbench = _compact_value(workspace_state.get("daily_workbench", {}), text_limit=72)
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
            "active_arc_digest": active_arc_digest,
            "live_hooks": live_hooks,
            "project_card": project_card,
            "current_volume_card": current_volume,
            "protagonist_profile": protagonist_profile,
            "near_7_chapter_outline": near_outline,
            "recent_progress": recent_progress,
            "recent_retrospectives": recent_retrospectives,
            "latest_stage_character_review": latest_stage_review,
            "character_roster": character_roster,
            "monster_roster": monster_roster,
            "power_system_snapshot": power_system_snapshot,
            "foreshadowing": foreshadowing,
            "daily_workbench": daily_workbench,
            "serial_rules": serial_rules,
            "fact_ledger": fact_ledger,
            "hard_fact_guard": hard_fact_guard,
            "opening_reveal_guidance": opening_reveal_guidance,
            "chapter_release_state": release_state,
            "book_execution_profile": _compact_value((story_bible.get("book_execution_profile") or {}), text_limit=72),
            "window_execution_bias": _compact_value((((story_bible.get("story_workspace") or {}).get("window_execution_bias") or {})), text_limit=72),
            "card_system_profile": _compact_value((story_bible.get("card_system_profile") or {}), text_limit=72),
            "workflow_runtime": {
                "stage": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("stage")), 24),
                "note": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("note")), 72),
                "failed_stage": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("failed_stage")), 24),
                "last_error_message": _truncate_text((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("last_error_message")), 72),
                "retry_feedback": _compact_value(((((story_bible.get("workflow_state") or {}).get("live_runtime") or {}).get("retry_feedback")) or {}), text_limit=64),
            },
        },
    }



def _pick_story_memory(base_story_memory: dict[str, Any]) -> dict[str, Any]:
    keep_keys = {
        "project_card",
        "current_volume_card",
        "protagonist_profile",
        "foreshadowing",
        "recent_retrospectives",
        "hard_fact_guard",
        "opening_reveal_guidance",
        "workflow_runtime",
        "continuity_rules",
        "fact_ledger",
        "chapter_release_state",
        "book_execution_profile",
        "window_execution_bias",
        "card_system_profile",
        "monster_roster",
        "power_system_snapshot",
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
