from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.chapter_quality import _progress_result_is_clear, _weak_ending
from app.services.agency_modes import AGENCY_MODES
from app.services.story_blueprint_builders import build_flow_templates
from app.services.llm_runtime import (
    begin_llm_trace,
    call_json_response,
    call_text_response,
    clear_llm_trace,
    current_chapter_max_output_tokens,
    extract_json,
    get_llm_runtime_config,
    get_llm_trace,
    is_openai_enabled,
    ping_generation_provider,
    provider_name,
)
from app.services.prompt_templates import (
    arc_outline_system_prompt,
    arc_outline_user_prompt,
    arc_casting_layout_review_system_prompt,
    arc_casting_layout_review_user_prompt,
    chapter_body_draft_system_prompt,
    chapter_body_draft_user_prompt,
    chapter_card_selector_system_prompt,
    chapter_card_selector_user_prompt,
    stage_character_review_system_prompt,
    stage_character_review_user_prompt,
    character_relation_schedule_review_system_prompt,
    character_relation_schedule_review_user_prompt,
    chapter_body_continue_system_prompt,
    chapter_body_continue_user_prompt,
    chapter_closing_system_prompt,
    chapter_closing_user_prompt,
    chapter_draft_system_prompt,
    chapter_draft_user_prompt,
    chapter_extension_system_prompt,
    chapter_extension_user_prompt,
    chapter_title_refinement_system_prompt,
    chapter_title_refinement_user_prompt,
    global_outline_system_prompt,
    global_outline_user_prompt,
    story_engine_diagnosis_system_prompt,
    story_engine_diagnosis_user_prompt,
    story_engine_strategy_bundle_system_prompt,
    story_engine_strategy_bundle_user_prompt,
    story_strategy_card_system_prompt,
    story_strategy_card_user_prompt,
    instruction_parse_system_prompt,
    instruction_parse_user_prompt,
    summary_system_prompt,
    summary_user_prompt,
)

logger = logging.getLogger(__name__)


def _infer_event_type(goal: str, conflict: str, ending_hook: str) -> str:
    text = f"{goal} {conflict} {ending_hook}"
    mapping = [
        ("危机爆发", ["危机", "围杀", "追杀", "爆发", "失控", "暴露", "追来", "围堵", "截杀"]),
        ("冲突类", ["对峙", "交手", "斗", "冲突", "反击", "硬碰", "厮杀", "伏击"]),
        ("反制类", ["反制", "误导", "设局", "借刀", "反咬", "栽赃", "误判"]),
        ("潜入类", ["潜入", "夜探", "摸进", "潜行", "偷入", "暗查"]),
        ("交易类", ["交易", "换", "买", "卖", "谈价", "交换"]),
        ("资源获取类", ["资源", "灵石", "材料", "药", "功法", "法器", "拿到", "取得"]),
        ("关系推进类", ["关系", "结交", "拉拢", "合作", "试探对方", "盟友", "师徒", "同门"]),
        ("身份伪装类", ["伪装", "藏身份", "遮掩", "冒名", "装作", "假扮"]),
        ("外部任务类", ["任务", "差事", "命令", "考核", "试炼", "委托"]),
        ("逃避类", ["撤", "逃", "避开", "脱身", "绕开", "退走"]),
        ("发现类", ["发现", "异样", "看见", "线索", "摸到", "察觉", "听见", "找到"]),
    ]
    for label, tokens in mapping:
        if any(token in text for token in tokens):
            return label
    return "试探类"


def _infer_progress_kind(goal: str, conflict: str, ending_hook: str) -> str:
    text = f"{goal} {conflict} {ending_hook}"
    mapping = [
        ("资源推进", ["资源", "灵石", "材料", "药", "法器", "功法", "拿到", "取得"]),
        ("实力推进", ["突破", "修为", "境界", "术法", "能力", "掌握"]),
        ("关系推进", ["关系", "合作", "结交", "信任", "同盟", "师徒", "同门"]),
        ("地点推进", ["进城", "进山", "去", "转入", "新场景", "新地点", "地图"]),
        ("风险升级", ["盯上", "暴露", "危机", "追查", "失控", "敌意", "围堵"]),
    ]
    for label, tokens in mapping:
        if any(token in text for token in tokens):
            return label
    return "信息推进"


def _infer_hook_kind(ending_hook: str, hook_style: str | None = None) -> str:
    text = f"{ending_hook} {hook_style or ''}"
    mapping = [
        ("新威胁", ["危险", "逼近", "追来", "盯上", "杀机", "围堵"]),
        ("新发现", ["发现", "异样", "真相", "线索", "反应"]),
        ("新任务", ["任务", "委托", "命令", "考核"]),
        ("身份暴露风险", ["暴露", "识破", "认出", "露馅"]),
        ("意外收获隐患", ["收获", "代价", "副作用", "隐患"]),
        ("关键人物动作", ["来客", "出手", "现身", "动作", "选择"]),
    ]
    for label, tokens in mapping:
        if any(token in text for token in tokens):
            return label
    return "更大谜团"


def _infer_proactive_move(goal: str, conflict: str, event_type: str) -> str:
    text = f"{goal} {conflict}"
    mapping = [
        ("主动试探他人", ["试探", "套话", "探口风"]),
        ("主动获取资源", ["拿到", "取得", "换取", "买下", "偷到"]),
        ("主动布置伪装", ["伪装", "遮掩", "藏", "装作", "假扮"]),
        ("主动引导误判", ["误导", "设局", "误判", "引开", "借刀"]),
        ("主动利用规则", ["规矩", "任务", "试炼", "借规则"]),
        ("主动绕开危险", ["绕开", "避开", "脱身", "退走"]),
    ]
    for label, tokens in mapping:
        if any(token in text for token in tokens):
            return label
    fallback = {
        "冲突类": "主动反制或抢先出手",
        "危机爆发": "主动脱身并保住关键筹码",
        "资源获取类": "主动争取资源并建立主动权",
        "关系推进类": "主动试探关系与交换立场",
    }
    return fallback.get(event_type, "主动做出判断并推动局势前进")


def _flow_templates_from_story_bible(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    template_library = (story_bible or {}).get("template_library") or {}
    flow_templates = template_library.get("flow_templates") or []
    normalized = [item for item in flow_templates if isinstance(item, dict) and str(item.get("flow_id") or "").strip()]
    return normalized or build_flow_templates()


def _keyword_hit_count(text: str, keywords: list[str]) -> int:
    return sum(1 for token in keywords if token and token in text)


def _flow_match_score(template: dict[str, Any], chapter: ChapterPlan, recent_flow_ids: list[str]) -> float:
    event_type = str(chapter.event_type or "").strip()
    progress_kind = str(chapter.progress_kind or "").strip()
    hook_style = str(chapter.hook_style or "").strip()
    text = " ".join(
        str(part or "").strip()
        for part in [
            chapter.title,
            chapter.goal,
            chapter.conflict,
            chapter.ending_hook,
            chapter.main_scene,
            chapter.proactive_move,
            chapter.supporting_character_focus,
        ]
    )
    score = 0.0
    if event_type and event_type in list(template.get("preferred_event_types") or []):
        score += 5.0
    if progress_kind and progress_kind in list(template.get("preferred_progress_kinds") or []):
        score += 4.0
    if hook_style and hook_style in list(template.get("preferred_hook_styles") or []):
        score += 2.0
    score += min(_keyword_hit_count(text, list(template.get("keyword_hints") or [])), 3) * 1.4
    recent = [str(item or "").strip() for item in recent_flow_ids if str(item or "").strip()]
    flow_id = str(template.get("flow_id") or "").strip()
    if flow_id in recent:
        distance = len(recent) - recent.index(flow_id)
        score -= max(2.0, 7.0 - distance)
    return score


def _choose_flow_template_for_chapter(chapter: ChapterPlan, story_bible: dict[str, Any]) -> dict[str, Any]:
    templates = _flow_templates_from_story_bible(story_bible)
    if not templates:
        return {}
    flow_control = (story_bible or {}).get("flow_control") or {}
    recent_flow_ids = list(flow_control.get("recent_flow_ids") or [])
    desired_id = str(getattr(chapter, "flow_template_id", None) or "").strip()
    template_by_id = {str(item.get("flow_id") or "").strip(): item for item in templates}

    candidates: list[tuple[float, dict[str, Any]]] = []
    for item in templates:
        score = _flow_match_score(item, chapter, recent_flow_ids)
        flow_id = str(item.get("flow_id") or "").strip()
        if desired_id and flow_id == desired_id:
            score += 8.0
        candidates.append((score, item))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    best = candidates[0][1]
    if desired_id and desired_id in template_by_id:
        chosen = template_by_id[desired_id]
        chosen_id = str(chosen.get("flow_id") or "").strip()
        if recent_flow_ids and desired_id == str(recent_flow_ids[-1] or "").strip():
            for _, alt in candidates:
                alt_id = str(alt.get("flow_id") or "").strip()
                if alt_id != chosen_id:
                    best = alt
                    break
        else:
            best = chosen
    return best


def _apply_flow_template_to_chapter(chapter: ChapterPlan, story_bible: dict[str, Any]) -> None:
    template = _choose_flow_template_for_chapter(chapter, story_bible)
    if not template:
        return
    chapter.flow_template_id = str(template.get("flow_id") or chapter.flow_template_id or "").strip() or None
    chapter.flow_template_tag = str(template.get("quick_tag") or chapter.flow_template_tag or "").strip() or None
    chapter.flow_template_name = str(template.get("name") or chapter.flow_template_name or "").strip() or None
    chapter.flow_turning_points = list(template.get("turning_points") or [])[:4] or None
    chapter.flow_variation_note = str(template.get("variation_notes") or "").strip() or None
    note = str(chapter.writing_note or "").strip()
    flow_hint = f"本章流程用‘{chapter.flow_template_name or chapter.flow_template_id}（{chapter.flow_template_tag or '流程'}）’，按其节奏推进，避免写散。"
    if flow_hint not in note:
        chapter.writing_note = f"{note} {flow_hint}".strip()


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


def _chapter_card_selection_limits() -> dict[str, int]:
    return {"character": 4, "resource": 3, "faction": 2, "relation": 3}


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


def _heuristic_select_card_ids(chapter_plan: dict[str, Any], planning_packet: dict[str, Any]) -> ChapterCardSelectionPayload:
    entries = _card_index_entries(planning_packet)
    if not entries:
        return ChapterCardSelectionPayload(selected_card_ids=[], selection_note="无候选卡。")
    text = " ".join(
        str(value or "").strip()
        for value in [
            (chapter_plan or {}).get("title"),
            (chapter_plan or {}).get("goal"),
            (chapter_plan or {}).get("conflict"),
            (chapter_plan or {}).get("main_scene"),
            (chapter_plan or {}).get("event_type"),
            (chapter_plan or {}).get("progress_kind"),
            (chapter_plan or {}).get("supporting_character_focus"),
            (chapter_plan or {}).get("ending_hook"),
            " ".join((chapter_plan or {}).get("new_resources") or []),
            " ".join((chapter_plan or {}).get("new_factions") or []),
        ]
        if str(value or "").strip()
    )
    focus_name = str(((planning_packet.get("selected_elements") or {}).get("focus_character")) or "").strip()
    schedule = (planning_packet.get("character_relation_schedule") or {}) if isinstance(planning_packet, dict) else {}
    appearance_schedule = (schedule.get("appearance_schedule") or {}) if isinstance(schedule, dict) else {}
    relationship_schedule = (schedule.get("relationship_schedule") or {}) if isinstance(schedule, dict) else {}
    due_characters = {str(item or "").strip() for item in (appearance_schedule.get("due_characters") or []) if str(item or "").strip()}
    resting_characters = {str(item or "").strip() for item in (appearance_schedule.get("resting_characters") or []) if str(item or "").strip()}
    due_relations = {str(item or "").strip() for item in (relationship_schedule.get("due_relations") or []) if str(item or "").strip()}
    limits = _chapter_card_selection_limits()
    scored: list[tuple[float, dict[str, Any]]] = []
    for idx, entry in enumerate(entries):
        title = str(entry.get("title") or "").strip()
        summary = str(entry.get("summary") or "").strip()
        tags = [str(item or "").strip() for item in (entry.get("tags") or [])]
        entity_type = str(entry.get("entity_type") or "").strip()
        score = float(entry.get("importance_score") or 0) / 5.0
        score += float(entry.get("importance_mainline_rank_score") or 0.0) / 18.0
        score += float(entry.get("importance_activation_rank_score") or 0.0) / 26.0
        if idx == 0 and entity_type == "character":
            score += 35.0
        if focus_name and title == focus_name:
            score += 60.0
        if entity_type == "character" and title in due_characters:
            score += 20.0
        if entity_type == "character" and title in resting_characters:
            score -= 4.0
        if entity_type == "relation" and (str(entry.get("key") or "").strip() in due_relations or title in due_relations):
            score += 18.0
        if title and title in text:
            score += 42.0
        if summary and any(token and token in text for token in [summary[:4], summary[:6]]):
            score += 10.0
        score += sum(6.0 for token in tags if token and token in text)
        status = str(entry.get("status") or "").strip()
        if status in {"planned", "刚建立"}:
            score += 8.0
        if float(entry.get("importance_activation_rank_score") or 0.0) >= max(float(entry.get("importance_mainline_rank_score") or 0.0) * 0.9, 72.0):
            score += 8.0
        if float(entry.get("importance_exploration_score") or 0.0) >= 52.0 and entity_type in {"character", "resource", "faction"}:
            score += 4.0
        tier = str(entry.get("importance_tier") or "").strip()
        if any(flag in tier for flag in ["核心", "重要"]):
            score += 10.0
        scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected_by_type: dict[str, list[str]] = {key: [] for key in limits}
    for _, entry in scored:
        entity_type = str(entry.get("entity_type") or "").strip()
        card_id = str(entry.get("card_id") or "").strip()
        if not card_id or entity_type not in selected_by_type:
            continue
        if len(selected_by_type[entity_type]) >= limits[entity_type]:
            continue
        if card_id in selected_by_type[entity_type]:
            continue
        selected_by_type[entity_type].append(card_id)
    selected_ids: list[str] = []
    for key in ["character", "resource", "faction", "relation"]:
        selected_ids.extend(selected_by_type[key])
    selected_ids = _enforce_required_card_ids(planning_packet, selected_ids, chapter_plan=chapter_plan)
    selection_note = "优先保留主角、焦点人物、该回场角色和本章真正会变化的资源/关系。"
    return ChapterCardSelectionPayload(selected_card_ids=selected_ids[:12], selection_note=selection_note)


def choose_chapter_card_selection(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> ChapterCardSelectionPayload:
    fallback = _heuristic_select_card_ids(chapter_plan, planning_packet)
    if not _card_index_entries(planning_packet):
        return fallback
    if not is_openai_enabled():
        return fallback
    timeout_seconds = request_timeout_seconds or int(getattr(settings, "chapter_card_selector_timeout_seconds", 12) or 12)
    try:
        data = call_json_response(
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
            selection_note=str(payload.selection_note or fallback.selection_note or "").strip() or fallback.selection_note,
        )
    except Exception:
        return fallback


def _schedule_valid_character_names(planning_packet: dict[str, Any]) -> list[str]:
    packet = planning_packet or {}
    names: list[str] = []
    relevant = (packet.get("relevant_cards") or {}) if isinstance(packet, dict) else {}
    names.extend([str(name or "").strip() for name in (relevant.get("characters") or {}).keys()])
    for item in ((_card_index_entries(packet) if isinstance(packet, dict) else []) or []):
        if str(item.get("entity_type") or "").strip() == "character":
            names.append(str(item.get("title") or "").strip())
    names.extend([str(item or "").strip() for item in ((packet.get("selected_elements") or {}).get("characters") or [])])
    output=[]; seen=set()
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
    output=[]; seen=set()
    for rid in ids:
        if not rid or rid in seen:
            continue
        seen.add(rid)
        output.append(rid)
    return output


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
    from app.services.stage_review_support import heuristic_stage_character_review

    fallback = _normalize_stage_character_review_payload(heuristic_stage_character_review(snapshot), snapshot)
    if not is_openai_enabled():
        return fallback

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
    except Exception:
        return fallback



def review_character_relation_schedule(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> CharacterRelationScheduleReviewPayload:
    fallback = _heuristic_character_relation_schedule_review(chapter_plan, planning_packet)
    if not (planning_packet or {}).get("character_relation_schedule"):
        return fallback
    if not is_openai_enabled():
        return fallback
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
    except Exception:
        return fallback


def apply_schedule_review_to_packet(
    planning_packet: dict[str, Any],
    review: CharacterRelationScheduleReviewPayload,
) -> dict[str, Any]:
    if not isinstance(planning_packet, dict):
        return planning_packet
    normalized = _normalize_schedule_review_payload(review, planning_packet)
    payload = normalized.model_dump(mode="python")
    payload["soft_rule"] = "本地先初排，AI 再复核；AI 可上调/下调本章推进重点，但不硬删除后面的候选。"
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
    input_policy["schedule_review_rule"] = "角色与关系调度采用‘本地初排 + AI 复核’；人物投放提示也会被 AI 复核，决定本章该执行、软考虑还是暂缓。"
    return planning_packet


def _enforce_event_type_variety(chapters: list[ChapterPlan]) -> None:
    for idx, chapter in enumerate(chapters):
        if idx < 2:
            continue
        a = chapters[idx - 2].event_type
        b = chapters[idx - 1].event_type
        c = chapter.event_type
        if a and a == b == c:
            alternatives = ["资源获取类", "关系推进类", "反制类", "外部任务类", "危机爆发", "发现类"]
            for alt in alternatives:
                if alt != c:
                    chapter.event_type = alt
                    break
            note = str(chapter.writing_note or "").strip()
            extra = f"本章禁止继续写成连续第三章的‘{c}’桥段，必须把重心改成‘{chapter.event_type}’，让局势真正换挡。"
            chapter.writing_note = f"{note} {extra}".strip()


class StoryEngineDiagnosisPayload(BaseModel):
    story_subgenres: list[str] = Field(default_factory=list)
    primary_story_engine: str
    secondary_story_engine: str | None = None
    opening_drive: str
    early_hook_focus: str
    protagonist_action_logic: str
    pacing_profile: str
    world_reveal_strategy: str
    power_growth_strategy: str
    early_must_haves: list[str] = Field(default_factory=list)
    avoid_tropes: list[str] = Field(default_factory=list)
    differentiation_focus: list[str] = Field(default_factory=list)
    must_establish_relationships: list[str] = Field(default_factory=list)
    tone_keywords: list[str] = Field(default_factory=list)


class ThirtyChapterPhase(BaseModel):
    range: str
    stage_mission: str
    reader_hook: str
    frequent_elements: list[str] = Field(default_factory=list)
    limited_elements: list[str] = Field(default_factory=list)
    relationship_tasks: list[str] = Field(default_factory=list)
    phase_result: str


class StoryStrategyCardPayload(BaseModel):
    story_promise: str
    strategic_premise: str
    main_conflict_axis: str
    first_30_mainline_summary: str
    chapter_1_to_10: ThirtyChapterPhase
    chapter_11_to_20: ThirtyChapterPhase
    chapter_21_to_30: ThirtyChapterPhase
    frequent_event_types: list[str] = Field(default_factory=list)
    limited_event_types: list[str] = Field(default_factory=list)
    must_establish_relationships: list[str] = Field(default_factory=list)
    escalation_path: list[str] = Field(default_factory=list)
    anti_homogenization_rules: list[str] = Field(default_factory=list)


class StoryEngineStrategyBundlePayload(BaseModel):
    story_engine_diagnosis: StoryEngineDiagnosisPayload
    story_strategy_card: StoryStrategyCardPayload


class PlannedRelationHint(BaseModel):
    subject: str
    target: str
    relation_type: str | None = None
    level: str | None = None
    status: str | None = None
    recent_trigger: str | None = None


class ChapterPlan(BaseModel):
    chapter_no: int
    title: str
    goal: str
    ending_hook: str
    chapter_type: str | None = None
    event_type: str | None = None
    progress_kind: str | None = None
    flow_template_id: str | None = None
    flow_template_tag: str | None = None
    flow_template_name: str | None = None
    flow_turning_points: list[str] | None = None
    flow_variation_note: str | None = None
    proactive_move: str | None = None
    payoff_or_pressure: str | None = None
    hook_kind: str | None = None
    target_visible_chars_min: int | None = None
    target_visible_chars_max: int | None = None
    hook_style: str | None = None
    main_scene: str | None = None
    conflict: str | None = None
    opening_beat: str | None = None
    mid_turn: str | None = None
    discovery: str | None = None
    closing_image: str | None = None
    supporting_character_focus: str | None = None
    supporting_character_note: str | None = None
    new_resources: list[str] | None = None
    new_factions: list[str] | None = None
    new_relations: list[PlannedRelationHint] | None = None
    stage_casting_action: str | None = None
    stage_casting_target: str | None = None
    stage_casting_note: str | None = None
    writing_note: str | None = None
    agency_mode: str | None = None
    agency_mode_label: str | None = None
    agency_style_summary: str | None = None
    agency_opening_instruction: str | None = None
    agency_mid_instruction: str | None = None
    agency_discovery_instruction: str | None = None
    agency_closing_instruction: str | None = None
    agency_avoid: list[str] | None = None


class ChapterCardSelectionPayload(BaseModel):
    selected_card_ids: list[str] = Field(default_factory=list)
    selection_note: str | None = None


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


class ArcCastingChapterDecision(BaseModel):
    chapter_no: int
    decision: str | None = None
    stage_casting_action: str | None = None
    stage_casting_target: str | None = None
    note: str | None = None


class ArcCastingLayoutReviewPayload(BaseModel):
    window_verdict: str | None = None
    chapter_adjustments: list[ArcCastingChapterDecision] = Field(default_factory=list)
    avoid_notes: list[str] = Field(default_factory=list)
    review_note: str | None = None


class StoryAct(BaseModel):
    act_no: int
    title: str
    purpose: str
    target_chapter_end: int
    summary: str


class GlobalOutlinePayload(BaseModel):
    story_positioning: dict[str, Any] = Field(default_factory=dict)
    acts: list[StoryAct]


class ArcOutlinePayload(BaseModel):
    arc_no: int
    start_chapter: int
    end_chapter: int
    focus: str
    bridge_note: str
    chapters: list[ChapterPlan]


class ChapterDraftPayload(BaseModel):
    title: str
    content: str
    body_segments: int = 1
    continuation_rounds: int = 0
    body_stop_reason: str | None = None


class ChapterSummaryPayload(BaseModel):
    event_summary: str
    character_updates: dict[str, Any] = Field(default_factory=dict)
    new_clues: list[str] = Field(default_factory=list)
    open_hooks: list[str] = Field(default_factory=list)
    closed_hooks: list[str] = Field(default_factory=list)


class ChapterTitleCandidate(BaseModel):
    title: str
    title_type: str | None = None
    angle: str | None = None
    reason: str | None = None


class ChapterTitleRefinementPayload(BaseModel):
    recommended_title: str
    candidates: list[ChapterTitleCandidate] = Field(default_factory=list)


class ParsedInstructionPayload(BaseModel):
    character_focus: dict[str, float] = Field(default_factory=dict)
    tone: str | None = None
    pace: str | None = None
    protected_characters: list[str] = Field(default_factory=list)
    relationship_direction: str | None = None


def _clean_plain_chapter_text(text: str, *, expected_title: str | None = None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    candidate = raw
    if raw.startswith("```"):
        fence_lines = raw.splitlines()
        if len(fence_lines) >= 3:
            candidate = "\n".join(fence_lines[1:-1]).strip()

    stripped = candidate.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
        except Exception:
            data = None
        if isinstance(data, dict):
            maybe_content = data.get("content") or data.get("text") or data.get("body")
            if isinstance(maybe_content, str) and maybe_content.strip():
                candidate = maybe_content.strip()
        else:
            match = re.search(r'"content"\s*:\s*"([\s\S]*)"\s*}\s*$', stripped)
            if match:
                candidate = match.group(1)
                candidate = candidate.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")

    normalized = candidate.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]

    def _looks_like_title(line: str) -> bool:
        line = line.strip().strip("#").strip()
        if not line:
            return False
        if expected_title and line == expected_title.strip():
            return True
        if re.fullmatch(r"第\s*\d+\s*章[:：\s\-—]*.*", line):
            return True
        if line.startswith("标题：") or line.startswith("标题:"):
            return True
        return False

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and _looks_like_title(lines[0]):
        lines.pop(0)
    while lines and lines[0].strip() in {"正文：", "正文:", "内容：", "内容:"}:
        lines.pop(0)

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _split_summary_items(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw or raw in {"无", "None", "none", "null", "[]", "-"}:
        return []
    parts = re.split(r"[；;\n]+", raw)
    items: list[str] = []
    for part in parts:
        item = part.strip().lstrip("-•* ").strip()
        if item and item not in {"无", "None", "none", "null"}:
            items.append(item[:80])
    return items[:6]


def _truncate_visible(text: str, limit: int) -> str:
    return text.strip()[:limit].strip()


def _heuristic_chapter_summary(title: str, content: str) -> ChapterSummaryPayload:
    normalized = re.sub(r"\s+", " ", (content or "").strip())
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", normalized) if s.strip()]
    if sentences:
        event_summary = _truncate_visible("".join(sentences[:2]), 80)
    else:
        event_summary = _truncate_visible(normalized, 80) or f"{title}中主角推进了当前线索。"

    final_sentence = sentences[-1] if sentences else ""
    open_hooks: list[str] = []
    if final_sentence and any(token in final_sentence for token in ["却", "忽然", "竟", "发现", "听见", "看见", "异样", "不对", "未", "?", "？"]):
        open_hooks = [_truncate_visible(final_sentence, 60)]

    return ChapterSummaryPayload(
        event_summary=event_summary or f"{title}中主角推进了当前线索。",
        character_updates={},
        new_clues=[],
        open_hooks=open_hooks,
        closed_hooks=[],
    )


def _parse_labeled_summary(text: str) -> ChapterSummaryPayload:
    raw = (text or "").strip()
    if not raw:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message="chapter_summary_generation 失败：模型没有返回任何可解析内容。",
            stage="chapter_summary_generation",
            retryable=True,
            http_status=422,
            provider=provider_name(),
        )

    labels = {
        "事件摘要": "event_summary",
        "人物变化": "character_updates_text",
        "新线索": "new_clues_text",
        "未回收钩子": "open_hooks_text",
        "已回收钩子": "closed_hooks_text",
    }
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        for label, key in labels.items():
            prefix = f"{label}："
            prefix2 = f"{label}:"
            if stripped.startswith(prefix):
                parsed[key] = stripped[len(prefix) :].strip()
            elif stripped.startswith(prefix2):
                parsed[key] = stripped[len(prefix2) :].strip()

    if not parsed.get("event_summary"):
        try:
            data = extract_json(raw, stage="chapter_summary_generation")
            return ChapterSummaryPayload.model_validate(data)
        except Exception:
            raise GenerationError(
                code=ErrorCodes.MODEL_RESPONSE_INVALID,
                message="chapter_summary_generation 失败：模型摘要未按约定格式返回。",
                stage="chapter_summary_generation",
                retryable=True,
                http_status=422,
                provider=provider_name(),
                details={"response_head": raw[:500]},
            )

    character_updates_raw = parsed.get("character_updates_text", "")
    character_updates = {} if character_updates_raw in {"", "无"} else {"notes": _truncate_visible(character_updates_raw, 120)}
    return ChapterSummaryPayload(
        event_summary=_truncate_visible(parsed.get("event_summary", ""), 80),
        character_updates=character_updates,
        new_clues=_split_summary_items(parsed.get("new_clues_text", "")),
        open_hooks=_split_summary_items(parsed.get("open_hooks_text", "")),
        closed_hooks=_split_summary_items(parsed.get("closed_hooks_text", "")),
    )


def _normalize_story_engine_diagnosis(payload: dict[str, Any], diagnosis: StoryEngineDiagnosisPayload) -> StoryEngineDiagnosisPayload:
    if not diagnosis.story_subgenres:
        genre = str((payload or {}).get("genre") or "").strip()
        premise = str((payload or {}).get("premise") or "").strip()
        diagnosis.story_subgenres = [item for item in [genre, premise[:12]] if item][:2] or ["待细化修仙子类型"]
    if not diagnosis.primary_story_engine:
        diagnosis.primary_story_engine = "处境压力驱动 + 主角主动试探"
    if not diagnosis.opening_drive:
        diagnosis.opening_drive = "先把主角处境、第一轮目标和关键压力钉牢。"
    if not diagnosis.early_hook_focus:
        diagnosis.early_hook_focus = "前几章尽快给出可感结果，避免只在同一线索上绕圈。"
    if not diagnosis.protagonist_action_logic:
        diagnosis.protagonist_action_logic = "主角先判断，再行动，关键时必须主动选择。"
    if not diagnosis.pacing_profile:
        diagnosis.pacing_profile = "稳中有推进"
    if not diagnosis.world_reveal_strategy:
        diagnosis.world_reveal_strategy = "先解释主角用得上的局部规则，再逐步抬高世界层级。"
    if not diagnosis.power_growth_strategy:
        diagnosis.power_growth_strategy = "成长必须绑定资源、代价和后果。"
    if not diagnosis.early_must_haves:
        diagnosis.early_must_haves = ["明确现实压力", "第一轮有效收益", "可持续主线入口"]
    if not diagnosis.avoid_tropes:
        diagnosis.avoid_tropes = ["固定药铺/坊市/残页组合", "连续多章只围着同一线索试探", "重复被怀疑后被动应付"]
    if not diagnosis.differentiation_focus:
        diagnosis.differentiation_focus = ["把题材真正的独特卖点写进前10章的推进方式"]
    if not diagnosis.must_establish_relationships:
        diagnosis.must_establish_relationships = ["与主角形成长期牵引的关键人物关系"]
    if not diagnosis.tone_keywords:
        diagnosis.tone_keywords = ["具体", "克制", "有代价"]
    return diagnosis



def _normalize_story_strategy_card(strategy: StoryStrategyCardPayload) -> StoryStrategyCardPayload:
    def _fill_phase(phase: ThirtyChapterPhase, *, phase_range: str, mission: str, result: str) -> ThirtyChapterPhase:
        if not phase.range:
            phase.range = phase_range
        if not phase.stage_mission:
            phase.stage_mission = mission
        if not phase.reader_hook:
            phase.reader_hook = "这一阶段必须给读者明确的局势变化与追更理由。"
        if not phase.frequent_elements:
            phase.frequent_elements = ["主角主动选择", "具体结果", "关系或资源变化"]
        if not phase.limited_elements:
            phase.limited_elements = ["重复试探同一线索"]
        if not phase.relationship_tasks:
            phase.relationship_tasks = ["建立或改写一条关键关系"]
        if not phase.phase_result:
            phase.phase_result = result
        return phase

    if not strategy.story_promise:
        strategy.story_promise = "前30章要让读者明确感到这本书有自己的推进方式。"
    if not strategy.strategic_premise:
        strategy.strategic_premise = "围绕主角处境、目标、代价与更大局势持续升级。"
    if not strategy.main_conflict_axis:
        strategy.main_conflict_axis = "立足需求与暴露风险的长期拉扯。"
    if not strategy.first_30_mainline_summary:
        strategy.first_30_mainline_summary = "前30章围绕立足、关系绑定、阶段破局与更大局势展开。"
    strategy.chapter_1_to_10 = _fill_phase(strategy.chapter_1_to_10, phase_range="1-10", mission="先用最有辨识度的推进方式抓住读者。", result="主角获得第一阶段立足资本。")
    strategy.chapter_11_to_20 = _fill_phase(strategy.chapter_11_to_20, phase_range="11-20", mission="扩大地图、关系和局势压力。", result="主角失去一部分原有安全区，但得到新的行动空间。")
    strategy.chapter_21_to_30 = _fill_phase(strategy.chapter_21_to_30, phase_range="21-30", mission="做出阶段高潮并确认下一层故事方向。", result="主角进入新的故事层级。")
    if not strategy.frequent_event_types:
        strategy.frequent_event_types = ["关系推进类", "资源获取类", "反制类"]
    if not strategy.limited_event_types:
        strategy.limited_event_types = ["连续被怀疑后被动应付"]
    if not strategy.must_establish_relationships:
        strategy.must_establish_relationships = ["核心绑定角色", "长期压迫源", "阶段合作对象"]
    if not strategy.escalation_path:
        strategy.escalation_path = ["处境压力", "局部破局", "关系重组", "阶段高潮"]
    if not strategy.anti_homogenization_rules:
        strategy.anti_homogenization_rules = ["不要让前30章只围着一个物件打转", "每个阶段都要换推进重心"]
    return strategy



def generate_story_engine_strategy_bundle(payload: dict[str, Any], story_bible: dict[str, Any]) -> StoryEngineStrategyBundlePayload:
    data = call_json_response(
        stage="story_engine_strategy_generation",
        system_prompt=story_engine_strategy_bundle_system_prompt(),
        user_prompt=story_engine_strategy_bundle_user_prompt(payload=payload, story_bible=story_bible),
        max_output_tokens=1800,
    )
    bundle = StoryEngineStrategyBundlePayload.model_validate(data)
    bundle.story_engine_diagnosis = _normalize_story_engine_diagnosis(payload, bundle.story_engine_diagnosis)
    bundle.story_strategy_card = _normalize_story_strategy_card(bundle.story_strategy_card)
    return bundle



def generate_story_engine_diagnosis(payload: dict[str, Any], story_bible: dict[str, Any]) -> StoryEngineDiagnosisPayload:
    data = call_json_response(
        stage="story_engine_diagnosis",
        system_prompt=story_engine_diagnosis_system_prompt(),
        user_prompt=story_engine_diagnosis_user_prompt(payload=payload, story_bible=story_bible),
        max_output_tokens=1000,
    )
    diagnosis = StoryEngineDiagnosisPayload.model_validate(data)
    return _normalize_story_engine_diagnosis(payload, diagnosis)



def generate_story_strategy_card(payload: dict[str, Any], story_bible: dict[str, Any]) -> StoryStrategyCardPayload:
    data = call_json_response(
        stage="story_strategy_generation",
        system_prompt=story_strategy_card_system_prompt(),
        user_prompt=story_strategy_card_user_prompt(payload=payload, story_bible=story_bible),
        max_output_tokens=1300,
    )
    strategy = StoryStrategyCardPayload.model_validate(data)
    return _normalize_story_strategy_card(strategy)


def generate_global_outline(payload: dict[str, Any], story_bible: dict[str, Any], total_acts: int) -> GlobalOutlinePayload:
    data = call_json_response(
        stage="global_outline_generation",
        system_prompt=global_outline_system_prompt(),
        user_prompt=global_outline_user_prompt(payload=payload, story_bible=story_bible, total_acts=total_acts),
        max_output_tokens=1800,
    )
    outline = GlobalOutlinePayload.model_validate(data)
    normalized: list[StoryAct] = []
    for idx, act in enumerate(outline.acts[:total_acts], start=1):
        act.act_no = idx
        if not act.title:
            act.title = f"第{idx}幕"
        if not act.purpose:
            act.purpose = "稳定推进主线"
        if not act.summary:
            act.summary = "主角被更大的局势逐步卷入。"
        if not act.target_chapter_end:
            act.target_chapter_end = idx * 10
        normalized.append(act)
    outline.acts = normalized
    return outline


def _chapter_casting_fit_score(chapter: dict[str, Any], action: str) -> int:
    chapter_type = str(chapter.get("chapter_type") or "").strip()
    event_type = str(chapter.get("event_type") or "").strip()
    hook_style = str(chapter.get("hook_style") or "").strip()
    goal = f"{chapter.get('goal') or ''} {chapter.get('conflict') or ''} {chapter.get('main_scene') or ''}"
    score = 0
    if chapter_type == "progress":
        score += 3
    elif chapter_type == "probe":
        score += 2
    elif chapter_type == "turning_point":
        score -= 2
    if hook_style in {"平稳过渡", "人物选择", "信息反转"}:
        score += 1
    if action == "new_core_entry":
        if event_type in {"发现类", "交易类", "关系推进类", "资源获取类", "外部任务类"}:
            score += 3
        if any(token in goal for token in ["结交", "合作", "接触", "接口", "线索", "势力"]):
            score += 2
    elif action == "role_refresh":
        if event_type in {"关系推进类", "交易类", "冲突类", "发现类"}:
            score += 3
        if any(token in goal for token in ["搭档", "拉扯", "谈", "合作", "试探", "对峙"]):
            score += 2
    if event_type == "危机爆发":
        score -= 2
    return score


def _normalize_arc_casting_layout_review(
    payload: Any,
    *,
    arc_bundle: dict[str, Any],
    story_bible: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
) -> ArcCastingLayoutReviewPayload:
    from app.services.stage_review_support import build_stage_character_review_snapshot, stage_character_review_for_window

    chapters = [ch for ch in (arc_bundle.get("chapters") or []) if isinstance(ch, dict)]
    valid_chapters = {int(ch.get("chapter_no", 0) or 0): ch for ch in chapters}
    current_chapter_no = max(int(arc_bundle.get("start_chapter", 1) or 1) - 1, 0)
    review = stage_character_review_for_window(story_bible, current_chapter_no=current_chapter_no) or {}
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=current_chapter_no, recent_summaries=recent_summaries or [])
    diagnostics = (snapshot.get("casting_defer_diagnostics") or {}) if isinstance(snapshot, dict) else {}
    candidate_slots = set(review.get("candidate_slot_ids") or [])
    refresh_targets = set(review.get("role_refresh_targets") or [])
    strategy = str(review.get("casting_strategy") or "hold_steady").strip()
    progress = review.get("window_progress") or {}
    new_open = str(progress.get("new_core_limit_status") or "open") not in {"full", "exceeded", "closed"}
    refresh_open = str(progress.get("role_refresh_limit_status") or "open") not in {"full", "exceeded", "closed"}
    max_new = max(int(review.get("max_new_core_entries") or 0), 0)
    max_refresh = max(int(review.get("max_role_refreshes") or 0), 0)

    if isinstance(payload, ArcCastingLayoutReviewPayload):
        source = payload.model_dump(mode="python")
    elif isinstance(payload, dict):
        source = payload
    else:
        source = {}

    adjustments = []
    for item in (source.get("chapter_adjustments") or []):
        if not isinstance(item, dict):
            continue
        chapter_no = int(item.get("chapter_no", 0) or 0)
        if chapter_no not in valid_chapters:
            continue
        decision = str(item.get("decision") or "").strip()
        if decision not in {"keep", "move_here", "drop", "soft_consider"}:
            continue
        action = str(item.get("stage_casting_action") or "").strip() or None
        target = str(item.get("stage_casting_target") or "").strip() or None
        note = str(item.get("note") or "").strip()[:72] or None
        if action not in {None, "new_core_entry", "role_refresh"}:
            action = None
        if action == "new_core_entry":
            if not new_open or strategy == "prefer_refresh_existing":
                decision = "drop"
            if target and target not in candidate_slots:
                target = None
        elif action == "role_refresh":
            if not refresh_open or strategy == "introduce_one_new":
                decision = "drop"
            if target and target not in refresh_targets:
                target = None
        adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision=decision, stage_casting_action=action, stage_casting_target=target, note=note))

    # heuristic fallback /补全
    if not adjustments:
        dominant = str(diagnostics.get("dominant_defer_cause") or "").strip()
        existing_actions = []
        for ch in chapters:
            action = str(ch.get("stage_casting_action") or "").strip()
            if action in {"new_core_entry", "role_refresh"}:
                existing_actions.append((int(ch.get("chapter_no", 0) or 0), action, str(ch.get("stage_casting_target") or "").strip() or None))
        if strategy == "hold_steady":
            for chapter_no, action, target in existing_actions:
                adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这一轮先稳住现有人物线。"))
        else:
            planned_by_action = {}
            for chapter_no, action, target in existing_actions:
                planned_by_action.setdefault(action, []).append((chapter_no, target))
            if dominant in {"chapter_fit", "pacing_mismatch"}:
                for action, rows in planned_by_action.items():
                    if action == "new_core_entry" and (strategy == "prefer_refresh_existing" or not new_open):
                        for chapter_no, target in rows:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这轮先别硬补新人。"))
                        continue
                    if action == "role_refresh" and (strategy == "introduce_one_new" or not refresh_open):
                        for chapter_no, target in rows:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这轮先别硬改旧角色作用位。"))
                        continue
                    best = None
                    best_score = -999
                    for ch in chapters:
                        score = _chapter_casting_fit_score(ch, action)
                        if score > best_score:
                            best = ch
                            best_score = score
                    if best and rows:
                        src_no, target = rows[0]
                        best_no = int(best.get("chapter_no", 0) or 0)
                        if best_no != src_no and best_score >= _chapter_casting_fit_score(valid_chapters[src_no], action) + 2:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=src_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这一章承压更重，人物投放先挪开。"))
                            adjustments.append(ArcCastingChapterDecision(chapter_no=best_no, decision="move_here", stage_casting_action=action, stage_casting_target=target, note="这一章更适合自然落地人物投放动作。"))
            elif dominant == "budget_pressure":
                # 预算紧时简化动作，优先保留与阶段策略一致的一类
                keep_action = None
                if strategy == "prefer_refresh_existing":
                    keep_action = "role_refresh"
                elif strategy == "introduce_one_new":
                    keep_action = "new_core_entry"
                for action, rows in planned_by_action.items():
                    if keep_action and action != keep_action:
                        for chapter_no, target in rows:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="窗口预算偏紧，这轮先简化同类动作。"))
        if not adjustments and existing_actions:
            for chapter_no, action, target in existing_actions:
                adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="keep", stage_casting_action=action, stage_casting_target=target, note="当前排法基本顺，先保持。"))

    # enforce limits and dedupe
    filtered = []
    seen_new = 0
    seen_refresh = 0
    chapter_has_action = {}
    for item in adjustments:
        action = item.stage_casting_action
        chapter_no = int(item.chapter_no or 0)
        if item.decision in {"move_here", "keep"} and action == "new_core_entry":
            if seen_new >= max_new or strategy == "prefer_refresh_existing" or not new_open:
                item = ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=item.stage_casting_target, note=item.note or "这轮新核心位名额不该再继续占用。")
            else:
                seen_new += 1
        elif item.decision in {"move_here", "keep"} and action == "role_refresh":
            if seen_refresh >= max_refresh or strategy == "introduce_one_new" or not refresh_open:
                item = ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=item.stage_casting_target, note=item.note or "这轮旧角色换功能名额不该再继续占用。")
            else:
                seen_refresh += 1
        if item.decision in {"move_here", "keep"} and chapter_has_action.get(chapter_no):
            item = ArcCastingChapterDecision(chapter_no=chapter_no, decision="soft_consider", stage_casting_action=action, stage_casting_target=item.stage_casting_target, note=item.note or "这一章已有别的人物投放动作，别同章双塞。")
        if item.decision in {"move_here", "keep"} and action:
            chapter_has_action[chapter_no] = True
        filtered.append(item)

    verdict = str(source.get("window_verdict") or "").strip()
    if verdict not in {"keep_current_layout", "shift_actions", "simplify_actions", "hold_steady"}:
        if any(item.decision == "move_here" for item in filtered):
            verdict = "shift_actions"
        elif any(item.decision == "drop" for item in filtered):
            verdict = "simplify_actions" if strategy in {"hold_steady", "prefer_refresh_existing", "introduce_one_new"} else "shift_actions"
        else:
            verdict = "keep_current_layout"

    avoid_notes = [str(x).strip()[:48] for x in (source.get("avoid_notes") or []) if str(x).strip()][:4]
    if not avoid_notes and diagnostics.get("summary"):
        avoid_notes.append(str(diagnostics.get("summary"))[:48])
    review_note = str(source.get("review_note") or "").strip()[:88]
    if not review_note:
        review_note = "这轮人物投放动作按窗口策略微调，尽量把动作落在更顺手的章节。"
    return ArcCastingLayoutReviewPayload(window_verdict=verdict, chapter_adjustments=filtered[:8], avoid_notes=avoid_notes, review_note=review_note)


def review_arc_casting_layout(
    *,
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    arc_bundle: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> ArcCastingLayoutReviewPayload:
    fallback = _normalize_arc_casting_layout_review({}, arc_bundle=arc_bundle, story_bible=story_bible, recent_summaries=recent_summaries)
    if not is_openai_enabled():
        return fallback
    timeout_seconds = request_timeout_seconds or int(getattr(settings, "arc_casting_layout_review_timeout_seconds", 10) or 10)
    max_output_tokens = max(int(getattr(settings, "arc_casting_layout_review_max_output_tokens", 420) or 420), 180)
    try:
        data = call_json_response(
            stage="arc_casting_layout_review",
            system_prompt=arc_casting_layout_review_system_prompt(),
            user_prompt=arc_casting_layout_review_user_prompt(
                payload=payload,
                story_bible=story_bible,
                global_outline=global_outline,
                recent_summaries=recent_summaries,
                arc_bundle=arc_bundle,
            ),
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        return _normalize_arc_casting_layout_review(data, arc_bundle=arc_bundle, story_bible=story_bible, recent_summaries=recent_summaries)
    except Exception:
        return fallback


def apply_arc_casting_layout_review(
    arc_bundle: dict[str, Any],
    review: ArcCastingLayoutReviewPayload,
) -> dict[str, Any]:
    if not isinstance(arc_bundle, dict):
        return arc_bundle
    chapters = [dict(ch) for ch in (arc_bundle.get("chapters") or []) if isinstance(ch, dict)]
    chapter_map = {int(ch.get("chapter_no", 0) or 0): ch for ch in chapters}
    adjustments = sorted(review.chapter_adjustments, key=lambda item: (int(item.chapter_no or 0), 0 if item.decision == "drop" else 1))
    for item in adjustments:
        ch = chapter_map.get(int(item.chapter_no or 0))
        if not ch:
            continue
        if item.decision == "drop":
            ch.pop("stage_casting_action", None)
            ch.pop("stage_casting_target", None)
            ch.pop("stage_casting_note", None)
            ch["stage_casting_review_note"] = str(item.note or "AI复核后本章先不承担该人物投放动作。")[:72]
        elif item.decision in {"keep", "move_here"}:
            if item.stage_casting_action:
                ch["stage_casting_action"] = item.stage_casting_action
            if item.stage_casting_target:
                ch["stage_casting_target"] = item.stage_casting_target
            note = str(item.note or "AI复核后确认本章更适合承担这个人物投放动作。")[:72]
            ch["stage_casting_note"] = note
            ch["stage_casting_review_note"] = note
        elif item.decision == "soft_consider":
            ch["stage_casting_review_note"] = str(item.note or "这章只适合轻量考虑人物投放动作，别硬塞。")[:72]
    arc_bundle["chapters"] = [chapter_map[int(ch.get("chapter_no", 0) or 0)] for ch in chapters]
    arc_bundle["casting_layout_review"] = review.model_dump(mode="python")
    return arc_bundle


def generate_arc_outline(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    start_chapter: int,
    end_chapter: int,
    arc_no: int,
) -> ArcOutlinePayload:
    data = call_json_response(
        stage="arc_outline_generation",
        system_prompt=arc_outline_system_prompt(),
        user_prompt=arc_outline_user_prompt(
            payload=payload,
            story_bible=story_bible,
            global_outline=global_outline,
            recent_summaries=recent_summaries,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            arc_no=arc_no,
        ),
        max_output_tokens=1400,
    )
    outline = ArcOutlinePayload.model_validate(data)
    normalized: list[ChapterPlan] = []
    expected_no = start_chapter
    for ch in outline.chapters[: max(end_chapter - start_chapter + 1, 0)]:
        ch.chapter_no = expected_no
        if not ch.title:
            ch.title = f"第{expected_no}章"
        if not ch.goal:
            ch.goal = "推进当前主线"
        if not ch.ending_hook:
            ch.ending_hook = "新的疑点浮出水面"
        if ch.chapter_type not in {"probe", "progress", "turning_point"}:
            goal_text = f"{ch.goal or ''} {ch.conflict or ''} {ch.ending_hook or ''}"
            if any(token in goal_text for token in ["追", "逃", "转折", "对峙", "揭示", "矿", "伏击"]):
                ch.chapter_type = "turning_point"
            elif any(token in goal_text for token in ["查", "买", "换", "谈", "探路", "坊市", "交易", "跟踪"]):
                ch.chapter_type = "progress"
            else:
                ch.chapter_type = "probe"
        if not ch.target_visible_chars_min or not ch.target_visible_chars_max:
            if ch.chapter_type == "turning_point":
                ch.target_visible_chars_min = settings.chapter_turning_point_target_min_visible_chars
                ch.target_visible_chars_max = settings.chapter_turning_point_target_max_visible_chars
            elif ch.chapter_type == "progress":
                ch.target_visible_chars_min = settings.chapter_progress_target_min_visible_chars
                ch.target_visible_chars_max = settings.chapter_progress_target_max_visible_chars
            else:
                ch.target_visible_chars_min = settings.chapter_probe_target_min_visible_chars
                ch.target_visible_chars_max = settings.chapter_probe_target_max_visible_chars
        if not ch.hook_style:
            hook_cycle = ["异象", "人物选择", "危险逼近", "信息反转", "平稳过渡", "余味收束"]
            ch.hook_style = hook_cycle[(expected_no - start_chapter) % len(hook_cycle)]
        if not ch.conflict:
            ch.conflict = "主角推进目标时遭遇新的阻力或暴露风险。"
        if not ch.main_scene:
            ch.main_scene = "当前主线所处的具体场景。"
        if not ch.opening_beat:
            ch.opening_beat = "开场先落在一个具体动作或眼前小异常上。"
        if not ch.mid_turn:
            ch.mid_turn = "中段加入一次受阻、遮掩或判断失误，让场面真正动起来。"
        if not ch.discovery:
            ch.discovery = "给出一个具体而可感的发现，推动本章信息增量。"
        if not ch.closing_image:
            ch.closing_image = "结尾收在一个可见可感的画面上，而不是抽象总结。"
        ch.event_type = str(ch.event_type or _infer_event_type(ch.goal, ch.conflict or "", ch.ending_hook)).strip()[:12]
        ch.progress_kind = str(ch.progress_kind or _infer_progress_kind(ch.goal, ch.conflict or "", ch.ending_hook)).strip()[:12]
        ch.proactive_move = str(ch.proactive_move or _infer_proactive_move(ch.goal, ch.conflict or "", ch.event_type)).strip()[:24]
        ch.payoff_or_pressure = str(ch.payoff_or_pressure or f"本章至少完成一次{ch.progress_kind}，并给出明确回报或压力升级。").strip()[:42]
        ch.hook_kind = str(ch.hook_kind or _infer_hook_kind(ch.ending_hook, ch.hook_style)).strip()[:16]
        if ch.supporting_character_focus:
            ch.supporting_character_focus = str(ch.supporting_character_focus).strip()[:20]
        if ch.supporting_character_note:
            ch.supporting_character_note = str(ch.supporting_character_note).strip()[:80]
        if ch.new_resources:
            ch.new_resources = [str(item).strip()[:24] for item in ch.new_resources if str(item).strip()][:4] or None
        if ch.new_factions:
            ch.new_factions = [str(item).strip()[:24] for item in ch.new_factions if str(item).strip()][:3] or None
        if ch.new_relations:
            normalized_relations: list[PlannedRelationHint] = []
            for relation in ch.new_relations[:3]:
                relation.subject = str(relation.subject or '').strip()[:20]
                relation.target = str(relation.target or '').strip()[:20]
                relation.relation_type = str(relation.relation_type or '').strip()[:24] or None
                relation.level = str(relation.level or '').strip()[:20] or None
                relation.status = str(relation.status or '').strip()[:24] or None
                relation.recent_trigger = str(relation.recent_trigger or '').strip()[:48] or None
                if relation.subject and relation.target:
                    normalized_relations.append(relation)
            ch.new_relations = normalized_relations or None
        if not ch.writing_note:
            ch.writing_note = "正文阶段避免模板句，保持单场景推进、主角主动性和自然收束。"
        _apply_flow_template_to_chapter(ch, story_bible)
        if ch.agency_mode and ch.agency_mode in AGENCY_MODES:
            spec = AGENCY_MODES[ch.agency_mode]
            if not ch.agency_mode_label:
                ch.agency_mode_label = str(spec.get("label") or ch.agency_mode)
            if not ch.agency_style_summary:
                ch.agency_style_summary = str(spec.get("summary") or "")
            if not ch.agency_opening_instruction:
                ch.agency_opening_instruction = str(spec.get("opening") or "")
            if not ch.agency_mid_instruction:
                ch.agency_mid_instruction = str(spec.get("mid") or "")
            if not ch.agency_discovery_instruction:
                ch.agency_discovery_instruction = str(spec.get("discovery") or "")
            if not ch.agency_closing_instruction:
                ch.agency_closing_instruction = str(spec.get("closing") or "")
            if not ch.agency_avoid:
                ch.agency_avoid = list(spec.get("avoid") or [])
        normalized.append(ch)
        expected_no += 1
    _enforce_event_type_variety(normalized)
    for chapter in normalized:
        _apply_flow_template_to_chapter(chapter, story_bible)
    outline.chapters = normalized
    outline.arc_no = arc_no
    outline.start_chapter = start_chapter
    outline.end_chapter = end_chapter
    return outline


def _chapter_phase_visible_char_targets(
    *,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> dict[str, int]:
    total_min = max(int(target_visible_chars_min or 0), 200)
    total_max = max(int(target_visible_chars_max or 0), total_min + 120)
    reserve_min = max(int(getattr(settings, "chapter_closing_target_min_visible_chars", 180) or 180), 80)
    reserve_max = max(int(getattr(settings, "chapter_closing_target_max_visible_chars", 360) or 360), reserve_min)
    ratio = float(getattr(settings, "chapter_body_generation_ratio", 0.82) or 0.82)
    ratio = max(min(ratio, 0.92), 0.58)

    body_max = min(max(total_min, int(total_max * ratio)), max(total_max - reserve_min, total_min))
    body_min = max(int(body_max * 0.82), min(total_min, max(body_max - 260, 240)))
    closing_min = max(80, min(reserve_min, max(total_min - body_max, 80)))
    closing_max = max(closing_min, min(reserve_max, max(total_max - body_min, closing_min)))
    return {
        "body_min": body_min,
        "body_max": body_max,
        "closing_min": closing_min,
        "closing_max": closing_max,
    }


def _chapter_phase_timeouts(request_timeout_seconds: int | None, *, max_segments: int) -> tuple[int | None, int | None, int | None]:
    if request_timeout_seconds is None:
        return None, None, None
    total = max(int(request_timeout_seconds), 18)
    preferred_closing = max(int(getattr(settings, "chapter_closing_timeout_seconds", 28) or 28), 8)
    preferred_body_ratio = float(getattr(settings, "chapter_body_timeout_ratio", 0.76) or 0.76)
    preferred_body_ratio = max(min(preferred_body_ratio, 0.9), 0.58)
    preferred_body_min = max(int(getattr(settings, "chapter_body_min_timeout_seconds", 84) or 84), 12)
    preferred_continuation = max(
        int(getattr(settings, "chapter_continuation_preferred_timeout_seconds", 48) or 48),
        int(getattr(settings, "chapter_continuation_min_timeout_seconds", 36) or 36),
    )

    if total <= 28:
        closing_timeout = min(preferred_closing, max(total // 4, 8))
        body_budget = max(total - closing_timeout, 10)
    else:
        closing_timeout = min(preferred_closing, max(total // 5, 12))
        body_budget = max(total - closing_timeout, 12)

    segments = max(int(max_segments or 1), 1)
    if segments <= 1:
        return max(body_budget, min(preferred_body_min, total - 8)), None, closing_timeout

    initial_body_timeout = max(int(body_budget * preferred_body_ratio), min(preferred_body_min, body_budget))
    initial_body_timeout = min(initial_body_timeout, body_budget)
    continuation_timeout = min(preferred_continuation, max(body_budget - initial_body_timeout, 0))
    if continuation_timeout <= 0:
        continuation_timeout = preferred_continuation
    return initial_body_timeout, continuation_timeout, closing_timeout


def _remaining_request_budget_seconds(
    request_timeout_seconds: int | None,
    started_at: float,
    *,
    reserve_seconds: int = 0,
) -> int | None:
    if request_timeout_seconds is None:
        return None
    elapsed = max(time.monotonic() - started_at, 0.0)
    remaining = int(request_timeout_seconds - elapsed - reserve_seconds)
    return max(0, remaining)


def _resolve_safe_continuation_timeout(
    request_timeout_seconds: int | None,
    started_at: float,
    *,
    preferred_continuation_timeout: int | None,
    preferred_closing_timeout: int | None,
) -> int | None:
    if preferred_continuation_timeout is None:
        return None
    preferred = max(int(preferred_continuation_timeout), 8)
    hard_min = max(int(getattr(settings, "chapter_continuation_min_timeout_seconds", 36) or 36), 8)
    share = float(getattr(settings, "chapter_continuation_timeout_share", 0.62) or 0.62)
    share = max(min(share, 0.9), 0.35)
    closing_reserve = max(
        int(
            getattr(
                settings,
                "chapter_continuation_closing_reserve_seconds",
                max(preferred_closing_timeout or 0, int(getattr(settings, "chapter_closing_timeout_seconds", 28) or 28)),
            )
            or max(preferred_closing_timeout or 0, int(getattr(settings, "chapter_closing_timeout_seconds", 28) or 28))
        ),
        8,
    )
    remaining_total = _remaining_request_budget_seconds(request_timeout_seconds, started_at)
    if remaining_total is None:
        return preferred
    usable = max(remaining_total - closing_reserve, 0)
    if usable < hard_min:
        return None
    dynamic_timeout = max(hard_min, int(usable * share))
    return min(preferred, dynamic_timeout, usable)


def _resolve_safe_closing_timeout(
    request_timeout_seconds: int | None,
    started_at: float,
    *,
    preferred_closing_timeout: int | None,
) -> int | None:
    if preferred_closing_timeout is None:
        return None
    preferred = max(int(preferred_closing_timeout), 8)
    remaining_total = _remaining_request_budget_seconds(request_timeout_seconds, started_at)
    if remaining_total is None:
        return preferred
    minimum = max(min(preferred, 12), 8)
    if remaining_total >= preferred:
        return preferred
    if remaining_total >= minimum:
        return remaining_total
    return max(8, remaining_total)


def _chapter_max_total_visible_chars(target_visible_chars_max: int) -> int:
    configured_cap = max(int(getattr(settings, "chapter_body_total_visible_chars_cap", 0) or 0), 0)
    dynamic_floor = max(int(target_visible_chars_max * 1.85), target_visible_chars_max + 600)
    if configured_cap <= 0:
        return dynamic_floor
    return max(configured_cap, target_visible_chars_max + 200)


def _tail_is_stable_for_continue(text: str) -> bool:
    raw = (text or "").rstrip()
    if not raw:
        return False
    if raw[-1] not in "。！？!?…；;”』」》）)】":
        return False
    paired = (("“", "”"), ('"', '"'), ("『", "』"), ("「", "」"), ("（", "）"), ("(", ")"))
    for left, right in paired:
        if raw.count(left) > raw.count(right):
            return False
    return True


def _should_continue_body_generation(
    *,
    content: str,
    chapter_plan: dict[str, Any],
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    max_total_visible_chars: int,
    current_segments: int,
    max_segments: int,
) -> tuple[bool, str]:
    if current_segments >= max_segments:
        return False, "segment_cap_reached"

    current_len = len((content or "").strip())
    min_growth = max(int(getattr(settings, "chapter_body_continuation_min_growth_chars", 180) or 180), 20)
    force_closing_margin = max(int(getattr(settings, "chapter_body_force_closing_margin_chars", 220) or 220), 80)
    remaining_room = max_total_visible_chars - current_len
    if remaining_room < max(min_growth, force_closing_margin):
        return False, "budget_margin_reached"

    progress_kind = str(chapter_plan.get("progress_kind") or "").strip() or None
    progress_clear, _ = _progress_result_is_clear(content, progress_kind, chapter_plan=chapter_plan)
    weak_ending_pattern = _weak_ending(content)
    tail_stable = _tail_is_stable_for_continue(content)

    if current_len < target_visible_chars_min:
        return True, "below_target_min"
    if not tail_stable and current_len < max_total_visible_chars - force_closing_margin:
        return True, "tail_not_stable"
    if (not progress_clear) and current_len < min(target_visible_chars_max + force_closing_margin, max_total_visible_chars - force_closing_margin):
        return True, "progress_not_clear"
    if weak_ending_pattern and current_len < min(target_visible_chars_max + force_closing_margin, max_total_visible_chars - force_closing_margin):
        return True, "ending_still_weak"
    return False, "ready_for_closing"


def _dedupe_tail_overlap(base: str, addition: str, *, min_overlap: int = 8, max_overlap: int = 120) -> str:
    base_text = base or ""
    extra = addition or ""
    if not base_text or not extra:
        return extra
    limit = min(len(base_text), len(extra), max_overlap)
    for size in range(limit, min_overlap - 1, -1):
        if base_text[-size:] == extra[:size]:
            return extra[size:]
    return extra


def _merge_generated_closing(base: str, addition: str) -> str:
    base_text = (base or "").rstrip()
    extra = (addition or "").strip()
    if not extra:
        return base_text
    if not base_text:
        return extra
    if extra in base_text[-max(len(extra) + 24, 260):]:
        return base_text
    extra = _dedupe_tail_overlap(base_text, extra).lstrip()
    if not extra:
        return base_text
    terminal = "。！？!?…；;”』」》）)】"
    inline_starts = tuple("，。！？!?；;：:、）)】」』》」”’")
    if base_text[-1] in terminal and not extra.startswith(inline_starts):
        return f"{base_text}\n\n{extra}".strip()
    return f"{base_text}{extra}".strip()


def _generate_body_continuation(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    continuation_target_visible_chars_min: int,
    continuation_target_visible_chars_max: int,
    continuation_round: int,
    max_segments: int,
    timeout_seconds: int | None,
) -> str:
    text = call_text_response(
        stage="chapter_generation_continue",
        system_prompt=chapter_body_continue_system_prompt(),
        user_prompt=chapter_body_continue_user_prompt(
            chapter_plan=chapter_plan,
            existing_content=existing_content,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            continuation_target_visible_chars_min=continuation_target_visible_chars_min,
            continuation_target_visible_chars_max=continuation_target_visible_chars_max,
            continuation_round=continuation_round,
            max_segments=max_segments,
        ),
        max_output_tokens=max(int(getattr(settings, "chapter_body_continuation_max_output_tokens", 720) or 720), 220),
        timeout_seconds=timeout_seconds,
    )
    return _clean_plain_chapter_text(text, expected_title=None)


def generate_chapter_from_plan(
    novel_context: dict[str, Any],
    chapter_plan: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
    target_words: int,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    request_timeout_seconds: int | None = None,
) -> ChapterDraftPayload:
    phase_targets = _chapter_phase_visible_char_targets(
        target_visible_chars_min=target_visible_chars_min,
        target_visible_chars_max=target_visible_chars_max,
    )
    generation_started_at = time.monotonic()
    max_segments = max(int(getattr(settings, "chapter_body_max_segments", 2) or 2), 1)
    body_timeout, continuation_timeout, closing_timeout = _chapter_phase_timeouts(
        request_timeout_seconds,
        max_segments=max_segments,
    )
    body_token_ratio = float(getattr(settings, "chapter_body_max_output_tokens_ratio", 0.78) or 0.78)
    body_token_ratio = max(min(body_token_ratio, 0.95), 0.45)
    body_max_output_tokens = min(
        current_chapter_max_output_tokens(),
        max(int(current_chapter_max_output_tokens() * body_token_ratio), 700),
    )

    body_text = call_text_response(
        stage="chapter_generation_body",
        system_prompt=chapter_body_draft_system_prompt(),
        user_prompt=chapter_body_draft_user_prompt(
            novel_context=novel_context,
            chapter_plan=chapter_plan,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            active_interventions=active_interventions,
            target_words=target_words,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            body_target_visible_chars_min=phase_targets["body_min"],
            body_target_visible_chars_max=phase_targets["body_max"],
        ),
        max_output_tokens=body_max_output_tokens,
        timeout_seconds=body_timeout,
    )
    body_content = _clean_plain_chapter_text(body_text, expected_title=chapter_plan.get("title"))
    body_segments = 1
    continuation_rounds = 0
    body_stop_reason = "initial_body_complete"

    dynamic_enabled = bool(getattr(settings, "chapter_dynamic_continuation_enabled", True))
    continuation_target_min = max(int(getattr(settings, "chapter_body_continuation_target_min_visible_chars", 360) or 360), 120)
    continuation_target_max = max(
        int(getattr(settings, "chapter_body_continuation_target_max_visible_chars", 900) or 900),
        continuation_target_min,
    )
    min_growth = max(int(getattr(settings, "chapter_body_continuation_min_growth_chars", 180) or 180), 80)
    max_total_visible_chars = _chapter_max_total_visible_chars(target_visible_chars_max)

    while dynamic_enabled:
        should_continue, reason = _should_continue_body_generation(
            content=body_content,
            chapter_plan=chapter_plan,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            max_total_visible_chars=max_total_visible_chars,
            current_segments=body_segments,
            max_segments=max_segments,
        )
        body_stop_reason = reason
        if not should_continue:
            break

        remaining_room = max(max_total_visible_chars - len(body_content), 0)
        if remaining_room < min_growth:
            body_stop_reason = "growth_margin_reached"
            break

        dynamic_max = min(continuation_target_max, remaining_room)
        dynamic_min = min(continuation_target_min, dynamic_max)
        required_growth = max(min(dynamic_min // 3, 80), 24)
        if dynamic_max <= 0:
            body_stop_reason = "no_room_for_continuation"
            break

        round_continuation_timeout = _resolve_safe_continuation_timeout(
            request_timeout_seconds,
            generation_started_at,
            preferred_continuation_timeout=continuation_timeout,
            preferred_closing_timeout=closing_timeout,
        )
        if round_continuation_timeout is None:
            body_stop_reason = "insufficient_time_for_safe_continuation"
            break

        try:
            addition = _generate_body_continuation(
                chapter_plan=chapter_plan,
                existing_content=body_content,
                last_chapter=last_chapter,
                recent_summaries=recent_summaries,
                target_visible_chars_min=target_visible_chars_min,
                target_visible_chars_max=target_visible_chars_max,
                continuation_target_visible_chars_min=dynamic_min,
                continuation_target_visible_chars_max=dynamic_max,
                continuation_round=continuation_rounds + 1,
                max_segments=max_segments,
                timeout_seconds=round_continuation_timeout,
            )
        except GenerationError as exc:
            if exc.code == ErrorCodes.API_TIMEOUT and exc.stage == "chapter_generation_continue":
                logger.warning(
                    "chapter continuation timed out; falling back to closing novel_id_like=%s chapter_no=%s timeout=%s",
                    (chapter_plan.get("novel_id") or chapter_plan.get("trace_id") or "unknown"),
                    chapter_plan.get("chapter_no"),
                    round_continuation_timeout,
                )
                body_stop_reason = "continuation_timeout_fallback_to_closing"
                break
            raise
        merged = _merge_generated_closing(body_content, addition)
        growth = len(merged) - len(body_content)
        if growth < required_growth:
            body_stop_reason = "continuation_growth_too_small"
            break
        body_content = merged
        body_segments += 1
        continuation_rounds += 1

    final_content = body_content
    if getattr(settings, "chapter_closing_enabled", True):
        dynamic_closing_cap = max_total_visible_chars if continuation_rounds > 0 else target_visible_chars_max
        dynamic_closing_max = max(
            phase_targets["closing_min"],
            min(phase_targets["closing_max"], max(dynamic_closing_cap - len(body_content), phase_targets["closing_min"])),
        )
        dynamic_closing_min = min(phase_targets["closing_min"], dynamic_closing_max)
        effective_closing_timeout = _resolve_safe_closing_timeout(
            request_timeout_seconds,
            generation_started_at,
            preferred_closing_timeout=closing_timeout,
        )
        closing_text = call_text_response(
            stage="chapter_generation_closing",
            system_prompt=chapter_closing_system_prompt(),
            user_prompt=chapter_closing_user_prompt(
                chapter_plan=chapter_plan,
                existing_content=body_content,
                last_chapter=last_chapter,
                recent_summaries=recent_summaries,
                target_visible_chars_min=target_visible_chars_min,
                target_visible_chars_max=dynamic_closing_cap,
                closing_target_visible_chars_min=dynamic_closing_min,
                closing_target_visible_chars_max=dynamic_closing_max,
            ),
            max_output_tokens=max(int(getattr(settings, "chapter_closing_max_output_tokens", 520) or 520), 180),
            timeout_seconds=effective_closing_timeout,
        )
        closing_content = _clean_plain_chapter_text(closing_text, expected_title=None)
        final_content = _merge_generated_closing(body_content, closing_content)
        if body_stop_reason == "initial_body_complete" and continuation_rounds > 0:
            body_stop_reason = "continued_then_closed"

    data = {
        "title": (chapter_plan.get("title") or "").strip() or f"第{chapter_plan.get('chapter_no', '')}章",
        "content": final_content,
        "body_segments": body_segments,
        "continuation_rounds": continuation_rounds,
        "body_stop_reason": body_stop_reason,
    }
    return ChapterDraftPayload.model_validate(data)


def extend_chapter_text(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    repair_mode: str = "append_inline_tail",
    ending_issue: str | None = None,
    repair_attempt_no: int = 1,
    previous_repair_modes: list[str] | None = None,
    request_timeout_seconds: int | None = None,
) -> str:
    mode_token_budget = {
        "append_inline_tail": min(max(current_chapter_max_output_tokens() // 4, 220), 420),
        "replace_last_paragraph": min(max(current_chapter_max_output_tokens() // 3, 360), 620),
        "replace_last_two_paragraphs": min(max(current_chapter_max_output_tokens() // 2, 520), 900),
    }
    text = call_text_response(
        stage="chapter_extension",
        system_prompt=chapter_extension_system_prompt(repair_mode=repair_mode),
        user_prompt=chapter_extension_user_prompt(
            chapter_plan=chapter_plan,
            existing_content=existing_content,
            reason=reason,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            repair_mode=repair_mode,
            ending_issue=ending_issue,
            repair_attempt_no=repair_attempt_no,
            previous_repair_modes=previous_repair_modes,
        ),
        max_output_tokens=mode_token_budget.get(repair_mode, min(max(current_chapter_max_output_tokens() // 3, 360), 620)),
        timeout_seconds=request_timeout_seconds,
    )
    return _clean_plain_chapter_text(text, expected_title=None)



def generate_chapter_title_candidates(
    *,
    chapter_no: int,
    original_title: str,
    chapter_plan: dict[str, Any],
    chapter_content: str,
    recent_titles: list[str],
    cooled_terms: list[str],
    summary: dict[str, Any] | None = None,
    candidate_count: int = 5,
    request_timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    if not is_openai_enabled():
        raise GenerationError(
            code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
            message="章节标题精修需要可用的 AI，但当前未检测到可用模型配置。",
            stage="chapter_title_refinement",
            retryable=True,
            http_status=503,
            provider=provider_name(),
        )

    content = (chapter_content or "").strip()
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    opening_excerpt = _truncate_visible(paragraphs[0] if paragraphs else normalized, 220)
    closing_excerpt = _truncate_visible(paragraphs[-1] if paragraphs else normalized[-220:], 220)
    content_digest = {
        "opening_excerpt": opening_excerpt,
        "closing_excerpt": closing_excerpt,
        "content_length": len(content),
    }
    summary_payload = summary or {}
    data = call_json_response(
        stage="chapter_title_refinement",
        system_prompt=chapter_title_refinement_system_prompt(),
        user_prompt=chapter_title_refinement_user_prompt(
            chapter_no=chapter_no,
            original_title=original_title,
            chapter_plan=chapter_plan,
            content_digest=content_digest,
            summary_payload=summary_payload,
            recent_titles=recent_titles,
            cooled_terms=cooled_terms,
            candidate_count=candidate_count,
        ),
        max_output_tokens=max(int(getattr(settings, "chapter_title_max_output_tokens", 900) or 900), 320),
        timeout_seconds=request_timeout_seconds,
    )
    payload = ChapterTitleRefinementPayload.model_validate(data)
    results: list[dict[str, Any]] = []
    if payload.recommended_title:
        results.append(
            {
                "title": payload.recommended_title,
                "title_type": "推荐标题",
                "angle": "模型推荐",
                "reason": "模型认为它最贴近成稿且更不易重复。",
                "source": "ai_recommended",
            }
        )
    for item in payload.candidates[: max(candidate_count, 1)]:
        if not item.title:
            continue
        results.append(
            {
                "title": item.title,
                "title_type": item.title_type,
                "angle": item.angle,
                "reason": item.reason,
                "source": "ai",
            }
        )
    return results


def summarize_chapter(title: str, content: str, request_timeout_seconds: int | None = None) -> ChapterSummaryPayload:
    mode = (getattr(settings, "chapter_summary_mode", "auto") or "auto").lower().strip()
    if mode == "heuristic" or (mode == "auto" and provider_name() in {"groq", "deepseek"}) or (mode == "auto" and request_timeout_seconds is not None and request_timeout_seconds < int(getattr(settings, "chapter_summary_force_heuristic_below_seconds", 30) or 30)):
        return _heuristic_chapter_summary(title, content)

    try:
        text = call_text_response(
            stage="chapter_summary_generation",
            system_prompt=summary_system_prompt(),
            user_prompt=summary_user_prompt(chapter_title=title, chapter_content=content),
            max_output_tokens=settings.chapter_summary_max_output_tokens,
            timeout_seconds=request_timeout_seconds,
        )
        return _parse_labeled_summary(text)
    except GenerationError:
        if mode == "auto":
            return _heuristic_chapter_summary(title, content)
        raise


def parse_instruction_with_openai(raw_instruction: str) -> ParsedInstructionPayload:
    data = call_json_response(
        stage="instruction_parse",
        system_prompt=instruction_parse_system_prompt(),
        user_prompt=instruction_parse_user_prompt(raw_instruction),
        max_output_tokens=600,
    )
    return ParsedInstructionPayload.model_validate(data)
