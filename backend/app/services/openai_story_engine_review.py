from __future__ import annotations

"""Review helpers extracted from the story engine.

This module owns stage-character review and character-relation schedule review
payloads plus their normalization/application helpers.
"""

import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, is_openai_enabled, provider_name
from app.services.prompt_templates import (
    character_relation_schedule_review_system_prompt,
    character_relation_schedule_review_user_prompt,
    stage_character_review_system_prompt,
    stage_character_review_user_prompt,
)

class CharacterRelationScheduleReviewPayload(BaseModel):
    focus_characters: list[str] = Field(default_factory=list)
    supporting_characters: list[str] = Field(default_factory=list)
    defer_characters: list[str] = Field(default_factory=list)
    main_relation_ids: list[str] = Field(default_factory=list)
    light_touch_relation_ids: list[str] = Field(default_factory=list)
    defer_relation_ids: list[str] = Field(default_factory=list)
    interaction_depth_overrides: dict[str, str] = Field(default_factory=dict)
    relation_push_overrides: dict[str, str] = Field(default_factory=dict)
    stage_casting_verdict: str | None = None
    should_execute_stage_casting_action: bool | None = None
    do_not_force_stage_casting_action: bool | None = None
    stage_casting_reason: str | None = None
    review_note: str | None = None


class StageCharacterReviewPayload(BaseModel):
    stage_start_chapter: int = 0
    stage_end_chapter: int = 0
    next_window_start: int = 0
    next_window_end: int = 0
    focus_characters: list[str] = Field(default_factory=list)
    supporting_characters: list[str] = Field(default_factory=list)
    defer_characters: list[str] = Field(default_factory=list)
    priority_relation_ids: list[str] = Field(default_factory=list)
    light_touch_relation_ids: list[str] = Field(default_factory=list)
    defer_relation_ids: list[str] = Field(default_factory=list)
    casting_strategy: str | None = None
    casting_strategy_note: str | None = None
    max_new_core_entries: int = 0
    max_role_refreshes: int = 0
    should_introduce_character: bool | None = None
    candidate_slot_ids: list[str] = Field(default_factory=list)
    should_refresh_role_functions: bool | None = None
    role_refresh_targets: list[str] = Field(default_factory=list)
    role_refresh_suggestions: list[dict[str, str]] = Field(default_factory=list)
    next_window_tasks: list[str] = Field(default_factory=list)
    watchouts: list[str] = Field(default_factory=list)
    review_note: str | None = None
    source: str | None = None






def _schedule_valid_character_names(planning_packet: dict[str, Any]) -> list[str]:
    packet = planning_packet or {}
    names: list[str] = []
    relevant = (packet.get("relevant_cards") or {}) if isinstance(packet, dict) else {}
    names.extend([str(name or "").strip() for name in (relevant.get("characters") or {}).keys()])
    card_index = (packet.get("card_index") or {}) if isinstance(packet, dict) else {}
    for item in card_index.get("characters") or []:
        if isinstance(item, dict):
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

def _raise_ai_required_error(*, stage: str, message: str, detail_reason: str = "", retryable: bool = True) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"{message}{('：' + detail_reason) if detail_reason else ''}",
        stage=stage,
        retryable=retryable,
        http_status=503,
        provider=provider_name(),
        details={"reason": detail_reason} if detail_reason else None,
    )

def _heuristic_character_relation_schedule_review(chapter_plan: dict[str, Any], planning_packet: dict[str, Any]) -> CharacterRelationScheduleReviewPayload:
    packet = planning_packet or {}
    schedule = (packet.get("character_relation_schedule") or {}) if isinstance(packet, dict) else {}
    appearance = (schedule.get("appearance_schedule") or {}) if isinstance(schedule, dict) else {}
    relation = (schedule.get("relationship_schedule") or {}) if isinstance(schedule, dict) else {}
    valid_characters = _schedule_valid_character_names(packet)
    valid_relations = _schedule_valid_relation_ids(packet)
    focus_name = str(((packet.get("selected_elements") or {}).get("focus_character")) or "").strip()
    protagonist = valid_characters[0] if valid_characters else ""
    priority_character_rows = [item for item in (appearance.get("priority_characters") or []) if isinstance(item, dict)]
    due_characters = [str(item or "").strip() for item in (appearance.get("due_characters") or []) if str(item or "").strip()]
    resting_characters = [str(item or "").strip() for item in (appearance.get("resting_characters") or []) if str(item or "").strip()]
    focus_characters: list[str] = []
    for name in [protagonist, focus_name] + due_characters:
        if name and name in valid_characters and name not in focus_characters:
            focus_characters.append(name)
        if len(focus_characters) >= 3:
            break
    supporting: list[str] = []
    for row in priority_character_rows:
        name = str(row.get("name") or "").strip()
        if not name or name not in valid_characters or name in focus_characters or name in supporting:
            continue
        due_status = str(row.get("due_status") or "").strip()
        if due_status in {"本章焦点", "该回场", "可推进", "到窗可登场", "本章默认在场"}:
            supporting.append(name)
        if len(supporting) >= 3:
            break
    defer_characters: list[str] = []
    for name in resting_characters:
        if name and name in valid_characters and name not in focus_characters and name not in supporting and name not in defer_characters:
            defer_characters.append(name)
        if len(defer_characters) >= 3:
            break
    priority_relation_rows = [item for item in (relation.get("priority_relations") or []) if isinstance(item, dict)]
    due_relations = [str(item or "").strip() for item in (relation.get("due_relations") or []) if str(item or "").strip()]
    main_relations: list[str] = []
    for rid in due_relations:
        if rid in valid_relations and rid not in main_relations:
            main_relations.append(rid)
        if len(main_relations) >= 2:
            break
    light_touch: list[str] = []
    for row in priority_relation_rows:
        rid = str(row.get("relation_id") or "").strip()
        if not rid or rid not in valid_relations or rid in main_relations or rid in light_touch:
            continue
        due_status = str(row.get("due_status") or "").strip()
        if due_status in {"本章应动", "该推进", "可推进", "可建立", "轻触或略过"}:
            light_touch.append(rid)
        if len(light_touch) >= 3:
            break
    defer_relations: list[str] = []
    for row in priority_relation_rows:
        rid = str(row.get("relation_id") or "").strip()
        if not rid or rid in main_relations or rid in light_touch or rid not in valid_relations or rid in defer_relations:
            continue
        if str(row.get("due_status") or "").strip() in {"待时机", "轻触或略过", "备用"}:
            defer_relations.append(rid)
        if len(defer_relations) >= 3:
            break
    interaction_depth_overrides = {}
    relation_push_overrides = {}
    for row in priority_relation_rows[:4]:
        rid = str(row.get("relation_id") or "").strip()
        if rid in main_relations:
            depth = str(row.get("interaction_depth") or "").strip()
            push = str(row.get("push_direction") or "").strip()
            if depth:
                interaction_depth_overrides[rid] = depth
            if push:
                relation_push_overrides[rid] = push
    stage_hint = (packet.get("chapter_stage_casting_hint") or {}) if isinstance(packet, dict) else {}
    planned_action = str(stage_hint.get("planned_action") or "").strip()
    local_should_execute = bool(stage_hint.get("should_execute_planned_action"))
    local_do_not_force = bool(stage_hint.get("do_not_force_action"))
    recommended_action = str(stage_hint.get("recommended_action") or "").strip()
    if planned_action and local_should_execute:
        stage_casting_verdict = "execute_now"
        should_execute_stage_casting_action = True
        do_not_force_stage_casting_action = False
        stage_casting_reason = "窗口允许且本章已承担该动作，默认优先自然落实。"
    elif planned_action and local_do_not_force:
        stage_casting_verdict = "defer_to_next"
        should_execute_stage_casting_action = False
        do_not_force_stage_casting_action = True
        stage_casting_reason = "虽然有预定动作，但当前窗口或目标不匹配，默认先别硬塞。"
    elif recommended_action in {"consider_new_core_entry", "consider_role_refresh", "balanced_light"}:
        stage_casting_verdict = "soft_consider"
        should_execute_stage_casting_action = False
        do_not_force_stage_casting_action = True
        stage_casting_reason = "本章最多轻量考虑人物投放动作，不建议硬执行。"
    else:
        stage_casting_verdict = "hold_steady"
        should_execute_stage_casting_action = False
        do_not_force_stage_casting_action = True
        stage_casting_reason = "本章默认稳住现有人物线，不额外承担人物投放动作。"
    note = "优先抓住本章最该正面推进的人物和关系，其余只做辅助或暂缓。"
    return CharacterRelationScheduleReviewPayload(
        focus_characters=focus_characters,
        supporting_characters=supporting,
        defer_characters=defer_characters,
        main_relation_ids=main_relations,
        light_touch_relation_ids=light_touch,
        defer_relation_ids=defer_relations,
        interaction_depth_overrides=interaction_depth_overrides,
        relation_push_overrides=relation_push_overrides,
        stage_casting_verdict=stage_casting_verdict,
        should_execute_stage_casting_action=should_execute_stage_casting_action,
        do_not_force_stage_casting_action=do_not_force_stage_casting_action,
        stage_casting_reason=stage_casting_reason,
        review_note=note,
    )


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
        out=[]; seen=set()
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
    focus_name = str(focus_name or "").strip()
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


def _normalize_stage_character_review_payload(payload: Any, snapshot: dict[str, Any]) -> StageCharacterReviewPayload:
    from app.services.stage_review_support import normalize_stage_character_review

    if isinstance(payload, StageCharacterReviewPayload):
        source = payload.model_dump(mode="python")
    elif isinstance(payload, dict):
        source = payload
    else:
        source = {}
    normalized = normalize_stage_character_review(source, snapshot)
    return StageCharacterReviewPayload.model_validate(normalized)



def review_stage_characters(
    *,
    snapshot: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> StageCharacterReviewPayload:
    if not is_openai_enabled():
        payload = _normalize_stage_character_review_payload({"source": "heuristic"}, snapshot)
        if not payload.source:
            payload.source = "heuristic"
        return payload

    base_timeout_seconds = request_timeout_seconds or int(getattr(settings, "stage_character_review_timeout_seconds", 60) or 60)
    max_output_tokens = max(int(getattr(settings, "stage_character_review_max_output_tokens", 520) or 520), 220)
    retry_attempts = max(int(getattr(settings, "stage_character_review_retry_attempts", 3) or 3), 1)
    retry_backoff_ms = max(int(getattr(settings, "stage_character_review_retry_backoff_ms", 1200) or 1200), 0)
    last_generation_error: GenerationError | None = None

    for attempt_no in range(1, retry_attempts + 1):
        timeout_seconds = max(base_timeout_seconds, 1)
        try:
            data = call_json_response(
                stage="stage_character_review",
                system_prompt=stage_character_review_system_prompt(),
                user_prompt=stage_character_review_user_prompt(snapshot=snapshot),
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
            )
            return _normalize_stage_character_review_payload(data, snapshot)
        except GenerationError as exc:
            last_generation_error = exc
            if exc.code != ErrorCodes.API_TIMEOUT or attempt_no >= retry_attempts:
                raise
            if retry_backoff_ms > 0:
                time.sleep(retry_backoff_ms / 1000)
        except Exception as exc:
            _raise_ai_required_error(
                stage="stage_character_review",
                message="阶段性人物复盘失败，已停止生成",
                detail_reason=str(exc),
                retryable=True,
            )

    if last_generation_error is not None:
        raise last_generation_error

    _raise_ai_required_error(
        stage="stage_character_review",
        message="阶段性人物复盘失败，已停止生成",
        retryable=True,
    )



def review_character_relation_schedule(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> CharacterRelationScheduleReviewPayload:
    if not (planning_packet or {}).get("character_relation_schedule"):
        return CharacterRelationScheduleReviewPayload()
    if not is_openai_enabled():
        return _normalize_schedule_review_payload(_heuristic_character_relation_schedule_review(chapter_plan, planning_packet), planning_packet)
    timeout_seconds = request_timeout_seconds or int(getattr(settings, "character_relation_schedule_review_timeout_seconds", 10) or 10)
    try:
        data = call_json_response(
            stage="character_relation_schedule_review",
            system_prompt=character_relation_schedule_review_system_prompt(),
            user_prompt=character_relation_schedule_review_user_prompt(chapter_plan=chapter_plan, planning_packet=planning_packet),
            max_output_tokens=max(int(getattr(settings, "character_relation_schedule_review_max_output_tokens", 360) or 360), 160),
            timeout_seconds=timeout_seconds,
        )
        payload = CharacterRelationScheduleReviewPayload.model_validate(data)
        return _normalize_schedule_review_payload(payload, planning_packet)
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            stage="character_relation_schedule_review",
            message="角色与关系调度复核失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )


def apply_schedule_review_to_packet(
    planning_packet: dict[str, Any],
    review: CharacterRelationScheduleReviewPayload,
) -> dict[str, Any]:
    if not isinstance(planning_packet, dict):
        return planning_packet
    normalized = _normalize_schedule_review_payload(review, planning_packet)
    payload = normalized.model_dump(mode="python")
    payload["soft_rule"] = "角色与关系调度由 AI 统一复核与裁定，默认按 AI 结果推进本章重点。"
    planning_packet["character_relation_schedule_ai"] = payload
    selected = planning_packet.setdefault("selected_elements", {})
    selected["ai_focus_characters"] = list(payload.get("focus_characters") or [])
    selected["ai_main_relations"] = list(payload.get("main_relation_ids") or [])

    stage_hint = planning_packet.get("chapter_stage_casting_hint") or {}
    if isinstance(stage_hint, dict) and stage_hint:
        local_should_execute = bool(stage_hint.get("should_execute_planned_action"))
        local_do_not_force = bool(stage_hint.get("do_not_force_action"))
        ai_verdict = str(payload.get("stage_casting_verdict") or "").strip() or None
        ai_reason = str(payload.get("stage_casting_reason") or "").strip() or None
        final_should_execute = bool(payload.get("should_execute_stage_casting_action")) if local_should_execute else False
        final_do_not_force = True if local_do_not_force else (bool(payload.get("do_not_force_stage_casting_action")) or not final_should_execute)
        if ai_verdict == "execute_now" and not local_should_execute:
            ai_verdict = "defer_to_next" if stage_hint.get("planned_action") else "hold_steady"
            final_should_execute = False
            final_do_not_force = True
            if not ai_reason:
                ai_reason = "窗口名额或本地提示不支持本章硬执行人物投放动作，先别强推。"
        if ai_verdict == "execute_now":
            final_action_priority = "must_execute"
            final_recommended_action = stage_hint.get("recommended_action") or "execute_now"
        elif ai_verdict == "soft_consider":
            final_action_priority = "soft_consider"
            final_recommended_action = "soft_consider"
        else:
            final_action_priority = "avoid" if stage_hint.get("planned_action") else "hold"
            final_recommended_action = "hold_steady" if ai_verdict == "hold_steady" else (stage_hint.get("recommended_action") or "defer_to_next")
        stage_hint["ai_stage_casting_verdict"] = ai_verdict
        stage_hint["ai_stage_casting_reason"] = ai_reason
        stage_hint["ai_should_execute_planned_action"] = bool(payload.get("should_execute_stage_casting_action"))
        stage_hint["ai_do_not_force_action"] = bool(payload.get("do_not_force_stage_casting_action"))
        stage_hint["final_should_execute_planned_action"] = final_should_execute
        stage_hint["final_do_not_force_action"] = final_do_not_force
        stage_hint["final_action_priority"] = final_action_priority
        stage_hint["final_recommended_action"] = final_recommended_action
        if ai_reason:
            base_hint = str(stage_hint.get("chapter_hint") or "").strip()
            stage_hint["chapter_hint"] = (f"{base_hint} AI复核：{ai_reason}".strip())[:120] if base_hint else f"AI复核：{ai_reason}"[:120]
        planning_packet["chapter_stage_casting_hint"] = stage_hint

    input_policy = planning_packet.setdefault("input_policy", {})
    input_policy["schedule_review_rule"] = "角色与关系调度及人物投放提示统一交给 AI 复核；AI 不可用时直接报错停止，不再回退到本地兜底。"
    return planning_packet



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
    "CharacterRelationScheduleReviewPayload",
    "StageCharacterReviewPayload",
    "_heuristic_character_relation_schedule_review",
    "_normalize_schedule_review_payload",
    "_normalize_stage_character_review_payload",
    "review_stage_characters",
    "review_character_relation_schedule",
    "apply_schedule_review_to_packet",
]
