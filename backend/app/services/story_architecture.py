from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.hard_fact_guard import (
    compact_hard_fact_guard,
    ensure_hard_fact_guard,
)
from app.services.importance_evaluator import evaluate_story_elements_importance
from app.services.story_blueprint_builders import (
    _default_cultivation_system,
    _default_world_bible,
    _endgame_direction,
    _golden_finger,
    _mid_term_direction,
    _one_line_intro,
    _sell_line,
    _target_end,
    build_control_console,
    build_core_cast_state_payload,
    build_entity_registry,
    build_flow_control,
    build_opening_constraints,
    build_planner_state,
    build_power_system,
    build_project_card,
    build_retrospective_state,
    build_story_domains,
    build_template_library,
    build_volume_cards,
)
from app.services.resource_card_support import apply_resource_capability_plan, apply_resource_plan, build_resource_card, ensure_resource_card_structure, normalize_resource_refs
from app.services.story_character_support import (
    _build_chapter_retrospective,
    _character_voice_pack,
    _recent_retrospective_feedback,
    _safe_list,
    _supporting_voice_template,
    _text,
    apply_character_template_defaults,
    pick_character_template,
)
from app.services.story_fact_ledger import (
    _compact_fact_text,
    _now_iso,
    promote_stock_fact_entries,
    record_chapter_fact_entries,
)
from app.services.core_cast_support import (
    bind_character_to_core_slot,
    core_cast_guidance_for_chapter,
    materialize_anchored_core_cast,
    update_core_cast_after_chapter,
)
from app.services.character_schedule_support import update_character_relation_schedule_after_chapter
from app.services.stage_review_support import (
    apply_role_refresh_execution,
    build_chapter_casting_runtime_summary,
    record_stage_casting_resolution,
    stage_character_review_for_window,
    summarize_arc_casting_layout_review,
)
from app.services.story_runtime_support import (
    DEFAULT_SERIAL_DELIVERY_MODE,
    _build_initialization_packet,
    _current_volume_card,
    ensure_story_bible_v2_structure,
    build_serial_rules,
    set_delivery_mode,
    sync_long_term_state,
)
from app.services.story_state import (
    ensure_control_console,
    ensure_planning_layers,
    ensure_serial_runtime,
    ensure_story_state_domains,
    ensure_workflow_state,
    update_story_state_bucket,
)

DEFAULT_CONTINUITY_RULES = [
    "主角每章都要有行动、判断、试探、隐藏或反击，不能整章只被剧情推着走。",
    "每章都要有新变化：得到信息、失去退路、关系变化、暴露风险或世界认知升级。",
    "最近两章若已经用了同类桥段，下一章必须换事件类型，不能连续三章都在同一结构里打转。",
    "如果时间跨度超过一天，开头两段必须写明过渡。",
    "章末要么留下拉力，要么自然收在结果落地与人物选择上，不能停在半句。",
]



def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


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

DEFAULT_STRICT_PIPELINE = [
    "定位",
    "读状态",
    "章纲",
    "场景",
    "正文",
    "检查",
    "摘要",
    "状态更新",
    "发布状态标记",
    "下一章入口",
]



def _chapter_cards_from_arc(arc: dict[str, Any] | None) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if not arc:
        return queue
    for chapter in _safe_list(arc.get("chapters")):
        queue.append(
            {
                "chapter_no": int(chapter.get("chapter_no", 0) or 0),
                "title": _text(chapter.get("title"), ""),
                "goal": _text(chapter.get("goal"), "推进当前主线"),
                "chapter_type": _text(chapter.get("chapter_type"), "progress"),
                "hook_style": _text(chapter.get("hook_style"), ""),
                "opening": _text(chapter.get("opening_beat"), ""),
                "middle": _text(chapter.get("mid_turn"), ""),
                "ending": _text(chapter.get("closing_image") or chapter.get("ending_hook"), ""),
                "hook": _text(chapter.get("ending_hook"), ""),
                "stage_casting_action": _text(chapter.get("stage_casting_action"), ""),
                "stage_casting_target": _text(chapter.get("stage_casting_target"), ""),
                "stage_casting_note": _text(chapter.get("stage_casting_note") or chapter.get("stage_casting_review_note"), ""),
                "stage_casting_review_note": _text(chapter.get("stage_casting_review_note"), ""),
            }
        )
    return queue


def _workflow_state_from_arc(first_arc: dict[str, Any] | None) -> dict[str, Any]:
    planned_until = int((first_arc or {}).get("end_chapter", 0) or 0)
    return {
        "mode": "document_first_strict_pipeline",
        "init_generates_chapters": False,
        "strict_pipeline": list(DEFAULT_STRICT_PIPELINE),
        "strict_pipeline_internal": [
            "project_card",
            "current_volume_card",
            "near_outline",
            "chapter_execution_card",
            "chapter_scene_outline",
            "chapter_draft",
            "quality_check",
            "summary_and_review",
            "publish_mark",
            "next_entry",
        ],
        "bootstrap_documents_ready": True,
        "bootstrap_generated_chapter_cards_until": planned_until,
        "current_pipeline": {
            "target_chapter_no": 1,
            "project_card_ready": True,
            "current_volume_ready": True,
            "near_outline_ready": planned_until > 0,
            "chapter_card_ready": planned_until > 0,
            "draft_ready": False,
            "summary_review_ready": False,
            "last_completed_stage": "bootstrap_documents",
            "last_completed_chapter_no": 0,
        },
    }




def _deep_fill_missing(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        existing = target.get(key)
        if key not in target or existing is None or existing == "" or existing == []:
            target[key] = deepcopy(value)
            continue
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_fill_missing(existing, value)
    return target



def _merge_character_template_library(existing: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_fill_missing(existing or {}, built or {})
    built_templates = (built.get("character_templates") or []) if isinstance(built, dict) else []
    current_templates = (merged.get("character_templates") or []) if isinstance(merged, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in built_templates:
        if isinstance(item, dict):
            template_id = _text(item.get("template_id"))
            if template_id:
                by_id[template_id] = deepcopy(item)
    for item in current_templates:
        if isinstance(item, dict):
            template_id = _text(item.get("template_id"))
            if template_id:
                base = by_id.get(template_id, {})
                merged_item = deepcopy(item)
                if isinstance(base, dict):
                    _deep_fill_missing(merged_item, base)
                by_id[template_id] = merged_item
    merged["character_templates"] = list(by_id.values()) or built_templates
    roadmap = merged.setdefault("roadmap", {})
    built_roadmap = (built.get("roadmap") or {}) if isinstance(built, dict) else {}
    _deep_fill_missing(roadmap, built_roadmap)
    roadmap["current_character_template_count"] = len(merged.get("character_templates") or [])
    roadmap["current_flow_template_count"] = len(merged.get("flow_templates") or [])
    return merged



def _upgrade_opening_constraints(existing: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    payload = _deep_fill_missing(existing or {}, built or {})
    payload["opening_phase_chapter_range"] = [1, 20]
    background_delivery = payload.setdefault("background_delivery", {})
    built_background = (built.get("background_delivery") or {}) if isinstance(built, dict) else {}
    for key, value in built_background.items():
        current = _text(background_delivery.get(key))
        if not current or current.startswith("前15章内") or current.startswith("前15章以内"):
            background_delivery[key] = value
    pace_rules = payload.setdefault("pace_rules", {})
    built_pace = (built.get("pace_rules") or {}) if isinstance(built, dict) else {}
    if not _text(pace_rules.get("first_three_chapters")):
        pace_rules["first_three_chapters"] = built_pace.get("first_three_chapters")
    if not _text(pace_rules.get("first_fifteen_chapters")):
        pace_rules["first_fifteen_chapters"] = built_pace.get("first_fifteen_chapters")
    if not _text(pace_rules.get("first_twenty_chapters")) or _text(pace_rules.get("first_twenty_chapters")).startswith("前15章"):
        pace_rules["first_twenty_chapters"] = built_pace.get("first_twenty_chapters")
    if not payload.get("foundation_reveal_schedule"):
        payload["foundation_reveal_schedule"] = deepcopy((built.get("foundation_reveal_schedule") or []) if isinstance(built, dict) else [])
    if not payload.get("power_system_reveal_plan"):
        payload["power_system_reveal_plan"] = deepcopy((built.get("power_system_reveal_plan") or []) if isinstance(built, dict) else [])
    return payload


def _rebuild_entity_registry(story_bible: dict[str, Any]) -> None:
    domains = story_bible.setdefault("story_domains", {})
    registry = story_bible.setdefault("entity_registry", build_entity_registry())
    by_type = registry.setdefault("by_type", {})
    by_type["character"] = list((domains.get("characters") or {}).keys())
    by_type["resource"] = list((domains.get("resources") or {}).keys())
    by_type["relation"] = list((domains.get("relations") or {}).keys())
    by_type["faction"] = list((domains.get("factions") or {}).keys())



def _upsert_story_domain_character(domains: dict[str, Any], *, protagonist_name: str, name: str, source: dict[str, Any]) -> None:
    if not name:
        return
    characters = domains.setdefault("characters", {})
    current = characters.get(name, {}) if isinstance(characters, dict) else {}
    role_type = _text(source.get("role_type"), "protagonist" if name == protagonist_name else "supporting")
    camp = _text(source.get("camp"), "主角阵营" if name == protagonist_name else "待观察")
    defaults = {
        "name": name,
        "entity_type": "character",
        "role_type": role_type,
        "importance_tier": "核心主角" if name == protagonist_name else _text(source.get("importance_tier"), "重要配角" if role_type in {"supporting", "partner"} else "功能配角"),
        "protagonist_relation_level": "self" if name == protagonist_name else _text(source.get("relationship_to_protagonist") or source.get("attitude_to_protagonist"), "待观察"),
        "narrative_priority": 100 if name == protagonist_name else (80 if role_type in {"supporting", "partner"} else 40),
        "current_strength": _text(source.get("current_strength"), "待补充"),
        "current_goal": _text(source.get("current_desire") or source.get("current_plot_function"), "待补充"),
        "core_desire": _text(source.get("core_desire"), "待补充"),
        "core_fear": _text(source.get("core_fear"), "待补充"),
        "behavior_template_id": _text(source.get("behavior_template_id"), "starter_cautious_observer" if name == protagonist_name else ""),
        "speech_style": _text(source.get("speech_style"), "待补充"),
        "work_style": _text(source.get("work_style") or source.get("behavior_logic"), "待补充"),
        "behavior_mode": _text(source.get("behavior_mode") or source.get("work_style") or source.get("behavior_logic"), "待补充"),
        "core_value": _text(source.get("core_value"), "待补充"),
        "decision_logic": _text(source.get("decision_logic"), "待补充"),
        "pressure_response": _text(source.get("pressure_response"), "待补充"),
        "small_tell": _text(source.get("small_tell"), "待补充"),
        "taboo": _text(source.get("taboo"), "待补充"),
        "relationship_index": deepcopy(source.get("relationship_index") or {}),
        "resource_refs": normalize_resource_refs(source.get("resource_refs") or []),
        "faction_refs": [camp] if camp else [],
        "status": _text(source.get("status"), "active"),
    }
    merged = deepcopy(defaults)
    if isinstance(current, dict):
        merged.update({k: deepcopy(v) for k, v in current.items() if v not in (None, "", [], {})})
    characters[name] = merged



def _normalize_story_domain_resources(domains: dict[str, Any], *, default_owner: str) -> None:
    resources = domains.setdefault("resources", {})
    normalized: dict[str, dict[str, Any]] = {}
    for key, card in list(resources.items()):
        raw_name = _text((card or {}).get("display_name") or (card or {}).get("name") or key)
        normalized_name = _text((card or {}).get("name") or key)
        if not normalized_name and raw_name:
            normalized_name, seeded = build_resource_card(
                raw_name,
                owner=default_owner,
                resource_type="待细化资源",
                status="持有中",
                rarity="普通/待判定",
                exposure_risk="待观察",
                narrative_role="资源状态待后续章节细化。",
                recent_change="结构补齐。",
                source="normalize_story_domains",
            )
            card = seeded
        normalized_card = ensure_resource_card_structure(card if isinstance(card, dict) else {}, fallback_name=raw_name or normalized_name, owner=default_owner)
        target_name = _text(normalized_card.get("name") or normalized_name or raw_name)
        if not target_name:
            continue
        existing = normalized.get(target_name)
        if existing and isinstance(existing, dict):
            existing_quantity = int(existing.get("quantity") or 0)
            new_quantity = int(normalized_card.get("quantity") or 0)
            if new_quantity > existing_quantity:
                existing["quantity"] = new_quantity
                existing["display_name"] = _text(normalized_card.get("display_name"), existing.get("display_name", target_name))
            continue
        normalized[target_name] = normalized_card
    domains["resources"] = normalized


def _bridge_story_domains_from_legacy(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
) -> dict[str, Any]:
    domains = story_bible.setdefault("story_domains", {})
    domains.setdefault("characters", {})
    domains.setdefault("resources", {})
    domains.setdefault("relations", {})
    domains.setdefault("factions", {})

    console = story_bible.get("control_console") or {}
    cards = console.get("character_cards") or {}
    if isinstance(cards, dict):
        for name, card in cards.items():
            if isinstance(card, dict):
                _upsert_story_domain_character(domains, protagonist_name=protagonist_name, name=_text(name), source=card)

    protagonist_state = console.get("protagonist_state") or {}
    if protagonist_name and protagonist_name not in (domains.get("characters") or {}):
        _upsert_story_domain_character(
            domains,
            protagonist_name=protagonist_name,
            name=protagonist_name,
            source={
                "role_type": "protagonist",
                "camp": "主角阵营",
                "current_strength": protagonist_state.get("current_realm"),
                "current_desire": protagonist_state.get("current_goal"),
                "core_desire": protagonist_state.get("current_goal"),
                "speech_style": "简短、留后手、尽量不把真实判断一次说满。",
                "work_style": protagonist_state.get("main_skill") or "先观察和试探，再决定是否行动。",
            },
        )

    resources = domains.setdefault("resources", {})
    for item in _safe_list(protagonist_state.get("current_resources")):
        resource_name, resource_card = build_resource_card(
            item,
            owner=protagonist_name or "主角阵营",
            resource_type="当前资源",
            status="持有中",
            rarity="普通/待判定",
            exposure_risk=_text(protagonist_state.get("exposure_risk"), "待观察"),
            narrative_role="当前生存与推进资源。",
            recent_change="由旧档主角状态迁入。",
            source="legacy_protagonist_state",
        )
        if resource_name:
            resources.setdefault(resource_name, resource_card)

    factions = domains.setdefault("factions", {})
    factions.setdefault(
        "主角阵营",
        {
            "name": "主角阵营",
            "entity_type": "faction",
            "faction_level": "个人",
            "faction_type": "临时自保单元",
            "territory": "当前活动区域",
            "core_goal": "先活下去，再建立稳定立足点。",
            "relation_to_protagonist": "self",
            "resource_control": list(resources.keys()),
            "key_characters": [protagonist_name] if protagonist_name else [],
        },
    )
    for item in _safe_list((story_bible.get("world_bible") or {}).get("factions")):
        if isinstance(item, dict):
            faction_name = _text(item.get("name"))
        else:
            faction_name = _text(item)
        if not faction_name:
            continue
        factions.setdefault(
            faction_name,
            {
                "name": faction_name,
                "entity_type": "faction",
                "faction_level": "地区级/待细化",
                "faction_type": "既有势力",
                "territory": "待后续章节补充",
                "core_goal": "控制资源、维持影响力并压住风险。",
                "relation_to_protagonist": "待观察",
                "resource_control": [],
                "key_characters": [],
            },
        )

    relations = domains.setdefault("relations", {})
    for track in _safe_list(console.get("relation_tracks")):
        if not isinstance(track, dict):
            continue
        subject = _text(track.get("subject"))
        target = _text(track.get("target"))
        if not subject or not target:
            continue
        relation_id = f"{subject}::{target}"
        entry = relations.setdefault(
            relation_id,
            {
                "relation_id": relation_id,
                "left": subject,
                "right": target,
                "relation_type": "待观察",
                "current_level": "待观察",
                "trust": 0,
                "hostility": 0,
                "dependency": 0,
                "recent_trigger": "",
                "next_direction": "待后续发展",
            },
        )
        entry["recent_trigger"] = _text(track.get("change"), entry.get("recent_trigger", ""))
        entry["last_updated_chapter"] = int(track.get("chapter_no", 0) or 0)
        if subject == protagonist_name or target == protagonist_name:
            entry["relation_type"] = "与主角关系"
            entry["current_level"] = _text(track.get("change"), entry.get("current_level", "待观察"))

    _normalize_story_domain_resources(domains, default_owner=protagonist_name or "主角阵营")
    _rebuild_entity_registry(story_bible)
    return story_bible



def _ensure_story_bible_foundation(
    story_bible: dict[str, Any],
    *,
    payload: NovelCreate,
    global_outline: dict[str, Any] | None = None,
    active_arc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    story_bible = ensure_story_bible_v2_structure(story_bible)
    world_bible = story_bible.setdefault("world_bible", _default_world_bible(payload))
    cultivation_system = story_bible.setdefault("cultivation_system", _default_cultivation_system(payload))
    story_bible["story_domains"] = _deep_fill_missing(
        story_bible.get("story_domains") or {},
        build_story_domains(payload, first_arc=active_arc, world_bible=world_bible, cultivation_system=cultivation_system),
    )
    story_bible["power_system"] = _deep_fill_missing(
        story_bible.get("power_system") or {},
        build_power_system(payload, cultivation_system),
    )
    built_opening_constraints = build_opening_constraints(payload, global_outline or {})
    story_bible["opening_constraints"] = _upgrade_opening_constraints(
        story_bible.get("opening_constraints") or {},
        built_opening_constraints,
    )
    built_template_library = build_template_library(payload)
    story_bible["template_library"] = _merge_character_template_library(
        story_bible.get("template_library") or {},
        built_template_library,
    )
    existing_core_cast = story_bible.get("core_cast_state") or {}
    built_core_cast = build_core_cast_state_payload(payload)
    story_bible["core_cast_state"] = _deep_fill_missing(existing_core_cast, built_core_cast)
    if not (story_bible["core_cast_state"].get("slots") and int(story_bible["core_cast_state"].get("target_count") or 0) > 0):
        story_bible["core_cast_state"] = built_core_cast
    materialize_anchored_core_cast(story_bible, protagonist_name=payload.protagonist_name)
    story_bible["planner_state"] = _deep_fill_missing(story_bible.get("planner_state") or {}, build_planner_state())
    story_bible["retrospective_state"] = _deep_fill_missing(
        story_bible.get("retrospective_state") or {},
        build_retrospective_state(),
    )
    story_bible["flow_control"] = _deep_fill_missing(story_bible.get("flow_control") or {}, build_flow_control())
    story_bible["entity_registry"] = _deep_fill_missing(story_bible.get("entity_registry") or {}, build_entity_registry())
    story_bible = _bridge_story_domains_from_legacy(story_bible, protagonist_name=payload.protagonist_name)
    importance_state = story_bible.get("importance_state") or {}
    entity_index = (importance_state.get("entity_index") or {}) if isinstance(importance_state, dict) else {}
    if not any((entity_index.get(key) or {}) for key in ["character", "resource", "relation", "faction"]):
        evaluate_story_elements_importance(
            story_bible=story_bible,
            protagonist_name=payload.protagonist_name,
            scope="foundation",
            chapter_no=0,
            plan=None,
            recent_summaries=None,
            touched_entities=None,
            allow_ai=False,
        )
    return story_bible


def refresh_planning_views(story_bible: dict[str, Any], current_chapter_no: int = 0) -> dict[str, Any]:
    story_bible = ensure_story_state_domains(story_bible, workflow_factory=_workflow_state_from_arc)
    console = ensure_control_console(story_bible)
    workflow_state = ensure_workflow_state(story_bible, workflow_factory=_workflow_state_from_arc)

    active_arc = story_bible.get("active_arc") or {}
    pending_arc = story_bible.get("pending_arc") or {}
    queue = [item for item in _chapter_cards_from_arc(active_arc) if int(item.get("chapter_no", 0) or 0) > current_chapter_no]
    if len(queue) < 7 and pending_arc:
        remaining = 7 - len(queue)
        queue.extend(_chapter_cards_from_arc(pending_arc)[:remaining])

    console["chapter_card_queue"] = queue[:7]
    outline_state = story_bible.get("outline_state") or {}
    current_stage_review = stage_character_review_for_window(story_bible, current_chapter_no=current_chapter_no)
    retrospective_state = story_bible.get("retrospective_state") or {}
    review_interval = max(int(retrospective_state.get("scheduled_review_interval", 5) or 5), 1)
    stage_review_due = bool(current_chapter_no > 0 and current_chapter_no % review_interval == 0 and int(retrospective_state.get("last_stage_review_chapter", 0) or 0) < current_chapter_no)

    active_arc_layout_review = summarize_arc_casting_layout_review(active_arc)
    pending_arc_layout_review = summarize_arc_casting_layout_review(pending_arc) if pending_arc else {}

    console["planning_status"] = {
        "documents_only_bootstrap": True,
        "auto_planning_enabled": True,
        "planned_until": int(outline_state.get("planned_until", 0) or 0),
        "next_arc_no": int(outline_state.get("next_arc_no", 0) or 0),
        "stage_review_due": stage_review_due,
        "stage_review_interval": review_interval,
        "current_stage_review": current_stage_review or {},
        "active_arc": {
            "arc_no": int(active_arc.get("arc_no", 0) or 0),
            "start_chapter": int(active_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(active_arc.get("end_chapter", 0) or 0),
            "focus": _text(active_arc.get("focus"), ""),
            "bridge_note": _text(active_arc.get("bridge_note"), ""),
            "casting_layout_review_summary": active_arc_layout_review,
        },
        "pending_arc": {
            "arc_no": int(pending_arc.get("arc_no", 0) or 0),
            "start_chapter": int(pending_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(pending_arc.get("end_chapter", 0) or 0),
            "focus": _text(pending_arc.get("focus"), ""),
            "bridge_note": _text(pending_arc.get("bridge_note"), ""),
            "casting_layout_review_summary": pending_arc_layout_review,
        } if pending_arc else None,
        "active_arc_casting_layout_review": active_arc_layout_review,
        "pending_arc_casting_layout_review": pending_arc_layout_review,
        "ready_chapter_cards": [int(item.get("chapter_no", 0) or 0) for item in queue[:7]],
        "core_cast_brief": core_cast_guidance_for_chapter(story_bible, chapter_no=current_chapter_no + 1),
    }

    if queue:
        console["near_7_chapter_outline"] = [
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "title": _text(item.get("title"), f"第{item.get('chapter_no', '')}章"),
                "goal": _text(item.get("goal"), "推进当前主线"),
                "hook": _text(item.get("hook"), "新问题浮出"),
            }
            for item in queue[:7]
        ]

    workflow_state["bootstrap_generated_chapter_cards_until"] = max(
        int(workflow_state.get("bootstrap_generated_chapter_cards_until", 0) or 0),
        int((active_arc or {}).get("end_chapter", 0) or 0),
        int((pending_arc or {}).get("end_chapter", 0) or 0),
    )
    current_pipeline = workflow_state.setdefault("current_pipeline", {})
    current_pipeline.setdefault("target_chapter_no", current_chapter_no + 1)
    current_pipeline["project_card_ready"] = bool(story_bible.get("project_card"))
    current_pipeline["current_volume_ready"] = bool(story_bible.get("volume_cards"))
    current_pipeline["near_outline_ready"] = bool(queue)
    current_pipeline["chapter_card_ready"] = bool(queue and int(queue[0].get("chapter_no", 0) or 0) == current_chapter_no + 1)
    runtime = ensure_serial_runtime(story_bible)
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers["serial_rules_ready"] = bool(story_bible.get("serial_rules"))
    planning_layers["long_term_state_ready"] = True
    planning_layers["initialization_packet_ready"] = True
    story_bible["workflow_state"] = workflow_state
    story_bible["control_console"] = console
    story_bible["serial_runtime"] = runtime
    story_bible["initialization_packet"] = _build_initialization_packet(story_bible, current_chapter_no)
    update_story_state_bucket(
        story_bible,
        planning_window={
            "current_chapter_no": current_chapter_no,
            "planned_until": int(outline_state.get("planned_until", 0) or 0),
            "queue_size": len(queue[:7]),
            "active_arc_no": int(active_arc.get("arc_no", 0) or 0),
            "pending_arc_no": int((pending_arc or {}).get("arc_no", 0) or 0) if pending_arc else None,
        },
    )
    return story_bible


def set_pipeline_target(
    story_bible: dict[str, Any],
    *,
    next_chapter_no: int,
    execution_brief: dict[str, Any] | None = None,
    stage: str = "chapter_execution_card",
    last_completed_chapter_no: int | None = None,
) -> dict[str, Any]:
    story_bible = refresh_planning_views(story_bible, max(next_chapter_no - 1, 0))
    workflow_state = ensure_workflow_state(story_bible, workflow_factory=_workflow_state_from_arc)
    pipeline = workflow_state.setdefault("current_pipeline", {})
    pipeline.update(
        {
            "target_chapter_no": next_chapter_no,
            "project_card_ready": bool(story_bible.get("project_card")),
            "current_volume_ready": bool(story_bible.get("volume_cards")),
            "near_outline_ready": bool((story_bible.get("control_console") or {}).get("chapter_card_queue")),
            "chapter_card_ready": execution_brief is not None,
            "draft_ready": False,
            "summary_review_ready": False,
            "last_completed_stage": stage,
        }
    )
    if last_completed_chapter_no is not None:
        pipeline["last_completed_chapter_no"] = last_completed_chapter_no
    if execution_brief is not None:
        console = ensure_control_console(story_bible)
        console["current_execution_packet"] = execution_brief
        console["daily_workbench"] = execution_brief.get("daily_workbench", {})
    story_bible["workflow_state"] = workflow_state
    return story_bible


def compose_story_bible(
    payload: NovelCreate,
    title: str,
    base_story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    first_arc: dict[str, Any],
    story_engine_diagnosis: dict[str, Any] | None = None,
    story_strategy_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    story_bible = ensure_story_state_domains(deepcopy(base_story_bible), workflow_factory=_workflow_state_from_arc, active_arc=first_arc)
    diagnosis = story_engine_diagnosis or story_bible.get("story_engine_diagnosis") or {}
    strategy = story_strategy_card or story_bible.get("story_strategy_card") or {}
    story_bible["story_engine_diagnosis"] = deepcopy(diagnosis)
    story_bible["story_strategy_card"] = deepcopy(strategy)
    story_bible["project_card"] = build_project_card(payload, title, global_outline, diagnosis, strategy)
    story_bible["world_bible"] = _default_world_bible(payload)
    story_bible["cultivation_system"] = _default_cultivation_system(payload)
    story_bible["volume_cards"] = build_volume_cards(global_outline, first_arc)
    story_bible["control_console"] = build_control_console(payload, first_arc)
    story_bible = _ensure_story_bible_foundation(
        story_bible,
        payload=payload,
        global_outline=global_outline,
        active_arc=first_arc,
    )
    story_bible["serial_rules"] = build_serial_rules()
    story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    story_bible["daily_workflow"] = {
        "steps": [
            "回看昨天结尾",
            "确定今天这章的功能",
            "写三行章纲",
            "写正文时盯住主角行动、事件推进、新变化和章末拉力",
            "收工时留下明天提示",
        ],
        "quality_floor": [
            "主角有没有行动",
            "事件有没有推进",
            "有没有新变化",
            "节奏有没有拖",
            "结尾有没有拉力",
        ],
    }
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers.clear()
    planning_layers.update({
        "global_outline_ready": bool(global_outline),
        "volume_cards_ready": True,
        "first_near_outline_ready": bool(first_arc),
        "first_chapter_cards_ready": bool((first_arc or {}).get("chapters")),
        "serial_rules_ready": True,
        "long_term_state_ready": True,
        "initialization_packet_ready": True,
    })
    story_bible["planning_layers"] = planning_layers
    story_bible["workflow_state"] = _workflow_state_from_arc(first_arc)
    story_bible = set_delivery_mode(story_bible, DEFAULT_SERIAL_DELIVERY_MODE)
    story_bible = refresh_planning_views(story_bible, 0)
    stub_novel = Novel(
        title=title,
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences or {},
        current_chapter_no=0,
    )
    return sync_long_term_state(story_bible, stub_novel, chapters=[])


def update_volume_card_statuses(story_bible: dict[str, Any], current_chapter_no: int) -> None:
    for card in _safe_list(story_bible.get("volume_cards")):
        start = int(card.get("start_chapter", 0) or 0)
        end = int(card.get("end_chapter", 0) or 0)
        if current_chapter_no >= end > 0:
            card["status"] = "completed"
        elif start <= current_chapter_no + 1 <= max(end, start):
            card["status"] = "current"
        else:
            card["status"] = "planned"


def ensure_story_architecture(story_bible: dict[str, Any], novel: Novel) -> dict[str, Any]:
    story_bible = ensure_story_state_domains(deepcopy(story_bible or {}), workflow_factory=_workflow_state_from_arc, active_arc=(story_bible or {}).get("active_arc") if isinstance(story_bible, dict) else None)
    payload = NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )
    global_outline = story_bible.get("global_outline") or {}
    active_arc = story_bible.get("active_arc") or {}
    diagnosis = story_bible.get("story_engine_diagnosis") or {}
    strategy = story_bible.get("story_strategy_card") or {}
    story_bible.setdefault("story_engine_diagnosis", deepcopy(diagnosis))
    story_bible.setdefault("story_strategy_card", deepcopy(strategy))
    if "project_card" not in story_bible:
        story_bible["project_card"] = build_project_card(payload, novel.title, global_outline, diagnosis, strategy)
    if "world_bible" not in story_bible:
        story_bible["world_bible"] = _default_world_bible(payload)
    if "cultivation_system" not in story_bible:
        story_bible["cultivation_system"] = _default_cultivation_system(payload)
    if "volume_cards" not in story_bible:
        story_bible["volume_cards"] = build_volume_cards(global_outline, active_arc)
    if "control_console" not in story_bible:
        story_bible["control_console"] = build_control_console(payload, active_arc)
    if "serial_rules" not in story_bible:
        story_bible["serial_rules"] = build_serial_rules()
    if "continuity_rules" not in story_bible:
        story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    if "daily_workflow" not in story_bible:
        story_bible["daily_workflow"] = {
            "steps": ["回看昨天结尾", "确定今天这章的功能", "写三行章纲", "写正文", "留明天提示"],
            "quality_floor": ["主角有没有行动", "事件有没有推进", "有没有新变化", "节奏有没有拖", "结尾有没有拉力"],
        }
    story_bible = _ensure_story_bible_foundation(
        story_bible,
        payload=payload,
        global_outline=global_outline,
        active_arc=active_arc,
    )
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers.setdefault("global_outline_ready", bool(global_outline))
    planning_layers.setdefault("volume_cards_ready", bool(story_bible.get("volume_cards")))
    planning_layers.setdefault("first_near_outline_ready", bool(active_arc))
    planning_layers.setdefault("first_chapter_cards_ready", bool((active_arc or {}).get("chapters")))
    planning_layers.setdefault("serial_rules_ready", True)
    planning_layers.setdefault("long_term_state_ready", True)
    planning_layers.setdefault("initialization_packet_ready", True)
    story_bible["planning_layers"] = planning_layers
    if "workflow_state" not in story_bible:
        story_bible["workflow_state"] = _workflow_state_from_arc(active_arc)
    story_bible = set_delivery_mode(story_bible, (story_bible.get("serial_runtime") or {}).get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE))
    ensure_hard_fact_guard(story_bible)
    update_volume_card_statuses(story_bible, novel.current_chapter_no)
    story_bible = refresh_planning_views(story_bible, novel.current_chapter_no)
    return sync_long_term_state(story_bible, novel)


def build_execution_brief(
    *,
    story_bible: dict[str, Any],
    next_chapter_no: int,
    plan: dict[str, Any],
    last_chapter_tail: str,
) -> dict[str, Any]:
    console = ensure_control_console(story_bible)
    current_volume = _current_volume_card(story_bible, next_chapter_no)
    today_function = _text(plan.get("goal"), "推进剧情")
    if plan.get("supporting_character_focus"):
        today_function += f" + 让{_text(plan.get('supporting_character_focus'))}在场面里立住"
    change_line = _text(plan.get("discovery") or plan.get("conflict"), "局势会在本章发生可感知的新变化。")
    focus_name = _text(plan.get("supporting_character_focus"))
    character_focus_card = {}
    if focus_name:
        character_focus_card = ((console.get("character_cards") or {}).get(focus_name) or {}) if isinstance(console.get("character_cards"), dict) else {}
    character_voice_pack = _character_voice_pack(character_focus_card) if character_focus_card else {}
    retrospective_feedback = _recent_retrospective_feedback(console)
    planning_packet = (plan.get("planning_packet") or {}) if isinstance(plan, dict) else {}
    rolling_continuity = (planning_packet.get("recent_continuity_plan") or {}) if isinstance(planning_packet, dict) else {}
    chapter_stage_casting_hint = (planning_packet.get("chapter_stage_casting_hint") or {}) if isinstance(planning_packet, dict) else {}
    chapter_stage_casting_runtime = build_chapter_casting_runtime_summary(
        story_bible,
        chapter_no=next_chapter_no,
        plan=plan,
        stage_hint=chapter_stage_casting_hint,
    )
    tomorrow_hints = [
        f"明天从第{next_chapter_no}章结尾的后续局势接上。",
        f"明天最大冲突：{_text(plan.get('conflict') or plan.get('goal'), '继续推进当前矛盾。')}",
        f"明天章末可往‘{_text(plan.get('ending_hook'), '新问题浮出')}’方向留钩子。",
    ]
    long_term_state = story_bible.get("long_term_state") or {}
    release_state = (long_term_state.get("chapter_release_state") or {})
    return {
        "project_card": story_bible.get("project_card", {}),
        "current_volume_card": current_volume,
        "chapter_execution_card": {
            "chapter_function": today_function,
            "event_type": _text(plan.get("event_type"), "试探类"),
            "progress_kind": _text(plan.get("progress_kind"), "信息推进"),
            "agency_mode": _text(plan.get("agency_mode_label") or plan.get("agency_mode"), "通用主动推进"),
            "proactive_move": _text(plan.get("proactive_move"), "主角必须主动做出判断并推动局势前进。"),
            "payoff_or_pressure": _text(plan.get("payoff_or_pressure"), "本章必须给出明确回报或压力升级。"),
            "hook_kind": _text(plan.get("hook_kind"), "更大谜团"),
            "opening": _text(plan.get("opening_beat"), "顺着上一章结尾自然接入场景。"),
            "middle": _text(plan.get("mid_turn"), "中段加入受阻、试探或代价。"),
            "ending": _text(plan.get("closing_image"), "结尾落在具体画面、结果或新问题上。"),
            "agency_summary": _text(plan.get("agency_style_summary")),
            "chapter_change": change_line,
            "chapter_hook": _text(plan.get("ending_hook"), "留下继续追更的拉力。"),
            "stage_casting_hint": _compact_value(chapter_stage_casting_hint, text_limit=72),
            "stage_casting_runtime": _compact_value(chapter_stage_casting_runtime, text_limit=72),
        },
        "scene_outline": [
            {"scene_no": 1, "purpose": _text(plan.get("opening_beat"), "承接上一章结尾并定位本章场景")},
            {"scene_no": 2, "purpose": _text(plan.get("mid_turn"), "中段制造受阻、试探或发现")},
            {"scene_no": 3, "purpose": _text(plan.get("closing_image") or plan.get("ending_hook"), "结尾落到结果、钩子或下一章入口")},
        ],
        "serial_context": {
            "delivery_mode": release_state.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE),
            "published_through": int(release_state.get("published_through", 0) or 0),
            "latest_available_chapter": int(release_state.get("latest_available_chapter", 0) or 0),
            "fact_priority": (story_bible.get("serial_rules") or {}).get("fact_priority", []),
        },
        "character_focus_card": character_focus_card,
        "character_voice_pack": character_voice_pack,
        "chapter_retrospective_feedback": retrospective_feedback,
        "daily_workbench": {
            "yesterday_ending": _text(last_chapter_tail),
            "today_function": today_function,
            "three_line_outline": {
                "opening": _text(plan.get("opening_beat")),
                "middle": _text(plan.get("mid_turn")),
                "ending": _text(plan.get("closing_image") or plan.get("ending_hook")),
            },
            "rolling_continuity": {
                "must_continue": _safe_list((((rolling_continuity.get("current_chapter_bridge") or {}).get("must_continue")) or []))[:3],
                "carry_in": _safe_list((((rolling_continuity.get("carry_in") or {}).get("carry_over_points")) or []))[:3],
                "preserve_for_next": _safe_list((((rolling_continuity.get("lookahead_handoff") or {}).get("preserve_for_next")) or []))[:3],
            },
            "chapter_stage_casting_hint": _compact_value(chapter_stage_casting_hint, text_limit=72),
            "chapter_stage_casting_runtime": _compact_value(chapter_stage_casting_runtime, text_limit=72),
            "chapter_stage_casting_runtime_note": _text(chapter_stage_casting_runtime.get("runtime_note")),
            "tomorrow_hints": tomorrow_hints,
        },
        "quality_floor": [
            "主角必须在本章主动做出至少一次观察、判断、试探、设局、争资源、验证、表态或反击。",
            "本章不能重复最近两章的主事件类型。",
            "本章必须出现事件推进，而不是只补设定。",
            "本章必须产生新变化：信息、关系、风险、资源、退路至少改变其一。",
            "节奏不能拖成长段说明书。",
            "章末必须有拉力或结果落地。",
        ],
        "continuity_rules": _safe_list(story_bible.get("continuity_rules")) or list(DEFAULT_CONTINUITY_RULES),
    }


def _merge_character_card(console: dict[str, Any], name: str, defaults: dict[str, Any]) -> None:
    cards = console.setdefault("character_cards", {})
    existing = cards.get(name, {}) if isinstance(cards, dict) else {}
    merged = dict(defaults)
    merged.update({k: v for k, v in existing.items() if v not in (None, "", [], {})})
    cards[name] = merged


def sync_character_registry(
    db: Session,
    novel: Novel,
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    summary: Any,
) -> None:
    console = story_bible.get("control_console") or {}
    protagonist_state = console.get("protagonist_state") or {}
    cards = console.get("character_cards") or {}

    def upsert(name: str, role_type: str, core_profile: dict[str, Any], dynamic_state: dict[str, Any]) -> None:
        if not name:
            return
        row = (
            db.query(Character)
            .filter(Character.novel_id == novel.id, Character.name == name)
            .first()
        )
        if not row:
            row = Character(novel_id=novel.id, name=name, role_type=role_type)
        row.core_profile = core_profile
        row.dynamic_state = dynamic_state
        db.add(row)

    protagonist_name = novel.protagonist_name
    protagonist_card = cards.get(protagonist_name, {}) if isinstance(cards, dict) else {}
    upsert(
        protagonist_name,
        "protagonist",
        protagonist_card or {"name": protagonist_name, "role_type": "protagonist"},
        protagonist_state,
    )

    focus_name = _text(plan.get("supporting_character_focus"))
    if focus_name:
        note = _text(plan.get("supporting_character_note"), "本卷的重要配角，需要持续保持辨识度。")
        current = cards.get(focus_name, {}) if isinstance(cards, dict) else {}
        palette = _supporting_voice_template(focus_name, note)
        template = pick_character_template(
            story_bible,
            name=focus_name,
            note=note,
            role_hint="supporting",
            relation_hint=_text((current or {}).get("attitude_to_protagonist"), "待观察"),
            fallback_id="starter_hard_shell_soft_core",
        )
        profile = apply_character_template_defaults(
            current
            or {
                "name": focus_name,
                "role_type": "supporting",
                "current_plot_function": "本阶段重要配角",
                "current_desire": _text(palette.get("private_goal"), "先保住自己的利益，再决定是否靠近主角。"),
                "attitude_to_protagonist": "待观察",
                "recent_impact": "刚在当前剧情中留下存在感。",
                "do_not_break": ["不能只会盘问和警告", "要保留角色自己的利益与语气"],
                "behavior_logic": _text(palette.get("work_style"), note),
            },
            template,
        )
        if note and len(note) >= 8:
            profile["speech_style"] = _text(note, _text(profile.get("speech_style")))
        dynamic_state = {
            "last_seen_chapter": int(plan.get("chapter_no", 0) or 0),
            "latest_note": note,
        }
        upsert(focus_name, "supporting", profile, dynamic_state)

    character_updates = getattr(summary, "character_updates", {}) or {}
    if isinstance(character_updates, dict):
        for name, state in character_updates.items():
            char_name = _text(name)
            if not char_name:
                continue
            current = cards.get(char_name, {}) if isinstance(cards, dict) else {}
            role_type = _text(current.get("role_type"), "supporting")
            profile = current or {"name": char_name, "role_type": role_type}
            dynamic_state = state if isinstance(state, dict) else {"latest_update": state}
            upsert(char_name, role_type, profile, dynamic_state)


def update_story_architecture_after_chapter(
    *,
    story_bible: dict[str, Any],
    novel: Novel,
    chapter_no: int,
    chapter_title: str,
    plan: dict[str, Any],
    summary: Any,
    last_chapter_tail: str,
) -> dict[str, Any]:
    story_bible = ensure_story_architecture(story_bible, novel)
    console = ensure_control_console(story_bible)
    protagonist_state = console.setdefault("protagonist_state", {})
    protagonist_state["current_goal"] = _text(plan.get("ending_hook") or plan.get("goal"), protagonist_state.get("current_goal", ""))
    protagonist_state["current_status"] = _text(getattr(summary, "event_summary", None), protagonist_state.get("current_status", ""))

    volume_card = _current_volume_card(story_bible, chapter_no)
    update_volume_card_statuses(story_bible, chapter_no)

    daily = build_execution_brief(
        story_bible=story_bible,
        next_chapter_no=chapter_no + 1,
        plan=plan,
        last_chapter_tail=last_chapter_tail,
    )
    console["daily_workbench"] = daily["daily_workbench"]

    progress = console.setdefault("recent_progress", [])
    progress.append(
        {
            "chapter_no": chapter_no,
            "title": chapter_title,
            "event_summary": _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), "推进当前主线")),
            "new_change": _text(plan.get("discovery") or plan.get("conflict"), "局势发生了新的偏移。"),
            "chapter_hook": _text(plan.get("ending_hook"), "新的问题浮出。"),
        }
    )
    console["recent_progress"] = progress[-12:]

    retrospective = _build_chapter_retrospective(
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        plan=plan,
        summary=summary,
        console=console,
    )
    retrospectives = console.setdefault("chapter_retrospectives", [])
    retrospectives.append(retrospective)
    console["chapter_retrospectives"] = retrospectives[-12:]

    near_progress = console.setdefault("near_30_progress", {})
    near_progress["current_position"] = f"已写到第{chapter_no}章"
    near_progress["current_volume_gap"] = _text(volume_card.get("main_conflict"), near_progress.get("current_volume_gap", ""))
    near_progress["next_big_payoff"] = _text(volume_card.get("cool_point"), near_progress.get("next_big_payoff", ""))
    near_progress["next_twist"] = _text(plan.get("ending_hook"), near_progress.get("next_twist", ""))

    timeline = console.setdefault("timeline", [])
    timeline.append(
        {
            "chapter_no": chapter_no,
            "event": _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), "推进当前主线")),
        }
    )
    console["timeline"] = timeline[-30:]

    foreshadowing = console.setdefault("foreshadowing", [])
    existing_open = {str(item.get("surface_info", "")): item for item in foreshadowing if isinstance(item, dict)}
    for hook in getattr(summary, "open_hooks", []) or []:
        hook_text = _text(hook)
        if not hook_text:
            continue
        existing_open.setdefault(
            hook_text,
            {
                "name": hook_text[:24],
                "introduced_in_chapter": chapter_no,
                "surface_info": hook_text,
                "real_info": "待后续揭示",
                "known_by": [novel.protagonist_name],
                "expected_resolution": "待后续回收",
                "status": "open",
            },
        )
    foreshadowing = list(existing_open.values())
    closed = {_text(item) for item in (getattr(summary, "closed_hooks", []) or []) if _text(item)}
    for item in foreshadowing:
        if _text(item.get("surface_info")) in closed:
            item["status"] = "closed"
            item["expected_resolution"] = f"已在第{chapter_no}章阶段性回收"
    console["foreshadowing"] = foreshadowing[-30:]

    protagonist_name = novel.protagonist_name
    _merge_character_card(
        console,
        protagonist_name,
        {
            "name": protagonist_name,
            "role_type": "protagonist",
            "current_strength": _text(protagonist_state.get("current_realm"), "低阶求生阶段"),
            "current_plot_function": "推动视角、承接风险、做出选择。",
            "behavior_logic": "先观察和试探，再决定是否行动。",
            "relationship_to_protagonist": "self",
        },
    )
    focus_name = _text(plan.get("supporting_character_focus"))
    if focus_name:
        note = _text(plan.get("supporting_character_note"))
        palette = _supporting_voice_template(focus_name, note)
        template = pick_character_template(
            story_bible,
            name=focus_name,
            note=note,
            role_hint="supporting",
            relation_hint="试探中",
            fallback_id="starter_hard_shell_soft_core",
        )
        _merge_character_card(
            console,
            focus_name,
            apply_character_template_defaults(
                {
                    "name": focus_name,
                    "role_type": "supporting",
                    "temperament": _text(note, "本阶段的重要配角。"),
                    "speech_style": _text(note, _text(palette.get("speech_style"), "说话方式需要有辨识度。")),
                    "work_style": _text(palette.get("work_style"), _text(plan.get("conflict") or plan.get("goal"), "做事有自己的算盘与顾虑。")),
                    "current_desire": _text(plan.get("goal"), _text(palette.get("private_goal"), "在当前局势中争取自己的利益。")),
                    "attitude_to_protagonist": "试探中",
                    "recent_impact": _text(plan.get("ending_hook") or plan.get("conflict"), "给主角带来新的局势变化。"),
                    "current_plot_function": "作为本章关键配角参与推进。",
                    "relationship_to_protagonist": "待剧情更新",
                    "possible_change": "关系可能由试探转向合作或对立。",
                    "do_not_break": ["不能所有配角都说同一种话", "不能只剩功能没有人格"],
                },
                template,
            ),
        )
        relations = console.setdefault("relation_tracks", [])
        relations.append(
            {
                "subject": protagonist_name,
                "target": focus_name,
                "chapter_no": chapter_no,
                "change": _text(plan.get("conflict") or plan.get("goal"), "关系发生新的试探或位移。"),
            }
        )
        console["relation_tracks"] = relations[-20:]

    if focus_name:
        bind_character_to_core_slot(
            story_bible,
            character_name=focus_name,
            chapter_no=chapter_no,
            note=_text(plan.get("supporting_character_note") or plan.get("goal")),
            protagonist_name=protagonist_name,
        )
    onstage_character_names = [
        protagonist_name,
        focus_name,
        *([str(key).strip() for key in ((getattr(summary, "character_updates", None) or {}).keys())] if isinstance(getattr(summary, "character_updates", None), dict) else []),
    ]
    update_core_cast_after_chapter(
        story_bible,
        chapter_no=chapter_no,
        onstage_characters=onstage_character_names,
    )
    apply_role_refresh_execution(
        story_bible,
        chapter_no=chapter_no,
        plan=plan,
    )
    record_stage_casting_resolution(
        story_bible,
        chapter_no=chapter_no,
        plan=plan,
    )
    update_character_relation_schedule_after_chapter(
        story_bible,
        chapter_no=chapter_no,
        onstage_characters=onstage_character_names,
        focus_name=focus_name,
        plan=plan,
    )

    current_volume_end = int(volume_card.get("end_chapter", 0) or 0)
    if current_volume_end and chapter_no >= current_volume_end:
        reviews = console.setdefault("volume_reviews", [])
        reviews.append(
            {
                "volume_no": int(volume_card.get("volume_no", 0) or 0),
                "volume_name": _text(volume_card.get("volume_name"), f"第{volume_card.get('volume_no', '')}卷"),
                "mainline_advanced": True,
                "protagonist_growth": _text(protagonist_state.get("current_status"), "主角完成了一次阶段性成长与位置变化。"),
                "best_cool_point": _text(volume_card.get("cool_point"), "阶段性破局。"),
                "drag_point": "留待人工复盘微调。",
                "recovered_foreshadowing": [_text(x) for x in (getattr(summary, "closed_hooks", []) or []) if _text(x)],
                "unresolved_foreshadowing": [_text(item.get("surface_info")) for item in console.get("foreshadowing", []) if item.get("status") != "closed"][:6],
                "next_volume_newness": _text(volume_card.get("next_hook"), "下一卷会抬高地图、规则与代价。"),
            }
        )
        console["volume_reviews"] = reviews[-8:]

    next_outline = console.setdefault("near_7_chapter_outline", [])
    if next_outline and next_outline[0].get("chapter_no") == chapter_no:
        next_outline = next_outline[1:]
    console["near_7_chapter_outline"] = next_outline
    delivery_mode = ((story_bible.get("serial_runtime") or {}).get("delivery_mode") or DEFAULT_SERIAL_DELIVERY_MODE)
    serial_stage = "published" if delivery_mode == "live_publish" else "stock"
    story_bible = record_chapter_fact_entries(
        story_bible,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        summary=summary,
        plan=plan,
        serial_stage=serial_stage,
        fallback_content=_text(getattr(summary, "event_summary", None), _text(plan.get("goal"), chapter_title)),
    )
    payload = NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )
    story_bible["planner_state"].setdefault("chapter_element_selection", {})[str(chapter_no)] = {
        "focus_character": focus_name,
        "event_type": _text(plan.get("event_type"), ""),
        "progress_kind": _text(plan.get("progress_kind"), ""),
    }
    story_bible["planner_state"]["last_planned_chapter"] = chapter_no + 1
    story_bible["retrospective_state"]["last_review_chapter"] = chapter_no
    story_bible["retrospective_state"]["last_review_notes"] = [
        {
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "core_problem": retrospective.get("core_problem"),
            "next_correction": retrospective.get("next_chapter_correction"),
        }
    ]
    planning_packet = (plan.get("planning_packet") or {}) if isinstance(plan, dict) else {}
    resource_plan = (planning_packet.get("resource_plan") or {}) if isinstance(planning_packet, dict) else {}
    resource_capability_plan = (planning_packet.get("resource_capability_plan") or {}) if isinstance(planning_packet, dict) else {}
    resources_domain = (((story_bible.get("story_domains") or {}).get("resources")) or {})
    apply_resource_plan(resources_domain, resource_plan, chapter_no=chapter_no)
    apply_resource_capability_plan(resources_domain, resource_capability_plan, chapter_no=chapter_no)
    planner_state = story_bible.setdefault("planner_state", build_planner_state())
    if resource_plan:
        planner_state.setdefault("resource_plan_cache", {})[str(chapter_no)] = resource_plan
        history = planner_state.setdefault("resource_plan_history", [])
        history.append({"chapter_no": chapter_no, "resource_names": list(resource_plan.keys())[:6]})
        planner_state["resource_plan_history"] = history[-12:]
    if resource_capability_plan:
        planner_state.setdefault("resource_capability_plan_cache", {})[str(chapter_no)] = resource_capability_plan
        capability_history = planner_state.setdefault("resource_capability_history", [])
        capability_history.append({
            "chapter_no": chapter_no,
            "resource_names": [name for name in list(resource_capability_plan.keys())[:6] if name != "__meta__"],
            "used_ai": bool(((resource_capability_plan.get("__meta__") or {}).get("used_ai"))) if isinstance(resource_capability_plan, dict) else False,
        })
        planner_state["resource_capability_history"] = capability_history[-12:]
    continuity_plan = (planning_packet.get("recent_continuity_plan") or {}) if isinstance(planning_packet, dict) else {}
    if continuity_plan:
        planner_state.setdefault("continuity_packet_cache", {})[str(chapter_no)] = continuity_plan
        continuity_history = planner_state.setdefault("rolling_continuity_history", [])
        continuity_history.append(
            {
                "chapter_no": chapter_no,
                "must_continue": _safe_list((((continuity_plan.get("current_chapter_bridge") or {}).get("must_continue")) or []))[:3],
                "preserve_for_next": _safe_list((((continuity_plan.get("lookahead_handoff") or {}).get("preserve_for_next")) or []))[:3],
            }
        )
        planner_state["rolling_continuity_history"] = continuity_history[-12:]
        planner_state["last_continuity_review_chapter"] = chapter_no
    flow_control = story_bible.setdefault("flow_control", build_flow_control())
    recent_event_types = flow_control.setdefault("recent_event_types", [])
    event_type = _text(plan.get("event_type"))
    if event_type:
        recent_event_types.append(event_type)
        flow_control["recent_event_types"] = recent_event_types[-int(flow_control.get("anti_repeat_window", 5) or 5):]
    flow_id = _text(plan.get("flow_template_id"))
    if flow_id:
        recent_flow_ids = flow_control.setdefault("recent_flow_ids", [])
        recent_flow_ids.append(flow_id)
        flow_control["recent_flow_ids"] = recent_flow_ids[-int(flow_control.get("anti_repeat_window", 5) or 5):]
    summary_character_updates = getattr(summary, "character_updates", None) or {}
    touched_entities = {
        "character": [
            name
            for name in [
                protagonist_name,
                focus_name,
                *([str(key).strip() for key in summary_character_updates.keys()] if isinstance(summary_character_updates, dict) else []),
            ]
            if name
        ],
        "resource": [name for name in _safe_list(list((resource_plan or {}).keys()) + list((resource_capability_plan or {}).keys())) if name and name != "__meta__"],
        "relation": [f"{protagonist_name}::{focus_name}"] if focus_name else [],
        "faction": list((((planning_packet.get("selected_elements") or {}).get("factions")) or [])),
    }
    evaluate_story_elements_importance(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        scope="post_chapter",
        chapter_no=chapter_no,
        plan=plan,
        recent_summaries=[
            {
                "chapter_no": chapter_no,
                "event_summary": _text(getattr(summary, "event_summary", None), chapter_title),
                "open_hooks": list(getattr(summary, "open_hooks", []) or []),
            }
        ],
        touched_entities=touched_entities,
        allow_ai=True,
    )
    story_bible["control_console"] = console
    story_bible = _ensure_story_bible_foundation(
        story_bible,
        payload=payload,
        global_outline=story_bible.get("global_outline") or {},
        active_arc=story_bible.get("active_arc") or {},
    )
    runtime = ensure_serial_runtime(story_bible)
    runtime["last_chapter_review"] = retrospective
    story_bible["serial_runtime"] = runtime
    story_bible = refresh_planning_views(story_bible, chapter_no)
    story_bible = set_pipeline_target(story_bible, next_chapter_no=chapter_no + 1, stage="summary_and_review", last_completed_chapter_no=chapter_no)
    update_story_state_bucket(
        story_bible,
        last_chapter_update={
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "delivery_mode": delivery_mode,
            "recent_progress_count": len(console.get("recent_progress", [])),
        },
    )
    return sync_long_term_state(story_bible, novel)


def build_control_console_snapshot(novel: Novel) -> dict[str, Any]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    console = ensure_control_console(story_bible)
    return {
        "novel_id": novel.id,
        "title": novel.title,
        "story_bible_meta": story_bible.get("story_bible_meta", {}),
        "project_card": story_bible.get("project_card", {}),
        "world_bible": story_bible.get("world_bible", {}),
        "cultivation_system": story_bible.get("cultivation_system", {}),
        "power_system": story_bible.get("power_system", {}),
        "opening_constraints": story_bible.get("opening_constraints", {}),
        "story_domains": story_bible.get("story_domains", {}),
        "template_library": story_bible.get("template_library", {}),
        "planner_state": story_bible.get("planner_state", {}),
        "retrospective_state": story_bible.get("retrospective_state", {}),
        "flow_control": story_bible.get("flow_control", {}),
        "serial_rules": story_bible.get("serial_rules", {}),
        "serial_runtime": story_bible.get("serial_runtime", {}),
        "fact_ledger": story_bible.get("fact_ledger", {}),
        "hard_fact_guard": compact_hard_fact_guard(story_bible.get("hard_fact_guard", {})),
        "long_term_state": story_bible.get("long_term_state", {}),
        "initialization_packet": story_bible.get("initialization_packet", {}),
        "current_volume_card": _current_volume_card(story_bible, novel.current_chapter_no + 1),
        "control_console": console,
        "planning_layers": story_bible.get("planning_layers", {}),
        "planning_state": story_bible.get("workflow_state", {}),
        "continuity_rules": story_bible.get("continuity_rules", list(DEFAULT_CONTINUITY_RULES)),
        "daily_workflow": story_bible.get("daily_workflow", {}),
        "story_state": story_bible.get("story_state", {}),
    }
