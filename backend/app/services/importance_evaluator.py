from __future__ import annotations

from copy import deepcopy
import time
from typing import Any

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, current_api_key
from app.services.resource_card_support import ensure_resource_card_structure
from app.services.prompt_support import clip_text, compact_data, compact_json, summarize_candidates
from app.services.story_character_support import _safe_list, _text
from app.services.story_fact_ledger import _now_iso

IMPORTANCE_TIERS = ["功能级", "临时级", "阶段级", "重要级", "核心级"]
TIER_TO_ANCHOR_SCORE = {
    "功能级": 24,
    "临时级": 42,
    "阶段级": 60,
    "重要级": 78,
    "核心级": 94,
}
TIER_TO_TRACKING = {
    "功能级": "minimal",
    "临时级": "light",
    "阶段级": "standard",
    "重要级": "focused",
    "核心级": "always_on",
}
TIER_TO_APPEARANCE = {
    "功能级": "按需",
    "临时级": "短期需要时进入规划",
    "阶段级": "当前阶段优先",
    "重要级": "相关章节优先",
    "核心级": "高频跟踪",
}
DIMENSION_KEYS = [
    "binding_depth",
    "recurrence",
    "mainline_leverage",
    "irreplaceability",
    "stage_relevance",
    "network_influence",
]
DIMENSION_WEIGHTS = {
    "binding_depth": 0.24,
    "recurrence": 0.18,
    "mainline_leverage": 0.22,
    "irreplaceability": 0.14,
    "stage_relevance": 0.12,
    "network_influence": 0.10,
}
CORE_RESOURCE_KEYWORDS = ["金手指", "古镜", "系统", "外挂", "本命", "传承", "血脉", "异火", "核心机缘"]
AI_EVAL_STAGE = "importance_evaluation"


def build_importance_state() -> dict[str, Any]:
    return {
        "version": 3,
        "status": "foundation_ready",
        "unified_dimensions": list(DIMENSION_KEYS),
        "last_scope": None,
        "last_evaluated_chapter": 0,
        "last_run_used_ai": False,
        "last_ai_eval_by_scope": {},
        "evaluation_history": [],
        "entity_index": {
            "character": {},
            "resource": {},
            "relation": {},
            "faction": {},
        },
    }


def ensure_importance_state(story_bible: dict[str, Any]) -> dict[str, Any]:
    state = story_bible.setdefault("importance_state", build_importance_state())
    for key, value in build_importance_state().items():
        if key not in state or state.get(key) in (None, "", []):
            state[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(state.get(key), dict):
            for sub_key, sub_value in value.items():
                state[key].setdefault(sub_key, deepcopy(sub_value))
    return state


def _score_to_tier(score: int) -> str:
    if score >= 90:
        return "核心级"
    if score >= 70:
        return "重要级"
    if score >= 52:
        return "阶段级"
    if score >= 34:
        return "临时级"
    return "功能级"


def _selection_hits(story_bible: dict[str, Any], entity_type: str, name: str) -> int:
    planner_state = story_bible.get("planner_state") or {}
    selected = planner_state.get("selected_entities_by_chapter") or {}
    hits = 0
    for _, bucket in list(selected.items())[-6:]:
        if not isinstance(bucket, dict):
            continue
        values = bucket.get(f"{entity_type}s")
        if entity_type == "relation":
            values = bucket.get("relations")
        if entity_type == "faction":
            values = bucket.get("factions")
        if entity_type == "resource":
            values = bucket.get("resources")
        if entity_type == "character":
            values = bucket.get("characters")
        if name in (values or []):
            hits += 1
    return hits


def _plan_text(plan: dict[str, Any] | None, recent_summaries: list[dict[str, Any]] | None) -> str:
    parts = []
    for key in [
        "title",
        "goal",
        "conflict",
        "ending_hook",
        "main_scene",
        "opening_beat",
        "mid_turn",
        "discovery",
        "closing_image",
        "supporting_character_focus",
        "supporting_character_note",
    ]:
        if isinstance(plan, dict):
            parts.append(_text(plan.get(key)))
    for item in recent_summaries or []:
        if isinstance(item, dict):
            parts.append(_text(item.get("event_summary")))
            parts.extend([_text(x) for x in (item.get("open_hooks") or [])[:3]])
    return "\n".join(part for part in parts if part)


def _truthy_mentions(text: str, values: list[str]) -> int:
    blob = str(text or "")
    return sum(1 for value in values if value and value in blob)


def _clamp_dimension(value: int) -> int:
    return max(0, min(int(value), 5))


def _base_dimensions() -> dict[str, int]:
    return {key: 1 for key in DIMENSION_KEYS}


def _evaluate_character(name: str, card: dict[str, Any], *, protagonist_name: str, plan_text: str, story_bible: dict[str, Any]) -> dict[str, Any]:
    dims = _base_dimensions()
    reasons: list[str] = []
    role_type = _text(card.get("role_type"))
    relation_level = _text(card.get("protagonist_relation_level") or card.get("attitude_to_protagonist"))
    selection_hits = _selection_hits(story_bible, "character", name)
    is_protagonist = name == protagonist_name or role_type == "protagonist"
    if is_protagonist:
        dims = {key: 5 for key in DIMENSION_KEYS}
        dims["network_influence"] = 4
        reasons.append("主角天然处在故事中心。")
    else:
        if role_type in {"supporting", "partner"}:
            dims["binding_depth"] += 2
            dims["mainline_leverage"] += 2
            dims["irreplaceability"] += 1
            reasons.append("角色身份已经被标成重要配角侧。")
        if relation_level and relation_level not in {"待观察", ""}:
            dims["binding_depth"] += 1
            dims["stage_relevance"] += 1
            reasons.append("与主角已有明确关系描述。")
        if selection_hits:
            dims["recurrence"] += min(selection_hits, 3)
            reasons.append("最近章节规划里反复被选中。")
        if name and name in plan_text:
            dims["stage_relevance"] += 2
            dims["recurrence"] += 1
            reasons.append("当前规划或最近摘要里直接点名。")
        if _safe_list(card.get("resource_refs")):
            dims["network_influence"] += 1
        if _safe_list(card.get("faction_refs")):
            dims["network_influence"] += 1
        if _text(card.get("current_goal") or card.get("current_desire")):
            dims["mainline_leverage"] += 1
        if _text(card.get("status")) in {"active", "planned"}:
            dims["stage_relevance"] += 1
    score = round(sum(_clamp_dimension(dims[key]) * DIMENSION_WEIGHTS[key] for key in DIMENSION_KEYS) * 20)
    if is_protagonist:
        score = 100
    dims = {key: _clamp_dimension(value) for key, value in dims.items()}
    if not reasons:
        reasons.append("当前更像功能位或边缘角色。")
    return {"dimensions": dims, "score": score, "reasons": reasons}


def _evaluate_resource(name: str, card: dict[str, Any], *, protagonist_name: str, plan_text: str, story_bible: dict[str, Any]) -> dict[str, Any]:
    resource = ensure_resource_card_structure(card, fallback_name=name, owner=protagonist_name)
    dims = _base_dimensions()
    reasons: list[str] = []
    owner = _text(resource.get("owner"))
    selection_hits = _selection_hits(story_bible, "resource", name)
    text_blob = " ".join(
        [
            _text(resource.get("name")),
            _text(resource.get("display_name")),
            _text(resource.get("resource_type")),
            _text(resource.get("resource_scope")),
            _text(resource.get("resource_kind")),
            _text(resource.get("narrative_role")),
            _text(resource.get("ability_summary")),
            _text(resource.get("ability_details")),
            _text(resource.get("core_functions")),
            _text(resource.get("activation_rules")),
            _text(((story_bible.get("project_card") or {}).get("golden_finger"))),
        ]
    )
    is_core_keyword = any(token in text_blob for token in CORE_RESOURCE_KEYWORDS)
    if is_core_keyword:
        dims["binding_depth"] = 5
        dims["recurrence"] = 5
        dims["mainline_leverage"] = 5
        dims["irreplaceability"] = 5
        dims["stage_relevance"] = 4
        dims["network_influence"] = 3
        reasons.append("命中了金手指/本命/传承类核心资源关键词。")
    else:
        if owner == protagonist_name:
            dims["binding_depth"] += 3
            dims["mainline_leverage"] += 1
            reasons.append("资源归主角持有。")
        if bool(resource.get("quantity_sensitive")):
            dims["recurrence"] += 1
            dims["stage_relevance"] += 1
        if bool(resource.get("stackable")) and int(resource.get("quantity") or 0) > 0:
            dims["recurrence"] += 1
        if _text(resource.get("status")) not in {"", "持有中"}:
            dims["stage_relevance"] += 1
        if name and name in plan_text:
            dims["stage_relevance"] += 2
            dims["mainline_leverage"] += 1
            reasons.append("当前规划或最近摘要里直接提到这个资源。")
        if selection_hits:
            dims["recurrence"] += min(selection_hits, 3)
            reasons.append("最近章节规划里反复被选中。")
        if _text(resource.get("quantity_mode")) == "entity":
            dims["irreplaceability"] += 1
        if int(resource.get("quantity") or 0) > 3:
            dims["recurrence"] += 1
        if _text(resource.get("resource_type")) in {"初始资源", "核心资源", "绑定资源"}:
            dims["binding_depth"] += 1
            dims["mainline_leverage"] += 1
    dims = {key: _clamp_dimension(value) for key, value in dims.items()}
    score = round(sum(dims[key] * DIMENSION_WEIGHTS[key] for key in DIMENSION_KEYS) * 20)
    if is_core_keyword:
        score = max(score, 92)
    if not reasons:
        reasons.append("当前更像阶段性或一次性物资。")
    return {"dimensions": dims, "score": score, "reasons": reasons}


def _relation_subject(card: dict[str, Any]) -> str:
    return _text(card.get("subject") or card.get("left"))


def _relation_target(card: dict[str, Any]) -> str:
    return _text(card.get("target") or card.get("right"))


def _evaluate_relation(name: str, card: dict[str, Any], *, protagonist_name: str, plan_text: str, story_bible: dict[str, Any]) -> dict[str, Any]:
    dims = _base_dimensions()
    reasons: list[str] = []
    subject = _relation_subject(card)
    target = _relation_target(card)
    involves_protagonist = protagonist_name in {subject, target}
    selection_hits = _selection_hits(story_bible, "relation", name)
    if involves_protagonist:
        dims["binding_depth"] += 3
        dims["irreplaceability"] += 2
        dims["mainline_leverage"] += 2
        reasons.append("这段关系直接牵着主角。")
    if _text(card.get("current_level") or card.get("level")) not in {"", "待观察"}:
        dims["mainline_leverage"] += 1
        dims["stage_relevance"] += 1
    if _text(card.get("recent_trigger") or card.get("change")):
        dims["stage_relevance"] += 1
        dims["recurrence"] += 1
    if subject and subject in plan_text or target and target in plan_text:
        dims["stage_relevance"] += 2
        reasons.append("当前规划或最近摘要里直接碰到了这段关系。")
    if selection_hits:
        dims["recurrence"] += min(selection_hits, 3)
    trust = int(card.get("trust") or 0)
    hostility = int(card.get("hostility") or 0)
    dependency = int(card.get("dependency") or 0)
    if abs(trust) + abs(hostility) + abs(dependency) > 0:
        dims["network_influence"] += 1
    dims = {key: _clamp_dimension(value) for key, value in dims.items()}
    score = round(sum(dims[key] * DIMENSION_WEIGHTS[key] for key in DIMENSION_KEYS) * 20)
    if not reasons:
        reasons.append("当前更像背景关系线。")
    return {"dimensions": dims, "score": score, "reasons": reasons}


def _evaluate_faction(name: str, card: dict[str, Any], *, protagonist_name: str, plan_text: str, story_bible: dict[str, Any]) -> dict[str, Any]:
    dims = _base_dimensions()
    reasons: list[str] = []
    relation_to_protagonist = _text(card.get("relation_to_protagonist"))
    selection_hits = _selection_hits(story_bible, "faction", name)
    if relation_to_protagonist in {"self", "主角阵营"} or name == "主角阵营":
        dims["binding_depth"] = 5
        dims["mainline_leverage"] = 4
        dims["irreplaceability"] = 4
        dims["stage_relevance"] = 4
        dims["network_influence"] = 3
        reasons.append("这是主角直接所在或直接绑定的势力。")
    else:
        if relation_to_protagonist and relation_to_protagonist not in {"", "待观察"}:
            dims["binding_depth"] += 2
            dims["mainline_leverage"] += 1
            reasons.append("势力和主角已有明确关系。")
        if _safe_list(card.get("key_characters")):
            dims["network_influence"] += 1
        if _safe_list(card.get("resource_control")):
            dims["mainline_leverage"] += 1
            dims["network_influence"] += 1
        if name and name in plan_text:
            dims["stage_relevance"] += 2
            dims["recurrence"] += 1
            reasons.append("当前规划或最近摘要里直接提到了这个势力。")
        if selection_hits:
            dims["recurrence"] += min(selection_hits, 3)
    dims = {key: _clamp_dimension(value) for key, value in dims.items()}
    score = round(sum(dims[key] * DIMENSION_WEIGHTS[key] for key in DIMENSION_KEYS) * 20)
    if not reasons:
        reasons.append("当前更像世界背景势力。")
    return {"dimensions": dims, "score": score, "reasons": reasons}


def _evaluate_one(entity_type: str, name: str, card: dict[str, Any], *, protagonist_name: str, plan_text: str, story_bible: dict[str, Any]) -> dict[str, Any]:
    if entity_type == "character":
        base = _evaluate_character(name, card, protagonist_name=protagonist_name, plan_text=plan_text, story_bible=story_bible)
    elif entity_type == "resource":
        base = _evaluate_resource(name, card, protagonist_name=protagonist_name, plan_text=plan_text, story_bible=story_bible)
    elif entity_type == "relation":
        base = _evaluate_relation(name, card, protagonist_name=protagonist_name, plan_text=plan_text, story_bible=story_bible)
    else:
        base = _evaluate_faction(name, card, protagonist_name=protagonist_name, plan_text=plan_text, story_bible=story_bible)
    score = int(base["score"])
    tier = _score_to_tier(score)
    return {
        "entity_type": entity_type,
        "name": name,
        "importance_score": score,
        "importance_tier": tier,
        "tracking_level": TIER_TO_TRACKING[tier],
        "appearance_priority": TIER_TO_APPEARANCE[tier],
        "importance_reason": "；".join(base["reasons"][:3]),
        "importance_dimensions": base["dimensions"],
        "rule_reasoning": list(base["reasons"][:4]),
        "ai_participated": False,
    }


def _ai_enabled() -> bool:
    return bool(getattr(settings, "importance_eval_ai_enabled", True)) and bool(current_api_key(AI_EVAL_STAGE))


def _raise_ai_required_error(*, entity_type: str, chapter_no: int, scope: str, detail_reason: str, retryable: bool) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"importance_evaluation 失败：AI 不可用，已停止生成。{detail_reason}",
        stage=AI_EVAL_STAGE,
        retryable=retryable,
        http_status=503 if retryable else 400,
        details={
            "entity_type": _text(entity_type),
            "chapter_no": int(chapter_no or 0),
            "scope": _text(scope),
            "reason": detail_reason,
        },
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _entity_last_selected_chapter(story_bible: dict[str, Any], entity_type: str, name: str) -> int:
    planner_state = story_bible.get("planner_state") or {}
    selected = planner_state.get("selected_entities_by_chapter") or {}
    bucket_key = {
        "character": "characters",
        "resource": "resources",
        "relation": "relations",
        "faction": "factions",
    }.get(entity_type, f"{entity_type}s")
    last_hit = 0
    for chapter_key, bucket in selected.items():
        if not isinstance(bucket, dict):
            continue
        if name not in (bucket.get(bucket_key) or []):
            continue
        try:
            last_hit = max(last_hit, int(chapter_key or 0))
        except Exception:
            continue
    return last_hit


def _entity_selection_streak(story_bible: dict[str, Any], entity_type: str, name: str, *, chapter_no: int) -> int:
    planner_state = story_bible.get("planner_state") or {}
    selected = planner_state.get("selected_entities_by_chapter") or {}
    bucket_key = {
        "character": "characters",
        "resource": "resources",
        "relation": "relations",
        "faction": "factions",
    }.get(entity_type, f"{entity_type}s")
    streak = 0
    current = max(int(chapter_no or 0) - 1, 0)
    while current > 0:
        bucket = selected.get(str(current)) or {}
        if not isinstance(bucket, dict) or name not in (bucket.get(bucket_key) or []):
            break
        streak += 1
        current -= 1
    return streak


def _entity_selection_total_hits(story_bible: dict[str, Any], entity_type: str, name: str) -> int:
    planner_state = story_bible.get("planner_state") or {}
    selected = planner_state.get("selected_entities_by_chapter") or {}
    bucket_key = {
        "character": "characters",
        "resource": "resources",
        "relation": "relations",
        "faction": "factions",
    }.get(entity_type, f"{entity_type}s")
    hits = 0
    for bucket in selected.values():
        if isinstance(bucket, dict) and name in (bucket.get(bucket_key) or []):
            hits += 1
    return hits


def _entity_activation_gap(story_bible: dict[str, Any], entity_type: str, name: str, *, chapter_no: int) -> int:
    last_selected = _entity_last_selected_chapter(story_bible, entity_type, name)
    if last_selected:
        return max(int(chapter_no or 0) - last_selected, 0)
    return max(int(chapter_no or 0) - 1, 0)


def _is_protagonist_bound(entity_type: str, name: str, card: dict[str, Any], protagonist_name: str) -> bool:
    if entity_type == "character":
        if name == protagonist_name:
            return True
        role_type = _text(card.get("role_type"))
        relation_level = _text(card.get("protagonist_relation_level") or card.get("attitude_to_protagonist"))
        return role_type in {"protagonist", "supporting", "partner"} or relation_level not in {"", "待观察"}
    if entity_type == "resource":
        return _text(card.get("owner")) == protagonist_name or _text(card.get("binding_target")) == protagonist_name
    if entity_type == "relation":
        return protagonist_name in {_relation_subject(card), _relation_target(card)}
    if entity_type == "faction":
        relation = _text(card.get("relation_to_protagonist"))
        return name == "主角阵营" or relation in {"self", "主角阵营", "盟友", "敌对", "盯上主角"}
    return False


def _importance_summary_fingerprint(entity_type: str, name: str, card: dict[str, Any], evaluation: dict[str, Any]) -> str:
    parts = [entity_type, name, _text(evaluation.get("importance_reason")), _text(evaluation.get("importance_tier"))]
    if entity_type == "character":
        parts.extend([
            _text(card.get("role_type")),
            _text(card.get("protagonist_relation_level") or card.get("attitude_to_protagonist")),
            _text(card.get("current_goal") or card.get("current_desire")),
            _text(card.get("status")),
        ])
    elif entity_type == "resource":
        parts.extend([
            _text(card.get("owner")),
            _text(card.get("resource_type") or card.get("resource_scope") or card.get("resource_kind")),
            _text(card.get("ability_summary") or card.get("core_functions") or card.get("ability_details")),
            _text(card.get("status")),
        ])
    elif entity_type == "relation":
        parts.extend([
            _relation_subject(card),
            _relation_target(card),
            _text(card.get("relation_type")),
            _text(card.get("current_level") or card.get("level")),
            _text(card.get("recent_trigger") or card.get("change")),
        ])
    else:
        parts.extend([
            _text(card.get("relation_to_protagonist")),
            _text(card.get("faction_goal") or card.get("current_goal") or card.get("positioning")),
            _text((card.get("key_characters") or [""])[0]),
            _text((card.get("resource_control") or [""])[0]),
        ])
    return "|".join(parts)


def _importance_summary_should_refresh(card: dict[str, Any], *, chapter_no: int) -> bool:
    last_eval = (card.get("last_importance_eval") or {}) if isinstance(card, dict) else {}
    last_chapter = _safe_int(last_eval.get("chapter_no"), 0)
    interval = max(int(getattr(settings, "importance_eval_summary_refresh_interval_chapters", 3) or 3), 1)
    return last_chapter <= 0 or max(int(chapter_no or 0) - last_chapter, 0) >= interval


def _should_run_ai_review(state: dict[str, Any], *, scope: str, chapter_no: int, allow_ai: bool) -> bool:
    if not allow_ai:
        return False
    if scope == "planning":
        interval = max(int(getattr(settings, "importance_eval_planning_ai_interval_chapters", 2) or 2), 1)
    elif scope == "post_chapter":
        interval = max(int(getattr(settings, "importance_eval_post_chapter_ai_interval_chapters", 3) or 3), 1)
    else:
        interval = 9999
    last_ai_map = (state.get("last_ai_eval_by_scope") or {}) if isinstance(state, dict) else {}
    last_ai_chapter = _safe_int(last_ai_map.get(scope), 0)
    return last_ai_chapter <= 0 or max(int(chapter_no or 0) - last_ai_chapter, 0) >= interval


def _build_importance_hint_summary(entity_type: str, name: str, card: dict[str, Any], evaluation: dict[str, Any], *, protagonist_name: str, chapter_no: int = 0) -> str:
    fingerprint = _importance_summary_fingerprint(entity_type, name, card, evaluation)
    cached_summary = _text(card.get("importance_hint_summary"))
    cached_fingerprint = _text(card.get("importance_hint_summary_fingerprint"))
    if cached_summary and cached_fingerprint == fingerprint and not _importance_summary_should_refresh(card, chapter_no=chapter_no):
        return cached_summary
    reason = _text(evaluation.get("importance_reason"))
    if entity_type == "character":
        parts = [
            f"人物：{name}",
            _text(card.get("role_type")),
            _text(card.get("protagonist_relation_level") or card.get("attitude_to_protagonist")),
            _text(card.get("current_goal") or card.get("current_desire")),
            _text(card.get("status")),
            reason,
        ]
    elif entity_type == "resource":
        parts = [
            f"资源：{name}",
            _text(card.get("owner")),
            _text(card.get("resource_type") or card.get("resource_scope") or card.get("resource_kind")),
            _text(card.get("ability_summary") or card.get("core_functions") or card.get("ability_details")),
            _text(card.get("status")),
            reason,
        ]
    elif entity_type == "relation":
        parts = [
            f"关系：{name}",
            _relation_subject(card),
            _relation_target(card),
            _text(card.get("relation_type")),
            _text(card.get("current_level") or card.get("level")),
            _text(card.get("recent_trigger") or card.get("change")),
            reason,
        ]
    else:
        parts = [
            f"势力：{name}",
            _text(card.get("relation_to_protagonist")),
            _text(card.get("faction_goal") or card.get("current_goal") or card.get("positioning")),
            _text((card.get("key_characters") or [""])[0]),
            _text((card.get("resource_control") or [""])[0]),
            reason,
        ]
    summary = clip_text("；".join(part for part in parts if part), 180)
    card["importance_hint_summary_fingerprint"] = fingerprint
    return summary


def _soft_rank_score(
    entity_type: str,
    name: str,
    card: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    protagonist_name: str,
    plan_text: str,
    story_bible: dict[str, Any],
    touched_names: set[str],
    chapter_no: int,
) -> tuple[float, list[str], float, list[str], float, list[str], dict[str, Any]]:
    base_score = float(_safe_int(evaluation.get("importance_score"), 0))
    mainline_score = base_score
    activation_score = base_score * 0.76
    exploration_score = max(8.0, base_score * 0.42)
    mainline_reasons: list[str] = ["规则分"]
    activation_reasons: list[str] = ["规则分"]
    exploration_reasons: list[str] = ["保留探索口"]

    if name in touched_names:
        mainline_score += 18.0
        activation_score += 10.0
        mainline_reasons.append("当前命中")
        activation_reasons.append("当前命中")
    if name and name in plan_text:
        mainline_score += 14.0
        activation_score += 8.0
        mainline_reasons.append("计划直提")
        activation_reasons.append("计划直提")

    selection_hits = _selection_hits(story_bible, entity_type, name)
    total_hits = _entity_selection_total_hits(story_bible, entity_type, name)
    if selection_hits:
        mainline_score += min(selection_hits, 4) * 5.0
        mainline_reasons.append("近章复现")
    if total_hits <= 1:
        exploration_score += 18.0
        exploration_reasons.append("低频潜力")
    elif total_hits <= 3:
        exploration_score += 8.0
        exploration_reasons.append("仍有新鲜度")

    if _is_protagonist_bound(entity_type, name, card, protagonist_name):
        mainline_score += 12.0
        activation_score += 4.0
        mainline_reasons.append("主角强绑定")
        activation_reasons.append("主角线")

    gap = _entity_activation_gap(story_bible, entity_type, name, chapter_no=chapter_no)
    streak = _entity_selection_streak(story_bible, entity_type, name, chapter_no=chapter_no)
    tier = _text(evaluation.get("importance_tier"))
    if tier in {"核心级", "重要级"} and gap >= 2:
        mainline_score += min(gap, 4) * 3.0
        mainline_reasons.append("应回场")
    if gap >= 2:
        activation_score += min(gap, 5) * 6.0
        activation_reasons.append("久未激活")
    elif gap == 1:
        activation_score += 4.0
        activation_reasons.append("可继续承接")
    if streak >= 2 and name != protagonist_name:
        penalty = min(streak - 1, 3) * float(getattr(settings, "importance_eval_continuous_presence_penalty", 8.0) or 8.0)
        mainline_score -= penalty
        activation_score -= penalty * 0.65
        exploration_score += min(12.0, penalty * 0.5)
        mainline_reasons.append("连续占位衰减")
        activation_reasons.append("连续占位衰减")
        exploration_reasons.append("给枝蔓留口")

    if entity_type == "resource" and _text(card.get("owner")) == protagonist_name:
        mainline_score += 6.0
        mainline_reasons.append("主角持有")
    if entity_type == "relation" and protagonist_name in {_relation_subject(card), _relation_target(card)}:
        mainline_score += 8.0
        activation_score += 5.0
        mainline_reasons.append("主角关系")
        activation_reasons.append("关系待推进")
    if entity_type == "faction" and _text(card.get("relation_to_protagonist")) in {"敌对", "盯上主角", "主角阵营", "self", "盟友"}:
        mainline_score += 6.0
        mainline_reasons.append("势力压迫/绑定")

    if entity_type == "character":
        role_type = _text(card.get("role_type"))
        if role_type not in {"protagonist", "supporting", "partner"}:
            exploration_score += 10.0
            exploration_reasons.append("边角角色可冒头")
        if _text(card.get("status")) in {"planned", "active"} and gap >= 1:
            activation_score += 4.0
    elif entity_type == "resource":
        if _text(card.get("status")) in {"planned", "持有中"} and _text(card.get("resource_type")) not in {"核心资源", "绑定资源"}:
            exploration_score += 6.0
            exploration_reasons.append("可做变化点")
    elif entity_type == "relation":
        if _text(card.get("current_level") or card.get("level")) in {"待观察", "试探", "互相试探"}:
            activation_score += 6.0
            exploration_score += 4.0
    elif entity_type == "faction":
        if _text(card.get("relation_to_protagonist")) in {"敌对", "盯上主角", "中立", "待观察"}:
            activation_score += 5.0

    meta = {
        "selection_hits": selection_hits,
        "total_hits": total_hits,
        "activation_gap": gap,
        "selection_streak": streak,
        "exploration_candidate": exploration_score >= max(40.0, base_score * 0.7) and name != protagonist_name,
    }
    return (
        round(mainline_score, 2),
        mainline_reasons[:5],
        round(activation_score, 2),
        activation_reasons[:5],
        round(exploration_score, 2),
        exploration_reasons[:5],
        meta,
    )



def _sort_evaluations_by_soft_rank(
    entity_type: str,
    evaluations: list[dict[str, Any]],
    *,
    container: dict[str, Any],
    protagonist_name: str,
    plan_text: str,
    story_bible: dict[str, Any],
    touched_names: set[str],
    chapter_no: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in evaluations:
        card = container.get(item["name"]) or {}
        mainline_score, mainline_reasons, activation_score, activation_reasons, exploration_score, exploration_reasons, meta = _soft_rank_score(
            entity_type,
            item["name"],
            card,
            item,
            protagonist_name=protagonist_name,
            plan_text=plan_text,
            story_bible=story_bible,
            touched_names=touched_names,
            chapter_no=chapter_no,
        )
        revised = dict(item)
        revised["importance_soft_rank_score"] = mainline_score
        revised["importance_soft_rank_reasons"] = mainline_reasons
        revised["importance_mainline_rank_score"] = mainline_score
        revised["importance_mainline_rank_reasons"] = mainline_reasons
        revised["importance_activation_rank_score"] = activation_score
        revised["importance_activation_rank_reasons"] = activation_reasons
        revised["importance_exploration_score"] = exploration_score
        revised["importance_exploration_reasons"] = exploration_reasons
        revised["importance_activation_gap"] = int(meta.get("activation_gap") or 0)
        revised["importance_selection_streak"] = int(meta.get("selection_streak") or 0)
        revised["importance_total_hits"] = int(meta.get("total_hits") or 0)
        revised["importance_recent_hits"] = int(meta.get("selection_hits") or 0)
        revised["importance_exploration_candidate"] = bool(meta.get("exploration_candidate"))
        revised["importance_hint_summary"] = _build_importance_hint_summary(entity_type, item["name"], card, revised, protagonist_name=protagonist_name, chapter_no=chapter_no)
        ranked.append(revised)
    ranked.sort(
        key=lambda item: (
            -float(item.get("importance_mainline_rank_score") or item.get("importance_soft_rank_score") or 0.0),
            -float(item.get("importance_activation_rank_score") or 0.0),
            -int(item.get("importance_score") or 0),
            item.get("name") or "",
        )
    )
    return ranked



def _summary_card(item: dict[str, Any], *, entity_type: str) -> dict[str, Any]:
    dims = item.get("importance_dimensions") or {}
    return {
        "name": item["name"],
        "entity_type": entity_type,
        "score": int(item.get("importance_score") or 0),
        "soft_rank_score": float(item.get("importance_soft_rank_score") or 0.0),
        "mainline_rank_score": float(item.get("importance_mainline_rank_score") or item.get("importance_soft_rank_score") or 0.0),
        "activation_rank_score": float(item.get("importance_activation_rank_score") or 0.0),
        "exploration_score": float(item.get("importance_exploration_score") or 0.0),
        "tier": item.get("importance_tier"),
        "tracking_level": item.get("tracking_level"),
        "appearance_priority": item.get("appearance_priority"),
        "binding_depth": _safe_int(dims.get("binding_depth"), 0),
        "stage_relevance": _safe_int(dims.get("stage_relevance"), 0),
        "recurrence": _safe_int(dims.get("recurrence"), 0),
        "activation_gap": _safe_int(item.get("importance_activation_gap"), 0),
        "selection_streak": _safe_int(item.get("importance_selection_streak"), 0),
        "summary": _text(item.get("importance_hint_summary")),
        "reason": _text(item.get("importance_reason")),
        "soft_rank_reasons": list(item.get("importance_soft_rank_reasons") or [])[:4],
    }


def _must_keep_summary(item: dict[str, Any], *, protagonist_name: str, plan_text: str) -> bool:
    name = _text(item.get("name"))
    if not name:
        return False
    if name == protagonist_name:
        return True
    if _text(item.get("importance_tier")) == "核心级":
        return True
    if int(item.get("importance_score") or 0) >= 86:
        return True
    return bool(name and name in plan_text)


def _summary_budget() -> tuple[int, int, int, int]:
    card_limit = max(int(getattr(settings, "importance_eval_summary_card_limit", 18) or 18), 6)
    char_budget = max(int(getattr(settings, "importance_eval_summary_budget_chars", 3600) or 3600), 1200)
    detail_limit = max(int(getattr(settings, "importance_eval_detail_review_limit", 3) or 3), 1)
    keep_limit = max(int(getattr(settings, "importance_eval_force_keep_limit", 4) or 4), 2)
    return card_limit, char_budget, detail_limit, keep_limit


def _pick_summary_candidates(
    evaluations: list[dict[str, Any]],
    *,
    protagonist_name: str,
    plan_text: str,
) -> list[dict[str, Any]]:
    if not evaluations:
        return []
    card_limit, char_budget, _detail_limit, keep_limit = _summary_budget()
    cards = [_summary_card(item, entity_type=_text(item.get("entity_type"))) for item in evaluations]
    total_chars = sum(len(_text(card.get("summary"))) + len(_text(card.get("reason"))) + 48 for card in cards)
    if len(cards) <= card_limit and total_chars <= char_budget:
        return cards
    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    must_keep = [card for card, item in zip(cards, evaluations) if _must_keep_summary(item, protagonist_name=protagonist_name, plan_text=plan_text)]
    for card in must_keep[:keep_limit]:
        selected.append(card)
        selected_names.add(card["name"])
    remaining_budget = char_budget - sum(len(_text(card.get("summary"))) + len(_text(card.get("reason"))) + 48 for card in selected)
    for card in cards:
        if card["name"] in selected_names:
            continue
        card_chars = len(_text(card.get("summary"))) + len(_text(card.get("reason"))) + 48
        if len(selected) >= card_limit:
            break
        if selected and card_chars > remaining_budget and len(selected) >= min(6, card_limit):
            continue
        selected.append(card)
        selected_names.add(card["name"])
        remaining_budget -= card_chars
        if remaining_budget <= 0 and len(selected) >= min(6, card_limit):
            break
    return selected or cards[:card_limit]


def _retryable_generation_error(exc: Exception) -> bool:
    return isinstance(exc, GenerationError) and bool(getattr(exc, "retryable", False))


def _sleep_ms(ms: int) -> None:
    if ms > 0:
        time.sleep(ms / 1000.0)


def _compact_summary_cards_for_attempt(summary_cards: list[dict[str, Any]], *, detail_limit: int, attempt_no: int) -> list[dict[str, Any]]:
    if attempt_no <= 1:
        return summary_cards
    shrink_by = (attempt_no - 1) * 4
    target_limit = max(detail_limit + 4, 8)
    target_limit = min(len(summary_cards), max(target_limit, len(summary_cards) - shrink_by))
    summary_limit = 72 if attempt_no == 2 else 52
    reason_limit = 40 if attempt_no == 2 else 28
    compacted: list[dict[str, Any]] = []
    for card in summary_cards[:target_limit]:
        compacted.append(
            {
                **card,
                "summary": _text(card.get("summary"))[:summary_limit],
                "reason": _text(card.get("reason"))[:reason_limit],
                "soft_rank_reasons": [_text(x)[:24] for x in (card.get("soft_rank_reasons") or [])[:2]],
            }
        )
    return compacted


def _compact_detail_candidates_for_attempt(candidates: list[dict[str, Any]], *, attempt_no: int) -> list[dict[str, Any]]:
    if attempt_no <= 1:
        return candidates
    compacted: list[dict[str, Any]] = []
    baseline_summary_limit = 84 if attempt_no == 2 else 60
    baseline_reason_limit = 56 if attempt_no == 2 else 40
    card_depth = 3 if attempt_no == 2 else 2
    card_items = 8 if attempt_no == 2 else 6
    card_text_limit = 56 if attempt_no == 2 else 40
    for item in candidates:
        baseline = dict(item.get("baseline") or {})
        baseline["summary"] = _text(baseline.get("summary"))[:baseline_summary_limit]
        baseline["reason"] = _text(baseline.get("reason"))[:baseline_reason_limit]
        baseline["dimensions"] = compact_data(baseline.get("dimensions") or {}, max_depth=2, max_items=5, text_limit=24)
        compacted.append(
            {
                "name": _text(item.get("name")),
                "baseline": baseline,
                "card": compact_data(item.get("card") or {}, max_depth=card_depth, max_items=card_items, text_limit=card_text_limit),
            }
        )
    return compacted


def _call_shortlist_payload_with_retry(
    *,
    entity_type: str,
    chapter_no: int,
    scope: str,
    protagonist_name: str,
    plan: dict[str, Any] | None,
    recent_summaries: list[dict[str, Any]] | None,
    summary_cards: list[dict[str, Any]],
    detail_limit: int,
) -> dict[str, Any]:
    attempts_total = max(int(getattr(settings, "importance_eval_shortlist_retry_attempts", 2) or 2), 1)
    retry_backoff_ms = max(int(getattr(settings, "importance_eval_shortlist_retry_backoff_ms", 500) or 500), 0)
    base_output_tokens = max(min(int(getattr(settings, "importance_eval_max_output_tokens", 360) or 360), 480), 180)
    base_timeout_seconds = max(min(int(getattr(settings, "importance_eval_timeout_seconds", 20) or 20), 26), 10)
    last_exc: Exception | None = None
    for attempt_no in range(1, attempts_total + 1):
        attempt_cards = _compact_summary_cards_for_attempt(summary_cards, detail_limit=detail_limit, attempt_no=attempt_no)
        attempt_output_tokens = max(min(base_output_tokens - (attempt_no - 1) * 60, 480), 180)
        attempt_timeout_seconds = max(min(base_timeout_seconds + (attempt_no - 1) * 2, 26), 10)
        try:
            return call_json_response(
                stage=AI_EVAL_STAGE,
                system_prompt=_ai_shortlist_system_prompt(),
                user_prompt=_ai_shortlist_user_prompt(
                    entity_type=entity_type,
                    chapter_no=chapter_no,
                    scope=scope,
                    protagonist_name=protagonist_name,
                    plan=plan,
                    recent_summaries=recent_summaries,
                    summary_cards=attempt_cards,
                    detail_limit=detail_limit,
                ),
                max_output_tokens=attempt_output_tokens,
                timeout_seconds=attempt_timeout_seconds,
            )
        except Exception as exc:
            last_exc = exc
            if attempt_no >= attempts_total or not _retryable_generation_error(exc):
                raise
            _sleep_ms(retry_backoff_ms * attempt_no)
    if last_exc is not None:
        raise last_exc
    return {}


def _call_detail_payload_with_retry(
    *,
    entity_type: str,
    chapter_no: int,
    scope: str,
    protagonist_name: str,
    plan: dict[str, Any] | None,
    recent_summaries: list[dict[str, Any]] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    attempts_total = max(int(getattr(settings, "importance_eval_detail_retry_attempts", 2) or 2), 1)
    retry_backoff_ms = max(int(getattr(settings, "importance_eval_detail_retry_backoff_ms", 500) or 500), 0)
    base_output_tokens = max(min(int(getattr(settings, "importance_eval_detail_max_output_tokens", 480) or 480), 720), 220)
    base_timeout_seconds = max(int(getattr(settings, "importance_eval_detail_timeout_seconds", 26) or 26), 10)
    last_exc: Exception | None = None
    for attempt_no in range(1, attempts_total + 1):
        attempt_candidates = _compact_detail_candidates_for_attempt(candidates, attempt_no=attempt_no)
        attempt_output_tokens = max(min(base_output_tokens - (attempt_no - 1) * 80, 720), 220)
        attempt_timeout_seconds = max(base_timeout_seconds + (attempt_no - 1) * 2, 10)
        try:
            return call_json_response(
                stage=AI_EVAL_STAGE,
                system_prompt=_ai_detail_system_prompt(),
                user_prompt=_ai_detail_user_prompt(
                    entity_type=entity_type,
                    chapter_no=chapter_no,
                    scope=scope,
                    protagonist_name=protagonist_name,
                    plan=plan,
                    recent_summaries=recent_summaries,
                    candidates=attempt_candidates,
                ),
                max_output_tokens=attempt_output_tokens,
                timeout_seconds=attempt_timeout_seconds,
            )
        except Exception as exc:
            last_exc = exc
            if attempt_no >= attempts_total or not _retryable_generation_error(exc):
                raise
            _sleep_ms(retry_backoff_ms * attempt_no)
    if last_exc is not None:
        raise last_exc
    return {}


def _ai_shortlist_system_prompt() -> str:
    return (
        "你是长篇连载小说里的重要性筛选器。"
        "你会先阅读摘要卡片，决定哪些对象值得进入细看名单。"
        "不要平均用力，也不要把所有对象都选上。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def _ai_shortlist_user_prompt(*, entity_type: str, chapter_no: int, scope: str, protagonist_name: str, plan: dict[str, Any] | None, recent_summaries: list[dict[str, Any]] | None, summary_cards: list[dict[str, Any]], detail_limit: int) -> str:
    compact_recent = []
    for item in (recent_summaries or [])[-3:]:
        if not isinstance(item, dict):
            continue
        compact_recent.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "event_summary": _text(item.get("event_summary"))[:100],
                "open_hooks": [_text(x)[:36] for x in (item.get("open_hooks") or [])[:3]],
            }
        )
    compact_plan = {
        "title": _text((plan or {}).get("title")),
        "goal": _text((plan or {}).get("goal")),
        "conflict": _text((plan or {}).get("conflict")),
        "main_scene": _text((plan or {}).get("main_scene")),
        "supporting_character_focus": _text((plan or {}).get("supporting_character_focus")),
        "ending_hook": _text((plan or {}).get("ending_hook")),
    }
    schema = {
        "shortlist": [
            {
                "name": "对象名",
                "confidence": 0.78,
                "reason": "为什么这个对象值得进一步细看，必须简短具体。",
            }
        ]
    }
    return f"""请先从当前{entity_type}摘要卡里筛出最值得细看的对象。

【当前章节】
第{chapter_no}章 / {scope}

【主角】
{protagonist_name}

【本章计划】
{compact_json(compact_plan, max_depth=2, max_items=8, text_limit=90)}

【最近摘要】
{compact_json(compact_recent, max_depth=2, max_items=6, text_limit=80)}

【全部摘要卡】
{compact_json(summary_cards, max_depth=3, max_items=max(len(summary_cards), 6), text_limit=90)}

要求：
1. 最多选 {detail_limit} 个。
2. 主角、主角强绑定资源、长期关键关系、直接压迫主角的大势力，应优先保留。
3. 不要把路人、一次性道具、纯背景关系都选进去。
4. 只输出 JSON。
5. schema 如下：
{schema}
"""


def _ai_detail_system_prompt() -> str:
    return (
        "你是长篇连载小说中的统一重要性评估器。"
        "你只对已经入围的少量对象做二次精判。"
        "只能温和修正已有规则评估，不要大起大落。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def _detail_card_payload(entity_type: str, card: dict[str, Any]) -> dict[str, Any]:
    if entity_type == "character":
        return compact_data(
            {
                "name": card.get("name"),
                "role_type": card.get("role_type"),
                "protagonist_relation_level": card.get("protagonist_relation_level"),
                "current_goal": card.get("current_goal"),
                "current_desire": card.get("current_desire"),
                "status": card.get("status"),
                "resource_refs": card.get("resource_refs"),
                "faction_refs": card.get("faction_refs"),
            },
            max_depth=2,
            max_items=8,
            text_limit=90,
        )
    if entity_type == "resource":
        return compact_data(
            {
                "name": card.get("name"),
                "owner": card.get("owner"),
                "resource_type": card.get("resource_type"),
                "resource_scope": card.get("resource_scope"),
                "ability_summary": card.get("ability_summary"),
                "core_functions": card.get("core_functions"),
                "status": card.get("status"),
                "quantity": card.get("quantity"),
                "quantity_mode": card.get("quantity_mode"),
            },
            max_depth=2,
            max_items=9,
            text_limit=90,
        )
    if entity_type == "relation":
        return compact_data(
            {
                "relation_id": card.get("relation_id"),
                "subject": card.get("subject") or card.get("left"),
                "target": card.get("target") or card.get("right"),
                "relation_type": card.get("relation_type"),
                "current_level": card.get("current_level") or card.get("level"),
                "recent_trigger": card.get("recent_trigger") or card.get("change"),
                "trust": card.get("trust"),
                "hostility": card.get("hostility"),
                "dependency": card.get("dependency"),
            },
            max_depth=2,
            max_items=9,
            text_limit=90,
        )
    return compact_data(
        {
            "name": card.get("name"),
            "relation_to_protagonist": card.get("relation_to_protagonist"),
            "faction_goal": card.get("faction_goal") or card.get("current_goal"),
            "positioning": card.get("positioning"),
            "key_characters": card.get("key_characters"),
            "resource_control": card.get("resource_control"),
            "status": card.get("status"),
        },
        max_depth=2,
        max_items=8,
        text_limit=90,
    )


def _ai_detail_user_prompt(*, entity_type: str, chapter_no: int, scope: str, protagonist_name: str, plan: dict[str, Any] | None, recent_summaries: list[dict[str, Any]] | None, candidates: list[dict[str, Any]]) -> str:
    compact_recent = []
    for item in (recent_summaries or [])[-3:]:
        if not isinstance(item, dict):
            continue
        compact_recent.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "event_summary": _text(item.get("event_summary"))[:100],
                "open_hooks": [_text(x)[:36] for x in (item.get("open_hooks") or [])[:3]],
            }
        )
    compact_plan = {
        "title": _text((plan or {}).get("title")),
        "goal": _text((plan or {}).get("goal")),
        "conflict": _text((plan or {}).get("conflict")),
        "main_scene": _text((plan or {}).get("main_scene")),
        "supporting_character_focus": _text((plan or {}).get("supporting_character_focus")),
        "ending_hook": _text((plan or {}).get("ending_hook")),
    }
    schema = {
        "evaluations": [
            {
                "name": "对象名",
                "suggested_tier": "核心级|重要级|阶段级|临时级|功能级",
                "tracking_level": "always_on|focused|standard|light|minimal",
                "appearance_priority": "高频跟踪|相关章节优先|当前阶段优先|短期需要时进入规划|按需",
                "confidence": 0.74,
                "reason": "为什么建议这么分级，必须简短具体。",
            }
        ]
    }
    return f"""请对入围的{entity_type}对象做二次精判。

【当前章节】
第{chapter_no}章 / {scope}

【主角】
{protagonist_name}

【本章计划】
{compact_json(compact_plan, max_depth=2, max_items=8, text_limit=90)}

【最近摘要】
{compact_json(compact_recent, max_depth=2, max_items=6, text_limit=80)}

【入围对象详情】
{compact_json(candidates, max_depth=4, max_items=max(len(candidates), 4), text_limit=90)}

要求：
1. 不要把一次性道具和路人强行抬成核心。
2. 主角、主角强绑定资源、长期关键关系与直接压迫主角的大势力，应更谨慎地维持高等级。
3. 这是在已有规则评估基础上的二次修正，只允许温和升降级。
4. 只输出 JSON。
5. schema 如下：
{schema}
"""


def _shortlist_names_from_payload(payload: dict[str, Any], evaluations: list[dict[str, Any]], detail_limit: int) -> list[str]:
    allowed = {item["name"] for item in evaluations}
    names: list[str] = []
    for item in (payload.get("shortlist") or []):
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if not name or name not in allowed or name in names:
            continue
        names.append(name)
        if len(names) >= detail_limit:
            break
    return names


def _detail_candidates(entity_type: str, evaluations: list[dict[str, Any]], *, container: dict[str, Any], shortlist_names: list[str]) -> list[dict[str, Any]]:
    eval_map = {item["name"]: item for item in evaluations}
    payload: list[dict[str, Any]] = []
    for name in shortlist_names:
        item = eval_map.get(name)
        card = container.get(name) or {}
        if not item or not isinstance(card, dict):
            continue
        payload.append(
            {
                "name": name,
                "baseline": {
                    "score": int(item.get("importance_score") or 0),
                    "tier": item.get("importance_tier"),
                    "tracking_level": item.get("tracking_level"),
                    "appearance_priority": item.get("appearance_priority"),
                    "dimensions": compact_data(item.get("importance_dimensions") or {}, max_depth=2, max_items=6, text_limit=40),
                    "reason": _text(item.get("importance_reason")),
                    "summary": _text(item.get("importance_hint_summary")),
                },
                "card": _detail_card_payload(entity_type, card),
            }
        )
    return payload


def _apply_ai_review(entity_type: str, evaluations: list[dict[str, Any]], *, container: dict[str, Any], chapter_no: int, scope: str, protagonist_name: str, plan: dict[str, Any] | None, recent_summaries: list[dict[str, Any]] | None, plan_text: str) -> tuple[list[dict[str, Any]], bool]:
    if not evaluations:
        return evaluations, False
    if not _ai_enabled():
        _raise_ai_required_error(
            entity_type=entity_type,
            chapter_no=chapter_no,
            scope=scope,
            detail_reason="当前没有可用的 AI 配置或密钥。",
            retryable=False,
        )
    _card_limit, _char_budget, detail_limit, _keep_limit = _summary_budget()
    summary_cards = _pick_summary_candidates(evaluations, protagonist_name=protagonist_name, plan_text=plan_text)
    shortlist_names: list[str]
    used_ai = False
    if len(summary_cards) <= detail_limit:
        shortlist_names = [card["name"] for card in summary_cards]
    else:
        try:
            shortlist_payload = _call_shortlist_payload_with_retry(
                entity_type=entity_type,
                chapter_no=chapter_no,
                scope=scope,
                protagonist_name=protagonist_name,
                plan=plan,
                recent_summaries=recent_summaries,
                summary_cards=summary_cards,
                detail_limit=detail_limit,
            )
            shortlist_names = _shortlist_names_from_payload(shortlist_payload, evaluations, detail_limit)
            used_ai = bool(shortlist_names)
        except GenerationError:
            raise
        except Exception as exc:
            _raise_ai_required_error(
                entity_type=entity_type,
                chapter_no=chapter_no,
                scope=scope,
                detail_reason=f"统一重要性摘要筛选失败：{exc}",
                retryable=True,
            )
    if not shortlist_names:
        shortlist_names = [item["name"] for item in evaluations[:detail_limit]]
    detail_candidates = _detail_candidates(entity_type, evaluations, container=container, shortlist_names=shortlist_names)
    if not detail_candidates:
        return evaluations, used_ai
    try:
        payload = _call_detail_payload_with_retry(
            entity_type=entity_type,
            chapter_no=chapter_no,
            scope=scope,
            protagonist_name=protagonist_name,
            plan=plan,
            recent_summaries=recent_summaries,
            candidates=detail_candidates,
        )
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            entity_type=entity_type,
            chapter_no=chapter_no,
            scope=scope,
            detail_reason=f"统一重要性二次精判失败：{exc}",
            retryable=True,
        )

    review_map = {
        _text(item.get("name")): item
        for item in (payload.get("evaluations") or [])
        if isinstance(item, dict) and _text(item.get("name"))
    }
    updated: list[dict[str, Any]] = []
    for item in evaluations:
        review = review_map.get(item["name"])
        if not review:
            updated.append(item)
            continue
        suggested_tier = _text(review.get("suggested_tier"), item["importance_tier"])
        if suggested_tier not in TIER_TO_ANCHOR_SCORE:
            suggested_tier = item["importance_tier"]
        confidence = review.get("confidence", 0.65)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.65
        confidence = max(0.35, min(confidence, 0.9))
        weight = 0.18 + (confidence - 0.35) * 0.28
        anchor = TIER_TO_ANCHOR_SCORE[suggested_tier]
        blended_score = round(item["importance_score"] * (1 - weight) + anchor * weight)
        final_tier = _score_to_tier(blended_score)
        if confidence >= 0.75:
            final_tier = suggested_tier
            blended_score = max(blended_score, TIER_TO_ANCHOR_SCORE[final_tier] - 4)
            blended_score = min(blended_score, TIER_TO_ANCHOR_SCORE[final_tier] + 6)
        revised = dict(item)
        revised.update(
            {
                "importance_score": int(blended_score),
                "importance_tier": final_tier,
                "tracking_level": _text(review.get("tracking_level"), TIER_TO_TRACKING[final_tier]),
                "appearance_priority": _text(review.get("appearance_priority"), TIER_TO_APPEARANCE[final_tier]),
                "ai_participated": True,
                "ai_reasoning": _text(review.get("reason")),
                "ai_confidence": confidence,
                "importance_reason": _text(review.get("reason"), item.get("importance_reason")) or item.get("importance_reason"),
            }
        )
        updated.append(revised)
        used_ai = True
    return updated, used_ai


def _write_entity_card(card: dict[str, Any], evaluation: dict[str, Any], *, entity_type: str, chapter_no: int = 0) -> None:
    card["importance_tier"] = evaluation["importance_tier"]
    card["importance_score"] = int(evaluation["importance_score"])
    card["importance_soft_rank_score"] = float(evaluation.get("importance_soft_rank_score") or 0.0)
    card["importance_soft_rank_reasons"] = list(evaluation.get("importance_soft_rank_reasons") or [])[:5]
    card["importance_mainline_rank_score"] = float(evaluation.get("importance_mainline_rank_score") or evaluation.get("importance_soft_rank_score") or 0.0)
    card["importance_mainline_rank_reasons"] = list(evaluation.get("importance_mainline_rank_reasons") or [])[:5]
    card["importance_activation_rank_score"] = float(evaluation.get("importance_activation_rank_score") or 0.0)
    card["importance_activation_rank_reasons"] = list(evaluation.get("importance_activation_rank_reasons") or [])[:5]
    card["importance_exploration_score"] = float(evaluation.get("importance_exploration_score") or 0.0)
    card["importance_exploration_reasons"] = list(evaluation.get("importance_exploration_reasons") or [])[:5]
    card["importance_activation_gap"] = int(evaluation.get("importance_activation_gap") or 0)
    card["importance_selection_streak"] = int(evaluation.get("importance_selection_streak") or 0)
    card["importance_exploration_candidate"] = bool(evaluation.get("importance_exploration_candidate"))
    card["tracking_level"] = evaluation["tracking_level"]
    card["appearance_priority"] = evaluation["appearance_priority"]
    card["importance_reason"] = evaluation.get("importance_reason") or ""
    card["importance_hint_summary"] = _text(evaluation.get("importance_hint_summary"))
    if card.get("importance_hint_summary_fingerprint") is None and evaluation.get("importance_hint_summary"):
        card["importance_hint_summary_fingerprint"] = _importance_summary_fingerprint(entity_type, _text(card.get("name")), card, evaluation)
    card["importance_dimensions"] = deepcopy(evaluation.get("importance_dimensions") or {})
    card["last_importance_eval"] = {
        "evaluated_at": _now_iso(),
        "chapter_no": int(chapter_no or 0),
        "tier": evaluation["importance_tier"],
        "score": int(evaluation["importance_score"]),
        "soft_rank_score": float(evaluation.get("importance_soft_rank_score") or 0.0),
        "mainline_rank_score": float(evaluation.get("importance_mainline_rank_score") or evaluation.get("importance_soft_rank_score") or 0.0),
        "activation_rank_score": float(evaluation.get("importance_activation_rank_score") or 0.0),
        "exploration_score": float(evaluation.get("importance_exploration_score") or 0.0),
        "soft_rank_reasons": list(evaluation.get("importance_soft_rank_reasons") or [])[:5],
        "hint_summary": _text(evaluation.get("importance_hint_summary")),
        "rule_reasoning": deepcopy(evaluation.get("rule_reasoning") or []),
        "ai_participated": bool(evaluation.get("ai_participated")),
        "ai_reasoning": _text(evaluation.get("ai_reasoning")),
    }
    if entity_type == "character":
        card["narrative_priority"] = int(evaluation["importance_score"])
    if entity_type == "resource":
        card["resource_tier"] = evaluation["importance_tier"]
        card.setdefault("binding_target", _text(card.get("owner")))
    if entity_type == "relation":
        card["relation_importance_tier"] = evaluation["importance_tier"]
    if entity_type == "faction":
        card["faction_importance_tier"] = evaluation["importance_tier"]


def _choose_names(container: dict[str, Any], names: list[str] | None) -> list[str]:
    if names is None:
        return [str(name) for name in container.keys()]
    return [name for name in names if name in container]


def evaluate_story_elements_importance(
    *,
    story_bible: dict[str, Any],
    protagonist_name: str,
    scope: str,
    chapter_no: int = 0,
    plan: dict[str, Any] | None = None,
    recent_summaries: list[dict[str, Any]] | None = None,
    touched_entities: dict[str, list[str]] | None = None,
    allow_ai: bool = True,
) -> dict[str, Any]:
    state = ensure_importance_state(story_bible)
    domains = story_bible.setdefault("story_domains", {})
    plan_text = _plan_text(plan, recent_summaries)
    evaluation_bundle: dict[str, dict[str, Any]] = {}
    used_ai_any = False
    run_ai_review = _should_run_ai_review(state, scope=scope, chapter_no=int(chapter_no or 0), allow_ai=allow_ai)

    for entity_type, domain_key in [("character", "characters"), ("resource", "resources"), ("relation", "relations"), ("faction", "factions")]:
        container = domains.setdefault(domain_key, {})
        names = _choose_names(container, (touched_entities or {}).get(entity_type))
        evaluations: list[dict[str, Any]] = []
        for name in names:
            card = container.get(name)
            if not isinstance(card, dict):
                continue
            evaluations.append(
                _evaluate_one(
                    entity_type,
                    name,
                    card,
                    protagonist_name=protagonist_name,
                    plan_text=plan_text,
                    story_bible=story_bible,
                )
            )
        evaluations = _sort_evaluations_by_soft_rank(
            entity_type,
            evaluations,
            container=container,
            protagonist_name=protagonist_name,
            plan_text=plan_text,
            story_bible=story_bible,
            touched_names=set((touched_entities or {}).get(entity_type) or []),
            chapter_no=int(chapter_no or 0),
        )
        if run_ai_review:
            evaluations, used_ai = _apply_ai_review(
                entity_type,
                evaluations,
                container=container,
                chapter_no=chapter_no,
                scope=scope,
                protagonist_name=protagonist_name,
                plan=plan,
                recent_summaries=recent_summaries,
                plan_text=plan_text,
            )
            used_ai_any = used_ai_any or used_ai
        evaluations = _sort_evaluations_by_soft_rank(
            entity_type,
            evaluations,
            container=container,
            protagonist_name=protagonist_name,
            plan_text=plan_text,
            story_bible=story_bible,
            touched_names=set((touched_entities or {}).get(entity_type) or []),
            chapter_no=int(chapter_no or 0),
        )
        entity_result: dict[str, Any] = {}
        for item in evaluations:
            card = container.get(item["name"])
            if not isinstance(card, dict):
                continue
            _write_entity_card(card, item, entity_type=entity_type, chapter_no=int(chapter_no or 0))
            state["entity_index"].setdefault(entity_type, {})[item["name"]] = {
                "importance_tier": item["importance_tier"],
                "importance_score": int(item["importance_score"]),
                "importance_soft_rank_score": float(item.get("importance_soft_rank_score") or 0.0),
                "importance_mainline_rank_score": float(item.get("importance_mainline_rank_score") or item.get("importance_soft_rank_score") or 0.0),
                "importance_activation_rank_score": float(item.get("importance_activation_rank_score") or 0.0),
                "importance_exploration_score": float(item.get("importance_exploration_score") or 0.0),
                "soft_rank_reasons": list(item.get("importance_soft_rank_reasons") or [])[:5],
                "tracking_level": item["tracking_level"],
                "appearance_priority": item["appearance_priority"],
                "reason": item.get("importance_reason") or "",
                "hint_summary": _text(item.get("importance_hint_summary")),
                "activation_gap": int(item.get("importance_activation_gap") or 0),
                "selection_streak": int(item.get("importance_selection_streak") or 0),
                "exploration_candidate": bool(item.get("importance_exploration_candidate")),
                "ai_participated": bool(item.get("ai_participated")),
            }
            entity_result[item["name"]] = {
                "tier": item["importance_tier"],
                "score": int(item["importance_score"]),
                "soft_rank_score": float(item.get("importance_soft_rank_score") or 0.0),
                "mainline_rank_score": float(item.get("importance_mainline_rank_score") or item.get("importance_soft_rank_score") or 0.0),
                "activation_rank_score": float(item.get("importance_activation_rank_score") or 0.0),
                "exploration_score": float(item.get("importance_exploration_score") or 0.0),
                "tracking_level": item["tracking_level"],
                "appearance_priority": item["appearance_priority"],
                "reason": item.get("importance_reason") or "",
                "hint_summary": _text(item.get("importance_hint_summary")),
                "activation_gap": int(item.get("importance_activation_gap") or 0),
                "selection_streak": int(item.get("importance_selection_streak") or 0),
                "exploration_candidate": bool(item.get("importance_exploration_candidate")),
                "ai_participated": bool(item.get("ai_participated")),
            }
        evaluation_bundle[entity_type] = entity_result

    state["last_scope"] = scope
    state["last_evaluated_chapter"] = int(chapter_no or 0)
    state["last_run_used_ai"] = bool(used_ai_any)
    if used_ai_any:
        ai_map = state.setdefault("last_ai_eval_by_scope", {})
        ai_map[scope] = int(chapter_no or 0)
    history = state.setdefault("evaluation_history", [])
    history.append(
        {
            "evaluated_at": _now_iso(),
            "scope": scope,
            "chapter_no": int(chapter_no or 0),
            "used_ai": bool(used_ai_any),
            "entity_counts": {key: len(value) for key, value in evaluation_bundle.items()},
        }
    )
    state["evaluation_history"] = history[-20:]
    return {
        "scope": scope,
        "chapter_no": int(chapter_no or 0),
        "used_ai": bool(used_ai_any),
        "evaluations": evaluation_bundle,
    }


def sort_entities_by_importance(container: dict[str, Any], names: list[str] | None, *, mode: str = "mainline") -> list[str]:
    values = [name for name in (names or []) if name in container]
    score_key = {
        "mainline": "importance_mainline_rank_score",
        "activation": "importance_activation_rank_score",
        "exploration": "importance_exploration_score",
        "combined": "importance_soft_rank_score",
    }.get(mode, "importance_soft_rank_score")
    return sorted(
        values,
        key=lambda item: (
            -float((container.get(item) or {}).get(score_key, 0.0) or 0.0),
            -float((container.get(item) or {}).get("importance_soft_rank_score", 0.0) or 0.0),
            -int((container.get(item) or {}).get("importance_score", 0) or 0),
            item,
        ),
    )
