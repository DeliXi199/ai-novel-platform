from __future__ import annotations

from copy import deepcopy
from typing import Any


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


CHARACTER_TIER_WEIGHT = {
    "核心主角": 100,
    "核心配角": 92,
    "核心级": 92,
    "重要配角": 82,
    "重要级": 78,
    "阶段级": 62,
    "临时级": 44,
    "功能配角": 28,
    "功能级": 24,
}

RELATION_TIER_WEIGHT = {
    "核心级": 92,
    "重要级": 78,
    "阶段级": 62,
    "临时级": 44,
    "功能级": 24,
    "核心配角": 84,
    "重要配角": 76,
}


DEPTH_KEYWORDS = {
    "deep": ["绑定", "信任", "共患难", "生死", "裂痕", "决裂", "盟友", "师徒", "家人", "宿敌"],
    "medium": ["合作", "试探", "利用", "竞争", "同路", "交易", "观察", "对照", "敌意"],
}

PUSH_KEYWORDS = {
    "conflict": ["敌", "裂", "压迫", "对立", "竞争", "决裂", "盯防"],
    "cooperate": ["合作", "信任", "盟友", "同路", "互助", "共患难"],
    "tension": ["试探", "利用", "交易", "观察", "摇摆", "未稳"],
}


def _planner_last_hit(story_bible: dict[str, Any], entity_type: str, name: str) -> int:
    planner_state = story_bible.get("planner_state") or {}
    selected = planner_state.get("selected_entities_by_chapter") or {}
    best = 0
    for key, bucket in selected.items():
        if not isinstance(bucket, dict):
            continue
        values = []
        if entity_type == "character":
            values = bucket.get("characters") or []
        elif entity_type == "relation":
            values = bucket.get("relations") or []
        if name in values:
            best = max(best, _int(key, 0))
    return best


def _appearance_window(card: dict[str, Any]) -> tuple[int, int]:
    freq = _text(card.get("appearance_frequency"))
    tier = _text(card.get("importance_tier"))
    priority = _text(card.get("appearance_priority"))
    if freq == "高频" or "核心" in tier or priority == "高频跟踪":
        return 1, 2
    if freq == "低频":
        return 4, 7
    if "阶段" in tier:
        return 2, 4
    return 2, 5


def _relation_window(card: dict[str, Any]) -> tuple[int, int]:
    tier = _text(card.get("relation_importance_tier") or card.get("importance_tier"))
    if "核心" in tier:
        return 1, 3
    if "重要" in tier:
        return 2, 4
    if "低频" in _text(card.get("appearance_frequency")):
        return 4, 7
    return 3, 6


def _infer_interaction_depth(card: dict[str, Any]) -> str:
    blob = " ".join(
        [
            _text(card.get("level") or card.get("current_level")),
            _text(card.get("status")),
            _text(card.get("relation_type")),
            _text(card.get("recent_trigger")),
        ]
    )
    if any(token in blob for token in DEPTH_KEYWORDS["deep"]):
        return "深互动"
    if any(token in blob for token in DEPTH_KEYWORDS["medium"]):
        return "中互动"
    return "轻互动"


def _infer_push_direction(card: dict[str, Any]) -> str:
    blob = " ".join(
        [
            _text(card.get("level") or card.get("current_level")),
            _text(card.get("status")),
            _text(card.get("relation_type")),
            _text(card.get("recent_trigger")),
        ]
    )
    if any(token in blob for token in PUSH_KEYWORDS["conflict"]):
        return "冲突推进"
    if any(token in blob for token in PUSH_KEYWORDS["cooperate"]):
        return "合作推进"
    if any(token in blob for token in PUSH_KEYWORDS["tension"]):
        return "拉扯推进"
    return "轻推一格"


def _character_priority_row(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
    chapter_no: int,
    focus_name: str,
    name: str,
    card: dict[str, Any],
    plan_text: str,
) -> dict[str, Any]:
    tier = _text(card.get("importance_tier"), "功能配角")
    score = max(_int(card.get("importance_score"), 0), CHARACTER_TIER_WEIGHT.get(tier, 52))
    last_seen = max(_int(card.get("last_onstage_chapter"), 0), _planner_last_hit(story_bible, "character", name))
    ideal_gap, overdue_gap = _appearance_window(card)
    gap = chapter_no - last_seen if last_seen > 0 else chapter_no
    due_status = "备用"
    reasons: list[str] = []
    if name == protagonist_name:
        score = max(score, 100)
        due_status = "本章默认在场"
        reasons.append("主角")
    else:
        if focus_name and name == focus_name:
            score += 34
            due_status = "本章焦点"
            reasons.append("焦点")
        elif last_seen <= 0:
            if card.get("core_cast_slot_id"):
                score += 18
                due_status = "到窗可登场"
                reasons.append("核心配角色位")
            else:
                due_status = "待机会"
        elif gap >= overdue_gap:
            score += 26
            due_status = "该回场"
            reasons.append("久未出场")
        elif gap >= ideal_gap:
            score += 12
            due_status = "可推进"
            reasons.append("适合推进")
        else:
            score -= 4
            due_status = "刚出场过"
        if "核心" in tier:
            score += 10
            reasons.append("核心")
        elif "重要" in tier:
            score += 6
            reasons.append("重要")
        relation_level = _text(card.get("protagonist_relation_level") or card.get("attitude_to_protagonist"))
        if relation_level and relation_level not in {"待观察", ""}:
            score += 4
            reasons.append("关系已建立")
        if name and name in plan_text:
            score += 16
            reasons.append("规划点名")
        if _text(card.get("appearance_frequency")) == "高频":
            score += 6
        if _text(card.get("appearance_frequency")) == "低频" and gap < ideal_gap:
            score -= 6
    row = {
        "name": name,
        "importance_tier": tier,
        "appearance_frequency": _text(card.get("appearance_frequency"), "中频"),
        "due_status": due_status,
        "last_onstage_chapter": last_seen,
        "chapters_since_last_appearance": max(gap, 0),
        "schedule_score": round(float(score), 2),
        "schedule_reason_tags": reasons[:4],
        "core_cast_slot_id": _text(card.get("core_cast_slot_id")),
        "interaction_hint": "深一点" if score >= 86 else ("推进一下" if score >= 66 else "轻触即可"),
    }
    card["appearance_due_status"] = due_status
    card["chapters_since_last_appearance"] = max(gap, 0)
    card["appearance_schedule_score"] = row["schedule_score"]
    card["appearance_schedule_grade"] = row["interaction_hint"]
    return row


def _relation_priority_row(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
    chapter_no: int,
    focus_name: str,
    relation_id: str,
    card: dict[str, Any],
    plan_text: str,
) -> dict[str, Any]:
    tier = _text(card.get("relation_importance_tier") or card.get("importance_tier"), "阶段级")
    score = max(_int(card.get("importance_score"), 0), RELATION_TIER_WEIGHT.get(tier, 58))
    subject = _text(card.get("subject") or card.get("left"))
    target = _text(card.get("target") or card.get("right"))
    last_touched = max(_int(card.get("last_touched_chapter"), 0), _planner_last_hit(story_bible, "relation", relation_id))
    ideal_gap, overdue_gap = _relation_window(card)
    gap = chapter_no - last_touched if last_touched > 0 else chapter_no
    depth = _infer_interaction_depth(card)
    push_direction = _infer_push_direction(card)
    due_status = "备用"
    reasons: list[str] = []
    pair_blob = f"{subject} {target} {relation_id}"
    if protagonist_name and protagonist_name in {subject, target}:
        score += 12
        reasons.append("主角关系")
    if focus_name and focus_name in {subject, target}:
        score += 18
        reasons.append("焦点关系")
        due_status = "本章应动"
    elif last_touched <= 0:
        if pair_blob and any(token and token in plan_text for token in [subject, target]):
            score += 10
            due_status = "可建立"
            reasons.append("规划触发")
        else:
            due_status = "待时机"
    elif gap >= overdue_gap:
        score += 18
        due_status = "该推进"
        reasons.append("久未推进")
    elif gap >= ideal_gap:
        score += 8
        due_status = "可推进"
        reasons.append("轮到推进")
    else:
        due_status = "轻触或略过"
        score -= 2
    if depth == "深互动":
        score += 10
        reasons.append("深互动")
    elif depth == "中互动":
        score += 5
    if pair_blob and pair_blob.strip() and any(token and token in plan_text for token in [subject, target, _text(card.get("relation_type"))]):
        score += 12
        reasons.append("规划命中")
    row = {
        "relation_id": relation_id,
        "subject": subject,
        "target": target,
        "relation_type": _text(card.get("relation_type") or card.get("change")),
        "level": _text(card.get("level") or card.get("current_level")),
        "status": _text(card.get("status") or card.get("direction")),
        "interaction_depth": depth,
        "push_direction": push_direction,
        "due_status": due_status,
        "last_touched_chapter": last_touched,
        "chapters_since_last_touch": max(gap, 0),
        "schedule_score": round(float(score), 2),
        "schedule_reason_tags": reasons[:4],
    }
    card["interaction_depth"] = depth
    card["relation_push_direction"] = push_direction
    card["relation_due_status"] = due_status
    card["relation_schedule_score"] = row["schedule_score"]
    return row


def build_character_relation_schedule_guidance(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
    chapter_no: int,
    focus_name: str = "",
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    domains = story_bible.setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    relations = domains.setdefault("relations", {})
    plan_text = " ".join(
        _text((plan or {}).get(key))
        for key in [
            "title",
            "goal",
            "conflict",
            "main_scene",
            "event_type",
            "progress_kind",
            "supporting_character_focus",
            "supporting_character_note",
            "ending_hook",
        ]
        if _text((plan or {}).get(key))
    )
    character_rows: list[dict[str, Any]] = []
    for name, card in characters.items():
        if not isinstance(card, dict):
            continue
        character_rows.append(
            _character_priority_row(
                story_bible,
                protagonist_name=protagonist_name,
                chapter_no=chapter_no,
                focus_name=_text(focus_name),
                name=name,
                card=card,
                plan_text=plan_text,
            )
        )
    character_rows.sort(key=lambda item: (-float(item.get("schedule_score") or 0), item.get("name") != protagonist_name, item.get("name") or ""))

    relation_rows: list[dict[str, Any]] = []
    for relation_id, card in relations.items():
        if not isinstance(card, dict):
            continue
        relation_rows.append(
            _relation_priority_row(
                story_bible,
                protagonist_name=protagonist_name,
                chapter_no=chapter_no,
                focus_name=_text(focus_name),
                relation_id=relation_id,
                card=card,
                plan_text=plan_text,
            )
        )
    relation_rows.sort(key=lambda item: (-float(item.get("schedule_score") or 0), item.get("relation_id") or ""))

    guidance = {
        "soft_rule": "只做分级与关系的软调度：更该回场/更该推进的排前，不硬删后面的候选。",
        "appearance_schedule": {
            "priority_characters": character_rows[:6],
            "due_characters": [item["name"] for item in character_rows if item.get("due_status") in {"本章焦点", "该回场", "可推进", "到窗可登场"}][:5],
            "resting_characters": [item["name"] for item in character_rows if item.get("due_status") in {"刚出场过", "备用", "待机会"}][:5],
            "summary": "高频/核心人物更该持续回场；低频人物尽量在关键节点推进，别刚亮相就连续刷脸。",
        },
        "relationship_schedule": {
            "priority_relations": relation_rows[:6],
            "due_relations": [item["relation_id"] for item in relation_rows if item.get("due_status") in {"本章应动", "该推进", "可推进", "可建立"}][:5],
            "summary": "深互动关系要给具体来回，轻互动关系只推一格，不必一章里把所有关系都写满。",
        },
    }
    story_bible["character_relation_schedule"] = {
        "last_chapter_no": int(chapter_no or 0),
        "appearance_schedule": deepcopy(guidance["appearance_schedule"]),
        "relationship_schedule": deepcopy(guidance["relationship_schedule"]),
    }
    return guidance


def sort_character_names_by_schedule(
    container: dict[str, Any],
    names: list[str] | None,
    *,
    guidance: dict[str, Any] | None,
    protagonist_name: str,
) -> list[str]:
    values = [name for name in (names or []) if name in container]
    if not values:
        return []
    priority_map = {
        _text(item.get("name")): float(item.get("schedule_score") or 0)
        for item in ((guidance or {}).get("appearance_schedule") or {}).get("priority_characters", [])
        if isinstance(item, dict)
    }
    return sorted(
        values,
        key=lambda name: (
            0 if name == protagonist_name else 1,
            -priority_map.get(name, 0.0),
            -_int((container.get(name) or {}).get("importance_score"), 0),
            name,
        ),
    )


def sort_relation_names_by_schedule(
    container: dict[str, Any],
    names: list[str] | None,
    *,
    guidance: dict[str, Any] | None,
) -> list[str]:
    values = [name for name in (names or []) if name in container]
    if not values:
        return []
    priority_map = {
        _text(item.get("relation_id")): float(item.get("schedule_score") or 0)
        for item in ((guidance or {}).get("relationship_schedule") or {}).get("priority_relations", [])
        if isinstance(item, dict)
    }
    return sorted(
        values,
        key=lambda name: (
            -priority_map.get(name, 0.0),
            -_int((container.get(name) or {}).get("importance_score"), 0),
            name,
        ),
    )


def update_character_relation_schedule_after_chapter(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    onstage_characters: list[str] | None,
    focus_name: str = "",
    plan: dict[str, Any] | None = None,
) -> None:
    domains = story_bible.setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    relations = domains.setdefault("relations", {})
    seen = [_text(name) for name in (onstage_characters or []) if _text(name)]
    seen_set = set(seen)
    for name in seen:
        card = characters.get(name)
        if not isinstance(card, dict):
            continue
        card["last_onstage_chapter"] = int(chapter_no or 0)
        history = [_int(item, 0) for item in (card.get("appearance_history") or []) if _int(item, 0) > 0]
        if int(chapter_no or 0) not in history:
            history.append(int(chapter_no or 0))
        card["appearance_history"] = history[-12:]
        card["recent_focus_flag"] = bool(focus_name and name == focus_name)

    explicit_relation_ids: set[str] = set()
    for item in (plan or {}).get("new_relations") or []:
        if isinstance(item, dict):
            subject = _text(item.get("subject"))
            target = _text(item.get("target"))
            if subject and target:
                explicit_relation_ids.add(f"{subject}::{target}")

    for relation_id, card in relations.items():
        if not isinstance(card, dict):
            continue
        subject = _text(card.get("subject") or card.get("left"))
        target = _text(card.get("target") or card.get("right"))
        touched = relation_id in explicit_relation_ids or (subject in seen_set and target in seen_set and subject and target)
        if not touched:
            continue
        card["last_touched_chapter"] = int(chapter_no or 0)
        history = [_int(item, 0) for item in (card.get("touch_history") or []) if _int(item, 0) > 0]
        if int(chapter_no or 0) not in history:
            history.append(int(chapter_no or 0))
        card["touch_history"] = history[-12:]
