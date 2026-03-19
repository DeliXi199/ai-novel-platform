from __future__ import annotations

"""Review helpers extracted from the story engine.

This module owns stage-character review and character-relation schedule review
payloads plus their normalization/application helpers.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, is_openai_enabled, provider_name
from app.services.prompt_templates import (
    character_relation_schedule_review_system_prompt,
    character_relation_schedule_review_user_prompt,
    scene_continuity_review_system_prompt,
    scene_continuity_review_user_prompt,
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


class SceneContinuityReviewPayload(BaseModel):
    must_continue_same_scene: bool | None = None
    recommended_scene_count: int | None = None
    transition_mode: str | None = None
    allowed_transition: str | None = None
    opening_anchor: str | None = None
    must_carry_over: list[str] = Field(default_factory=list)
    cut_plan: list[dict[str, Any]] = Field(default_factory=list)
    scene_sequence_plan: list[dict[str, Any]] = Field(default_factory=list)
    review_note: str | None = None



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



def _scene_review_text(value: Any, limit: int = 96) -> str:
    return str(value or "").strip()[:limit]


def _scene_review_plan_signals(planning_packet: dict[str, Any], chapter_plan: dict[str, Any] | None = None) -> dict[str, str]:
    plan = chapter_plan or {}
    packet = planning_packet or {}
    selected_flow_card = (packet.get("selected_flow_card") or {}) if isinstance(packet.get("selected_flow_card"), dict) else {}
    continuity_window = (packet.get("continuity_window") or {}) if isinstance(packet.get("continuity_window"), dict) else {}
    handoff = (continuity_window.get("scene_handoff_card") or {}) if isinstance(continuity_window.get("scene_handoff_card"), dict) else {}
    return {
        "goal": _scene_review_text(plan.get("goal")),
        "conflict": _scene_review_text(plan.get("conflict")),
        "main_scene": _scene_review_text(plan.get("main_scene") or selected_flow_card.get("scene_label"), 64),
        "opening_beat": _scene_review_text(plan.get("opening_beat")),
        "mid_turn": _scene_review_text(plan.get("mid_turn")),
        "closing_image": _scene_review_text(plan.get("closing_image")),
        "ending_hook": _scene_review_text(plan.get("ending_hook")),
        "handoff_anchor": _scene_review_text(handoff.get("next_opening_anchor") or continuity_window.get("opening_anchor")),
        "handoff_status": _scene_review_text(handoff.get("scene_status_at_end"), 64),
    }


def _synthesize_scene_sequence_plan(
    *,
    scene_count: int,
    opening_anchor: str,
    must_carry_over: list[str],
    planning_packet: dict[str, Any],
    chapter_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    scene_count = max(1, min(int(scene_count or 1), 3))
    signals = _scene_review_plan_signals(planning_packet, chapter_plan)
    goal = signals.get("goal") or "推进本章主动作"
    conflict = signals.get("conflict") or "当前压力仍在眼前"
    opening_beat = signals.get("opening_beat") or opening_anchor or signals.get("handoff_anchor") or "先接住上一章留下的动作与后果"
    mid_turn = signals.get("mid_turn") or f"围绕{goal[:18]}出现一次受阻、误判或条件变化"
    closing_image = signals.get("closing_image") or signals.get("ending_hook") or f"围绕{goal[:18]}收在一个可见结果上"
    main_scene = signals.get("main_scene") or "当前主场景"
    carry = [str(item or "").strip()[:56] for item in (must_carry_over or []) if str(item or "").strip()][:4]

    templates: list[dict[str, str]] = []
    if scene_count == 1:
        templates = [
            {
                "scene_name": f"{main_scene[:12] or '单场推进'}",
                "scene_role": "opening",
                "purpose": goal,
                "transition_in": opening_beat,
                "target_result": closing_image,
            }
        ]
    elif scene_count == 2:
        templates = [
            {
                "scene_name": "续场承压",
                "scene_role": "opening",
                "purpose": opening_beat if len(opening_beat) <= 120 else goal,
                "transition_in": opening_beat,
                "target_result": mid_turn,
            },
            {
                "scene_name": "推进落点",
                "scene_role": "ending",
                "purpose": goal,
                "transition_in": mid_turn,
                "target_result": closing_image,
            },
        ]
    else:
        templates = [
            {
                "scene_name": "续场承压",
                "scene_role": "opening",
                "purpose": opening_beat if len(opening_beat) <= 120 else goal,
                "transition_in": opening_beat,
                "target_result": mid_turn,
            },
            {
                "scene_name": "中段变招",
                "scene_role": "main",
                "purpose": goal,
                "transition_in": mid_turn,
                "target_result": conflict,
            },
            {
                "scene_name": "收束留钩",
                "scene_role": "ending",
                "purpose": closing_image,
                "transition_in": conflict,
                "target_result": signals.get("ending_hook") or closing_image,
            },
        ]

    plan_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(templates, start=1):
        plan_rows.append({
            "scene_no": idx,
            "scene_name": _scene_review_text(row.get("scene_name") or f"第{idx}场", 32) or f"第{idx}场",
            "scene_role": _scene_review_text(row.get("scene_role") or "main", 16) or "main",
            "purpose": _scene_review_text(row.get("purpose") or goal, 120) or goal,
            "transition_in": _scene_review_text(row.get("transition_in") or opening_anchor or goal, 96) or goal,
            "target_result": _scene_review_text(row.get("target_result") or closing_image or goal, 96) or goal,
            "must_carry_over": carry,
        })
    return plan_rows


def _synthesize_scene_cut_plan(*, scene_sequence_plan: list[dict[str, Any]], scene_count: int) -> list[dict[str, Any]]:
    if scene_count <= 1 or len(scene_sequence_plan) <= 1:
        return []
    cut_rows: list[dict[str, Any]] = []
    for idx in range(1, min(scene_count, len(scene_sequence_plan))):
        current_scene = scene_sequence_plan[idx - 1]
        next_scene = scene_sequence_plan[idx]
        cut_rows.append({
            "cut_after_scene_no": idx,
            "reason": _scene_review_text(current_scene.get("target_result") or current_scene.get("purpose") or "先拿到阶段结果再切场", 96) or "先拿到阶段结果再切场",
            "required_result": _scene_review_text(current_scene.get("target_result") or current_scene.get("purpose") or "完成当前场阶段结果", 96) or "完成当前场阶段结果",
            "transition_anchor": _scene_review_text(next_scene.get("transition_in") or next_scene.get("purpose") or "切场后先接住上一场结果", 96) or "切场后先接住上一场结果",
        })
    return cut_rows

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




SCENE_TRANSITION_MODES = {"continue_same_scene", "soft_cut", "single_scene"}
SCENE_ALLOWED_TRANSITIONS = {"stay_in_scene", "resolve_then_cut", "soft_cut_only", "time_skip_allowed"}


def _normalize_scene_continuity_review_payload(payload: Any, planning_packet: dict[str, Any], chapter_plan: dict[str, Any] | None = None) -> SceneContinuityReviewPayload:
    if isinstance(payload, SceneContinuityReviewPayload):
        data = payload.model_dump(mode="python")
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {}

    missing: list[str] = []

    must_continue_raw = data.get("must_continue_same_scene")
    if must_continue_raw is None:
        missing.append("must_continue_same_scene")
        must_continue = False
    else:
        must_continue = bool(must_continue_raw)

    try:
        scene_count = int(data.get("recommended_scene_count"))
    except Exception:
        scene_count = 0
    if scene_count < 1 or scene_count > 3:
        missing.append("recommended_scene_count")

    transition_mode = str(data.get("transition_mode") or "").strip()
    if transition_mode not in SCENE_TRANSITION_MODES:
        missing.append("transition_mode")

    allowed_transition = str(data.get("allowed_transition") or "").strip()
    if allowed_transition not in SCENE_ALLOWED_TRANSITIONS:
        missing.append("allowed_transition")

    opening_anchor = str(data.get("opening_anchor") or "").strip()[:120]
    if not opening_anchor:
        missing.append("opening_anchor")

    must_carry_over: list[str] = []
    seen_carry: set[str] = set()
    raw_carry = data.get("must_carry_over")
    if isinstance(raw_carry, list):
        for item in raw_carry:
            text = str(item or "").strip()[:56]
            if not text or text in seen_carry:
                continue
            seen_carry.add(text)
            must_carry_over.append(text)
            if len(must_carry_over) >= 5:
                break

    normalized_cut_plan: list[dict[str, Any]] = []
    raw_cut_plan = data.get("cut_plan")
    if isinstance(raw_cut_plan, list) and scene_count >= 1:
        seen_cut_points: set[int] = set()
        for item in raw_cut_plan:
            if not isinstance(item, dict):
                continue
            try:
                cut_after = int(item.get("cut_after_scene_no") or 0)
            except Exception:
                cut_after = 0
            if cut_after < 1 or cut_after >= scene_count or cut_after in seen_cut_points:
                continue
            seen_cut_points.add(cut_after)
            reason = str(item.get("reason") or "").strip()[:96]
            required_result = str(item.get("required_result") or "").strip()[:96]
            transition_anchor = str(item.get("transition_anchor") or "").strip()[:96]
            if not reason or not required_result or not transition_anchor:
                continue
            normalized_cut_plan.append({
                "cut_after_scene_no": cut_after,
                "reason": reason,
                "required_result": required_result,
                "transition_anchor": transition_anchor,
            })
        normalized_cut_plan.sort(key=lambda row: row.get("cut_after_scene_no") or 0)

    expected_cut_count = max(scene_count - 1, 0)
    if scene_count <= 1:
        normalized_cut_plan = []

    normalized_sequence: list[dict[str, Any]] = []
    raw_sequence = data.get("scene_sequence_plan")
    if isinstance(raw_sequence, list):
        for idx, item in enumerate(raw_sequence, start=1):
            if not isinstance(item, dict):
                continue
            try:
                scene_no = int(item.get("scene_no") or idx)
            except Exception:
                scene_no = idx
            scene_role = str(item.get("scene_role") or "").strip()
            purpose = str(item.get("purpose") or "").strip()[:120]
            transition_in = str(item.get("transition_in") or "").strip()[:96]
            target_result = str(item.get("target_result") or "").strip()[:96]
            if scene_role not in {"opening", "main", "ending", "bridge"}:
                continue
            if not purpose or not transition_in or not target_result:
                continue
            normalized_sequence.append({
                "scene_no": scene_no,
                "scene_name": str(item.get("scene_name") or f"第{scene_no}场").strip()[:32],
                "scene_role": scene_role,
                "purpose": purpose,
                "transition_in": transition_in,
                "target_result": target_result,
                "must_carry_over": must_carry_over[:4],
            })
    normalized_sequence.sort(key=lambda row: row.get("scene_no") or 0)
    if scene_count >= 1 and len(normalized_sequence) != scene_count:
        normalized_sequence = _synthesize_scene_sequence_plan(
            scene_count=scene_count,
            opening_anchor=opening_anchor,
            must_carry_over=must_carry_over,
            planning_packet=planning_packet,
            chapter_plan=chapter_plan,
        )

    if scene_count > 1 and len(normalized_cut_plan) != expected_cut_count:
        normalized_cut_plan = _synthesize_scene_cut_plan(
            scene_sequence_plan=normalized_sequence,
            scene_count=scene_count,
        )

    review_note = str(data.get("review_note") or "").strip()[:120] or None
    if missing:
        _raise_ai_required_error(
            stage="scene_continuity_review",
            message="场景连续性评审结果不完整，已停止生成",
            detail_reason="缺少或非法字段：" + ", ".join(dict.fromkeys(missing)),
            retryable=True,
        )

    return SceneContinuityReviewPayload(
        must_continue_same_scene=must_continue,
        recommended_scene_count=scene_count,
        transition_mode=transition_mode,
        allowed_transition=allowed_transition,
        opening_anchor=opening_anchor,
        must_carry_over=must_carry_over,
        cut_plan=normalized_cut_plan,
        scene_sequence_plan=normalized_sequence,
        review_note=review_note,
    )


def review_scene_continuity(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> SceneContinuityReviewPayload:
    if not is_openai_enabled():
        _raise_ai_required_error(
            stage="scene_continuity_review",
            message="场景连续性评审必须依赖 AI，当前未配置可用模型",
            detail_reason="scene_continuity_review requires AI and no local fallback is allowed",
            retryable=False,
        )
    timeout_seconds = request_timeout_seconds or int(getattr(settings, "scene_continuity_ai_timeout_seconds", 26) or 26)
    try:
        data = call_json_response(
            stage="scene_continuity_review",
            system_prompt=scene_continuity_review_system_prompt(),
            user_prompt=scene_continuity_review_user_prompt(chapter_plan=chapter_plan, planning_packet=planning_packet),
            max_output_tokens=max(int(getattr(settings, "scene_continuity_ai_max_output_tokens", 560) or 560), 220),
            timeout_seconds=timeout_seconds,
        )
        return _normalize_scene_continuity_review_payload(data, planning_packet, chapter_plan)
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            stage="scene_continuity_review",
            message="场景连续性评审失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )


def apply_scene_continuity_review_to_packet(
    planning_packet: dict[str, Any],
    review: SceneContinuityReviewPayload,
) -> dict[str, Any]:
    if not isinstance(planning_packet, dict):
        return planning_packet
    normalized = _normalize_scene_continuity_review_payload(review, planning_packet)
    payload = normalized.model_dump(mode="python")
    payload["soft_rule"] = "场景连续性的续场/切场/过渡锚点必须由 AI 决定，本地不再提供任何替代方案。"
    planning_packet["scene_continuity_review"] = payload
    planning_packet["scene_continuity_ai"] = payload
    return planning_packet

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

    timeout_seconds = request_timeout_seconds or int(getattr(settings, "stage_character_review_timeout_seconds", 10) or 10)
    max_output_tokens = max(int(getattr(settings, "stage_character_review_max_output_tokens", 420) or 420), 220)
    try:
        data = call_json_response(
            stage="stage_character_review",
            system_prompt=stage_character_review_system_prompt(),
            user_prompt=stage_character_review_user_prompt(snapshot=snapshot),
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        return _normalize_stage_character_review_payload(data, snapshot)
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            stage="stage_character_review",
            message="阶段性人物复盘失败，已停止生成",
            detail_reason=str(exc),
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
    "CharacterRelationScheduleReviewPayload",
    "StageCharacterReviewPayload",
    "SceneContinuityReviewPayload",
    "_heuristic_character_relation_schedule_review",
    "_normalize_schedule_review_payload",
    "_normalize_stage_character_review_payload",
    "review_stage_characters",
    "review_character_relation_schedule",
    "review_scene_continuity",
    "apply_schedule_review_to_packet",
    "apply_scene_continuity_review_to_packet",
]
