from __future__ import annotations

"""Selection/review boundary for chapter-preparation AI calls.

This module exposes a smaller, more stable surface than the monolithic
``openai_story_engine``. Selection-specific shaping helpers now live here,
so prompt builders and execution code do not need to reach back into engine
internals for every compact/focused index operation.
"""

import json
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


class SceneTemplateSelectionPayload(BaseModel):
    selected_scene_template_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


class PromptStrategySelectionPayload(BaseModel):
    selected_flow_template_id: str | None = None
    selected_strategy_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


class ChapterPreparationShortlistPayload(BaseModel):
    focus_characters: list[str] = Field(default_factory=list)
    main_relation_ids: list[str] = Field(default_factory=list)
    card_candidate_ids: list[str] = Field(default_factory=list)
    payoff_candidate_ids: list[str] = Field(default_factory=list)
    scene_template_ids: list[str] = Field(default_factory=list)
    flow_template_ids: list[str] = Field(default_factory=list)
    prompt_strategy_ids: list[str] = Field(default_factory=list)
    shortlist_note: str | None = None


class ChapterPreparationSelectionResult(BaseModel):
    schedule_review: CharacterRelationScheduleReviewPayload = Field(default_factory=lambda: CharacterRelationScheduleReviewPayload())
    card_selection: ChapterCardSelectionPayload = Field(default_factory=lambda: ChapterCardSelectionPayload())
    payoff_selection: PayoffSelectionPayload = Field(default_factory=lambda: PayoffSelectionPayload())
    scene_selection: SceneTemplateSelectionPayload = Field(default_factory=lambda: SceneTemplateSelectionPayload())
    prompt_strategy_selection: PromptStrategySelectionPayload = Field(default_factory=lambda: PromptStrategySelectionPayload())
    selection_trace: dict[str, Any] = Field(default_factory=dict)


class ChapterFrontloadDecisionPayload(BaseModel):
    schedule_review: CharacterRelationScheduleReviewPayload = Field(default_factory=lambda: CharacterRelationScheduleReviewPayload())
    card_selection: ChapterCardSelectionPayload = Field(default_factory=ChapterCardSelectionPayload)
    payoff_selection: PayoffSelectionPayload = Field(default_factory=PayoffSelectionPayload)
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
    if not shortlist:
        return payoff_index
    wanted = {str(item or '').strip() for item in (shortlist.get('payoff_candidate_ids') or []) if str(item or '').strip()}
    candidates = [item for item in (payoff_index.get('candidates') or []) if isinstance(item, dict)]
    if not wanted:
        return payoff_index
    focused = [item for item in candidates if str(item.get('card_id') or '').strip() in wanted]
    return {
        **{k: v for k, v in payoff_index.items() if k != 'candidates'},
        'candidates': focused or candidates[:3],
        'focus_counts': {'focused': len(focused or []), 'full': len(candidates)},
    }


def _focused_scene_template_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    scene_index = (packet.get('scene_template_index') or {}) if isinstance(packet, dict) else {}
    if not shortlist:
        return scene_index
    wanted = {str(item or '').strip() for item in (shortlist.get('scene_template_ids') or []) if str(item or '').strip()}
    templates = [item for item in (scene_index.get('scene_templates') or []) if isinstance(item, dict)]
    if not wanted:
        return scene_index
    focused = [item for item in templates if str(item.get('scene_template_id') or '').strip() in wanted]
    return {
        **{k: v for k, v in scene_index.items() if k != 'scene_templates'},
        'scene_templates': focused or templates[:4],
        'focus_counts': {'focused': len(focused or []), 'full': len(templates)},
    }


def _focused_prompt_bundle_index(packet: dict[str, Any], shortlist: dict[str, Any] | None) -> dict[str, Any]:
    bundle = (packet.get('prompt_bundle_index') or {}) if isinstance(packet, dict) else {}
    if not shortlist:
        return bundle
    wanted_flow = {str(item or '').strip() for item in (shortlist.get('flow_template_ids') or []) if str(item or '').strip()}
    wanted_prompt = {str(item or '').strip() for item in (shortlist.get('prompt_strategy_ids') or []) if str(item or '').strip()}
    flows = [item for item in (bundle.get('flow_templates') or []) if isinstance(item, dict)]
    prompts = [item for item in (bundle.get('prompt_strategies') or []) if isinstance(item, dict)]
    focused_flows = [item for item in flows if str(item.get('flow_id') or '').strip() in wanted_flow]
    focused_prompts = [item for item in prompts if str(item.get('strategy_id') or '').strip() in wanted_prompt]
    return {
        'flow_templates': focused_flows or flows[:4],
        'prompt_strategies': focused_prompts or prompts[:6],
        'focus_counts': {
            'flow_templates': {'focused': len(focused_flows or []), 'full': len(flows)},
            'prompt_strategies': {'focused': len(focused_prompts or []), 'full': len(prompts)},
        },
    }


def _selection_scope(packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> dict[str, Any]:
    packet = packet or {}
    focused_schedule = _focused_schedule_candidate_index(packet, shortlist)
    focused_cards = _focused_card_index(packet, shortlist)
    focused_payoff = _focused_payoff_candidate_index(packet, shortlist)
    focused_scene = _focused_scene_template_index(packet, shortlist)
    focused_prompt = _focused_prompt_bundle_index(packet, shortlist)
    return {
        "schedule": focused_schedule,
        "cards": focused_cards,
        "payoff": focused_payoff,
        "scene": focused_scene,
        "prompt": focused_prompt,
        "stats": {
            "schedule": {
                "appearance_candidates": len((focused_schedule.get("appearance_candidates") or [])),
                "relation_candidates": len((focused_schedule.get("relation_candidates") or [])),
            },
            "cards": {bucket: len((focused_cards.get(bucket) or [])) for bucket in ["characters", "resources", "factions", "relations"]},
            "payoff": {"candidates": len((focused_payoff.get("candidates") or []))},
            "scene": {"scene_templates": len((focused_scene.get("scene_templates") or []))},
            "prompt": {
                "flow_templates": len((focused_prompt.get("flow_templates") or [])),
                "prompt_strategies": len((focused_prompt.get("prompt_strategies") or [])),
            },
        },
    }


def _normalize_payoff_selection_payload(payload: PayoffSelectionPayload, planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> PayoffSelectionPayload:
    index = (_selection_scope(planning_packet, shortlist).get("payoff") or {}).get("candidates") or []
    allowed_ids = [str(item.get("card_id") or "").strip() for item in index if isinstance(item, dict) and str(item.get("card_id") or "").strip()]
    selected_card_id = str(payload.selected_card_id or "").strip()
    if selected_card_id not in set(allowed_ids):
        selected_card_id = allowed_ids[0] if allowed_ids else ""
    return PayoffSelectionPayload(
        selected_card_id=selected_card_id or None,
        selection_note=str(payload.selection_note or "").strip() or "AI 已从聚焦爽点候选中直接选定本章执行卡。",
    )


def _normalize_scene_selection_payload(payload: SceneTemplateSelectionPayload, planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> SceneTemplateSelectionPayload:
    index = (_selection_scope(planning_packet, shortlist).get("scene") or {}).get("scene_templates") or []
    allowed_ids = [str(item.get("scene_template_id") or "").strip() for item in index if isinstance(item, dict) and str(item.get("scene_template_id") or "").strip()]
    allowed_set = set(allowed_ids)
    selected_ids = [str(item or "").strip() for item in (payload.selected_scene_template_ids or []) if str(item or "").strip() in allowed_set]
    target_count = int(((planning_packet or {}).get("scene_template_index") or {}).get("scene_count") or 0) or 1
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
    index = bundle.get("prompt_strategies") or []
    flow_index = bundle.get("flow_templates") or []
    allowed_ids = [str(item.get("strategy_id") or "").strip() for item in index if isinstance(item, dict) and str(item.get("strategy_id") or "").strip()]
    allowed_set = set(allowed_ids)
    allowed_flow_ids = [str(item.get("flow_id") or "").strip() for item in flow_index if isinstance(item, dict) and str(item.get("flow_id") or "").strip()]
    selected_ids = [str(item or "").strip() for item in (payload.selected_strategy_ids or []) if str(item or "").strip() in allowed_set]
    if not selected_ids:
        selected_ids = allowed_ids[:3]
    selected_flow_template_id = str(payload.selected_flow_template_id or "").strip()
    if selected_flow_template_id not in set(allowed_flow_ids):
        selected_flow_template_id = str(((planning_packet or {}).get("chapter_identity") or {}).get("flow_template_id") or "").strip()
    if selected_flow_template_id not in set(allowed_flow_ids):
        selected_flow_template_id = allowed_flow_ids[0] if allowed_flow_ids else ""
    return PromptStrategySelectionPayload(
        selected_flow_template_id=selected_flow_template_id or None,
        selected_strategy_ids=selected_ids[:4],
        selection_note=str(payload.selection_note or "").strip() or "AI 已从聚焦 prompt / 流程压缩索引里直接选定本章写法。",
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
    "_normalize_scene_selection_payload",
    "_normalize_prompt_strategy_selection_payload",
    "_selection_scope",
    "_card_index_entries",
    "_compact_for_prompt",
    "_focused_schedule_candidate_index",
    "_focused_card_index",
    "_focused_payoff_candidate_index",
    "_focused_scene_template_index",
    "_focused_prompt_bundle_index",
    "_pretty_json",
]
