from __future__ import annotations

"""Selection/review boundary for chapter-preparation AI calls.

This module exposes a smaller, more stable surface than the monolithic
``openai_story_engine``. Selection-specific shaping helpers now live here,
so prompt builders and execution code do not need to reach back into engine
internals for every compact/focused index operation.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, provider_name
from app.services.prompt_templates import (
    chapter_card_selector_system_prompt,
    chapter_card_selector_user_prompt,
)
from app.services.openai_story_engine_review import (
    CharacterRelationScheduleReviewPayload,
    StageCharacterReviewPayload,
    apply_schedule_review_to_packet,
    review_character_relation_schedule,
    review_stage_characters,
)

class SelectorTaskSpec(BaseModel):
    name: str
    stage: str
    system_prompt: str
    output_tokens: int
    timeout_floor: int = 12
    timeout_cap: int = 28


class ChapterCardSelectionPayload(BaseModel):
    selected_card_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


class PayoffSelectionPayload(BaseModel):
    selected_card_id: str | None = None
    selection_note: str | None = None


class ForeshadowingSelectionPayload(BaseModel):
    selected_primary_candidate_id: str | None = None
    selected_supporting_candidate_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


class SceneTemplateSelectionPayload(BaseModel):
    selected_scene_template_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


class PromptStrategySelectionPayload(BaseModel):
    selected_flow_template_id: str | None = None
    selected_flow_child_card_id: str | None = None
    selected_strategy_ids: list[str] = Field(default_factory=list)
    selected_writing_child_card_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


class ChapterPreparationShortlistPayload(BaseModel):
    focus_characters: list[str] = Field(default_factory=list)
    main_relation_ids: list[str] = Field(default_factory=list)
    card_candidate_ids: list[str] = Field(default_factory=list)
    payoff_candidate_ids: list[str] = Field(default_factory=list)
    foreshadowing_parent_card_ids: list[str] = Field(default_factory=list)
    foreshadowing_child_card_ids: list[str] = Field(default_factory=list)
    foreshadowing_candidate_ids: list[str] = Field(default_factory=list)
    scene_template_ids: list[str] = Field(default_factory=list)  # deprecated: scene continuity no longer uses template selection
    flow_template_ids: list[str] = Field(default_factory=list)
    flow_child_card_ids: list[str] = Field(default_factory=list)
    prompt_strategy_ids: list[str] = Field(default_factory=list)
    writing_child_card_ids: list[str] = Field(default_factory=list)
    shortlist_note: str | None = None


class ChapterPreparationSelectionResult(BaseModel):
    schedule_review: CharacterRelationScheduleReviewPayload = Field(default_factory=lambda: CharacterRelationScheduleReviewPayload())
    card_selection: ChapterCardSelectionPayload = Field(default_factory=lambda: ChapterCardSelectionPayload())
    payoff_selection: PayoffSelectionPayload = Field(default_factory=lambda: PayoffSelectionPayload())
    foreshadowing_selection: ForeshadowingSelectionPayload = Field(default_factory=lambda: ForeshadowingSelectionPayload())
    scene_selection: SceneTemplateSelectionPayload = Field(default_factory=lambda: SceneTemplateSelectionPayload())
    prompt_strategy_selection: PromptStrategySelectionPayload = Field(default_factory=lambda: PromptStrategySelectionPayload())
    selection_trace: dict[str, Any] = Field(default_factory=dict)


class ChapterFrontloadDecisionPayload(BaseModel):
    schedule_review: CharacterRelationScheduleReviewPayload = Field(default_factory=lambda: CharacterRelationScheduleReviewPayload())
    card_selection: ChapterCardSelectionPayload = Field(default_factory=ChapterCardSelectionPayload)
    payoff_selection: PayoffSelectionPayload = Field(default_factory=PayoffSelectionPayload)
    foreshadowing_selection: ForeshadowingSelectionPayload = Field(default_factory=ForeshadowingSelectionPayload)
    scene_selection: SceneTemplateSelectionPayload = Field(default_factory=SceneTemplateSelectionPayload)
    prompt_strategy_selection: PromptStrategySelectionPayload = Field(default_factory=PromptStrategySelectionPayload)





def is_openai_enabled() -> bool:
    from app.services.openai_story_engine import is_openai_enabled as _impl
    return _impl()

def raise_ai_required_error(*, stage: str, message: str, detail_reason: str, retryable: bool = False) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"{message}{('：' + detail_reason) if detail_reason else ''}",
        stage=stage,
        retryable=retryable,
        http_status=503,
        provider=provider_name(),
        details={"reason": detail_reason} if detail_reason else None,
    )


def _engine_call_json_response(**kwargs: Any) -> Any:
    try:
        from app.services import openai_story_engine as engine
        return engine.call_json_response(**kwargs)
    except Exception:
        return call_json_response(**kwargs)


def _heuristic_chapter_card_selection(*, chapter_plan: dict[str, Any], planning_packet: dict[str, Any]) -> ChapterCardSelectionPayload:
    selected_ids = _enforce_required_card_ids(planning_packet, [], chapter_plan=chapter_plan)
    if not selected_ids:
        selected_ids = [str(item.get("card_id") or "").strip() for item in _card_index_entries(planning_packet)[:6] if str(item.get("card_id") or "").strip()]
    return ChapterCardSelectionPayload(selected_card_ids=selected_ids[:12], selection_note="AI 不可用，已按本章重点做启发式卡片筛选。")



def choose_chapter_card_selection(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> ChapterCardSelectionPayload:
    if not _card_index_entries(planning_packet):
        return ChapterCardSelectionPayload(selected_card_ids=[], selection_note="当前章节没有可筛选卡片。")
    if not is_openai_enabled():
        return _heuristic_chapter_card_selection(chapter_plan=chapter_plan, planning_packet=planning_packet)
    timeout_seconds = request_timeout_seconds or int(getattr(settings, "chapter_card_selector_timeout_seconds", 12) or 12)
    try:
        data = _engine_call_json_response(
            stage="chapter_card_selection",
            system_prompt=chapter_card_selector_system_prompt(),
            user_prompt=chapter_card_selector_user_prompt(chapter_plan=chapter_plan, planning_packet=planning_packet),
            max_output_tokens=max(int(getattr(settings, "chapter_card_selector_max_output_tokens", 260) or 260), 120),
            timeout_seconds=timeout_seconds,
        )
        payload = ChapterCardSelectionPayload.model_validate(data)
        selected_ids = _enforce_required_card_ids(planning_packet, payload.selected_card_ids, chapter_plan=chapter_plan)
        return ChapterCardSelectionPayload(
            selected_card_ids=selected_ids[:12],
            selection_note=str(payload.selection_note or "").strip() or "AI 已完成本章卡片筛选。",
        )
    except GenerationError:
        raise
    except Exception as exc:
        raise_ai_required_error(
            stage="chapter_card_selection",
            message="章节卡筛选失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )


def run_chapter_preparation_selection(*args: Any, **kwargs: Any):
    from app.services.chapter_preparation_selection import run_chapter_preparation_selection as _impl
    return _impl(*args, **kwargs)


def review_character_relation_schedule_and_select_cards(*args: Any, **kwargs: Any):
    from app.services.chapter_preparation_selection import review_character_relation_schedule_and_select_cards as _impl
    return _impl(*args, **kwargs)


def _book_execution_profile(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    profile = packet.get("book_execution_profile") or packet.get("book_execution_profile_brief") or {}
    return profile if isinstance(profile, dict) else {}


def _clean_priority_bucket(value: Any, *, limit: int = 8) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in value or []:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        output.append(clean)
        if len(output) >= limit:
            break
    return output


def _priority_lists(profile: dict[str, Any], key: str, *, primary_key: str = "high", secondary_key: str = "medium", low_key: str = "low") -> dict[str, list[str]]:
    source = profile.get(key) or {}
    if not isinstance(source, dict):
        return {"high": [], "medium": [], "low": []}
    return {
        "high": _clean_priority_bucket(source.get(primary_key)),
        "medium": _clean_priority_bucket(source.get(secondary_key)),
        "low": _clean_priority_bucket(source.get(low_key)),
    }


def _book_guidance_meta(packet: dict[str, Any]) -> dict[str, Any]:
    profile = _book_execution_profile(packet)
    return {
        "mode": "prompt_only",
        "applied": False,
        "positioning_summary": str(profile.get("positioning_summary") or "").strip(),
        "flow_family_priority": _priority_lists(profile, "flow_family_priority"),
        "scene_template_priority": _priority_lists(profile, "scene_template_priority"),
        "payoff_priority": _priority_lists(profile, "payoff_priority"),
        "foreshadowing_priority": _priority_lists(profile, "foreshadowing_priority", primary_key="primary", secondary_key="secondary", low_key="hold_back"),
        "writing_strategy_priority": _priority_lists(profile, "writing_strategy_priority"),
        "character_template_priority": profile.get("character_template_priority") or {},
        "rhythm_bias": profile.get("rhythm_bias") or {},
        "demotion_rules": _clean_priority_bucket(profile.get("demotion_rules"), limit=5),
    }


def _book_bias_brief(packet: dict[str, Any]) -> dict[str, Any]:
    return _book_guidance_meta(packet)


def _selector_key(prefix: str, position: int) -> str:
    clean_prefix = ''.join(ch for ch in str(prefix or '').strip().lower() if ch.isalnum() or ch == '_') or 'candidate'
    return f"{clean_prefix}_{max(int(position or 0), 0):03d}"


def _attach_selector_keys(rows: list[dict[str, Any]], *, prefix: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, item in enumerate(rows or [], start=1):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.setdefault('selector_key', _selector_key(prefix, index))
        row.setdefault('selector_index', index)
        enriched.append(row)
    return enriched


def _normalized_ref_token(value: Any) -> str:
    text = str(value or '').strip().lower()
    return ''.join(ch for ch in text if ch.isalnum())


def _semantic_ref_token(value: Any) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[：:·•、,，。！!？?（）()\-_/]+", "", text)
    for token in ["候选", "动作", "主动作", "primary", "supporting", "selected", "candidate", "option"]:
        text = text.replace(token, "")
    for ch in ["在", "的", "与", "和", "及", "了", "一", "块", "个", "条", "份", "张", "枚", "片", "只", "把", "将"]:
        text = text.replace(ch, "")
    return ''.join(ch for ch in text if ch.isalnum())


def _resolve_selector_reference(
    value: Any,
    rows: list[dict[str, Any]],
    *,
    primary_keys: list[str],
    prefix: str,
    name_keys: list[str] | None = None,
) -> str:
    clean = str(value or '').strip()
    if not clean:
        return ''
    normalized = _normalized_ref_token(clean)
    semantic_normalized = _semantic_ref_token(clean)
    if not normalized and not semantic_normalized:
        return ''

    exact_map: dict[str, str] = {}
    loose_map: dict[str, str] = {}
    display_matches: dict[str, set[str]] = {}
    semantic_matches: dict[str, set[str]] = {}

    for index, item in enumerate(rows or [], start=1):
        if not isinstance(item, dict):
            continue
        primary = ''
        for key in primary_keys:
            primary = str(item.get(key) or '').strip()
            if primary:
                break
        if not primary:
            continue
        exact_tokens = {
            primary,
            str(item.get('selector_key') or '').strip(),
            _selector_key(prefix, index),
            str(index),
            f"{index:02d}",
            f"{index:03d}",
            f"{prefix}_{index:03d}",
            f"{prefix}-{index:03d}",
            f"{prefix}{index:03d}",
            f"candidate_{index}",
            f"candidate_{index:02d}",
            f"candidate_{index:03d}",
            f"candidate-{index}",
            f"candidate{index}",
            f"option_{index}",
            f"option_{index:02d}",
            f"option_{index:03d}",
            f"option-{index}",
            f"option{index}",
        }
        for alias_key in ['legacy_candidate_id', 'legacy_id', 'legacy_selector_key']:
            alias_value = str(item.get(alias_key) or '').strip()
            if alias_value:
                exact_tokens.add(alias_value)
                suffix = alias_value.split('::', 1)[-1].strip()
                if suffix:
                    exact_tokens.add(suffix)
        for token in exact_tokens:
            token = str(token or '').strip()
            if not token:
                continue
            exact_map[token] = primary
            token_norm = _normalized_ref_token(token)
            if token_norm:
                loose_map[token_norm] = primary
                display_matches.setdefault(token_norm, set()).add(primary)
            token_sem = _semantic_ref_token(token)
            if token_sem:
                semantic_matches.setdefault(token_sem, set()).add(primary)
        for key in (name_keys or []):
            label = str(item.get(key) or '').strip()
            if not label:
                continue
            label_norm = _normalized_ref_token(label)
            if label_norm:
                display_matches.setdefault(label_norm, set()).add(primary)
            label_sem = _semantic_ref_token(label)
            if label_sem:
                semantic_matches.setdefault(label_sem, set()).add(primary)
            if '::' in label:
                suffix = label.split('::', 1)[-1].strip()
                suffix_norm = _normalized_ref_token(suffix)
                if suffix_norm:
                    display_matches.setdefault(suffix_norm, set()).add(primary)
                suffix_sem = _semantic_ref_token(suffix)
                if suffix_sem:
                    semantic_matches.setdefault(suffix_sem, set()).add(primary)

    if clean in exact_map:
        return exact_map[clean]
    if normalized in loose_map:
        return loose_map[normalized]
    direct_matches = list(display_matches.get(normalized) or []) if normalized else []
    if len(direct_matches) == 1:
        return direct_matches[0]
    semantic_direct = list(semantic_matches.get(semantic_normalized) or []) if semantic_normalized else []
    if len(semantic_direct) == 1:
        return semantic_direct[0]
    if semantic_normalized:
        fuzzy: set[str] = set()
        for token, primaries in semantic_matches.items():
            if not token:
                continue
            if semantic_normalized == token:
                fuzzy.update(primaries)
            elif len(semantic_normalized) >= 4 and len(token) >= 4 and (semantic_normalized in token or token in semantic_normalized):
                fuzzy.update(primaries)
        if len(fuzzy) == 1:
            return next(iter(fuzzy))
    return ''


def _card_index_entries(packet: dict[str, Any]) -> list[dict[str, Any]]:
    index = (packet.get("card_index") or {}) if isinstance(packet, dict) else {}
    entries: list[dict[str, Any]] = []
    for bucket, entity_type in [("characters", "character"), ("resources", "resource"), ("factions", "faction"), ("relations", "relation")]:
        for item in index.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            card_id = str(item.get("card_id") or "").strip()
            if not card_id:
                continue
            entries.append({
                **item,
                "entity_type": entity_type,
                "bucket": bucket,
            })
    return entries


def _enforce_required_card_ids(packet: dict[str, Any], selected_ids: list[str], *, chapter_plan: dict[str, Any]) -> list[str]:
    index_entries = _card_index_entries(packet)
    id_by_title = {str(item.get("title") or "").strip(): str(item.get("card_id") or "").strip() for item in index_entries}
    selected = [str(item or "").strip() for item in selected_ids if str(item or "").strip()]
    focus_name = str(((packet.get("selected_elements") or {}).get("focus_character")) or "").strip()
    required_names = []
    protagonist_candidates = [item for item in index_entries if item.get("entity_type") == "character"]
    if protagonist_candidates:
        required_names.append(str(protagonist_candidates[0].get("title") or "").strip())
    if focus_name:
        required_names.append(focus_name)
    for key in ["new_resources", "new_factions"]:
        for name in list((chapter_plan or {}).get(key) or []):
            clean = str(name or "").strip()
            if clean:
                required_names.append(clean)
    for relation in list((chapter_plan or {}).get("new_relations") or []):
        if isinstance(relation, dict):
            title = f"{str(relation.get('subject') or '').strip()}-{str(relation.get('target') or '').strip()}".strip("-")
            if title:
                required_names.append(title)
    seen = set(selected)
    for name in required_names:
        card_id = id_by_title.get(name)
        if card_id and card_id not in seen:
            selected.append(card_id)
            seen.add(card_id)
    return selected


def _schedule_valid_character_names(planning_packet: dict[str, Any]) -> list[str]:
    packet = planning_packet or {}
    names: list[str] = []
    relevant = (packet.get("relevant_cards") or {}) if isinstance(packet, dict) else {}
    names.extend([str(name or "").strip() for name in (relevant.get("characters") or {}).keys()])
    for item in _card_index_entries(packet):
        if str(item.get("entity_type") or "").strip() == "character":
            names.append(str(item.get("title") or "").strip())
    names.extend([str(item or "").strip() for item in ((packet.get("selected_elements") or {}).get("characters") or [])])
    output: list[str] = []
    seen: set[str] = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        output.append(name)
    return output


def _schedule_valid_relation_ids(planning_packet: dict[str, Any]) -> list[str]:
    packet = planning_packet or {}
    schedule = (packet.get("character_relation_schedule") or {}) if isinstance(packet, dict) else {}
    relationship_schedule = (schedule.get("relationship_schedule") or {}) if isinstance(schedule, dict) else {}
    ids: list[str] = []
    ids.extend([str(item or "").strip() for item in (relationship_schedule.get("due_relations") or [])])
    for item in (relationship_schedule.get("priority_relations") or []):
        if isinstance(item, dict):
            ids.append(str(item.get("relation_id") or "").strip())
    relevant = (packet.get("relevant_cards") or {}) if isinstance(packet, dict) else {}
    for card in (relevant.get("relations") or []):
        if isinstance(card, dict):
            ids.append(str(card.get("relation_id") or card.get("key") or card.get("title") or "").strip())
    output: list[str] = []
    seen: set[str] = set()
    for rid in ids:
        if not rid or rid in seen:
            continue
        seen.add(rid)
        output.append(rid)
    return output


def _normalize_schedule_review_payload(
    payload: CharacterRelationScheduleReviewPayload,
    planning_packet: dict[str, Any],
) -> CharacterRelationScheduleReviewPayload:
    valid_character_list = _schedule_valid_character_names(planning_packet)
    valid_characters = set(valid_character_list)
    valid_relations = set(_schedule_valid_relation_ids(planning_packet))
    protagonist = valid_character_list[0] if valid_character_list else ""
    focus_name = str((((planning_packet or {}).get("selected_elements") or {}).get("focus_character")) or "").strip()
    stage_hint = ((planning_packet or {}).get("chapter_stage_casting_hint") or {}) if isinstance(planning_packet, dict) else {}
    planned_action = str(stage_hint.get("planned_action") or "").strip()
    local_should_execute = bool(stage_hint.get("should_execute_planned_action"))
    local_do_not_force = bool(stage_hint.get("do_not_force_action"))

    def _dedupe_keep(items: list[str], valid: set[str], limit: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            name = str(item or "").strip()
            if not name or name in seen or name not in valid:
                continue
            seen.add(name)
            out.append(name)
            if len(out) >= limit:
                break
        return out

    focus = _dedupe_keep(payload.focus_characters, valid_characters, 4)
    protagonist = str(protagonist or "").strip()
    if protagonist and protagonist in focus:
        focus = [name for name in focus if name != protagonist]
        focus.insert(0, protagonist)
    elif protagonist and protagonist in valid_characters and len(focus) < 4:
        focus.insert(0, protagonist)
    if focus_name and focus_name in valid_characters and focus_name not in focus and len(focus) < 4:
        focus.append(focus_name)
    supporting = [item for item in _dedupe_keep(payload.supporting_characters, valid_characters, 4) if item not in focus]
    defer_chars = [item for item in _dedupe_keep(payload.defer_characters, valid_characters, 4) if item not in focus and item not in supporting]
    main_rel = _dedupe_keep(payload.main_relation_ids, valid_relations, 3)
    light_touch = [item for item in _dedupe_keep(payload.light_touch_relation_ids, valid_relations, 4) if item not in main_rel]
    defer_rel = [item for item in _dedupe_keep(payload.defer_relation_ids, valid_relations, 4) if item not in main_rel and item not in light_touch]
    depth = {str(key or "").strip(): str(value or "").strip() for key, value in (payload.interaction_depth_overrides or {}).items() if str(key or "").strip() in valid_relations and str(value or "").strip()}
    push = {str(key or "").strip(): str(value or "").strip() for key, value in (payload.relation_push_overrides or {}).items() if str(key or "").strip() in valid_relations and str(value or "").strip()}

    valid_verdicts = {"execute_now", "defer_to_next", "soft_consider", "hold_steady"}
    verdict = str(payload.stage_casting_verdict or "").strip()
    if verdict not in valid_verdicts:
        if planned_action and local_should_execute:
            verdict = "execute_now"
        elif planned_action and local_do_not_force:
            verdict = "defer_to_next"
        elif local_do_not_force:
            verdict = "hold_steady"
        else:
            verdict = "soft_consider"

    ai_execute = payload.should_execute_stage_casting_action
    if ai_execute is None:
        if verdict == "execute_now":
            ai_execute = True
        elif verdict in {"defer_to_next", "soft_consider", "hold_steady"}:
            ai_execute = False
    ai_do_not = payload.do_not_force_stage_casting_action
    if ai_do_not is None:
        ai_do_not = verdict != "execute_now"

    if local_should_execute:
        final_should_execute = bool(ai_execute)
        final_do_not_force = bool(ai_do_not) or not final_should_execute
    elif local_do_not_force:
        final_should_execute = False
        final_do_not_force = True
    else:
        final_should_execute = False
        final_do_not_force = True

    stage_reason = str(payload.stage_casting_reason or "").strip()[:96] or None
    note = str(payload.review_note or "").strip()[:96] or None
    return CharacterRelationScheduleReviewPayload(
        focus_characters=focus,
        supporting_characters=supporting,
        defer_characters=defer_chars,
        main_relation_ids=main_rel,
        light_touch_relation_ids=light_touch,
        defer_relation_ids=defer_rel,
        interaction_depth_overrides=depth,
        relation_push_overrides=push,
        stage_casting_verdict=verdict,
        should_execute_stage_casting_action=final_should_execute,
        do_not_force_stage_casting_action=final_do_not_force,
        stage_casting_reason=stage_reason,
        review_note=note,
    )


def _compact_for_prompt(value: Any, *, max_depth: int = 3, max_items: int = 6, text_limit: int = 80) -> Any:
    if max_depth <= 0:
        if isinstance(value, (dict, list)):
            return '…'
        return _compact_for_prompt(str(value), max_depth=1, max_items=max_items, text_limit=text_limit)
    if isinstance(value, dict):
        items = []
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                items.append(('…', f'+{len(value) - max_items} more'))
                break
            items.append((str(key), _compact_for_prompt(item, max_depth=max_depth - 1, max_items=max_items, text_limit=text_limit)))
        return dict(items)
    if isinstance(value, list):
        trimmed = [_compact_for_prompt(item, max_depth=max_depth - 1, max_items=max_items, text_limit=text_limit) for item in value[:max_items]]
        if len(value) > max_items:
            trimmed.append(f'… +{len(value) - max_items} more')
        return trimmed
    if isinstance(value, tuple):
        return _compact_for_prompt(list(value), max_depth=max_depth, max_items=max_items, text_limit=text_limit)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned[:text_limit] + ('…' if len(cleaned) > text_limit else '')
    return value


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _focused_schedule_candidate_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    schedule_index = (packet.get("schedule_candidate_index") or {}) if isinstance(packet, dict) else {}
    if not shortlist:
        return schedule_index
    focus_names = {str(item or '').strip() for item in (shortlist.get('focus_characters') or []) if str(item or '').strip()}
    relation_ids = {str(item or '').strip() for item in (shortlist.get('main_relation_ids') or []) if str(item or '').strip()}
    appearance = [item for item in (schedule_index.get('appearance_candidates') or []) if isinstance(item, dict) and str(item.get('name') or '').strip() in focus_names]
    relations = [item for item in (schedule_index.get('relation_candidates') or []) if isinstance(item, dict) and str(item.get('relation_id') or '').strip() in relation_ids]
    return {
        'appearance_candidates': appearance or (schedule_index.get('appearance_candidates') or [])[:4],
        'relation_candidates': relations or (schedule_index.get('relation_candidates') or [])[:3],
        'schedule_summary': schedule_index.get('schedule_summary') or {},
        'core_cast_summary': schedule_index.get('core_cast_summary') or {},
        'stage_casting': schedule_index.get('stage_casting') or {},
        'focus_counts': {
            'appearance_candidates': len(appearance or []),
            'relation_candidates': len(relations or []),
            'full_appearance_candidates': len(schedule_index.get('appearance_candidates') or []),
            'full_relation_candidates': len(schedule_index.get('relation_candidates') or []),
        },
    }


def _focused_card_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    card_index = (packet.get('card_index') or {}) if isinstance(packet, dict) else {}
    if not shortlist:
        return card_index
    wanted = {str(item or '').strip() for item in (shortlist.get('card_candidate_ids') or []) if str(item or '').strip()}
    if not wanted:
        return card_index
    focused: dict[str, Any] = {}
    total_counts: dict[str, int] = {}
    focus_counts: dict[str, int] = {}
    for bucket in ['characters', 'resources', 'factions', 'relations']:
        rows = [item for item in (card_index.get(bucket) or []) if isinstance(item, dict)]
        total_counts[bucket] = len(rows)
        chosen = [item for item in rows if str(item.get('card_id') or '').strip() in wanted]
        focus_counts[bucket] = len(chosen)
        if chosen:
            focused[bucket] = chosen
    focused['focus_counts'] = {'focused': focus_counts, 'full': total_counts}
    return focused or card_index


def _focused_payoff_candidate_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    payoff_index = (packet.get('payoff_candidate_index') or {}) if isinstance(packet, dict) else {}
    candidates = [item for item in (payoff_index.get('candidates') or []) if isinstance(item, dict)]
    guidance_meta = _book_guidance_meta(packet)
    candidates = _attach_selector_keys(candidates, prefix='payoff')
    if not shortlist:
        return {
            **payoff_index,
            'candidates': candidates,
            'book_bias': guidance_meta,
        }
    wanted = {str(item or '').strip() for item in (shortlist.get('payoff_candidate_ids') or []) if str(item or '').strip()}
    if not wanted:
        return {
            **payoff_index,
            'candidates': candidates,
            'book_bias': guidance_meta,
        }
    focused = [item for item in candidates if str(item.get('card_id') or '').strip() in wanted]
    return {
        **{k: v for k, v in payoff_index.items() if k != 'candidates'},
        'candidates': focused or candidates[:3],
        'focus_counts': {'focused': len(focused or []), 'full': len(candidates)},
        'book_bias': guidance_meta,
    }


def _focused_foreshadowing_candidate_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    foreshadowing_index = (packet.get('foreshadowing_candidate_index') or {}) if isinstance(packet, dict) else {}
    parents = [item for item in (foreshadowing_index.get('parent_cards') or []) if isinstance(item, dict)]
    children = [item for item in (foreshadowing_index.get('child_cards') or []) if isinstance(item, dict)]
    candidates = [item for item in (foreshadowing_index.get('candidates') or []) if isinstance(item, dict)]
    guidance_meta = _book_guidance_meta(packet)
    candidates = _attach_selector_keys(candidates, prefix='foreshadow')
    if not shortlist:
        return {
            **{k: v for k, v in foreshadowing_index.items() if k not in {'parent_cards', 'child_cards', 'candidates'}},
            'parent_cards': parents,
            'child_cards': children,
            'candidates': candidates,
            'focus_path': {
                'mode': 'full_index',
                'parent_filter_mode': 'none',
                'child_filter_mode': 'none',
                'candidate_filter_mode': 'none',
            },
            'book_bias': guidance_meta,
        }

    wanted_parents = {str(item or '').strip() for item in (shortlist.get('foreshadowing_parent_card_ids') or []) if str(item or '').strip()}
    wanted_children = {str(item or '').strip() for item in (shortlist.get('foreshadowing_child_card_ids') or []) if str(item or '').strip()}
    wanted_candidates = {str(item or '').strip() for item in (shortlist.get('foreshadowing_candidate_ids') or []) if str(item or '').strip()}

    if wanted_parents:
        focused_parents = [item for item in parents if str(item.get('card_id') or '').strip() in wanted_parents]
        parent_filter_mode = 'shortlist_parent_ids'
    else:
        focused_parents = list(parents[:4])
        parent_filter_mode = 'fallback_top_parents'
    active_parent_ids = {str(item.get('card_id') or '').strip() for item in focused_parents if str(item.get('card_id') or '').strip()}

    if wanted_children:
        focused_children = [
            item for item in children
            if str(item.get('child_id') or '').strip() in wanted_children
            and (not active_parent_ids or str(item.get('parent_id') or '').strip() in active_parent_ids)
        ]
        child_filter_mode = 'shortlist_child_ids'
    elif active_parent_ids:
        focused_children = [item for item in children if str(item.get('parent_id') or '').strip() in active_parent_ids]
        child_filter_mode = 'inherit_parent_focus'
    else:
        focused_children = list(children[:6])
        child_filter_mode = 'fallback_top_children'
    active_child_ids = {str(item.get('child_id') or '').strip() for item in focused_children if str(item.get('child_id') or '').strip()}

    if wanted_candidates:
        focused_candidates = [
            item for item in candidates
            if str(item.get('candidate_id') or '').strip() in wanted_candidates
            and (not active_child_ids or str(item.get('child_card_id') or '').strip() in active_child_ids)
            and (not active_parent_ids or str(item.get('parent_card_id') or '').strip() in active_parent_ids)
        ]
        candidate_filter_mode = 'shortlist_candidate_ids'
    elif active_child_ids:
        focused_candidates = [item for item in candidates if str(item.get('child_card_id') or '').strip() in active_child_ids]
        candidate_filter_mode = 'inherit_child_focus'
    elif active_parent_ids:
        focused_candidates = [item for item in candidates if str(item.get('parent_card_id') or '').strip() in active_parent_ids]
        candidate_filter_mode = 'inherit_parent_focus'
    else:
        focused_candidates = list(candidates[:6])
        candidate_filter_mode = 'fallback_top_candidates'
    focused_candidates = _attach_selector_keys(focused_candidates or candidates[:6], prefix='foreshadow')

    focused_parent_ids = [str(item.get('card_id') or '').strip() for item in focused_parents if str(item.get('card_id') or '').strip()]
    focused_child_ids = [str(item.get('child_id') or '').strip() for item in focused_children if str(item.get('child_id') or '').strip()]
    focused_candidate_ids = [str(item.get('candidate_id') or '').strip() for item in focused_candidates if str(item.get('candidate_id') or '').strip()]

    return {
        **{k: v for k, v in foreshadowing_index.items() if k not in {'parent_cards', 'child_cards', 'candidates'}},
        'parent_cards': focused_parents or parents[:4],
        'child_cards': focused_children or children[:6],
        'candidates': focused_candidates,
        'focus_counts': {
            'parent_cards': {'focused': len(focused_parents or []), 'full': len(parents)},
            'child_cards': {'focused': len(focused_children or []), 'full': len(children)},
            'candidates': {'focused': len(focused_candidates or []), 'full': len(candidates)},
        },
        'focus_path': {
            'mode': 'layered_narrowing',
            'parent_filter_mode': parent_filter_mode,
            'child_filter_mode': child_filter_mode,
            'candidate_filter_mode': candidate_filter_mode,
            'active_parent_ids': focused_parent_ids,
            'active_child_ids': focused_child_ids,
            'active_candidate_ids': focused_candidate_ids,
            'single_parent_locked': len(focused_parent_ids) == 1,
            'single_child_locked': len(focused_child_ids) == 1,
            'single_candidate_locked': len(focused_candidate_ids) == 1,
        },
        'book_bias': guidance_meta,
    }




def _preview_strings(values: list[str], *, limit: int = 6) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or '').strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        output.append(clean)
        if len(output) >= limit:
            break
    return output


def _preview_from_rows(rows: list[dict[str, Any]], *, id_keys: list[str], name_keys: list[str] | None = None, limit: int = 6) -> list[str]:
    preview: list[str] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        identifier = ''
        for key in id_keys:
            identifier = str(item.get(key) or '').strip()
            if identifier:
                break
        label = ''
        for key in (name_keys or []):
            label = str(item.get(key) or '').strip()
            if label:
                break
        text = identifier
        if identifier and label and label != identifier:
            text = f"{identifier}（{label}）"
        elif not text:
            text = label
        if not text or text in seen:
            continue
        seen.add(text)
        preview.append(text)
        if len(preview) >= limit:
            break
    return preview


def _payoff_selection_layers(packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> dict[str, Any]:
    payoff_index = (packet.get('payoff_candidate_index') or {}) if isinstance(packet, dict) else {}
    raw_candidates = [item for item in (payoff_index.get('candidates') or []) if isinstance(item, dict)]
    raw_families = _preview_strings([str(item.get('family') or '').strip() for item in raw_candidates if str(item.get('family') or '').strip()], limit=8)
    shortlist_ids = [str(item or '').strip() for item in ((shortlist or {}).get('payoff_candidate_ids') or []) if str(item or '').strip()]
    shortlisted_candidates = [item for item in raw_candidates if str(item.get('card_id') or '').strip() in set(shortlist_ids)] if shortlist else []
    focused_index = _focused_payoff_candidate_index(packet, shortlist)
    focused_candidates = [item for item in (focused_index.get('candidates') or []) if isinstance(item, dict)]
    focused_families = _preview_strings([str(item.get('family') or '').strip() for item in focused_candidates if str(item.get('family') or '').strip()], limit=8)
    return {
        'family_layer': {
            'raw_count': len({str(item.get('family') or '').strip() for item in raw_candidates if str(item.get('family') or '').strip()}),
            'raw_preview': raw_families,
            'focused_count': len({str(item.get('family') or '').strip() for item in focused_candidates if str(item.get('family') or '').strip()}),
            'focused_preview': focused_families,
        },
        'candidate_layer': {
            'raw_count': len(raw_candidates),
            'raw_preview': _preview_from_rows(raw_candidates, id_keys=['card_id'], name_keys=['name']),
            'shortlist_count': len(shortlisted_candidates or shortlist_ids),
            'shortlist_preview': _preview_from_rows(shortlisted_candidates, id_keys=['card_id'], name_keys=['name']) or _preview_strings(shortlist_ids),
            'focused_count': len(focused_candidates),
            'focused_preview': _preview_from_rows(focused_candidates, id_keys=['card_id'], name_keys=['name']),
        },
    }


def _foreshadowing_selection_layers(packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> dict[str, Any]:
    index = (packet.get('foreshadowing_candidate_index') or {}) if isinstance(packet, dict) else {}
    raw_parents = [item for item in (index.get('parent_cards') or []) if isinstance(item, dict)]
    raw_children = [item for item in (index.get('child_cards') or []) if isinstance(item, dict)]
    raw_candidates = [item for item in (index.get('candidates') or []) if isinstance(item, dict)]

    shortlist_parent_ids = [str(item or '').strip() for item in ((shortlist or {}).get('foreshadowing_parent_card_ids') or []) if str(item or '').strip()]
    shortlist_child_ids = [str(item or '').strip() for item in ((shortlist or {}).get('foreshadowing_child_card_ids') or []) if str(item or '').strip()]
    shortlist_candidate_ids = [str(item or '').strip() for item in ((shortlist or {}).get('foreshadowing_candidate_ids') or []) if str(item or '').strip()]

    shortlist_parent_set = set(shortlist_parent_ids)
    shortlist_child_set = set(shortlist_child_ids)
    shortlist_candidate_set = set(shortlist_candidate_ids)

    shortlisted_parents = [item for item in raw_parents if str(item.get('card_id') or '').strip() in shortlist_parent_set]
    shortlisted_children = [item for item in raw_children if str(item.get('child_id') or '').strip() in shortlist_child_set]
    shortlisted_candidates = [item for item in raw_candidates if str(item.get('candidate_id') or '').strip() in shortlist_candidate_set]

    focused_index = _focused_foreshadowing_candidate_index(packet, shortlist)
    focused_parents = [item for item in (focused_index.get('parent_cards') or []) if isinstance(item, dict)]
    focused_children = [item for item in (focused_index.get('child_cards') or []) if isinstance(item, dict)]
    focused_candidates = [item for item in (focused_index.get('candidates') or []) if isinstance(item, dict)]

    focus_path = focused_index.get('focus_path') or {}
    focused_parent_ids = [str(item.get('card_id') or '').strip() for item in focused_parents if str(item.get('card_id') or '').strip()]
    focused_child_ids = [str(item.get('child_id') or '').strip() for item in focused_children if str(item.get('child_id') or '').strip()]
    focused_candidate_ids = [str(item.get('candidate_id') or '').strip() for item in focused_candidates if str(item.get('candidate_id') or '').strip()]

    return {
        'parent_layer': {
            'raw_count': len(raw_parents),
            'raw_preview': _preview_from_rows(raw_parents, id_keys=['card_id'], name_keys=['name']),
            'shortlist_count': len(shortlisted_parents or shortlist_parent_ids),
            'shortlist_preview': _preview_from_rows(shortlisted_parents, id_keys=['card_id'], name_keys=['name']) or _preview_strings(shortlist_parent_ids),
            'focused_count': len(focused_parents),
            'focused_preview': _preview_from_rows(focused_parents, id_keys=['card_id'], name_keys=['name']),
            'focused_ids': focused_parent_ids,
            'single_locked': len(focused_parent_ids) == 1,
        },
        'child_layer': {
            'raw_count': len(raw_children),
            'raw_preview': _preview_from_rows(raw_children, id_keys=['child_id'], name_keys=['name']),
            'shortlist_count': len(shortlisted_children or shortlist_child_ids),
            'shortlist_preview': _preview_from_rows(shortlisted_children, id_keys=['child_id'], name_keys=['name']) or _preview_strings(shortlist_child_ids),
            'focused_count': len(focused_children),
            'focused_preview': _preview_from_rows(focused_children, id_keys=['child_id'], name_keys=['name']),
            'focused_ids': focused_child_ids,
            'single_locked': len(focused_child_ids) == 1,
        },
        'candidate_layer': {
            'raw_count': len(raw_candidates),
            'raw_preview': _preview_from_rows(raw_candidates, id_keys=['candidate_id'], name_keys=['display_label', 'selector_label', 'source_hook', 'child_card_name']),
            'shortlist_count': len(shortlisted_candidates or shortlist_candidate_ids),
            'shortlist_preview': _preview_from_rows(shortlisted_candidates, id_keys=['candidate_id'], name_keys=['display_label', 'selector_label', 'source_hook', 'child_card_name']) or _preview_strings(shortlist_candidate_ids),
            'focused_count': len(focused_candidates),
            'focused_preview': _preview_from_rows(focused_candidates, id_keys=['candidate_id'], name_keys=['display_label', 'selector_label', 'source_hook', 'child_card_name']),
            'focused_ids': focused_candidate_ids,
            'single_locked': len(focused_candidate_ids) == 1,
        },
        'path_summary': {
            'parent_filter_mode': str(focus_path.get('parent_filter_mode') or ''),
            'child_filter_mode': str(focus_path.get('child_filter_mode') or ''),
            'candidate_filter_mode': str(focus_path.get('candidate_filter_mode') or ''),
        },
    }


def _selection_layer_overview(packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'payoff': _payoff_selection_layers(packet, shortlist),
        'foreshadowing': _foreshadowing_selection_layers(packet, shortlist),
    }


def _focused_scene_template_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    scene_index = (packet.get('scene_continuity_index') or packet.get('scene_template_index') or {}) if isinstance(packet, dict) else {}
    scene_templates = _attach_selector_keys([item for item in (scene_index.get('scene_templates') or []) if isinstance(item, dict)], prefix='scene')
    return {
        **scene_index,
        'scene_templates': scene_templates or (scene_index.get('scene_templates') or []),
        'book_bias': _book_guidance_meta(packet),
    }


def _focused_prompt_bundle_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    bundle = (packet.get('prompt_bundle_index') or {}) if isinstance(packet, dict) else {}
    flows = [item for item in (bundle.get('flow_cards') or bundle.get('flow_templates') or []) if isinstance(item, dict)]
    prompts = [item for item in (bundle.get('writing_cards') or bundle.get('prompt_strategies') or []) if isinstance(item, dict)]
    flow_children = [item for item in (bundle.get('flow_child_cards') or []) if isinstance(item, dict)]
    writing_children = [item for item in (bundle.get('writing_child_cards') or []) if isinstance(item, dict)]
    guidance_meta = _book_guidance_meta(packet)
    flows = _attach_selector_keys(flows, prefix='flow')
    prompts = _attach_selector_keys(prompts, prefix='strategy')
    flow_children = _attach_selector_keys(flow_children, prefix='flowchild')
    writing_children = _attach_selector_keys(writing_children, prefix='writingchild')
    if not shortlist:
        return {
            'flow_templates': flows,
            'prompt_strategies': prompts,
            'flow_cards': flows,
            'writing_cards': prompts,
            'flow_child_cards': flow_children,
            'writing_child_cards': writing_children,
            'book_bias': guidance_meta,
        }
    wanted_flow = {str(item or '').strip() for item in (shortlist.get('flow_template_ids') or []) if str(item or '').strip()}
    wanted_flow_child = {str(item or '').strip() for item in (shortlist.get('flow_child_card_ids') or []) if str(item or '').strip()}
    wanted_prompt = {str(item or '').strip() for item in (shortlist.get('prompt_strategy_ids') or []) if str(item or '').strip()}
    wanted_writing_child = {str(item or '').strip() for item in (shortlist.get('writing_child_card_ids') or []) if str(item or '').strip()}
    focused_flows = [item for item in flows if str(item.get('flow_id') or item.get('card_id') or '').strip() in wanted_flow]
    focused_prompts = [item for item in prompts if str(item.get('strategy_id') or item.get('card_id') or '').strip() in wanted_prompt]
    active_flow_ids = {str(item.get('flow_id') or item.get('card_id') or '').strip() for item in (focused_flows or flows[:4])}
    active_prompt_ids = {str(item.get('strategy_id') or item.get('card_id') or '').strip() for item in (focused_prompts or prompts[:6])}
    focused_flow_children = [item for item in flow_children if str(item.get('child_id') or item.get('card_id') or '').strip() in wanted_flow_child or str(item.get('parent_flow_id') or item.get('parent_id') or '').strip() in active_flow_ids]
    focused_writing_children = [item for item in writing_children if str(item.get('child_id') or item.get('card_id') or '').strip() in wanted_writing_child or str(item.get('parent_strategy_id') or item.get('parent_id') or '').strip() in active_prompt_ids]
    return {
        'flow_templates': focused_flows or flows[:4],
        'prompt_strategies': focused_prompts or prompts[:6],
        'flow_cards': focused_flows or flows[:4],
        'writing_cards': focused_prompts or prompts[:6],
        'flow_child_cards': focused_flow_children or flow_children[:8],
        'writing_child_cards': focused_writing_children or writing_children[:8],
        'focus_counts': {
            'flow_templates': {'focused': len(focused_flows or []), 'full': len(flows)},
            'prompt_strategies': {'focused': len(focused_prompts or []), 'full': len(prompts)},
            'flow_child_cards': {'focused': len(focused_flow_children or []), 'full': len(flow_children)},
            'writing_child_cards': {'focused': len(focused_writing_children or []), 'full': len(writing_children)},
        },
        'book_bias': guidance_meta,
    }


def _selection_scope(packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> dict[str, Any]:
    packet = packet or {}
    focused_schedule = _focused_schedule_candidate_index(packet, shortlist)
    focused_cards = _focused_card_index(packet, shortlist)
    focused_payoff = _focused_payoff_candidate_index(packet, shortlist)
    focused_foreshadowing = _focused_foreshadowing_candidate_index(packet, shortlist)
    focused_scene = _focused_scene_template_index(packet, shortlist)
    focused_prompt = _focused_prompt_bundle_index(packet, shortlist)
    return {
        "schedule": focused_schedule,
        "cards": focused_cards,
        "payoff": focused_payoff,
        "foreshadowing": focused_foreshadowing,
        "scene": focused_scene,
        "prompt": focused_prompt,
        "book_bias": _book_bias_brief(packet),
        "stats": {
            "schedule": {
                "appearance_candidates": len((focused_schedule.get("appearance_candidates") or [])),
                "relation_candidates": len((focused_schedule.get("relation_candidates") or [])),
            },
            "cards": {bucket: len((focused_cards.get(bucket) or [])) for bucket in ["characters", "resources", "factions", "relations"]},
            "payoff": {"candidates": len((focused_payoff.get("candidates") or []))},
            "foreshadowing": {
                "parent_cards": len((focused_foreshadowing.get("parent_cards") or [])),
                "child_cards": len((focused_foreshadowing.get("child_cards") or [])),
                "candidates": len((focused_foreshadowing.get("candidates") or [])),
            },
            "scene": {"scene_templates": len((focused_scene.get("scene_templates") or [])), "scene_count": int(focused_scene.get("scene_count") or 0), "planned_cuts": len((focused_scene.get("cut_plan") or []))},
            "prompt": {
                "flow_templates": len((focused_prompt.get("flow_templates") or [])),
                "prompt_strategies": len((focused_prompt.get("prompt_strategies") or [])),
                "flow_child_cards": len((focused_prompt.get("flow_child_cards") or [])),
                "writing_child_cards": len((focused_prompt.get("writing_child_cards") or [])),
            },
        },
    }


def _normalize_payoff_selection_payload(payload: PayoffSelectionPayload, planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> PayoffSelectionPayload:
    index = (_selection_scope(planning_packet, shortlist).get("payoff") or {}).get("candidates") or []
    allowed_ids = [str(item.get("card_id") or "").strip() for item in index if isinstance(item, dict) and str(item.get("card_id") or "").strip()]
    selected_card_id = str(payload.selected_card_id or "").strip()
    if not allowed_ids:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message='chapter_prepare_payoff_selector 失败：当前没有可供 AI 终选的爽点压缩候选。',
            stage='chapter_prepare_payoff_selector',
            retryable=True,
            http_status=422,
            provider=provider_name(),
        )
    resolved_card_id = _resolve_selector_reference(selected_card_id, list(index), primary_keys=['card_id'], prefix='payoff', name_keys=['name'])
    if not resolved_card_id and len(allowed_ids) == 1:
        resolved_card_id = allowed_ids[0]
    if not resolved_card_id:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message='chapter_prepare_payoff_selector 失败：AI 返回了不在聚焦爽点压缩索引中的 card_id。',
            stage='chapter_prepare_payoff_selector',
            retryable=True,
            http_status=422,
            provider=provider_name(),
            details={'selected_card_id': selected_card_id, 'resolved_card_id': resolved_card_id, 'allowed_ids': allowed_ids},
        )
    return PayoffSelectionPayload(
        selected_card_id=resolved_card_id,
        selection_note=str(payload.selection_note or "").strip() or "AI 已从聚焦爽点压缩索引中直接选定本章执行卡。",
    )


def _normalize_foreshadowing_selection_payload(payload: ForeshadowingSelectionPayload, planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> ForeshadowingSelectionPayload:
    index = _selection_scope(planning_packet, shortlist).get("foreshadowing") or {}
    candidate_rows = [item for item in (index.get("candidates") or []) if isinstance(item, dict)]
    allowed_ids = [str(item.get("candidate_id") or "").strip() for item in candidate_rows if str(item.get("candidate_id") or "").strip()]
    if not allowed_ids:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message='chapter_prepare_foreshadowing_selector 失败：当前没有可供 AI 终选的伏笔压缩候选。',
            stage='chapter_prepare_foreshadowing_selector',
            retryable=True,
            http_status=422,
            provider=provider_name(),
        )

    raw_primary = str(payload.selected_primary_candidate_id or "").strip()
    resolved_primary = _resolve_selector_reference(
        raw_primary,
        candidate_rows,
        primary_keys=['candidate_id'],
        prefix='foreshadow',
        name_keys=['display_label', 'selector_label', 'legacy_candidate_id', 'summary', 'note', 'source_hook', 'surface_info', 'execution_hint'],
    )
    if not resolved_primary and len(allowed_ids) == 1:
        resolved_primary = allowed_ids[0]

    if not resolved_primary:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message='chapter_prepare_foreshadowing_selector 失败：AI 返回了不在聚焦伏笔压缩索引中的 candidate_id。',
            stage='chapter_prepare_foreshadowing_selector',
            retryable=True,
            http_status=422,
            provider=provider_name(),
            details={
                'selected_primary_candidate_id': raw_primary,
                'resolved_primary_candidate_id': resolved_primary,
                'allowed_ids': allowed_ids,
            },
        )

    selected_primary = resolved_primary
    allowed_set = set(allowed_ids)
    supporting: list[str] = []
    seen: set[str] = {selected_primary}
    for item in (payload.selected_supporting_candidate_ids or []):
        clean = _resolve_selector_reference(
            item,
            candidate_rows,
            primary_keys=['candidate_id'],
            prefix='foreshadow',
            name_keys=['display_label', 'selector_label', 'legacy_candidate_id', 'summary', 'note', 'source_hook', 'surface_info', 'execution_hint'],
        )
        if not clean or clean in seen or clean not in allowed_set:
            continue
        supporting.append(clean)
        seen.add(clean)
        if len(supporting) >= 2:
            break
    return ForeshadowingSelectionPayload(
        selected_primary_candidate_id=selected_primary,
        selected_supporting_candidate_ids=supporting,
        selection_note=str(payload.selection_note or '').strip() or 'AI 已从聚焦伏笔压缩索引中确定本章伏笔动作。',
    )


def _normalize_scene_selection_payload(payload: SceneTemplateSelectionPayload, planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> SceneTemplateSelectionPayload:
    index = (_selection_scope(planning_packet, shortlist).get("scene") or {}).get("scene_templates") or []
    allowed_ids = [str(item.get("scene_template_id") or "").strip() for item in index if isinstance(item, dict) and str(item.get("scene_template_id") or "").strip()]
    target_count = int(((planning_packet or {}).get("scene_template_index") or {}).get("scene_count") or 0) or 1
    selected_ids: list[str] = []
    for raw in (payload.selected_scene_template_ids or []):
        resolved = _resolve_selector_reference(raw, list(index), primary_keys=['scene_template_id'], prefix='scene', name_keys=['scene_name', 'scene_type'])
        if resolved and resolved not in selected_ids:
            selected_ids.append(resolved)
    if not selected_ids:
        selected_ids = allowed_ids[:target_count]
    if len(selected_ids) < target_count:
        for item in allowed_ids:
            if item not in selected_ids:
                selected_ids.append(item)
            if len(selected_ids) >= target_count:
                break
    return SceneTemplateSelectionPayload(
        selected_scene_template_ids=selected_ids[:max(target_count, 1)],
        selection_note=str(payload.selection_note or "").strip() or "AI 已从聚焦场景模板索引里直接选定本章场景链。",
    )


def _normalize_prompt_strategy_selection_payload(payload: PromptStrategySelectionPayload, planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> PromptStrategySelectionPayload:
    bundle = _selection_scope(planning_packet, shortlist).get("prompt") or {}
    index = bundle.get("writing_cards") or bundle.get("prompt_strategies") or []
    flow_index = bundle.get("flow_cards") or bundle.get("flow_templates") or []
    flow_child_index = bundle.get("flow_child_cards") or []
    writing_child_index = bundle.get("writing_child_cards") or []
    allowed_ids = [str(item.get("strategy_id") or item.get("card_id") or "").strip() for item in index if isinstance(item, dict) and str(item.get("strategy_id") or item.get("card_id") or "").strip()]
    allowed_set = set(allowed_ids)
    allowed_flow_ids = [str(item.get("flow_id") or item.get("card_id") or "").strip() for item in flow_index if isinstance(item, dict) and str(item.get("flow_id") or item.get("card_id") or "").strip()]
    selected_ids = [str(item or "").strip() for item in (payload.selected_strategy_ids or []) if str(item or "").strip() in allowed_set]
    if not selected_ids:
        selected_ids = allowed_ids[:3]
    selected_flow_template_id = str(payload.selected_flow_template_id or "").strip()
    if selected_flow_template_id not in set(allowed_flow_ids):
        selected_flow_template_id = str(((planning_packet or {}).get("chapter_identity") or {}).get("flow_template_id") or "").strip()
    if selected_flow_template_id not in set(allowed_flow_ids):
        selected_flow_template_id = allowed_flow_ids[0] if allowed_flow_ids else ""

    allowed_flow_child_ids = [str(item.get("child_id") or item.get("card_id") or "").strip() for item in flow_child_index if isinstance(item, dict) and str(item.get("parent_flow_id") or item.get("parent_id") or "").strip() == selected_flow_template_id]
    selected_flow_child_card_id = str(payload.selected_flow_child_card_id or "").strip()
    if selected_flow_child_card_id not in set(allowed_flow_child_ids):
        selected_flow_child_card_id = allowed_flow_child_ids[0] if allowed_flow_child_ids else ""

    selected_writing_child_card_ids = [str(item or "").strip() for item in (payload.selected_writing_child_card_ids or []) if str(item or "").strip()]
    allowed_writing_child_ids = [str(item.get("child_id") or item.get("card_id") or "").strip() for item in writing_child_index if isinstance(item, dict) and str(item.get("parent_strategy_id") or item.get("parent_id") or "").strip() in set(selected_ids)]
    selected_writing_child_card_ids = [item for item in selected_writing_child_card_ids if item in set(allowed_writing_child_ids)]
    if not selected_writing_child_card_ids:
        per_parent: list[str] = []
        for strategy_id in selected_ids:
            for item in writing_child_index:
                if not isinstance(item, dict):
                    continue
                if str(item.get("parent_strategy_id") or item.get("parent_id") or "").strip() == strategy_id:
                    child_id = str(item.get("child_id") or item.get("card_id") or "").strip()
                    if child_id:
                        per_parent.append(child_id)
                        break
        selected_writing_child_card_ids = per_parent[:4]

    return PromptStrategySelectionPayload(
        selected_flow_template_id=selected_flow_template_id or None,
        selected_flow_child_card_id=selected_flow_child_card_id or None,
        selected_strategy_ids=selected_ids[:4],
        selected_writing_child_card_ids=selected_writing_child_card_ids[:4],
        selection_note=str(payload.selection_note or "").strip() or "AI 已从聚焦流程母卡/子卡与写法母卡/子卡索引里直接选定本章写法。",
    )


__all__ = [
    "ChapterPreparationSelectionResult",
    "is_openai_enabled",
    "raise_ai_required_error",
    "SelectorTaskSpec",
    "_normalize_schedule_review_payload",
    "_enforce_required_card_ids",
    "ChapterCardSelectionPayload",
    "PayoffSelectionPayload",
    "ForeshadowingSelectionPayload",
    "SceneTemplateSelectionPayload",
    "PromptStrategySelectionPayload",
    "ChapterPreparationShortlistPayload",
    "CharacterRelationScheduleReviewPayload",
    "ChapterFrontloadDecisionPayload",
    "StageCharacterReviewPayload",
    "apply_schedule_review_to_packet",
    "choose_chapter_card_selection",
    "review_stage_characters",
    "review_character_relation_schedule",
    "run_chapter_preparation_selection",
    "review_character_relation_schedule_and_select_cards",
    "_normalize_payoff_selection_payload",
    "_normalize_foreshadowing_selection_payload",
    "_normalize_scene_selection_payload",
    "_normalize_prompt_strategy_selection_payload",
    "_selection_scope",
    "_card_index_entries",
    "_compact_for_prompt",
    "_focused_schedule_candidate_index",
    "_focused_card_index",
    "_focused_payoff_candidate_index",
    "_focused_foreshadowing_candidate_index",
    "_selection_layer_overview",
    "_focused_scene_template_index",
    "_focused_prompt_bundle_index",
    "_pretty_json",
]
