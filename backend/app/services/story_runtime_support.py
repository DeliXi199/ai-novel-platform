from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.models.novel import Novel
from app.services.hard_fact_guard import (
    build_hard_fact_guard_rules,
    ensure_hard_fact_guard,
    rebuild_hard_fact_guard_from_chapters,
)
from app.services.story_fact_ledger import _ensure_fact_ledger, _empty_fact_ledger, rebuild_fact_ledger_from_chapters
from app.services.core_cast_support import empty_core_cast_state, ensure_core_cast_state_shape, summarize_core_cast_state
from app.services.prompt_support import compact_data

STORY_BIBLE_SCHEMA_VERSION = 9
STORY_BIBLE_ARCHITECTURE = "story_bible_v2_foundation"
DEFAULT_SERIAL_DELIVERY_MODE = "live_publish"



def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def build_serial_rules() -> dict[str, Any]:
    return {
        "published_chapters_immutable": True,
        "published_text_is_not_draft": True,
        "fact_priority": ["published_chapters", "stock_chapters", "planning_docs"],
        "fact_ledger_policy": {
            "enabled": True,
            "published_facts_locked": True,
            "stock_facts_promotable": True,
            "fallback_indexing": "chapter_title_and_summary",
        },
        "inventory_policy": {
            "unpublished_inventory_repairable": True,
            "repair_scope": "tail_only",
            "published_chapters_never_rewritten": True,
        },
        "batch_generation": {
            "sequential_only": True,
            "refresh_state_between_chapters": True,
            "parallel_generation_forbidden": True,
        },
        "daily_modes": ["live_publish", "stockpile"],
        "problem_resolution_policy": "一旦发现问题，优先调整后续结构、近纲、库存稿与后文承接，不回改已发布硬事实。",
        "ending_policy": "项目不能只会往前拖，必须在后期主动收束主线、人物、伏笔与主角成长。",
        "hard_fact_guard": build_hard_fact_guard_rules(),
    }



def _empty_story_domains() -> dict[str, Any]:
    return {
        "characters": {},
        "resources": {},
        "relations": {},
        "factions": {},
    }



def _empty_power_system() -> dict[str, Any]:
    return {
        "system_name": "主修力量体系",
        "realm_system": {
            "realms": [],
            "realm_cards": [],
            "current_reference_realm": "低阶求生阶段",
        },
        "power_rules": {
            "gap_rules": "高阶压制有效，越阶战只能偶发成立。",
            "breakthrough_conditions": "需要资源、时机、心境与风险承受能力。",
            "cross_realm_rule": "越阶战必须靠准备、代价、环境和对手失误成立。",
            "core_limitations": [],
        },
        "combat_rules": {
            "combat_styles": "战斗力不只是数值，还包括信息掌控、法器、经验与持续力。",
            "same_realm_layers": "同境界内也分准备程度与经验。",
            "forbidden_patterns": [],
        },
    }



def _empty_opening_constraints() -> dict[str, Any]:
    return {
        "opening_phase_chapter_range": [1, 20],
        "must_gradually_explain": [],
        "background_delivery": {
            "world_background": "前20章内逐步交代世界背景。",
            "faction_landscape": "前20章内逐步显影主要势力格局。",
            "power_system": "前20章内逐步交代修炼/力量体系与实力等级骨架。",
        },
        "pace_rules": {
            "first_three_chapters": "前三章要先钉牢主角处境与第一轮目标。",
            "first_fifteen_chapters": "前15章内持续轮换风险、关系、资源与世界认知推进。",
            "first_twenty_chapters": "前20章内逐步补齐世界、势力与实力等级体系的基础认知。",
            "forbidden_shortcuts": [],
        },
        "foundation_reveal_schedule": [],
        "power_system_reveal_plan": [],
        "long_term_mainline": {
            "opening_goal": "先活下去，再争取立足资本与主动权。",
            "mid_term_hint": "中期扩大势力、资源与真相博弈层级。",
            "endgame_hint": "后期收束主线、人物与主题。",
        },
    }



def _empty_template_library() -> dict[str, Any]:
    return {
        "character_templates": [],
        "flow_templates": [],
        "payoff_cards": [],
        "scene_templates": [],
        "roadmap": {
            "character_template_target_count": 40,
            "flow_template_target_count": 36,
            "payoff_card_target_count": 40,
            "scene_template_target_count": 20,
            "current_character_template_count": 0,
            "current_flow_template_count": 0,
            "current_payoff_card_count": 0,
            "current_scene_template_count": 0,
            "status": "foundation_ready",
            "note": "先把模板库仓位建出来，后续再扩充完整模板。",
        },
    }



def _empty_planner_state() -> dict[str, Any]:
    return {
        "recent_flow_usage": [],
        "chapter_element_selection": {},
        "resource_plan_cache": {},
        "resource_capability_plan_cache": {},
        "resource_plan_history": [],
        "resource_capability_history": [],
        "selected_entities_by_chapter": {},
        "continuity_packet_cache": {},
        "rolling_continuity_history": [],
        "last_planned_chapter": 0,
        "last_continuity_review_chapter": 0,
        "status": "foundation_ready",
    }



def _empty_retrospective_state() -> dict[str, Any]:
    return {
        "last_review_chapter": 0,
        "last_stage_review_chapter": 0,
        "pending_character_reviews": [],
        "relationship_watchlist": [],
        "scheduled_review_interval": 5,
        "last_review_notes": [],
        "latest_stage_character_review": {},
        "status": "foundation_ready",
    }



def _empty_flow_control() -> dict[str, Any]:
    return {
        "anti_repeat_window": 5,
        "recent_event_types": [],
        "recent_flow_ids": [],
        "consecutive_flow_penalty": 2,
        "status": "foundation_ready",
    }



def _empty_entity_registry() -> dict[str, Any]:
    return {
        "by_type": {
            "character": [],
            "resource": [],
            "relation": [],
            "faction": [],
        },
        "card_ids": {
            "character": {},
            "resource": {},
            "relation": {},
            "faction": {},
        },
        "next_seq": {
            "character": 1,
            "resource": 1,
            "relation": 1,
            "faction": 1,
        },
        "last_rebuilt_at": None,
    }


def _empty_importance_state() -> dict[str, Any]:
    return {
        "version": 4,
        "status": "foundation_ready",
        "unified_dimensions": [
            "binding_depth",
            "recurrence",
            "mainline_leverage",
            "irreplaceability",
            "stage_relevance",
            "network_influence",
        ],
        "last_scope": None,
        "last_evaluated_chapter": 0,
        "last_run_used_ai": False,
        "last_ai_eval_by_scope": {},
        "evaluation_history": [],
        "next_chapter_handoff": {},
        "entity_index": {
            "character": {},
            "resource": {},
            "relation": {},
            "faction": {},
        },
    }


def _empty_constraint_reasoning_state() -> dict[str, Any]:
    return {
        "version": 1,
        "status": "foundation_ready",
        "last_task_type": None,
        "last_scope": None,
        "last_chapter": 0,
        "last_run_used_ai": False,
        "last_run_at": None,
        "history": [],
    }


def _empty_core_cast_state() -> dict[str, Any]:
    return empty_core_cast_state()



def _deep_fill_missing(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        existing = target.get(key)
        if key not in target or existing is None or existing == "" or existing == []:
            target[key] = deepcopy(value)
            continue
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_fill_missing(existing, value)
    return target



def _empty_long_term_state(delivery_mode: str = DEFAULT_SERIAL_DELIVERY_MODE) -> dict[str, Any]:
    return {
        "protagonist_profile": {},
        "character_states": {},
        "resource_states": {},
        "relation_states": {},
        "faction_states": {},
        "foreshadowing_state": [],
        "history_summaries": [],
        "volume_progress": [],
        "planner_state_snapshot": {},
        "fact_ledger": _empty_fact_ledger(),
        "chapter_release_state": {
            "delivery_mode": delivery_mode,
            "published_through": 0,
            "latest_generated_chapter": 0,
            "latest_available_chapter": 0,
            "stock_chapter_count": 0,
            "published_chapter_count": 0,
            "locked_chapter_count": 0,
            "chapters": {},
        },
    }



def _ensure_serial_runtime(story_bible: dict[str, Any]) -> dict[str, Any]:
    runtime = story_bible.setdefault("serial_runtime", {})
    runtime.setdefault("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)
    runtime.setdefault("supports_live_publish", True)
    runtime.setdefault("supports_stockpile", True)
    runtime.setdefault("last_publish_action", None)
    runtime.setdefault("continuity_mode", "strong_bridge")
    runtime.setdefault("previous_chapter_bridge", {})
    return runtime



def _ensure_story_bible_meta(story_bible: dict[str, Any]) -> dict[str, Any]:
    meta = story_bible.setdefault("story_bible_meta", {})
    previous_version = int(meta.get("schema_version", 0) or 0)
    previous_architecture = str(meta.get("architecture") or "").strip()
    if previous_version and previous_version != STORY_BIBLE_SCHEMA_VERSION:
        history = meta.setdefault("upgrade_history", [])
        history.append(
            {
                "from_version": previous_version,
                "to_version": STORY_BIBLE_SCHEMA_VERSION,
                "from_architecture": previous_architecture or None,
                "to_architecture": STORY_BIBLE_ARCHITECTURE,
                "reason": "升级到 Story Bible V2 正式结构。",
            }
        )
    meta["schema_version"] = STORY_BIBLE_SCHEMA_VERSION
    meta["architecture"] = STORY_BIBLE_ARCHITECTURE
    meta.setdefault(
        "migration_notes",
        [
            "Story Bible 已升级到统一的 V2 地基结构。",
            "新增 story_domains、power_system、opening_constraints、template_library 等正式域。",
            "新增统一 importance_state，用同一流程跟踪角色/资源/关系/势力的重要性。",
            "新增 constraint_reasoning_state，用局部约束包统一承接判断/生成型推理。",
            "新增 core_cast_state，用名额制规划核心配角的人数、登场阶段与长期关系线。",
            "story_workspace 运行态字段已统一改名为 protagonist_profile / cast_cards / relationship_journal，不再保留旧工作区字段口径。",
        ],
    )
    return story_bible



def ensure_story_bible_v2_structure(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    payload = story_bible if isinstance(story_bible, dict) else {}
    _ensure_story_bible_meta(payload)
    payload.setdefault("project_card", payload.get("project_card") or {})
    payload.setdefault("world_bible", payload.get("world_bible") or {})
    payload.setdefault("cultivation_system", payload.get("cultivation_system") or {})
    payload.setdefault("story_domains", _empty_story_domains())
    payload.setdefault("power_system", _empty_power_system())
    payload.setdefault("opening_constraints", _empty_opening_constraints())
    payload.setdefault("template_library", _empty_template_library())
    payload.setdefault("planner_state", _empty_planner_state())
    payload.setdefault("retrospective_state", _empty_retrospective_state())
    payload.setdefault("flow_control", _empty_flow_control())
    payload.setdefault("entity_registry", _empty_entity_registry())
    payload.setdefault("importance_state", _empty_importance_state())
    payload.setdefault("constraint_reasoning_state", _empty_constraint_reasoning_state())
    payload.setdefault("core_cast_state", _empty_core_cast_state())
    _deep_fill_missing(payload["story_domains"], _empty_story_domains())
    _deep_fill_missing(payload["power_system"], _empty_power_system())
    _deep_fill_missing(payload["opening_constraints"], _empty_opening_constraints())
    _deep_fill_missing(payload["template_library"], _empty_template_library())
    _deep_fill_missing(payload["planner_state"], _empty_planner_state())
    _deep_fill_missing(payload["retrospective_state"], _empty_retrospective_state())
    _deep_fill_missing(payload["flow_control"], _empty_flow_control())
    _deep_fill_missing(payload["entity_registry"], _empty_entity_registry())
    _deep_fill_missing(payload["importance_state"], _empty_importance_state())
    _deep_fill_missing(payload["constraint_reasoning_state"], _empty_constraint_reasoning_state())
    payload["core_cast_state"] = ensure_core_cast_state_shape(payload.get("core_cast_state"))
    return payload



def _current_volume_card(story_bible: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    volume_cards = story_bible.get("volume_cards") or []
    if not volume_cards:
        return {}
    current = volume_cards[-1]
    for card in volume_cards:
        start = int(card.get("start_chapter", 0) or 0)
        end = int(card.get("end_chapter", 0) or 0)
        if start <= chapter_no <= end or (start <= chapter_no and end == 0):
            current = card
            break
    return current



def _build_initialization_packet(story_bible: dict[str, Any], current_chapter_no: int = 0) -> dict[str, Any]:
    current_volume = _current_volume_card(story_bible, max(current_chapter_no + 1, 1)) if story_bible.get("volume_cards") else {}
    workspace_state = story_bible.get("story_workspace") or {}
    opening_constraints = story_bible.get("opening_constraints") or {}
    return {
        "documents_only": True,
        "current_volume_card": current_volume,
        "near_7_chapter_outline": (workspace_state.get("near_7_chapter_outline") or [])[:7],
        "chapter_card_queue": (workspace_state.get("chapter_card_queue") or [])[:7],
        "opening_constraints_brief": {
            "chapter_range": opening_constraints.get("opening_phase_chapter_range") or [1, 20],
            "must_gradually_explain": (opening_constraints.get("must_gradually_explain") or [])[:5],
        },
        "core_cast_brief": summarize_core_cast_state(story_bible.get("core_cast_state"), chapter_no=current_chapter_no + 1, limit=4),
        "book_execution_profile_brief": {
            "positioning_summary": _text(((story_bible.get("book_execution_profile") or {}).get("positioning_summary")), ""),
            "flow_family_priority": compact_data(((story_bible.get("book_execution_profile") or {}).get("flow_family_priority") or {}), max_depth=2, max_items=6, text_limit=60),
            "payoff_priority": compact_data(((story_bible.get("book_execution_profile") or {}).get("payoff_priority") or {}), max_depth=2, max_items=6, text_limit=60),
            "rhythm_bias": compact_data(((story_bible.get("book_execution_profile") or {}).get("rhythm_bias") or {}), max_depth=2, max_items=6, text_limit=60),
        },
        "window_execution_bias_brief": compact_data((((story_bible.get("story_workspace") or {}).get("window_execution_bias") or {})), max_depth=2, max_items=6, text_limit=60),
        "card_system_profile_brief": compact_data((story_bible.get("card_system_profile") or {}), max_depth=2, max_items=6, text_limit=60),
        "contains_generated_text": False,
        "note": "初始化只准备当前卷与近期章节所需文档，不预生成正文。",
    }



def _refresh_entity_registry(story_bible: dict[str, Any]) -> None:
    domains = story_bible.get("story_domains") or {}
    registry = story_bible.setdefault("entity_registry", _empty_entity_registry())
    by_type = registry.setdefault("by_type", {})
    by_type["character"] = list((domains.get("characters") or {}).keys())
    by_type["resource"] = list((domains.get("resources") or {}).keys())
    by_type["relation"] = list((domains.get("relations") or {}).keys())
    by_type["faction"] = list((domains.get("factions") or {}).keys())



def sync_long_term_state(story_bible: dict[str, Any], novel: Novel, chapters: list[Any] | None = None) -> dict[str, Any]:
    story_bible = ensure_story_bible_v2_structure(deepcopy(story_bible or {}))
    runtime = _ensure_serial_runtime(story_bible)
    workspace_state = story_bible.setdefault("story_workspace", {})
    _ensure_fact_ledger(story_bible)
    ensure_hard_fact_guard(story_bible)
    domains = story_bible.get("story_domains") or {}
    _refresh_entity_registry(story_bible)
    state = story_bible.setdefault("long_term_state", _empty_long_term_state(runtime.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)))
    state["protagonist_profile"] = deepcopy(workspace_state.get("protagonist_profile") or {})
    state["character_states"] = deepcopy((domains.get("characters") or {}) or (workspace_state.get("cast_cards") or {}))
    state["resource_states"] = deepcopy(domains.get("resources") or {})
    state["relation_states"] = deepcopy(domains.get("relations") or {})
    state["faction_states"] = deepcopy(domains.get("factions") or {})
    state["foreshadowing_state"] = deepcopy(workspace_state.get("foreshadowing") or [])
    state["history_summaries"] = deepcopy((workspace_state.get("recent_progress") or [])[-20:])
    state["volume_progress"] = deepcopy(story_bible.get("volume_cards") or [])
    state["planner_state_snapshot"] = deepcopy(story_bible.get("planner_state") or {})

    release = state.setdefault("chapter_release_state", {})
    release["delivery_mode"] = runtime.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)
    release.setdefault("chapters", {})

    if chapters is not None:
        ordered = sorted(chapters, key=lambda item: int(getattr(item, "chapter_no", 0) or 0))
        release_map: dict[str, Any] = {}
        published_nos: list[int] = []
        latest_available = 0
        latest_generated = 0
        stock_count = 0
        for item in ordered:
            chapter_no = int(getattr(item, "chapter_no", 0) or 0)
            latest_generated = max(latest_generated, chapter_no)
            latest_available = max(latest_available, chapter_no)
            is_published = bool(getattr(item, "is_published", False))
            if is_published:
                published_nos.append(chapter_no)
            else:
                stock_count += 1
            release_map[str(chapter_no)] = {
                "chapter_no": chapter_no,
                "title": getattr(item, "title", ""),
                "serial_stage": getattr(item, "serial_stage", "stock") or "stock",
                "is_published": is_published,
                "locked_from_edit": bool(getattr(item, "locked_from_edit", False)),
                "published_at": getattr(getattr(item, "published_at", None), "isoformat", lambda: None)(),
                "created_at": getattr(getattr(item, "created_at", None), "isoformat", lambda: None)(),
            }
        published_through = 0
        for no in published_nos:
            if no == published_through + 1:
                published_through = no
            else:
                break
        release.update(
            {
                "published_through": published_through,
                "latest_generated_chapter": latest_generated,
                "latest_available_chapter": latest_available,
                "stock_chapter_count": stock_count,
                "published_chapter_count": len(published_nos),
                "locked_chapter_count": len(published_nos),
                "chapters": release_map,
            }
        )
        story_bible = rebuild_fact_ledger_from_chapters(story_bible, ordered)
        story_bible = rebuild_hard_fact_guard_from_chapters(story_bible, protagonist_name=novel.protagonist_name, chapters=ordered)
    state["fact_ledger"] = deepcopy(story_bible.get("fact_ledger") or _empty_fact_ledger())
    state["hard_fact_guard"] = deepcopy(story_bible.get("hard_fact_guard") or {})
    state["chapter_release_state"] = release
    story_bible["long_term_state"] = state
    story_bible["initialization_packet"] = _build_initialization_packet(story_bible, novel.current_chapter_no)
    return story_bible



def set_delivery_mode(story_bible: dict[str, Any], delivery_mode: str) -> dict[str, Any]:
    ensure_story_bible_v2_structure(story_bible)
    runtime = _ensure_serial_runtime(story_bible)
    runtime["delivery_mode"] = delivery_mode
    story_bible["serial_runtime"] = runtime
    state = story_bible.setdefault("long_term_state", _empty_long_term_state(delivery_mode))
    release = state.setdefault("chapter_release_state", {})
    release["delivery_mode"] = delivery_mode
    story_bible["long_term_state"] = state
    return story_bible
