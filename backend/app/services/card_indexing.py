from __future__ import annotations

from typing import Any

CARD_ID_PREFIX = {
    "character": "C",
    "resource": "R",
    "faction": "F",
    "relation": "REL",
}


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def _unique_texts(values: list[Any] | None, *, limit: int, item_limit: int = 16) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values or []:
        text = _truncate_text(value, item_limit)
        norm = "".join(text.split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def ensure_entity_registry_shape(registry: dict[str, Any] | None) -> dict[str, Any]:
    payload = registry if isinstance(registry, dict) else {}
    payload.setdefault("by_type", {})
    payload.setdefault("card_ids", {})
    payload.setdefault("next_seq", {})
    for entity_type in ["character", "resource", "relation", "faction"]:
        payload["by_type"].setdefault(entity_type, [])
        payload["card_ids"].setdefault(entity_type, {})
        try:
            next_value = int(payload["next_seq"].get(entity_type, 1) or 1)
        except Exception:
            next_value = 1
        payload["next_seq"][entity_type] = max(next_value, 1)
    payload.setdefault("last_rebuilt_at", None)
    return payload


def _sync_next_seq_for_existing_id(registry: dict[str, Any], *, entity_type: str, card_id: str) -> None:
    prefix = CARD_ID_PREFIX.get(entity_type, "X")
    if not str(card_id or "").startswith(prefix):
        return
    suffix = str(card_id)[len(prefix) :]
    if not suffix.isdigit():
        return
    current = int(registry["next_seq"].get(entity_type, 1) or 1)
    registry["next_seq"][entity_type] = max(current, int(suffix) + 1)


def ensure_card_id(story_bible: dict[str, Any], *, entity_type: str, entity_name: str, card: dict[str, Any] | None) -> str | None:
    clean_name = _truncate_text(entity_name, 48)
    if not clean_name:
        return None
    registry = ensure_entity_registry_shape(story_bible.setdefault("entity_registry", {}))
    card_ids = registry["card_ids"].setdefault(entity_type, {})
    existing = _truncate_text((card or {}).get("card_id"), 16)
    if existing:
        card_ids[clean_name] = existing
        _sync_next_seq_for_existing_id(registry, entity_type=entity_type, card_id=existing)
        return existing
    mapped = _truncate_text(card_ids.get(clean_name), 16)
    if mapped:
        if isinstance(card, dict):
            card["card_id"] = mapped
        _sync_next_seq_for_existing_id(registry, entity_type=entity_type, card_id=mapped)
        return mapped

    used_ids: set[str] = set()
    for mapping in registry.get("card_ids", {}).values():
        if isinstance(mapping, dict):
            used_ids.update(str(value or "").strip() for value in mapping.values() if str(value or "").strip())
    prefix = CARD_ID_PREFIX.get(entity_type, "X")
    next_seq = int(registry["next_seq"].get(entity_type, 1) or 1)
    candidate = ""
    while not candidate:
        probe = f"{prefix}{next_seq:03d}"
        next_seq += 1
        if probe not in used_ids:
            candidate = probe
    registry["next_seq"][entity_type] = next_seq
    card_ids[clean_name] = candidate
    if isinstance(card, dict):
        card["card_id"] = candidate
    return candidate


def _summary_for_character(card: dict[str, Any]) -> str:
    parts = [
        _truncate_text(card.get("role_type"), 12),
        _truncate_text(card.get("entry_phase"), 8),
        _truncate_text(card.get("relation_level"), 16),
        _truncate_text(card.get("current_goal"), 28),
    ]
    parts = [item for item in parts if item]
    if not parts:
        return "当前章可能需要出场的角色。"
    return _truncate_text("，".join(parts), 48)


def _summary_for_resource(card: dict[str, Any]) -> str:
    pieces = [
        _truncate_text(card.get("resource_type") or card.get("resource_kind"), 12),
        _truncate_text(card.get("ability_summary") or card.get("narrative_role"), 28),
        _truncate_text(card.get("status"), 14),
    ]
    pieces = [item for item in pieces if item]
    if not pieces:
        return "当前章可能会用到的资源。"
    return _truncate_text("，".join(pieces), 48)


def _summary_for_faction(card: dict[str, Any]) -> str:
    pieces = [
        _truncate_text(card.get("faction_type") or card.get("faction_level"), 12),
        _truncate_text(card.get("relation_to_protagonist"), 16),
        _truncate_text(card.get("core_goal"), 24),
    ]
    pieces = [item for item in pieces if item]
    if not pieces:
        return "当前章可能会牵动的势力。"
    return _truncate_text("，".join(pieces), 48)


def _summary_for_relation(card: dict[str, Any]) -> str:
    pieces = [
        _truncate_text(card.get("relation_type"), 16),
        _truncate_text(card.get("level"), 14),
        _truncate_text(card.get("status"), 18),
    ]
    pieces = [item for item in pieces if item]
    if not pieces:
        return "当前章可能变化的一条关系。"
    return _truncate_text("，".join(pieces), 48)


def build_card_index_entry(entity_type: str, compact_card: dict[str, Any] | None) -> dict[str, Any]:
    card = compact_card or {}
    card_id = _truncate_text(card.get("card_id"), 16)
    if not card_id:
        return {}
    if entity_type == "character":
        title = _truncate_text(card.get("name"), 20)
        tags = _unique_texts(
            [card.get("role_type"), card.get("importance_tier"), card.get("relation_level"), card.get("entry_phase"), card.get("appearance_frequency"), card.get("appearance_due_status"), card.get("small_tell"), *(card.get("resource_refs") or [])[:1]],
            limit=4,
            item_limit=12,
        )
        summary = _summary_for_character(card)
        status = _truncate_text(card.get("tracking_level") or card.get("relation_level"), 16)
        key_name = title
    elif entity_type == "resource":
        title = _truncate_text(card.get("display_name") or card.get("name"), 24)
        tags = _unique_texts(
            [card.get("resource_type"), card.get("rarity"), card.get("status"), card.get("resource_scope"), *(card.get("core_functions") or [])[:1]],
            limit=4,
            item_limit=12,
        )
        summary = _summary_for_resource(card)
        status = _truncate_text(card.get("status") or card.get("unlock_level"), 16)
        key_name = _truncate_text(card.get("name") or title, 24)
    elif entity_type == "faction":
        title = _truncate_text(card.get("name"), 24)
        tags = _unique_texts(
            [card.get("faction_type"), card.get("relation_to_protagonist"), card.get("importance_tier"), *(card.get("resource_control") or [])[:1]],
            limit=4,
            item_limit=12,
        )
        summary = _summary_for_faction(card)
        status = _truncate_text(card.get("relation_to_protagonist") or card.get("importance_tier"), 16)
        key_name = title
    else:
        subject = _truncate_text(card.get("subject"), 20)
        target = _truncate_text(card.get("target"), 20)
        title = _truncate_text(f"{subject}-{target}" if subject and target else card.get("card_id"), 30)
        tags = _unique_texts([card.get("relation_type"), card.get("level"), card.get("status"), card.get("interaction_depth"), card.get("push_direction"), card.get("relation_due_status")], limit=4, item_limit=12)
        summary = _summary_for_relation(card)
        status = _truncate_text(card.get("status") or card.get("level"), 16)
        key_name = _truncate_text(card.get("relation_id") or title, 48)
    return {
        "card_id": card_id,
        "entity_type": entity_type,
        "key": key_name,
        "title": title,
        "summary": _truncate_text(card.get("importance_hint_summary") or summary, 72),
        "tags": tags,
        "status": status,
        "importance_tier": _truncate_text(card.get("importance_tier"), 16),
        "importance_score": int(card.get("importance_score") or 0),
        "importance_mainline_rank_score": float(card.get("importance_mainline_rank_score") or card.get("importance_soft_rank_score") or 0.0),
        "importance_activation_rank_score": float(card.get("importance_activation_rank_score") or 0.0),
        "importance_exploration_score": float(card.get("importance_exploration_score") or 0.0),
    }


def build_card_index_payload(relevant_cards: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    payload = {"characters": [], "resources": [], "factions": [], "relations": []}
    source = relevant_cards or {}
    for key, entity_type in [("characters", "character"), ("resources", "resource"), ("factions", "faction")]:
        cards = source.get(key) or {}
        if isinstance(cards, dict):
            for card in cards.values():
                entry = build_card_index_entry(entity_type, card)
                if entry:
                    payload[key].append(entry)
    relation_cards = source.get("relations") or []
    if isinstance(relation_cards, list):
        for card in relation_cards:
            entry = build_card_index_entry("relation", card if isinstance(card, dict) else {})
            if entry:
                payload["relations"].append(entry)
    return payload


def _card_soft_query_terms(chapter_plan: dict[str, Any] | None, planning_packet: dict[str, Any] | None) -> list[str]:
    plan = chapter_plan or {}
    packet = planning_packet or {}
    raw_terms: list[Any] = [
        plan.get("title"),
        plan.get("goal"),
        plan.get("conflict"),
        plan.get("main_scene"),
        plan.get("event_type"),
        plan.get("progress_kind"),
        plan.get("flow_template_tag"),
        plan.get("flow_template_name"),
        plan.get("supporting_character_focus"),
        plan.get("supporting_character_note"),
        plan.get("ending_hook"),
        (packet.get("selected_elements") or {}).get("focus_character"),
    ]
    raw_terms.extend(plan.get("new_resources") or [])
    raw_terms.extend(plan.get("new_factions") or [])
    for relation in plan.get("new_relations") or []:
        if isinstance(relation, dict):
            raw_terms.extend([relation.get("subject"), relation.get("target"), relation.get("relation_type"), relation.get("status")])
    tokens: list[str] = []
    seen: set[str] = set()
    for value in raw_terms:
        text = _truncate_text(value, 24)
        if not text:
            continue
        for chunk in [piece.strip() for piece in text.replace("，", " ").replace("。", " ").replace("；", " ").replace("：", " ").replace("-", " ").split() if piece.strip()]:
            if len(chunk) < 2 or chunk in seen:
                continue
            seen.add(chunk)
            tokens.append(chunk)
            if len(tokens) >= 32:
                return tokens
    return tokens


def _soft_score_card_index_entry(
    entry: dict[str, Any],
    *,
    query_terms: list[str],
    focus_name: str,
    protagonist_name: str,
    due_character_names: set[str],
    resting_character_names: set[str],
    due_relation_ids: set[str],
    ai_focus_characters: set[str],
    ai_supporting_characters: set[str],
    ai_defer_characters: set[str],
    ai_main_relation_ids: set[str],
    ai_light_touch_relation_ids: set[str],
    ai_defer_relation_ids: set[str],
    stage_casting_action: str,
    stage_casting_target: str,
    stage_casting_should_execute: bool,
    stage_casting_soft_consider: bool,
) -> tuple[float, list[str]]:
    title = str(entry.get("title") or "").strip()
    summary = str(entry.get("summary") or "").strip()
    tags = [str(item or "").strip() for item in (entry.get("tags") or []) if str(item or "").strip()]
    entity_type = str(entry.get("entity_type") or "").strip()
    score = float(entry.get("importance_score") or 0) / 5.0
    score += float(entry.get("importance_mainline_rank_score") or 0.0) / 18.0
    score += float(entry.get("importance_activation_rank_score") or 0.0) / 26.0
    reasons: list[str] = []
    if protagonist_name and title == protagonist_name:
        score += 38.0
        reasons.append("主角")
    if focus_name and title == focus_name:
        score += 42.0
        reasons.append("焦点")
    if any(term and title and term == title for term in query_terms):
        score += 36.0
        reasons.append("标题命中")
    if any(term and summary and term in summary for term in query_terms[:10]):
        score += 12.0
        reasons.append("摘要命中")
    key = str(entry.get("key") or "").strip()
    if entity_type == "character" and title in due_character_names:
        score += 18.0
        reasons.append("该回场")
    if entity_type == "character" and title in resting_character_names:
        score -= 4.0
    if entity_type == "character" and title in ai_focus_characters:
        score += 24.0
        reasons.append("AI焦点")
    elif entity_type == "character" and title in ai_supporting_characters:
        score += 10.0
        reasons.append("AI辅助")
    if entity_type == "character" and title in ai_defer_characters:
        score -= 8.0
        reasons.append("AI暂缓")
    if entity_type == "relation" and (key in due_relation_ids or title in due_relation_ids):
        score += 18.0
        reasons.append("关系推进")
    if entity_type == "relation" and (key in ai_main_relation_ids or title in ai_main_relation_ids):
        score += 22.0
        reasons.append("AI主推")
    elif entity_type == "relation" and (key in ai_light_touch_relation_ids or title in ai_light_touch_relation_ids):
        score += 8.0
        reasons.append("AI轻触")
    if entity_type == "relation" and (key in ai_defer_relation_ids or title in ai_defer_relation_ids):
        score -= 8.0
        reasons.append("AI暂缓")
    if stage_casting_should_execute and stage_casting_action == "role_refresh" and entity_type == "character" and title == stage_casting_target:
        score += 26.0
        reasons.append("本章换功能")
    elif stage_casting_soft_consider and stage_casting_action == "role_refresh" and entity_type == "character" and title == stage_casting_target:
        score += 8.0
        reasons.append("换功能候选")
    tag_hits = 0
    for token in tags:
        if any(term and (term in token or token in term) for term in query_terms):
            tag_hits += 1
    if tag_hits:
        score += min(tag_hits, 3) * 7.0
        reasons.append("标签命中")
    status = str(entry.get("status") or "").strip()
    if status in {"planned", "刚建立"}:
        score += 8.0
        reasons.append("新引入")
    if float(entry.get("importance_activation_rank_score") or 0.0) >= max(float(entry.get("importance_mainline_rank_score") or 0.0) * 0.9, 72.0):
        score += 8.0
        reasons.append("激活位")
    if float(entry.get("importance_exploration_score") or 0.0) >= 52.0 and entity_type in {"character", "resource", "faction"}:
        score += 5.0
        reasons.append("探索槽")
    tier = str(entry.get("importance_tier") or "").strip()
    if any(flag in tier for flag in ["核心", "重要"]):
        score += 10.0
        reasons.append("重要")
    if entity_type == "relation" and any(term and term in title for term in query_terms[:8]):
        score += 10.0
        reasons.append("关系相关")
    return score, reasons[:4]


def _soft_bucket(score: float) -> str:
    if score >= 65:
        return "high"
    if score >= 28:
        return "medium"
    return "backup"


def soft_sort_card_index_payload(
    card_index: dict[str, list[dict[str, Any]]] | None,
    *,
    chapter_plan: dict[str, Any] | None,
    planning_packet: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    payload = card_index or {}
    focus_name = str((((planning_packet or {}).get("selected_elements") or {}).get("focus_character")) or "").strip()
    protagonist_name = ""
    for item in (payload.get("characters") or []):
        title = str((item or {}).get("title") or "").strip()
        if title:
            protagonist_name = title
            break
    query_terms = _card_soft_query_terms(chapter_plan, planning_packet)
    schedule = (planning_packet or {}).get("character_relation_schedule") or {}
    appearance_schedule = (schedule.get("appearance_schedule") or {}) if isinstance(schedule, dict) else {}
    relationship_schedule = (schedule.get("relationship_schedule") or {}) if isinstance(schedule, dict) else {}
    due_character_names = {str(item or "").strip() for item in (appearance_schedule.get("due_characters") or []) if str(item or "").strip()}
    resting_character_names = {str(item or "").strip() for item in (appearance_schedule.get("resting_characters") or []) if str(item or "").strip()}
    due_relation_ids = {str(item or "").strip() for item in (relationship_schedule.get("due_relations") or []) if str(item or "").strip()}
    ai_schedule = (planning_packet or {}).get("character_relation_schedule_ai") or {}
    ai_focus_characters = {str(item or "").strip() for item in (ai_schedule.get("focus_characters") or []) if str(item or "").strip()}
    ai_supporting_characters = {str(item or "").strip() for item in (ai_schedule.get("supporting_characters") or []) if str(item or "").strip()}
    ai_defer_characters = {str(item or "").strip() for item in (ai_schedule.get("defer_characters") or []) if str(item or "").strip()}
    ai_main_relation_ids = {str(item or "").strip() for item in (ai_schedule.get("main_relation_ids") or []) if str(item or "").strip()}
    ai_light_touch_relation_ids = {str(item or "").strip() for item in (ai_schedule.get("light_touch_relation_ids") or []) if str(item or "").strip()}
    ai_defer_relation_ids = {str(item or "").strip() for item in (ai_schedule.get("defer_relation_ids") or []) if str(item or "").strip()}
    stage_casting_hint = (planning_packet or {}).get("chapter_stage_casting_hint") or {}
    stage_casting_action = str(stage_casting_hint.get("planned_action") or "").strip()
    stage_casting_target = str(stage_casting_hint.get("planned_target") or "").strip()
    stage_casting_should_execute = bool(stage_casting_hint.get("final_should_execute_planned_action", stage_casting_hint.get("should_execute_planned_action")))
    final_recommended_action = str(stage_casting_hint.get("final_recommended_action") or stage_casting_hint.get("recommended_action") or "").strip()
    stage_casting_soft_consider = final_recommended_action in {"soft_consider", "consider_role_refresh", "balanced_light"}
    sorted_payload: dict[str, list[dict[str, Any]]] = {"characters": [], "resources": [], "factions": [], "relations": []}
    for bucket in ["characters", "resources", "factions", "relations"]:
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for idx, entry in enumerate(payload.get(bucket) or []):
            if not isinstance(entry, dict):
                continue
            normalized_entry = {
                **entry,
                "entity_type": str(entry.get("entity_type") or ("relation" if bucket == "relations" else bucket[:-1])),
            }
            score, reasons = _soft_score_card_index_entry(
                normalized_entry,
                query_terms=query_terms,
                focus_name=focus_name,
                protagonist_name=protagonist_name,
                due_character_names=due_character_names,
                resting_character_names=resting_character_names,
                due_relation_ids=due_relation_ids,
                ai_focus_characters=ai_focus_characters,
                ai_supporting_characters=ai_supporting_characters,
                ai_defer_characters=ai_defer_characters,
                ai_main_relation_ids=ai_main_relation_ids,
                ai_light_touch_relation_ids=ai_light_touch_relation_ids,
                ai_defer_relation_ids=ai_defer_relation_ids,
                stage_casting_action=stage_casting_action,
                stage_casting_target=stage_casting_target,
                stage_casting_should_execute=stage_casting_should_execute,
                stage_casting_soft_consider=stage_casting_soft_consider,
            )
            ranked.append(
                (
                    score,
                    idx,
                    {
                        **normalized_entry,
                        "soft_priority": _soft_bucket(score),
                        "soft_score": round(score, 2),
                        "soft_reason_tags": reasons,
                    },
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        sorted_payload[bucket] = [item[2] for item in ranked]
    return sorted_payload


def apply_soft_card_ranking_to_packet(packet: dict[str, Any], *, chapter_plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return packet
    card_index = packet.get("card_index") or {}
    if not card_index:
        return packet
    sorted_index = soft_sort_card_index_payload(card_index, chapter_plan=chapter_plan, planning_packet=packet)
    packet["card_index"] = sorted_index
    packet["card_index_meta"] = {
        "soft_sorting_rule": "本地先做相关度软排序，不硬删候选；若存在 AI 调度复核，则一并作为加权提示。",
        "query_terms": _card_soft_query_terms(chapter_plan, packet)[:12],
        "ai_schedule_used": bool(packet.get("character_relation_schedule_ai")),
        "stage_casting_hint_used": bool(packet.get("chapter_stage_casting_hint")),
        "importance_lanes_used": bool((packet.get("importance_runtime") or {}).get("selection_lanes")),
    }
    input_policy = packet.setdefault("input_policy", {})
    input_policy["card_soft_sort_rule"] = "card_index 仅做本地软排序，不删除候选；靠前代表更可能相关。"
    return packet


def apply_card_selection_to_packet(packet: dict[str, Any], selected_card_ids: list[str] | None, *, selection_note: str | None = None) -> dict[str, Any]:
    ordered_ids = [str(item or "").strip() for item in (selected_card_ids or []) if str(item or "").strip()]
    selected_set = set(ordered_ids)
    if not selected_set:
        return packet
    relevant_cards = (packet.get("relevant_cards") or {}) if isinstance(packet, dict) else {}
    filtered_characters = {
        name: card
        for name, card in (relevant_cards.get("characters") or {}).items()
        if str((card or {}).get("card_id") or "").strip() in selected_set
    }
    filtered_resources = {
        name: card
        for name, card in (relevant_cards.get("resources") or {}).items()
        if str((card or {}).get("card_id") or "").strip() in selected_set
    }
    filtered_factions = {
        name: card
        for name, card in (relevant_cards.get("factions") or {}).items()
        if str((card or {}).get("card_id") or "").strip() in selected_set
    }
    filtered_relations = [
        card
        for card in (relevant_cards.get("relations") or [])
        if str((card or {}).get("card_id") or "").strip() in selected_set
    ]
    packet["relevant_cards"] = {
        "characters": filtered_characters,
        "resources": filtered_resources,
        "factions": filtered_factions,
        "relations": filtered_relations,
    }
    selected_elements = packet.setdefault("selected_elements", {})
    selected_elements["characters"] = list(filtered_characters.keys())
    selected_elements["resources"] = list(filtered_resources.keys())
    selected_elements["factions"] = list(filtered_factions.keys())
    relation_names: list[str] = []
    for card in filtered_relations:
        if isinstance(card, dict):
            relation_name = _truncate_text(card.get("relation_id") or f"{card.get('subject') or ''}::{card.get('target') or ''}", 48)
            if relation_name:
                relation_names.append(relation_name)
    selected_elements["relations"] = relation_names
    packet["card_selection"] = {
        "selected_card_ids": ordered_ids,
        "selection_note": _truncate_text(selection_note, 96),
    }
    selected_resource_names = set(filtered_resources.keys())
    resource_plan = packet.get("resource_plan") or {}
    if isinstance(resource_plan, dict) and selected_resource_names:
        packet["resource_plan"] = {
            key: value
            for key, value in resource_plan.items()
            if key in selected_resource_names
        }
    capability_plan = packet.get("resource_capability_plan") or {}
    if isinstance(capability_plan, dict) and selected_resource_names:
        filtered_capability = {}
        for key, value in capability_plan.items():
            if key == "__meta__":
                filtered_capability[key] = value
            elif key in selected_resource_names:
                filtered_capability[key] = value
        packet["resource_capability_plan"] = filtered_capability
    input_policy = packet.setdefault("input_policy", {})
    input_policy["card_selection_rule"] = "AI 先看 card_index 里的全量轻量索引做筛选，再只展开 card_selection 选中的完整卡。"
    return packet
