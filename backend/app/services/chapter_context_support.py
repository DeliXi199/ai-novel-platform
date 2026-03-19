from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import settings
from app.services.chapter_context_common import (
    _collect_live_hooks,
    _compact_arc,
    _compact_scene_card,
    _compact_scene_handoff_card,
    _compact_value,
    _json_size,
    _normalize_hook,
    _phase_rule,
    _published_and_stock_facts,
    _resolve_opening_reveal_guidance,
    _select_outline_window,
    _tail_paragraphs,
    _truncate_list,
    _truncate_text,
    _unique_texts,
)
from app.services.chapter_context_serialization import (
    _extract_continuity_bridge,
    _load_recent_chapters,
    _serialize_active_interventions,
    _serialize_last_chapter,
    _serialize_novel_context,
    _serialize_recent_summaries,
    _validate_fact_ledger_state,
    serialize_local_novel_context,
)
from app.services.chapter_payload_budget import _fit_chapter_payload_budget, _similarity
from app.services.importance_evaluator import _ai_enabled as _importance_ai_enabled, evaluate_story_elements_importance
from app.services.constraint_reasoning import _ai_enabled as _constraint_ai_enabled
from app.services.resource_card_support import build_resource_capability_plan, build_resource_card, ensure_resource_card_structure, infer_resource_plan_entry
from app.services.core_cast_support import bind_character_to_core_slot, core_cast_guidance_for_chapter
from app.services.character_schedule_support import build_character_relation_schedule_guidance
from app.services.card_indexing import apply_card_selection_to_packet, build_card_index_payload, ensure_card_id
from app.services.stage_review_support import build_chapter_stage_casting_hint
from app.services.story_character_support import apply_character_template_defaults, character_template_prompt_brief, pick_character_template
from app.services import payoff_cards as payoff_cards_module
from app.services.payoff_cards import build_payoff_candidate_index, realize_payoff_selection_from_index, select_payoff_card_from_candidate_index
from app.services.foreshadowing_cards import (
    build_foreshadowing_candidate_index,
    build_foreshadowing_child_card_index,
    build_foreshadowing_parent_card_index,
    realize_foreshadowing_selection_from_index,
)
from app.services.scene_templates import build_scene_continuity_index
from app.services.prompt_strategy_library import (
    build_flow_card_index,
    build_flow_child_card_index,
    build_prompt_bundle_index,
    build_prompt_strategy_index,
    build_writing_card_index,
    build_writing_child_card_index,
)





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





def _build_schedule_candidate_index(
    guidance: dict[str, Any] | None,
    *,
    core_cast_guidance: dict[str, Any] | None,
    stage_hint: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = guidance or {}
    appearance = (payload.get("appearance_schedule") or {}) if isinstance(payload, dict) else {}
    relation = (payload.get("relationship_schedule") or {}) if isinstance(payload, dict) else {}
    core_cast = core_cast_guidance or {}
    hint = stage_hint or {}

    def _compact_character_row(row: dict[str, Any]) -> dict[str, Any]:
        summary = _truncate_text(row.get("summary") or row.get("reason"), 72)
        push_direction = _truncate_text(row.get("push_direction"), 24)
        return {
            "name": _truncate_text(row.get("name"), 20),
            "type": "schedule_character",
            "title": _truncate_text(row.get("name"), 20),
            "summary": summary,
            "chapter_use": push_direction or summary,
            "constraint": _truncate_text(row.get("interaction_need"), 18),
            "priority_hint": _truncate_text(row.get("due_status"), 16),
            "due_status": _truncate_text(row.get("due_status"), 16),
            "interaction_need": _truncate_text(row.get("interaction_need"), 18),
            "push_direction": push_direction,
        }

    def _compact_relation_row(row: dict[str, Any]) -> dict[str, Any]:
        summary = _truncate_text(row.get("summary") or row.get("reason"), 72)
        push_direction = _truncate_text(row.get("push_direction"), 24)
        return {
            "relation_id": _truncate_text(row.get("relation_id"), 48),
            "type": "schedule_relation",
            "title": _truncate_text(row.get("relation_id"), 32),
            "summary": summary,
            "chapter_use": push_direction or summary,
            "constraint": _truncate_text(row.get("interaction_depth"), 18),
            "priority_hint": _truncate_text(row.get("due_status"), 16),
            "due_status": _truncate_text(row.get("due_status"), 16),
            "interaction_depth": _truncate_text(row.get("interaction_depth"), 18),
            "push_direction": push_direction,
        }

    return {
        "appearance_candidates": [
            item for item in [
                _compact_character_row(row)
                for row in (appearance.get("priority_characters") or [])[:8]
                if isinstance(row, dict)
            ]
            if item.get("name")
        ],
        "relation_candidates": [
            item for item in [
                _compact_relation_row(row)
                for row in (relation.get("priority_relations") or [])[:8]
                if isinstance(row, dict)
            ]
            if item.get("relation_id")
        ],
        "schedule_summary": {
            "due_characters": _truncate_list(appearance.get("due_characters"), max_items=5, item_limit=20),
            "resting_characters": _truncate_list(appearance.get("resting_characters"), max_items=5, item_limit=20),
            "due_relations": _truncate_list(relation.get("due_relations"), max_items=5, item_limit=48),
        },
        "core_cast_summary": {
            "focus_character": _truncate_text(core_cast.get("focus_character") or ((core_cast.get("focus_slot") or {}).get("name")), 20),
            "must_keep": _truncate_list(core_cast.get("must_keep_characters"), max_items=4, item_limit=20),
            "relationship_focus": _truncate_text(core_cast.get("relationship_focus"), 48),
        },
        "stage_casting": {
            "planned_action": _truncate_text(hint.get("planned_action"), 24),
            "planned_target": _truncate_text(hint.get("planned_target"), 20),
            "recommended_action": _truncate_text(hint.get("recommended_action"), 24),
            "chapter_hint": _truncate_text(hint.get("chapter_hint"), 88),
            "watchouts": _truncate_list(hint.get("watchouts"), max_items=4, item_limit=24),
        },
    }





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


_RESOURCE_CAPABILITY_ACTION_TOKENS = [
    "动用", "催动", "激活", "祭出", "引动", "试探", "试着", "试出", "共鸣", "发热", "异动", "照出", "映出",
    "炼化", "炼制", "服下", "吞下", "灌注", "破局", "护身", "保命", "压价", "交换", "支付", "驱动", "探查", "窥测",
]


def _resource_text_hit(text: str, candidates: list[str]) -> bool:
    blob = "".join(str(text or "").split())
    return any(candidate and "".join(candidate.split()) in blob for candidate in candidates)


def _resource_capability_card_signature(card: dict[str, Any], *, fallback_name: str, owner: str) -> dict[str, Any]:
    normalized = ensure_resource_card_structure(card, fallback_name=fallback_name, owner=owner)
    unlock_state = normalized.get("unlock_state") or {}
    last_trigger = unlock_state.get("last_trigger") or {}
    last_update = normalized.get("last_capability_update") or {}
    known = _unique_texts(list(unlock_state.get("known_abilities") or []), limit=6, item_limit=24)
    locked = _unique_texts(list(unlock_state.get("locked_abilities") or []), limit=6, item_limit=24)
    return {
        "quantity": int(normalized.get("quantity") or 0),
        "resource_scope": _truncate_text(normalized.get("resource_scope"), 12),
        "importance_tier": _truncate_text(normalized.get("importance_tier") or normalized.get("resource_tier"), 12),
        "unlock_level": _truncate_text(unlock_state.get("level"), 16),
        "known_abilities": known,
        "locked_abilities": locked,
        "cooldown": _truncate_text(unlock_state.get("cooldown"), 24),
        "last_trigger_chapter": int((last_trigger or {}).get("chapter_no") or 0),
        "last_capability_update_chapter": int((last_update or {}).get("chapter_no") or 0),
        "resource_kind": _truncate_text(normalized.get("resource_kind"), 16),
    }


def _is_key_resource(card: dict[str, Any]) -> bool:
    normalized = ensure_resource_card_structure(card, fallback_name=_truncate_text(card.get("name"), 24), owner=_truncate_text(card.get("owner"), 24))
    scope = _truncate_text(normalized.get("resource_scope"), 12)
    tier = _truncate_text(normalized.get("importance_tier") or normalized.get("resource_tier"), 12)
    score = int(normalized.get("importance_score") or 0)
    return scope == "核心资源" or tier in {"核心级", "重要级"} or score >= 72


def _latest_resource_capability_plan_cache_entry(planner_state: dict[str, Any], *, chapter_no: int) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    cache = planner_state.setdefault("resource_capability_plan_cache", {})
    candidates: list[tuple[int, dict[str, Any]]] = []
    for key, value in cache.items():
        if not isinstance(value, dict):
            continue
        try:
            cached_chapter = int(key)
        except (TypeError, ValueError):
            continue
        if cached_chapter >= int(chapter_no or 0):
            continue
        candidates.append((cached_chapter, value))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0]


def _resource_capability_plan_requires_resource_action(plan_text: str, selected_resources: list[str], resources: dict[str, Any]) -> tuple[bool, list[str]]:
    blob = "".join(str(plan_text or "").split())
    if not blob or not selected_resources:
        return False, []
    matched_resources: list[str] = []
    has_action_token = any(token in blob for token in _RESOURCE_CAPABILITY_ACTION_TOKENS)
    for name in selected_resources:
        card = ensure_resource_card_structure(resources.get(name) or {}, fallback_name=name, owner="")
        ability_tokens = _unique_texts(
            list(card.get("core_functions") or [])
            + list(card.get("activation_rules") or [])
            + [card.get("ability_summary")],
            limit=8,
            item_limit=18,
        )
        direct_name_hit = _resource_text_hit(blob, [name])
        ability_hit = _resource_text_hit(blob, ability_tokens)
        if ability_hit or (has_action_token and direct_name_hit):
            matched_resources.append(name)
    return bool(matched_resources), matched_resources[:4]


def _resource_capability_continuity_signal(selected_resources: list[str], resources: dict[str, Any], serialized_last: dict[str, Any], recent_summaries: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else {}
    text_parts: list[str] = [
        serialized_last.get("tail_excerpt"),
        bridge.get("opening_anchor"),
        *list(bridge.get("unresolved_action_chain") or []),
        *list(bridge.get("carry_over_clues") or []),
    ]
    if recent_summaries:
        latest = recent_summaries[-1] if isinstance(recent_summaries[-1], dict) else {}
        text_parts.extend(list((latest.get("open_hooks") or [])))
        text_parts.append(latest.get("event_summary") or latest.get("summary"))
    blob = "\n".join(str(item or "") for item in text_parts if str(item or "").strip())
    if not blob:
        return False, []
    matched: list[str] = []
    for name in selected_resources:
        card = ensure_resource_card_structure(resources.get(name) or {}, fallback_name=name, owner="")
        hint_tokens = _unique_texts(
            [name, card.get("ability_summary"), *list(card.get("core_functions") or []), *list(card.get("activation_rules") or [])],
            limit=8,
            item_limit=18,
        )
        if _resource_text_hit(blob, hint_tokens):
            matched.append(name)
    return bool(matched), matched[:4]


def _detect_resource_capability_refresh_signals(
    *,
    story_bible: dict[str, Any],
    protagonist_name: str,
    plan: dict[str, Any],
    resources: dict[str, Any],
    selected_resources: list[str],
    recent_summaries: list[dict[str, Any]],
    serialized_last: dict[str, Any],
    chapter_no: int,
) -> dict[str, Any]:
    planner_state = story_bible.setdefault("planner_state", {})
    current_selected = _unique_texts(list(selected_resources), limit=12, item_limit=24)
    current_signatures: dict[str, Any] = {
        name: _resource_capability_card_signature(resources.get(name) or {}, fallback_name=name, owner=protagonist_name)
        for name in current_selected
    }
    cached_chapter, cached_plan = _latest_resource_capability_plan_cache_entry(planner_state, chapter_no=chapter_no)
    runtime: dict[str, Any] = {
        "cache_enabled": bool(settings.resource_capability_plan_cache_enabled),
        "cache_hit": False,
        "cache_status": "ai_regenerated",
        "refresh": True,
        "reasons": [],
        "matched_resources": [],
        "source_chapter": cached_chapter,
        "selected_resources": current_selected,
        "resource_state_signatures": current_signatures,
        "plan_requires_resource_capability": False,
        "continuity_signal": False,
    }
    if not settings.resource_capability_plan_cache_enabled:
        runtime["reasons"] = ["cache_disabled"]
        return runtime
    if not isinstance(cached_plan, dict) or not cached_plan:
        runtime["reasons"] = ["cache_miss"]
        return runtime

    runtime["cache_hit"] = True
    cached_meta = cached_plan.get("__meta__") if isinstance(cached_plan.get("__meta__"), dict) else {}
    cached_selected = _unique_texts(
        list(cached_meta.get("selected_resources") or [name for name in cached_plan.keys() if name != "__meta__"]),
        limit=12,
        item_limit=24,
    )
    reasons: list[str] = []
    matched_resources: list[str] = []
    new_resources = [name for name in current_selected if name not in cached_selected]
    removed_resources = [name for name in cached_selected if name not in current_selected]
    if new_resources:
        reasons.extend([f"new_resource:{name}" for name in new_resources[:3]])
        matched_resources.extend(new_resources[:3])
    if removed_resources:
        reasons.extend([f"resource_selection_changed:{name}" for name in removed_resources[:3]])
    force_interval = max(int(settings.resource_capability_plan_force_refresh_interval_chapters or 0), 0)
    if force_interval and cached_chapter is not None and int(chapter_no or 0) - int(cached_chapter or 0) >= force_interval:
        reasons.append(f"refresh_interval:{cached_chapter}->{chapter_no}")

    cached_signatures = cached_meta.get("resource_state_signatures") if isinstance(cached_meta.get("resource_state_signatures"), dict) else {}
    recent_trigger_window = max(int(settings.resource_capability_plan_recent_trigger_window or 1), 1)
    for name in current_selected:
        card = resources.get(name) or {}
        current_signature = current_signatures.get(name) or {}
        if not _is_key_resource(card):
            continue
        previous_signature = cached_signatures.get(name) if isinstance(cached_signatures, dict) else None
        if not isinstance(previous_signature, dict):
            reasons.append(f"key_resource_uncached:{name}")
            matched_resources.append(name)
            continue
        unlock_fields = ["unlock_level", "known_abilities", "locked_abilities"]
        if any(previous_signature.get(field) != current_signature.get(field) for field in unlock_fields):
            reasons.append(f"unlock_state_changed:{name}")
            matched_resources.append(name)
        if previous_signature.get("cooldown") != current_signature.get("cooldown"):
            reasons.append(f"cooldown_changed:{name}")
            matched_resources.append(name)
        last_trigger_chapter = int(current_signature.get("last_trigger_chapter") or 0)
        last_update_chapter = int(current_signature.get("last_capability_update_chapter") or 0)
        if int(chapter_no or 0) - max(last_trigger_chapter, last_update_chapter) <= recent_trigger_window and max(last_trigger_chapter, last_update_chapter) > 0:
            reasons.append(f"recent_capability_use:{name}")
            matched_resources.append(name)

    plan_text = _plan_text_blob(plan)
    plan_requires_resource_capability, plan_matched = _resource_capability_plan_requires_resource_action(plan_text, current_selected, resources)
    if plan_requires_resource_capability:
        reasons.append("plan_requires_resource_capability")
        matched_resources.extend(plan_matched)

    continuity_signal, continuity_matched = _resource_capability_continuity_signal(current_selected, resources, serialized_last, recent_summaries)
    if continuity_signal:
        reasons.append("continuity_bridge_mentions_resource")
        matched_resources.extend(continuity_matched)

    refresh = bool(reasons)
    runtime.update(
        {
            "refresh": refresh,
            "reasons": reasons or ["stable_reuse"],
            "matched_resources": _unique_texts(matched_resources, limit=6, item_limit=24),
            "plan_requires_resource_capability": plan_requires_resource_capability,
            "continuity_signal": continuity_signal,
        }
    )
    if not refresh:
        runtime["cache_status"] = "reused"
    return runtime



def _build_resource_capability_plan_with_cache(
    *,
    story_bible: dict[str, Any],
    protagonist_name: str,
    plan: dict[str, Any],
    resources: dict[str, Any],
    selected_resources: list[str],
    recent_summaries: list[dict[str, Any]],
    serialized_last: dict[str, Any],
    chapter_no: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    planner_state = story_bible.setdefault("planner_state", {})
    runtime = _detect_resource_capability_refresh_signals(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        plan=plan,
        resources=resources,
        selected_resources=selected_resources,
        recent_summaries=recent_summaries,
        serialized_last=serialized_last,
        chapter_no=chapter_no,
    )
    cached_chapter, cached_plan = _latest_resource_capability_plan_cache_entry(planner_state, chapter_no=chapter_no)
    if runtime.get("cache_hit") and not runtime.get("refresh") and isinstance(cached_plan, dict):
        reused_plan: dict[str, Any] = {"__meta__": {}}
        for name in runtime.get("selected_resources") or []:
            if name == "__meta__":
                continue
            entry = cached_plan.get(name)
            if isinstance(entry, dict):
                reused_plan[name] = deepcopy(entry)
        cached_meta = cached_plan.get("__meta__") if isinstance(cached_plan.get("__meta__"), dict) else {}
        meta = deepcopy(cached_meta)
        meta.update(
            {
                "reasoning_mode": "cache_reuse",
                "used_ai": False,
                "source_used_ai": bool(cached_meta.get("used_ai") or cached_meta.get("source_used_ai")),
                "cache_hit": True,
                "cache_status": "reused",
                "reused_from_chapter": cached_chapter,
                "selected_count": len(runtime.get("selected_resources") or []),
                "selected_resources": list(runtime.get("selected_resources") or []),
                "resource_state_signatures": deepcopy(runtime.get("resource_state_signatures") or {}),
                "refresh_reasons": list(runtime.get("reasons") or []),
                "generated_for_chapter": chapter_no,
            }
        )
        reused_plan["__meta__"] = meta
        return reused_plan, runtime

    result = build_resource_capability_plan(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        plan=plan,
        resources=resources,
        selected_resources=selected_resources,
        recent_summaries=recent_summaries,
        serialized_last=serialized_last,
        allow_ai=True,
    )
    if not isinstance(result, dict):
        result = {"__meta__": {}}
    meta = result.setdefault("__meta__", {})
    used_ai = bool(meta.get("used_ai"))
    runtime["cache_status"] = "ai_regenerated" if used_ai else "local_regenerated"
    meta.update(
        {
            "cache_hit": bool(runtime.get("cache_hit")),
            "cache_status": runtime.get("cache_status"),
            "reused_from_chapter": None,
            "selected_count": len(runtime.get("selected_resources") or []),
            "selected_resources": list(runtime.get("selected_resources") or []),
            "resource_state_signatures": deepcopy(runtime.get("resource_state_signatures") or {}),
            "refresh_reasons": list(runtime.get("reasons") or []),
            "generated_for_chapter": chapter_no,
            "source_used_ai": used_ai,
        }
    )
    return result, runtime


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
    workspace_state = story_bible.setdefault("story_workspace", {})
    cards = workspace_state.setdefault("cast_cards", {})
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


def _active_importance_handoff(story_bible: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    if not bool(getattr(settings, "importance_handoff_enabled", True)):
        return {}
    importance_state = (story_bible.get("importance_state") or {}) if isinstance(story_bible, dict) else {}
    handoff = (importance_state.get("next_chapter_handoff") or {}) if isinstance(importance_state, dict) else {}
    if not isinstance(handoff, dict) or not handoff:
        return {}
    try:
        confidence = float(handoff.get("confidence", 0.0) or 0.0)
    except Exception:
        confidence = 0.0
    min_confidence = float(getattr(settings, "importance_handoff_min_confidence", 0.55) or 0.55)
    if confidence < min_confidence:
        return {}
    source_chapter = int(handoff.get("source_chapter", 0) or 0)
    if source_chapter <= 0 or int(chapter_no or 0) <= source_chapter:
        return {}
    decay_window = max(int(getattr(settings, "importance_handoff_decay_chapters", 2) or 2), 1)
    age = int(chapter_no or 0) - source_chapter
    if age > decay_window:
        return {}
    return handoff



def _planning_importance_allow_ai(story_bible: dict[str, Any], *, chapter_no: int) -> bool:
    return True



def _handoff_bias_map(entity_type: str, handoff: dict[str, Any] | None, *, chapter_no: int) -> dict[str, float]:
    if not isinstance(handoff, dict) or not handoff:
        return {}
    source_chapter = int(handoff.get("source_chapter", 0) or 0)
    if source_chapter <= 0:
        return {}
    age = max(int(chapter_no or 0) - source_chapter, 1)
    decay_window = max(int(getattr(settings, "importance_handoff_decay_chapters", 2) or 2), 1)
    if age > decay_window:
        return {}
    decay_factor = 1.0 if age <= 1 else max(0.45, 1.0 - 0.35 * (age - 1))
    must_bonus = float(getattr(settings, "importance_handoff_must_carry_bonus", 20.0) or 20.0)
    warm_bonus = float(getattr(settings, "importance_handoff_warm_bonus", 10.0) or 10.0)
    cooldown_penalty = float(getattr(settings, "importance_handoff_cooldown_penalty", 8.0) or 8.0)
    defer_penalty = float(getattr(settings, "importance_handoff_defer_penalty", 5.0) or 5.0)
    bias: dict[str, float] = {}
    buckets = {
        must_bonus: ((handoff.get("must_carry") or {}).get(entity_type) or []),
        warm_bonus: ((handoff.get("warm") or {}).get(entity_type) or []),
        -cooldown_penalty: ((handoff.get("cooldown") or {}).get(entity_type) or []),
        -defer_penalty: ((handoff.get("defer") or {}).get(entity_type) or []),
    }
    for delta, names in buckets.items():
        for raw in names:
            name = _truncate_text(raw, 48)
            if not name:
                continue
            bias[name] = bias.get(name, 0.0) + float(delta) * decay_factor
    return bias



def _sort_names_with_handoff_bias(container: dict[str, Any], names: list[str], *, mode: str, entity_type: str, handoff: dict[str, Any] | None, chapter_no: int) -> list[str]:
    ordered_names = [name for name in names if name in container]
    if not ordered_names:
        return []
    score_key = {
        "mainline": "importance_mainline_rank_score",
        "activation": "importance_activation_rank_score",
        "exploration": "importance_exploration_score",
        "combined": "importance_soft_rank_score",
    }.get(mode, "importance_soft_rank_score")
    bias_map = _handoff_bias_map(entity_type, handoff, chapter_no=chapter_no)
    return sorted(
        ordered_names,
        key=lambda item: (
            -(float((container.get(item) or {}).get(score_key, 0.0) or 0.0) + float(bias_map.get(item, 0.0) or 0.0)),
            -float((container.get(item) or {}).get("importance_soft_rank_score", 0.0) or 0.0),
            -int((container.get(item) or {}).get("importance_score", 0) or 0),
            item,
        ),
    )


def _combine_importance_lanes(
    container: dict[str, Any],
    names: list[str],
    *,
    entity_type: str,
    chapter_no: int,
    base_limit: int,
    keep_names: list[str] | None = None,
    allow_exploration: bool = True,
    handoff: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    ordered_names = [name for name in names if name in container]
    keep = [name for name in (keep_names or []) if name in ordered_names]
    mainline_ranked = _sort_names_with_handoff_bias(container, ordered_names, mode="mainline", entity_type=entity_type, handoff=handoff, chapter_no=chapter_no)
    activation_ranked = _sort_names_with_handoff_bias(container, ordered_names, mode="activation", entity_type=entity_type, handoff=handoff, chapter_no=chapter_no)
    exploration_ranked = [
        name
        for name in _sort_names_with_handoff_bias(container, ordered_names, mode="exploration", entity_type=entity_type, handoff=handoff, chapter_no=chapter_no)
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
        "handoff_applied": bool(_handoff_bias_map(entity_type, handoff, chapter_no=chapter_no)),
        "handoff_reason_summary": _truncate_text((handoff or {}).get("reason_summary"), 120),
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


def _outline_entry_for_chapter(workspace_state: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    for source_key in ("chapter_card_queue", "near_7_chapter_outline"):
        for item in (workspace_state.get(source_key) or []):
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
    recent_plan_meta: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workspace_state = (story_bible.get("story_workspace") or {}) if isinstance(story_bible, dict) else {}
    chapter_no = int(plan.get("chapter_no", 0) or 0)
    bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else {}
    current_outline = _outline_entry_for_chapter(workspace_state, chapter_no)
    next_outline = _outline_entry_for_chapter(workspace_state, chapter_no + 1)
    next_two_outline = _outline_entry_for_chapter(workspace_state, chapter_no + 2)

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
    recent_plan_meta: list[dict[str, Any]] | None = None,
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
    active_importance_handoff = _active_importance_handoff(story_bible, chapter_no=chapter_no)
    importance_summary = evaluate_story_elements_importance(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        scope="planning",
        chapter_no=chapter_no,
        plan=plan,
        recent_summaries=recent_summaries,
        touched_entities=touched_entities,
        allow_ai=_planning_importance_allow_ai(story_bible, chapter_no=chapter_no),
    )

    priority_resources = []
    for item in ((characters.get(protagonist_name) or {}).get("resource_refs") or []):
        card = resources.get(item) or {}
        tier = _truncate_text(card.get("importance_tier") or card.get("resource_tier"), 16)
        score = int(card.get("importance_score") or 0)
        if tier in {"核心级", "重要级"} or score >= 72:
            priority_resources.append(item)

    all_character_names = list((characters or {}).keys())
    all_resource_names = list((resources or {}).keys())
    all_faction_names = list((factions or {}).keys())
    all_relation_names = list((relations or {}).keys())
    candidate_characters = _unique_texts([protagonist_name, focus_name] + list(candidate_characters) + all_character_names, limit=max(len(all_character_names) + 6, 12), item_limit=20)
    selected_resources = _unique_texts(priority_resources[:2] + list(selected_resources) + all_resource_names, limit=max(len(all_resource_names) + 6, 12), item_limit=24)
    selected_factions = _unique_texts(list(selected_factions) + all_faction_names, limit=max(len(all_faction_names) + 4, 10), item_limit=24)
    relation_keys = _unique_texts(list(relation_keys) + all_relation_names, limit=max(len(all_relation_names) + 6, 12), item_limit=32)

    character_selection_lanes: dict[str, Any] = {
        "mode": "ai_direct_selection",
        "candidate_count": len(candidate_characters),
        "selected_by_lane": {"all_candidates": list(candidate_characters)},
        "handoff_applied": bool(_handoff_bias_map("character", active_importance_handoff, chapter_no=chapter_no)),
        "handoff_reason_summary": _truncate_text((active_importance_handoff or {}).get("reason_summary"), 120),
    }
    resource_selection_lanes: dict[str, Any] = {
        "mode": "ai_direct_selection",
        "candidate_count": len(selected_resources),
        "selected_by_lane": {"all_candidates": list(selected_resources)},
        "handoff_applied": bool(_handoff_bias_map("resource", active_importance_handoff, chapter_no=chapter_no)),
        "handoff_reason_summary": _truncate_text((active_importance_handoff or {}).get("reason_summary"), 120),
    }
    faction_selection_lanes: dict[str, Any] = {
        "mode": "ai_direct_selection",
        "candidate_count": len(selected_factions),
        "selected_by_lane": {"all_candidates": list(selected_factions)},
        "handoff_applied": bool(_handoff_bias_map("faction", active_importance_handoff, chapter_no=chapter_no)),
        "handoff_reason_summary": _truncate_text((active_importance_handoff or {}).get("reason_summary"), 120),
    }
    relation_selection_lanes: dict[str, Any] = {
        "mode": "ai_direct_selection",
        "candidate_count": len(relation_keys),
        "selected_by_lane": {"all_candidates": list(relation_keys)},
        "handoff_applied": bool(_handoff_bias_map("relation", active_importance_handoff, chapter_no=chapter_no)),
        "handoff_reason_summary": _truncate_text((active_importance_handoff or {}).get("reason_summary"), 120),
    }

    character_relation_schedule = build_character_relation_schedule_guidance(
        story_bible,
        protagonist_name=protagonist_name,
        chapter_no=chapter_no or 1,
        focus_name=focus_name,
        plan=plan,
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
    resource_capability_plan, resource_capability_runtime = _build_resource_capability_plan_with_cache(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        plan=plan,
        resources=resources,
        selected_resources=selected_resources,
        recent_summaries=recent_summaries,
        serialized_last=serialized_last,
        chapter_no=chapter_no,
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

    payoff_candidate_index = build_payoff_candidate_index(
        story_bible=story_bible,
        plan=plan,
        recent_summaries=recent_summaries,
        recent_plan_meta=recent_plan_meta,
    )
    foreshadowing_parent_card_index = build_foreshadowing_parent_card_index(story_bible) or []
    foreshadowing_child_card_index = build_foreshadowing_child_card_index(story_bible) or []
    foreshadowing_candidate_index = build_foreshadowing_candidate_index(
        story_bible=story_bible,
        plan=plan,
        recent_summaries=recent_summaries,
    )
    scene_continuity_index = build_scene_continuity_index(
        story_bible=story_bible,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=recent_summaries,
    )
    flow_template_index = build_flow_card_index(story_bible) or []
    prompt_strategy_index = build_writing_card_index()
    flow_child_card_index = build_flow_child_card_index(story_bible) or []
    writing_child_card_index = build_writing_child_card_index() or []
    prompt_bundle_index = build_prompt_bundle_index(story_bible)
    scene_runtime = {
        "scene_sequence_plan": [],
        "scene_execution_card": {
            "scene_count": 0,
            "must_continue_same_scene": None,
            "transition_mode": "ai_required",
            "allowed_transition": "ai_required",
            "selection_mode": "awaiting_ai_scene_review",
        },
        "scene_templates_used": [],
        "recent_scene_hints": scene_continuity_index.get("recent_scene_hints") or [],
    }

    payoff_candidates = [item for item in (payoff_candidate_index.get("candidates") or []) if isinstance(item, dict)]
    selected_payoff_id = ""
    payoff_selection_note = ""
    payoff_execution_hint = ""
    payoff_selector_mode = "ai_compressed_index"
    if payoff_candidates:
        ai_payload = select_payoff_card_from_candidate_index(
            chapter_plan=plan,
            payoff_candidate_index=payoff_candidate_index,
        )
        selected_payoff_id = _truncate_text(ai_payload.get("selected_card_id"), 48)
        payoff_selection_note = _truncate_text(ai_payload.get("reason"), 96)
        payoff_execution_hint = _truncate_text(ai_payload.get("execution_hint"), 96)
    payoff_runtime = realize_payoff_selection_from_index(
        story_bible=story_bible,
        plan=plan,
        selected_card_id=selected_payoff_id,
        recent_summaries=recent_summaries,
        recent_plan_meta=recent_plan_meta,
        selection_note=payoff_selection_note,
    )
    payoff_runtime["selector_mode"] = payoff_selector_mode
    foreshadowing_runtime = {
        "selected_primary_candidate": {},
        "selected_supporting_candidates": [],
        "selected_instance_cards": [],
        "selection_note": "",
        "selector_mode": "ai_compressed_index",
        "candidate_count": len((foreshadowing_candidate_index.get("candidates") or [])),
        "diagnostics": foreshadowing_candidate_index.get("diagnostics") or {},
    }
    if payoff_execution_hint and isinstance(payoff_runtime.get("selected_payoff_card"), dict):
        payoff_runtime["selected_payoff_card"]["ai_execution_hint"] = payoff_execution_hint
    payoff_runtime.setdefault("payoff_card_candidates", payoff_candidates)
    if isinstance(payoff_runtime.get("payoff_diagnostics"), dict):
        payoff_runtime["payoff_diagnostics"]["selector_mode"] = payoff_selector_mode
        if payoff_execution_hint:
            payoff_runtime["payoff_diagnostics"]["ai_execution_hint"] = payoff_execution_hint

    schedule_candidate_index = _build_schedule_candidate_index(
        character_relation_schedule,
        core_cast_guidance=core_cast_guidance,
        stage_hint=chapter_stage_casting_hint,
    )

    continuity_window = {
        "recent_chapter_summaries": _compact_value(recent_summaries[-3:], text_limit=72),
        "last_chapter_tail_excerpt": _truncate_text(serialized_last.get("tail_excerpt"), settings.chapter_last_excerpt_chars),
        "last_two_paragraphs": _truncate_list(serialized_last.get("last_two_paragraphs"), max_items=2, item_limit=220),
        "opening_anchor": _truncate_text((bridge or {}).get("opening_anchor"), 120),
        "unresolved_action_chain": _truncate_list((bridge or {}).get("unresolved_action_chain"), max_items=3, item_limit=64),
        "carry_over_clues": _truncate_list((bridge or {}).get("carry_over_clues"), max_items=3, item_limit=56),
        "scene_handoff_card": _compact_value((bridge or {}).get("scene_handoff_card") or {}, text_limit=72),
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
            "payoff_mode": ((payoff_runtime.get("selected_payoff_card") or {}).get("payoff_mode")),
            "payoff_visibility": ((payoff_runtime.get("selected_payoff_card") or {}).get("payoff_visibility")),
            "payoff_compensation_priority": (((payoff_runtime.get("payoff_compensation") or {}).get("priority")) or ((plan.get("payoff_compensation") or {}).get("priority"))),
            "foreshadowing_candidate_count": len((foreshadowing_candidate_index.get("candidates") or [])),
            "due_characters": list((character_relation_schedule.get("appearance_schedule") or {}).get("due_characters") or []),
            "due_relations": list((character_relation_schedule.get("relationship_schedule") or {}).get("due_relations") or []),
            "importance_mainline_characters": list(character_selection_lanes.get("selected_by_lane", {}).get("mainline") or []),
            "importance_activation_characters": list(character_selection_lanes.get("selected_by_lane", {}).get("activation") or []),
            "importance_exploration_characters": list(character_selection_lanes.get("selected_by_lane", {}).get("exploration") or []),
            "importance_activation_resources": list(resource_selection_lanes.get("selected_by_lane", {}).get("activation") or []),
            "importance_exploration_resources": list(resource_selection_lanes.get("selected_by_lane", {}).get("exploration") or []),
        },
        "book_execution_profile": deepcopy(story_bible.get("book_execution_profile") or {}),
        "window_execution_bias": deepcopy(((story_bible.get("story_workspace") or {}).get("window_execution_bias") or {})),
        "window_execution_bias_brief": _compact_value((((story_bible.get("story_workspace") or {}).get("window_execution_bias") or {})), text_limit=48),
        "card_system_profile": deepcopy(story_bible.get("card_system_profile") or {}),
        "card_system_profile_brief": _compact_value((story_bible.get("card_system_profile") or {}), text_limit=48),
        "book_execution_profile_brief": {
            "positioning_summary": _truncate_text(((story_bible.get("book_execution_profile") or {}).get("positioning_summary")), 96),
            "flow_family_priority": _compact_value(((story_bible.get("book_execution_profile") or {}).get("flow_family_priority") or {}), text_limit=48),
            "payoff_priority": _compact_value(((story_bible.get("book_execution_profile") or {}).get("payoff_priority") or {}), text_limit=48),
            "foreshadowing_priority": _compact_value(((story_bible.get("book_execution_profile") or {}).get("foreshadowing_priority") or {}), text_limit=48),
            "writing_strategy_priority": _compact_value(((story_bible.get("book_execution_profile") or {}).get("writing_strategy_priority") or {}), text_limit=48),
            "rhythm_bias": _compact_value(((story_bible.get("book_execution_profile") or {}).get("rhythm_bias") or {}), text_limit=48),
            "demotion_rules": _truncate_list(((story_bible.get("book_execution_profile") or {}).get("demotion_rules") or []), max_items=4, item_limit=32),
        },
        "core_cast_guidance": core_cast_guidance,
        "chapter_stage_casting_hint": chapter_stage_casting_hint,
        "character_relation_schedule": character_relation_schedule,
        "schedule_candidate_index": schedule_candidate_index,
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
        "payoff_runtime": payoff_runtime,
        "payoff_candidate_index": payoff_candidate_index,
        "payoff_compensation": payoff_runtime.get("payoff_compensation") or plan.get("payoff_compensation") or {},
        "selected_payoff_card": payoff_runtime.get("selected_payoff_card") or {},
        "foreshadowing_parent_card_index": foreshadowing_parent_card_index,
        "foreshadowing_child_card_index": foreshadowing_child_card_index,
        "foreshadowing_candidate_index": foreshadowing_candidate_index,
        "foreshadowing_runtime": foreshadowing_runtime,
        "selected_foreshadowing_primary": {},
        "selected_foreshadowing_supporting": [],
        "selected_foreshadowing_instance_cards": [],
        "scene_runtime": scene_runtime,
        "scene_continuity_index": scene_continuity_index,
        "scene_template_index": scene_continuity_index,
        "scene_sequence_plan": scene_runtime.get("scene_sequence_plan") or [],
        "scene_execution_card": scene_runtime.get("scene_execution_card") or {},
        "flow_template_index": flow_template_index,
        "flow_card_index": flow_template_index,
        "flow_child_card_index": flow_child_card_index,
        "prompt_strategy_index": prompt_strategy_index,
        "writing_card_index": prompt_strategy_index,
        "writing_child_card_index": writing_child_card_index,
        "prompt_bundle_index": prompt_bundle_index,
        "writing_card_bundle_index": prompt_bundle_index,
        "selected_prompt_strategies": [],
        "selected_writing_cards": [],
        "selected_writing_child_cards": [],
        "resource_plan": resource_plan,
        "resource_capability_plan": resource_capability_plan,
        "resource_capability_runtime": resource_capability_runtime,
        "recent_continuity_plan": recent_continuity_plan,
        "opening_reveal_guidance": opening_reveal_guidance,
        "character_template_guidance": character_template_guidance,
        "importance_snapshot": importance_summary.get("evaluations") or {},
        "importance_handoff": active_importance_handoff,
        "importance_runtime": {
            "used_ai": bool(importance_summary.get("used_ai")),
            "selection_lanes": {
                "characters": character_selection_lanes,
                "resources": resource_selection_lanes,
                "factions": faction_selection_lanes,
                "relations": relation_selection_lanes,
            },
        },
        "resource_runtime": {
            "capability_plan": resource_capability_runtime,
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
            "write_from": ["chapter_plan", "recent_continuity_plan", "selected_story_cards", "selected_payoff_card", "selected_writing_cards", "resource_plan", "resource_capability_plan", "recent_chapter_summaries", "last_chapter_tail_excerpt"],
            "avoid": ["full_card_pool_dump", "whole_book_recap", "detached_scene_reset"],
            "continuity_priority": "先承接上一章末尾，再落实本章拍表，并兼顾最近几章的连续推进。",
            "resource_quantity_rule": "资源若带数量字段，正文必须保持前后数量一致，不得随意改写。",
            "resource_ability_rule": "资源若带能力档案，只能按 resource_capability_plan 和资源卡里的条件/代价/限制来写，不得突然无代价开新功能。",
            "stage_casting_rule": "若 chapter_stage_casting_hint 里的 final_should_execute_planned_action=true，就自然落实补新人或旧人换功能；若 final_do_not_force_action=true，则不要硬塞。",
            "selector_input_rule": "章节准备阶段的所有筛选输入都应来自压缩索引或压缩摘要；爽点、伏笔、流程卡、写法卡与场景连续性的续场/切场/场景顺序都必须由 AI 输出，本地不再提供替代规划。",
            "importance_lane_rule": "准备阶段不再用本地推进榜/激活榜做终选；这里只保留 importance 诊断供 AI 看全量压缩候选时参考。",
            "payoff_rule": "若 selected_payoff_card 存在，就把它视为本章爽点执行卡：先让读者拿到可感的回报，再让后患、代价或新压力跟上。",
            "foreshadowing_rule": "若 selected_foreshadowing_instance_cards 存在，就把它视为本章伏笔执行卡：本章只落实 1 条主伏笔动作和 0-2 条辅助动作，明确区分新埋、轻碰、加深、验证或回收，不要什么都碰。",
            "scene_rule": "场景层现在只负责续场、切场数量与切场过渡约束：是否先续上一章场景、章内是否需要切场、切场前必须先拿到阶段结果，并写出时间/地点/动作锚点。",
        },
    }
    return packet



