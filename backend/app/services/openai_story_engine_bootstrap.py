from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, extract_json, provider_name
from app.services.prompt_templates import (
    arc_outline_system_prompt,
    arc_outline_user_prompt,
    bootstrap_execution_profile_system_prompt,
    bootstrap_execution_profile_user_prompt,
    bootstrap_intent_parse_system_prompt,
    bootstrap_intent_parse_user_prompt,
    bootstrap_intent_strategy_bundle_system_prompt,
    bootstrap_intent_strategy_bundle_user_prompt,
    bootstrap_story_review_system_prompt,
    bootstrap_story_review_user_prompt,
    bootstrap_strategy_arbitration_system_prompt,
    bootstrap_strategy_arbitration_user_prompt,
    bootstrap_strategy_candidates_system_prompt,
    bootstrap_strategy_candidates_user_prompt,
    bootstrap_outline_title_system_prompt,
    bootstrap_outline_title_user_prompt,
    bootstrap_title_system_prompt,
    bootstrap_title_user_prompt,
    global_outline_system_prompt,
    global_outline_user_prompt,
    instruction_parse_system_prompt,
    instruction_parse_user_prompt,
    story_engine_diagnosis_system_prompt,
    story_engine_diagnosis_user_prompt,
    story_engine_strategy_bundle_system_prompt,
    story_engine_strategy_bundle_user_prompt,
    story_strategy_card_system_prompt,
    story_strategy_card_user_prompt,
)
from app.services.story_blueprint_builders import build_flow_templates


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


class ParsedInstructionPayload(BaseModel):
    character_focus: dict[str, float] = Field(default_factory=dict)
    tone: str | None = None
    pace: str | None = None
    protected_characters: list[str] = Field(default_factory=list)
    relationship_direction: str | None = None


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
    flow_template_label: str | None = None
    flow_template_summary: str | None = None
    flow_template_beats: list[str] | None = None
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


class OpeningWindowPhase(BaseModel):
    range: str = ""
    stage_mission: str = ""
    reader_hook: str = ""
    frequent_elements: list[str] = Field(default_factory=list)
    limited_elements: list[str] = Field(default_factory=list)
    relationship_tasks: list[str] = Field(default_factory=list)
    phase_result: str = ""


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


class StoryStrategyCardPayload(BaseModel):
    story_promise: str = ""
    strategic_premise: str = ""
    main_conflict_axis: str = ""
    long_term_direction: str = ""
    opening_five_summary: str = ""
    opening_window: OpeningWindowPhase = Field(default_factory=OpeningWindowPhase)
    rolling_replan_rule: str = ""
    frequent_event_types: list[str] = Field(default_factory=list)
    limited_event_types: list[str] = Field(default_factory=list)
    must_establish_relationships: list[str] = Field(default_factory=list)
    escalation_path: list[str] = Field(default_factory=list)
    anti_homogenization_rules: list[str] = Field(default_factory=list)


class StoryEngineStrategyBundlePayload(BaseModel):
    story_engine_diagnosis: StoryEngineDiagnosisPayload
    story_strategy_card: StoryStrategyCardPayload


class BootstrapIntentPacket(BaseModel):
    story_promise: str
    protagonist_core_drive: str
    core_conflict: str
    expected_payoffs: list[str] = Field(default_factory=list)
    pacing_mode: str
    world_reveal_mode: str
    first_ten_chapter_tasks: list[str] = Field(default_factory=list)
    major_risks: list[str] = Field(default_factory=list)


class BootstrapIntentStrategyBundlePayload(BaseModel):
    bootstrap_intent_packet: BootstrapIntentPacket
    story_engine_diagnosis: StoryEngineDiagnosisPayload
    story_strategy_card: StoryStrategyCardPayload


class BootstrapStrategyCandidate(BaseModel):
    candidate_id: str
    design_focus: str
    story_engine_diagnosis: StoryEngineDiagnosisPayload
    story_strategy_card: StoryStrategyCardPayload


class BootstrapStrategyCandidatesPayload(BaseModel):
    candidates: list[BootstrapStrategyCandidate] = Field(default_factory=list)


class BootstrapInitializationCardsPayload(BaseModel):
    story_engine_card: dict[str, Any] = Field(default_factory=dict)
    mainline_drive_card: dict[str, Any] = Field(default_factory=dict)
    growth_upgrade_card: dict[str, Any] = Field(default_factory=dict)
    pressure_source_card: dict[str, Any] = Field(default_factory=dict)
    payoff_rhythm_card: dict[str, Any] = Field(default_factory=dict)
    darkline_card: dict[str, Any] = Field(default_factory=dict)
    foreshadowing_mother_card: dict[str, Any] = Field(default_factory=dict)
    chapter_structure_card: dict[str, Any] = Field(default_factory=dict)
    expression_emphasis_card: dict[str, Any] = Field(default_factory=dict)
    world_reveal_card: dict[str, Any] = Field(default_factory=dict)


class BootstrapStrategyArbitrationPayload(BaseModel):
    selected_candidate_id: str
    selection_reason: str
    merge_notes: list[str] = Field(default_factory=list)
    story_engine_diagnosis: StoryEngineDiagnosisPayload
    story_strategy_card: StoryStrategyCardPayload
    initialization_cards: BootstrapInitializationCardsPayload = Field(default_factory=BootstrapInitializationCardsPayload)


class BookExecutionProfilePriority(BaseModel):
    high: list[str] = Field(default_factory=list)
    medium: list[str] = Field(default_factory=list)
    low: list[str] = Field(default_factory=list)


class BookExecutionForeshadowPriority(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    hold_back: list[str] = Field(default_factory=list)


class BookExecutionCharacterPriority(BaseModel):
    high: list[str] = Field(default_factory=list)
    medium: list[str] = Field(default_factory=list)


class BookExecutionRhythmBias(BaseModel):
    opening_pace: str = ""
    world_reveal_density: str = ""
    relationship_weight: str = ""
    hook_strength: str = ""
    payoff_interval: str = ""
    pressure_curve: str = ""


class BookExecutionProfilePayload(BaseModel):
    positioning_summary: str = ""
    template_pool_policy: str = ""
    flow_family_priority: BookExecutionProfilePriority = Field(default_factory=BookExecutionProfilePriority)
    scene_template_priority: BookExecutionProfilePriority = Field(default_factory=BookExecutionProfilePriority)
    payoff_priority: BookExecutionProfilePriority = Field(default_factory=BookExecutionProfilePriority)
    foreshadowing_priority: BookExecutionForeshadowPriority = Field(default_factory=BookExecutionForeshadowPriority)
    writing_strategy_priority: BookExecutionProfilePriority = Field(default_factory=BookExecutionProfilePriority)
    character_template_priority: BookExecutionCharacterPriority = Field(default_factory=BookExecutionCharacterPriority)
    rhythm_bias: BookExecutionRhythmBias
    demotion_rules: list[str] = Field(default_factory=list)


class BootstrapArcAdjustment(BaseModel):
    chapter_no: int
    field: str
    value: str
    reason: str | None = None


class BootstrapStoryReviewPayload(BaseModel):
    status: str
    summary: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    must_fix: list[str] = Field(default_factory=list)
    arc_adjustments: list[BootstrapArcAdjustment] = Field(default_factory=list)


class BootstrapTitlePayload(BaseModel):
    title: str
    packaging_line: str | None = None
    reason: str | None = None


class BootstrapOutlineAndTitlePayload(BaseModel):
    title: str
    packaging_line: str | None = None
    reason: str | None = None
    global_outline: GlobalOutlinePayload


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


def _book_execution_profile_from_story_bible(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    profile = ((story_bible or {}).get("book_execution_profile") or {}) if isinstance(story_bible, dict) else {}
    return profile if isinstance(profile, dict) else {}



def _priority_bucket_score(value: str, *, high: list[str] | None = None, medium: list[str] | None = None, low: list[str] | None = None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    high_list = [str(item or "").strip() for item in (high or []) if str(item or "").strip()]
    medium_list = [str(item or "").strip() for item in (medium or []) if str(item or "").strip()]
    low_list = [str(item or "").strip() for item in (low or []) if str(item or "").strip()]
    if any(token == text or token in text or text in token for token in high_list):
        return 3.5
    if any(token == text or token in text or text in token for token in medium_list):
        return 1.2
    if any(token == text or token in text or text in token for token in low_list):
        return -2.4
    return 0.0



def _flow_match_score(template: dict[str, Any], chapter: ChapterPlan, recent_flow_ids: list[str], story_bible: dict[str, Any] | None = None) -> float:
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
    profile = _book_execution_profile_from_story_bible(story_bible)
    flow_priority = (profile.get("flow_family_priority") or {}) if isinstance(profile, dict) else {}
    score += _priority_bucket_score(
        str(template.get("family") or "").strip(),
        high=list(flow_priority.get("high") or []),
        medium=list(flow_priority.get("medium") or []),
        low=list(flow_priority.get("low") or []),
    )
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
        score = _flow_match_score(item, chapter, recent_flow_ids, story_bible)
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


def _preferred_hook_styles_for_profile(profile: dict[str, Any] | None) -> list[str]:
    rhythm = ((profile or {}).get("rhythm_bias") or {}) if isinstance(profile, dict) else {}
    hook_strength = str(rhythm.get("hook_strength") or "").strip()
    pressure_curve = str(rhythm.get("pressure_curve") or "").strip()
    if any(token in hook_strength for token in ["强", "高"]):
        ordered = ["危险逼近", "信息反转", "人物选择", "异象", "余味收束", "平稳过渡"]
    elif any(token in hook_strength for token in ["弱", "低"]):
        ordered = ["平稳过渡", "余味收束", "人物选择", "信息反转", "危险逼近", "异象"]
    else:
        ordered = ["人物选择", "信息反转", "危险逼近", "余味收束", "平稳过渡", "异象"]
    if any(token in pressure_curve for token in ["渐压", "递增"]):
        ordered = ["危险逼近", "人物选择", "信息反转", "余味收束", "平稳过渡", "异象"]
    seen: set[str] = set()
    result: list[str] = []
    for item in ordered:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result



def _apply_book_execution_profile_to_chapter(chapter: ChapterPlan, story_bible: dict[str, Any], *, chapter_offset: int = 0) -> None:
    profile = _book_execution_profile_from_story_bible(story_bible)
    if not profile:
        return
    rhythm = (profile.get("rhythm_bias") or {}) if isinstance(profile, dict) else {}
    if not getattr(chapter, "hook_style", None):
        hook_styles = _preferred_hook_styles_for_profile(profile)
        if hook_styles:
            chapter.hook_style = hook_styles[int(chapter_offset or 0) % len(hook_styles)]
    if not getattr(chapter, "opening_beat", None):
        opening_pace = str(rhythm.get("opening_pace") or "稳推").strip() or "稳推"
        chapter.opening_beat = f"按{opening_pace}节奏开场，主角先手推进。"[:24]
    if not getattr(chapter, "mid_turn", None):
        pressure_curve = str(rhythm.get("pressure_curve") or "渐压").strip() or "渐压"
        chapter.mid_turn = f"中段按{pressure_curve}抬压并逼出换招。"[:24]
    if not getattr(chapter, "discovery", None):
        world_density = str(rhythm.get("world_reveal_density") or "中").strip() or "中"
        chapter.discovery = f"只按{world_density}密度补当前必要信息。"[:24]
    if not getattr(chapter, "closing_image", None):
        hook_strength = str(rhythm.get("hook_strength") or "中强").strip() or "中强"
        chapter.closing_image = f"章尾按{hook_strength}拉力落在结果或新压上。"[:24]
    if not getattr(chapter, "flow_variation_note", None):
        flow_priority = (profile.get("flow_family_priority") or {}) if isinstance(profile, dict) else {}
        high = [str(item or "").strip() for item in (flow_priority.get("high") or []) if str(item or "").strip()]
        if high:
            chapter.flow_variation_note = f"本章优先贴近{' / '.join(high[:2])}系节奏。"[:36]
    relationship_weight = str(rhythm.get("relationship_weight") or "").strip()
    if not getattr(chapter, "supporting_character_note", None) and relationship_weight:
        chapter.supporting_character_note = (f"关系占比{relationship_weight}，配角先给立场与受压反应。")[:40]
    notes: list[str] = []
    positioning = str(profile.get("positioning_summary") or "").strip()
    if positioning:
        notes.append(f"长期气质：{positioning[:28]}")
    opening_pace = str(rhythm.get("opening_pace") or "").strip()
    if opening_pace:
        notes.append(f"开场节奏{opening_pace}")
    world_density = str(rhythm.get("world_reveal_density") or "").strip()
    if world_density:
        notes.append(f"世界揭示{world_density}")
    payoff_interval = str(rhythm.get("payoff_interval") or "").strip()
    if payoff_interval:
        notes.append(f"兑现节奏{payoff_interval}")
    pressure_curve = str(rhythm.get("pressure_curve") or "").strip()
    if pressure_curve:
        notes.append(f"压力曲线{pressure_curve}")
    demotion_rules = [str(item or "").strip() for item in (profile.get("demotion_rules") or []) if str(item or "").strip()]
    if demotion_rules:
        notes.append(f"避免：{demotion_rules[0][:18]}")
    existing = str(chapter.writing_note or "").strip()
    merged = "；".join([item for item in notes if item])
    if merged:
        chapter.writing_note = (f"{existing} {merged}".strip() if existing else merged)[:120]


def _apply_flow_template_to_chapter(chapter: ChapterPlan, story_bible: dict[str, Any]) -> None:
    template = _choose_flow_template_for_chapter(chapter, story_bible)
    if not template:
        return
    flow_id = str(template.get("flow_id") or "").strip()
    chapter.flow_template_id = flow_id or getattr(chapter, "flow_template_id", None)
    if not getattr(chapter, "flow_template_tag", None):
        chapter.flow_template_tag = str(template.get("quick_tag") or template.get("label") or flow_id or "").strip() or None
    if not getattr(chapter, "flow_template_name", None):
        chapter.flow_template_name = str(template.get("name") or template.get("label") or flow_id or "").strip() or None
    if not getattr(chapter, "flow_template_label", None):
        chapter.flow_template_label = str(template.get("label") or template.get("name") or flow_id or "").strip() or None
    beats = [str(item or "").strip() for item in ((template.get("beats") or template.get("sequence") or template.get("turning_points") or [])) if str(item or "").strip()]
    if beats and not getattr(chapter, "flow_template_beats", None):
        chapter.flow_template_beats = beats[:6]
    if beats and not getattr(chapter, "flow_turning_points", None):
        chapter.flow_turning_points = beats[:4]
    if not getattr(chapter, "flow_template_summary", None):
        chapter.flow_template_summary = str(template.get("summary") or template.get("closing_feel") or "").strip() or None
    if not getattr(chapter, "writing_note", None):
        chapter.writing_note = ""
    note = str(chapter.writing_note or "").strip()
    if beats:
        beat_hint = "；".join(beats[:4])
        extra = f"流程节奏参考：{beat_hint}。"
        if extra not in note:
            chapter.writing_note = f"{note} {extra}".strip()


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
    legacy_opening = getattr(strategy, "__pydantic_extra__", {}) or {}
    old_phase = legacy_opening.get("chapter_1_to_10") if isinstance(legacy_opening, dict) else {}
    if isinstance(old_phase, dict):
        if not strategy.opening_window.range:
            strategy.opening_window.range = str(old_phase.get("range") or "")
        if not strategy.opening_window.stage_mission:
            strategy.opening_window.stage_mission = str(old_phase.get("stage_mission") or "")
        if not strategy.opening_window.reader_hook:
            strategy.opening_window.reader_hook = str(old_phase.get("reader_hook") or "")
        if not strategy.opening_window.frequent_elements:
            strategy.opening_window.frequent_elements = list(old_phase.get("frequent_elements") or [])
        if not strategy.opening_window.limited_elements:
            strategy.opening_window.limited_elements = list(old_phase.get("limited_elements") or [])
        if not strategy.opening_window.relationship_tasks:
            strategy.opening_window.relationship_tasks = list(old_phase.get("relationship_tasks") or [])
        if not strategy.opening_window.phase_result:
            strategy.opening_window.phase_result = str(old_phase.get("phase_result") or "")
        if not strategy.opening_five_summary:
            strategy.opening_five_summary = str(legacy_opening.get("first_30_mainline_summary") or old_phase.get("stage_mission") or "")

    phase = strategy.opening_window
    if not strategy.story_promise:
        strategy.story_promise = "开书就要让读者明确感到这本书有自己的推进方式。"
    if not strategy.strategic_premise:
        strategy.strategic_premise = "围绕主角处境、目标、代价与更大局势持续升级。"
    if not strategy.main_conflict_axis:
        strategy.main_conflict_axis = "立足需求与暴露风险的长期拉扯。"
    if not strategy.long_term_direction:
        strategy.long_term_direction = "先立足，再扩张关系、资源与地图，始终让成长绑定代价与后果。"
    if not strategy.opening_five_summary:
        strategy.opening_five_summary = "开局五章围绕立足、关系绑定、阶段破局与第一次明确回报展开。"
    if not phase.range:
        phase.range = "1-5"
    if not phase.stage_mission:
        phase.stage_mission = "先用最有辨识度的推进方式抓住读者，并立住修炼与成长主线。"
    if not phase.reader_hook:
        phase.reader_hook = "这一阶段必须给读者明确的局势变化、第一轮回报和继续追更的理由。"
    if not phase.frequent_elements:
        phase.frequent_elements = ["主角主动选择", "具体结果", "关系或资源变化"]
    if not phase.limited_elements:
        phase.limited_elements = ["重复试探同一线索"]
    if not phase.relationship_tasks:
        phase.relationship_tasks = ["建立或改写一条关键关系"]
    if not phase.phase_result:
        phase.phase_result = "主角拿到第一阶段立足资本，并进入下一轮五章滚动规划。"
    strategy.opening_window = phase
    if not strategy.rolling_replan_rule:
        strategy.rolling_replan_rule = "初始化只定书级骨架和首个五章方向，之后每五章重规划一次。"
    if not strategy.frequent_event_types:
        strategy.frequent_event_types = ["关系推进类", "资源获取类", "反制类"]
    if not strategy.limited_event_types:
        strategy.limited_event_types = ["连续被怀疑后被动应付"]
    if not strategy.must_establish_relationships:
        strategy.must_establish_relationships = ["核心绑定角色", "长期压迫源", "阶段合作对象"]
    if not strategy.escalation_path:
        strategy.escalation_path = ["处境压力", "局部破局", "关系重组", "阶段高潮"]
    if not strategy.anti_homogenization_rules:
        strategy.anti_homogenization_rules = ["不要让开局五章只围着一个物件打转", "滚动重规划后也要持续换推进重心"]
    return strategy


def _normalize_bootstrap_intent(payload: dict[str, Any], packet: BootstrapIntentPacket) -> BootstrapIntentPacket:
    genre = str((payload or {}).get("genre") or "").strip()
    premise = str((payload or {}).get("premise") or "").strip()
    protagonist = str((payload or {}).get("protagonist_name") or "主角").strip()
    if not packet.story_promise:
        packet.story_promise = f"让读者持续看到{protagonist}如何在‘{premise or genre}’里一步步破局。"
    if not packet.protagonist_core_drive:
        packet.protagonist_core_drive = f"{protagonist}必须先保住立足点，再争取更主动的位置。"
    if not packet.core_conflict:
        packet.core_conflict = f"{protagonist}的生存需求与更大规则压迫之间的拉扯。"
    if not packet.expected_payoffs:
        packet.expected_payoffs = ["第一轮有效收益", "更高层风险显影", "关键关系站位变化"]
    if not packet.pacing_mode:
        packet.pacing_mode = "稳推但每章要有结果"
    if not packet.world_reveal_mode:
        packet.world_reveal_mode = "局部先行，逐层抬高"
    if not packet.first_ten_chapter_tasks:
        packet.first_ten_chapter_tasks = ["建立主角处境", "钉牢主线入口", "给第一轮明确回报"]
    if not packet.major_risks:
        packet.major_risks = ["连续只写气氛不落结果", "重复同一种试探结构"]
    return packet



def _normalize_bootstrap_strategy_candidates(payload: dict[str, Any], bundle: BootstrapStrategyCandidatesPayload) -> BootstrapStrategyCandidatesPayload:
    normalized: list[BootstrapStrategyCandidate] = []
    fallback_ids = ["A", "B", "C"]
    for idx, item in enumerate(bundle.candidates[:3]):
        item.candidate_id = str(item.candidate_id or fallback_ids[idx]).strip()[:8] or fallback_ids[idx]
        if not item.design_focus:
            item.design_focus = f"候选{item.candidate_id}：强调不同的开局抓力与阶段推进方式。"
        item.story_engine_diagnosis = _normalize_story_engine_diagnosis(payload, item.story_engine_diagnosis)
        item.story_strategy_card = _normalize_story_strategy_card(item.story_strategy_card)
        normalized.append(item)
    if not normalized:
        fallback = generate_story_engine_strategy_bundle(payload, {})
        normalized.append(BootstrapStrategyCandidate(candidate_id="A", design_focus="默认候选", story_engine_diagnosis=fallback.story_engine_diagnosis, story_strategy_card=fallback.story_strategy_card))
    bundle.candidates = normalized
    return bundle



def _normalize_priority_bucket(items: list[Any] | None, *, limit: int = 6) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        text = str(item or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text[:40])
        if len(output) >= limit:
            break
    return output


def _fallback_priority(*preferred: str, available: list[str], low_defaults: list[str] | None = None) -> BookExecutionProfilePriority:
    high = [item for item in _normalize_priority_bucket(list(preferred), limit=6) if item in available]
    medium = [item for item in available if item not in high][:6]
    low = [item for item in _normalize_priority_bucket(low_defaults or [], limit=6) if item in available and item not in high and item not in medium]
    return BookExecutionProfilePriority(high=high, medium=medium, low=low)


def _normalize_book_execution_profile(
    payload: dict[str, Any],
    template_pool_profile: dict[str, Any],
    diagnosis: StoryEngineDiagnosisPayload,
    strategy: StoryStrategyCardPayload,
    profile: BookExecutionProfilePayload,
) -> BookExecutionProfilePayload:
    flow_available = [str(item).strip() for item in (((template_pool_profile.get('flow_templates') or {}).get('families')) or []) if str(item).strip()] or ['成长', '冲突', '探查', '关系']
    scene_available = [str(item).strip() for item in (((template_pool_profile.get('scene_templates') or {}).get('scene_ids')) or []) if str(item).strip()] or ['same_scene_continuation', 'bridge_settlement']
    payoff_available = [str(item).strip() for item in (((template_pool_profile.get('payoff_cards') or {}).get('sample_names')) or []) if str(item).strip()] or ['捡漏反压', '公开打脸']
    foreshadow_available = [str(item).strip() for item in (((template_pool_profile.get('foreshadowing') or {}).get('parent_names')) or []) if str(item).strip()] or ['身份真相型', '规则异常型']
    writing_available = [str(item).strip() for item in (((template_pool_profile.get('writing_cards') or {}).get('strategy_ids')) or []) if str(item).strip()] or ['continuity_guard', 'proactive_drive']
    character_available = [str(item).strip() for item in (((template_pool_profile.get('character_templates') or {}).get('sample_ids')) or []) if str(item).strip()] or ['starter_cautious_observer']

    if not str(profile.positioning_summary or '').strip():
        profile.positioning_summary = f"{diagnosis.primary_story_engine}为主轴，整套修仙模板池全量保留，具体章节再做 AI 重筛。"[:120]
    if not str(profile.template_pool_policy or '').strip():
        profile.template_pool_policy = '整套修仙模板池全量保留；初始化阶段只定义长期偏置与降权规则，具体取用交给章级 AI 重筛。'

    if not (profile.flow_family_priority.high or profile.flow_family_priority.medium or profile.flow_family_priority.low):
        profile.flow_family_priority = _fallback_priority(*list(strategy.frequent_event_types[:3]), available=flow_available, low_defaults=list(strategy.limited_event_types[:3]))
    else:
        profile.flow_family_priority.high = [item for item in _normalize_priority_bucket(profile.flow_family_priority.high) if item in flow_available]
        profile.flow_family_priority.medium = [item for item in _normalize_priority_bucket(profile.flow_family_priority.medium) if item in flow_available and item not in profile.flow_family_priority.high]
        profile.flow_family_priority.low = [item for item in _normalize_priority_bucket(profile.flow_family_priority.low) if item in flow_available and item not in profile.flow_family_priority.high and item not in profile.flow_family_priority.medium]

    for bucket_name, available in [('scene_template_priority', scene_available), ('payoff_priority', payoff_available), ('writing_strategy_priority', writing_available)]:
        bucket = getattr(profile, bucket_name)
        bucket.high = [item for item in _normalize_priority_bucket(bucket.high) if item in available]
        bucket.medium = [item for item in _normalize_priority_bucket(bucket.medium) if item in available and item not in bucket.high]
        bucket.low = [item for item in _normalize_priority_bucket(bucket.low) if item in available and item not in bucket.high and item not in bucket.medium]
        if not (bucket.high or bucket.medium or bucket.low):
            filled = _fallback_priority(available[0] if available else '', available=available)
            bucket.high, bucket.medium, bucket.low = filled.high, filled.medium, filled.low

    profile.foreshadowing_priority.primary = [item for item in _normalize_priority_bucket(profile.foreshadowing_priority.primary) if item in foreshadow_available]
    profile.foreshadowing_priority.secondary = [item for item in _normalize_priority_bucket(profile.foreshadowing_priority.secondary) if item in foreshadow_available and item not in profile.foreshadowing_priority.primary]
    profile.foreshadowing_priority.hold_back = _normalize_priority_bucket(profile.foreshadowing_priority.hold_back)
    if not profile.foreshadowing_priority.primary:
        profile.foreshadowing_priority.primary = foreshadow_available[:2]
    if not profile.foreshadowing_priority.secondary:
        profile.foreshadowing_priority.secondary = [item for item in foreshadow_available if item not in profile.foreshadowing_priority.primary][:2]

    profile.character_template_priority.high = [item for item in _normalize_priority_bucket(profile.character_template_priority.high) if item in character_available]
    profile.character_template_priority.medium = [item for item in _normalize_priority_bucket(profile.character_template_priority.medium) if item in character_available and item not in profile.character_template_priority.high]
    if not profile.character_template_priority.high:
        profile.character_template_priority.high = character_available[:2]
    if not profile.character_template_priority.medium:
        profile.character_template_priority.medium = [item for item in character_available if item not in profile.character_template_priority.high][:2]

    profile.rhythm_bias.opening_pace = str(profile.rhythm_bias.opening_pace or diagnosis.pacing_profile or '稳推').strip()[:24]
    profile.rhythm_bias.world_reveal_density = str(profile.rhythm_bias.world_reveal_density or diagnosis.world_reveal_strategy or '中').strip()[:24]
    profile.rhythm_bias.relationship_weight = str(profile.rhythm_bias.relationship_weight or ('中' if strategy.must_establish_relationships else '低')).strip()[:16]
    profile.rhythm_bias.hook_strength = str(profile.rhythm_bias.hook_strength or '中强').strip()[:16]
    profile.rhythm_bias.payoff_interval = str(profile.rhythm_bias.payoff_interval or '中短').strip()[:16]
    profile.rhythm_bias.pressure_curve = str(profile.rhythm_bias.pressure_curve or '渐压').strip()[:16]
    profile.demotion_rules = _normalize_priority_bucket(profile.demotion_rules or diagnosis.avoid_tropes or strategy.limited_event_types, limit=5)
    if len(profile.demotion_rules) < 2:
        for fallback in ['不要连续重复同一试探结构', '不要前期高密度硬灌世界说明']:
            if fallback not in profile.demotion_rules:
                profile.demotion_rules.append(fallback)
            if len(profile.demotion_rules) >= 2:
                break
    return profile


def _normalize_initialization_cards(
    *,
    payload: dict[str, Any],
    intent_packet: BootstrapIntentPacket,
    diagnosis: StoryEngineDiagnosisPayload,
    strategy: StoryStrategyCardPayload,
    cards: BootstrapInitializationCardsPayload,
) -> BootstrapInitializationCardsPayload:
    protagonist = str((payload or {}).get("protagonist_name") or "主角").strip() or "主角"
    cards.story_engine_card = dict(cards.story_engine_card or {})
    cards.story_engine_card.setdefault("engine_name", diagnosis.primary_story_engine)
    cards.story_engine_card.setdefault("core_loop", diagnosis.protagonist_action_logic)
    cards.story_engine_card.setdefault("do_not_write", list(diagnosis.avoid_tropes or [])[:4])

    cards.mainline_drive_card = dict(cards.mainline_drive_card or {})
    cards.mainline_drive_card.setdefault("short_term_goal", (strategy.opening_window.stage_mission or "开局五章先抓住读者"))
    cards.mainline_drive_card.setdefault("mid_term_goal", (strategy.long_term_direction or strategy.opening_five_summary or strategy.strategic_premise))
    cards.mainline_drive_card.setdefault("pressure_source", strategy.main_conflict_axis)

    cards.growth_upgrade_card = dict(cards.growth_upgrade_card or {})
    cards.growth_upgrade_card.setdefault("growth_path", diagnosis.power_growth_strategy)
    cards.growth_upgrade_card.setdefault("cost_rule", "成长必须绑定资源、代价与后果。")
    cards.growth_upgrade_card.setdefault("unlock_style", "每次升级都要带来新选择，而不只是数值上涨。")

    cards.pressure_source_card = dict(cards.pressure_source_card or {})
    cards.pressure_source_card.setdefault("core_pressure", intent_packet.core_conflict)
    cards.pressure_source_card.setdefault("secondary_pressure", strategy.opening_window.reader_hook or strategy.long_term_direction or "局势进一步升级")
    cards.pressure_source_card.setdefault("escalation_rule", "先现实压力，再关系/资源压力，最后推到阶段性破局。")

    cards.payoff_rhythm_card = dict(cards.payoff_rhythm_card or {})
    cards.payoff_rhythm_card.setdefault("early_payoff", list(intent_packet.expected_payoffs or [])[:3])
    cards.payoff_rhythm_card.setdefault("mid_payoff", list(strategy.escalation_path or [])[:3])
    cards.payoff_rhythm_card.setdefault("avoid_payoff_pattern", ["不要连续多章只蓄压不兑现", "不要把回报全写成围观或感叹"]) 

    cards.darkline_card = dict(cards.darkline_card or {})
    cards.darkline_card.setdefault("hidden_question", diagnosis.early_hook_focus)
    cards.darkline_card.setdefault("early_signal", list(diagnosis.differentiation_focus or [])[:3])
    cards.darkline_card.setdefault("late_release_rule", "暗线前期给信号，中期给代价，后期再放大真相。")

    cards.foreshadowing_mother_card = dict(cards.foreshadowing_mother_card or {})
    cards.foreshadowing_mother_card.setdefault("long_term_threads", [diagnosis.early_hook_focus, strategy.main_conflict_axis][:2])
    cards.foreshadowing_mother_card.setdefault("short_term_threads", list(intent_packet.first_ten_chapter_tasks or [])[:3])
    cards.foreshadowing_mother_card.setdefault("reveal_rule", "短伏笔在近章就回收，长伏笔只先给信号与牵引。")

    cards.chapter_structure_card = dict(cards.chapter_structure_card or {})
    cards.chapter_structure_card.setdefault("opening_rule", f"开场先让{protagonist}面对具体压力并做出动作。")
    cards.chapter_structure_card.setdefault("middle_rule", "中段必须出现受阻、换招或判断失误，不能平推。")
    cards.chapter_structure_card.setdefault("ending_rule", "结尾要留下下一章继续看的理由，但不必每章都硬悬念。")

    cards.expression_emphasis_card = dict(cards.expression_emphasis_card or {})
    cards.expression_emphasis_card.setdefault("language_focus", list(diagnosis.tone_keywords or ["具体", "克制", "有代价"])[:4])
    cards.expression_emphasis_card.setdefault("emotion_delivery", "情绪落在动作、停顿、视线和处理具体物件上。")
    cards.expression_emphasis_card.setdefault("ban_generic_patterns", ["不要空泛氛围词堆积", "不要把情绪只写成抽象判断"]) 

    cards.world_reveal_card = dict(cards.world_reveal_card or {})
    cards.world_reveal_card.setdefault("phase_1", list(intent_packet.first_ten_chapter_tasks or [])[:3])
    cards.world_reveal_card.setdefault("phase_2", list(strategy.escalation_path or strategy.opening_window.frequent_elements or [])[:3])
    cards.world_reveal_card.setdefault("do_not_dump", ["不要一口气灌完整世界观", "不要先讲百科再推进剧情"]) 
    return cards



def _normalize_bootstrap_strategy_arbitration(
    payload: dict[str, Any],
    intent_packet: BootstrapIntentPacket,
    arbitration: BootstrapStrategyArbitrationPayload,
) -> BootstrapStrategyArbitrationPayload:
    arbitration.story_engine_diagnosis = _normalize_story_engine_diagnosis(payload, arbitration.story_engine_diagnosis)
    arbitration.story_strategy_card = _normalize_story_strategy_card(arbitration.story_strategy_card)
    arbitration.initialization_cards = _normalize_initialization_cards(
        payload=payload,
        intent_packet=intent_packet,
        diagnosis=arbitration.story_engine_diagnosis,
        strategy=arbitration.story_strategy_card,
        cards=arbitration.initialization_cards,
    )
    if not arbitration.selected_candidate_id:
        arbitration.selected_candidate_id = "A"
    if not arbitration.selection_reason:
        arbitration.selection_reason = "该方案更适合长篇连载，且能兼顾前期抓力与后续扩展。"
    if not arbitration.merge_notes:
        arbitration.merge_notes = ["保留主方案的推进重心，同时吸收其它候选的局部优点。"]
    return arbitration



def _normalize_bootstrap_story_review(review: BootstrapStoryReviewPayload) -> BootstrapStoryReviewPayload:
    review.status = str(review.status or "keep").strip().lower()
    if review.status not in {"keep", "repair"}:
        review.status = "keep"
    if not review.summary:
        review.summary = "初始化方案可直接落地。"
    normalized: list[BootstrapArcAdjustment] = []
    for item in review.arc_adjustments[:6]:
        item.field = str(item.field or "").strip()
        if item.field not in {"goal", "conflict", "ending_hook", "payoff_or_pressure", "writing_note"}:
            continue
        item.value = str(item.value or "").strip()[:120]
        if not item.value:
            continue
        normalized.append(item)
    review.arc_adjustments = normalized
    return review



def generate_bootstrap_intent_packet(payload: dict[str, Any], story_bible: dict[str, Any]) -> BootstrapIntentPacket:
    data = call_json_response(
        stage="bootstrap_intent_parse",
        system_prompt=bootstrap_intent_parse_system_prompt(),
        user_prompt=bootstrap_intent_parse_user_prompt(payload=payload, story_bible=story_bible),
        max_output_tokens=900,
    )
    packet = BootstrapIntentPacket.model_validate(data)
    return _normalize_bootstrap_intent(payload, packet)



def generate_bootstrap_intent_strategy_bundle(payload: dict[str, Any], story_bible: dict[str, Any]) -> BootstrapIntentStrategyBundlePayload:
    data = call_json_response(
        stage="bootstrap_intent_strategy_generation",
        system_prompt=bootstrap_intent_strategy_bundle_system_prompt(),
        user_prompt=bootstrap_intent_strategy_bundle_user_prompt(payload=payload, story_bible=story_bible),
        max_output_tokens=2200,
    )
    bundle = BootstrapIntentStrategyBundlePayload.model_validate(data)
    bundle.bootstrap_intent_packet = _normalize_bootstrap_intent(payload, bundle.bootstrap_intent_packet)
    bundle.story_engine_diagnosis = _normalize_story_engine_diagnosis(payload, bundle.story_engine_diagnosis)
    bundle.story_strategy_card = _normalize_story_strategy_card(bundle.story_strategy_card)
    return bundle



def generate_bootstrap_strategy_candidates(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    intent_packet: dict[str, Any] | BootstrapIntentPacket,
    *,
    candidate_count: int = 3,
) -> BootstrapStrategyCandidatesPayload:
    intent_data = intent_packet.model_dump(mode="python") if isinstance(intent_packet, BootstrapIntentPacket) else dict(intent_packet or {})
    data = call_json_response(
        stage="bootstrap_strategy_candidate_generation",
        system_prompt=bootstrap_strategy_candidates_system_prompt(),
        user_prompt=bootstrap_strategy_candidates_user_prompt(
            payload=payload,
            story_bible=story_bible,
            intent_packet=intent_data,
            candidate_count=max(int(candidate_count or 3), 2),
        ),
        max_output_tokens=2600,
    )
    bundle = BootstrapStrategyCandidatesPayload.model_validate(data)
    return _normalize_bootstrap_strategy_candidates(payload, bundle)



def arbitrate_bootstrap_strategy_bundle(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    intent_packet: dict[str, Any] | BootstrapIntentPacket,
    candidates: dict[str, Any] | BootstrapStrategyCandidatesPayload,
) -> BootstrapStrategyArbitrationPayload:
    intent_model = intent_packet if isinstance(intent_packet, BootstrapIntentPacket) else BootstrapIntentPacket.model_validate(intent_packet)
    candidate_data = candidates.model_dump(mode="python") if isinstance(candidates, BootstrapStrategyCandidatesPayload) else dict(candidates or {})
    data = call_json_response(
        stage="bootstrap_strategy_arbitration",
        system_prompt=bootstrap_strategy_arbitration_system_prompt(),
        user_prompt=bootstrap_strategy_arbitration_user_prompt(
            payload=payload,
            story_bible=story_bible,
            intent_packet=intent_model.model_dump(mode="python"),
            candidates=candidate_data,
        ),
        max_output_tokens=2600,
    )
    arbitration = BootstrapStrategyArbitrationPayload.model_validate(data)
    return _normalize_bootstrap_strategy_arbitration(payload, intent_model, arbitration)



def generate_bootstrap_execution_profile(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    intent_packet: dict[str, Any] | BootstrapIntentPacket,
    template_pool_profile: dict[str, Any],
    story_engine_diagnosis: dict[str, Any] | StoryEngineDiagnosisPayload,
    story_strategy_card: dict[str, Any] | StoryStrategyCardPayload,
) -> BookExecutionProfilePayload:
    intent_model = intent_packet if isinstance(intent_packet, BootstrapIntentPacket) else BootstrapIntentPacket.model_validate(intent_packet or {})
    diagnosis = story_engine_diagnosis if isinstance(story_engine_diagnosis, StoryEngineDiagnosisPayload) else StoryEngineDiagnosisPayload.model_validate(story_engine_diagnosis or {})
    strategy = story_strategy_card if isinstance(story_strategy_card, StoryStrategyCardPayload) else StoryStrategyCardPayload.model_validate(story_strategy_card or {})
    data = call_json_response(
        stage="bootstrap_execution_profile_generation",
        system_prompt=bootstrap_execution_profile_system_prompt(),
        user_prompt=bootstrap_execution_profile_user_prompt(
            payload=payload,
            story_bible=story_bible,
            intent_packet=intent_model.model_dump(mode="python"),
            template_pool_profile=template_pool_profile,
            story_engine_diagnosis=diagnosis.model_dump(mode="python"),
            story_strategy_card=strategy.model_dump(mode="python"),
        ),
        max_output_tokens=1300,
    )
    profile = BookExecutionProfilePayload.model_validate(data)
    return _normalize_book_execution_profile(payload, template_pool_profile, diagnosis, strategy, profile)


def review_bootstrap_story_package(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    first_arc: dict[str, Any],
    arc_digest: dict[str, Any] | None = None,
) -> BootstrapStoryReviewPayload:
    data = call_json_response(
        stage="bootstrap_story_review",
        system_prompt=bootstrap_story_review_system_prompt(),
        user_prompt=bootstrap_story_review_user_prompt(
            payload=payload,
            story_bible=story_bible,
            global_outline=global_outline,
            first_arc=first_arc,
            arc_digest=arc_digest,
        ),
        max_output_tokens=1200,
    )
    review = BootstrapStoryReviewPayload.model_validate(data)
    return _normalize_bootstrap_story_review(review)


def generate_bootstrap_outline_and_title(payload: dict[str, Any], story_bible: dict[str, Any], total_acts: int) -> BootstrapOutlineAndTitlePayload:
    data = call_json_response(
        stage="bootstrap_outline_title_generation",
        system_prompt=bootstrap_outline_title_system_prompt(),
        user_prompt=bootstrap_outline_title_user_prompt(payload=payload, story_bible=story_bible, total_acts=total_acts),
        max_output_tokens=2200,
    )
    result = BootstrapOutlineAndTitlePayload.model_validate(data)
    result.title = str(result.title or "").strip()[:40]
    if not result.title:
        raise GenerationError(
            code=ErrorCodes.EMPTY_OUTPUT,
            message="创建阶段总纲/书名联合生成失败：AI 未返回有效标题。",
            stage="bootstrap_outline_title_generation",
            retryable=True,
            provider=provider_name(),
        )
    outline = result.global_outline
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
    result.global_outline = outline
    return result



def generate_bootstrap_title(payload: dict[str, Any], story_bible: dict[str, Any]) -> BootstrapTitlePayload:
    data = call_json_response(
        stage="bootstrap_title_generation",
        system_prompt=bootstrap_title_system_prompt(),
        user_prompt=bootstrap_title_user_prompt(payload=payload, story_bible=story_bible),
        max_output_tokens=420,
    )
    result = BootstrapTitlePayload.model_validate(data)
    result.title = str(result.title or "").strip()[:40]
    if not result.title:
        raise GenerationError(
            code=ErrorCodes.EMPTY_OUTPUT,
            message="创建阶段书名生成失败：AI 未返回有效标题。",
            stage="bootstrap_title_generation",
            retryable=True,
            provider=provider_name(),
        )
    return result


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
        _apply_book_execution_profile_to_chapter(ch, story_bible, chapter_offset=expected_no - start_chapter)
        if not ch.conflict:
            ch.conflict = "主角推进目标时遭遇新的阻力或暴露风险。"
        if not ch.main_scene:
            ch.main_scene = "当前主线所处的具体场景。"
        ch.event_type = str(ch.event_type or _infer_event_type(ch.goal, ch.conflict or "", ch.ending_hook)).strip()[:12]
        ch.progress_kind = str(ch.progress_kind or _infer_progress_kind(ch.goal, ch.conflict or "", ch.ending_hook)).strip()[:12]
        ch.proactive_move = str(ch.proactive_move or _infer_proactive_move(ch.goal, ch.conflict or "", ch.event_type)).strip()[:24]
        ch.payoff_or_pressure = str(ch.payoff_or_pressure or f"本章至少完成一次{ch.progress_kind}，并给出明确回报或压力升级。").strip()[:42]
        ch.hook_kind = str(ch.hook_kind or _infer_hook_kind(ch.ending_hook, ch.hook_style)).strip()[:16]
        _apply_book_execution_profile_to_chapter(ch, story_bible, chapter_offset=expected_no - start_chapter)
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
        # agency mode 已退役：保留旧字段兼容解析，但这里统一清空，避免再把模板化模式注入章节计划。
        ch.agency_mode = None
        ch.agency_mode_label = None
        ch.agency_style_summary = None
        ch.agency_opening_instruction = None
        ch.agency_mid_instruction = None
        ch.agency_discovery_instruction = None
        ch.agency_closing_instruction = None
        ch.agency_avoid = None
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


def parse_instruction_with_openai(raw_instruction: str) -> ParsedInstructionPayload:
    data = call_json_response(
        stage="instruction_parse",
        system_prompt=instruction_parse_system_prompt(),
        user_prompt=instruction_parse_user_prompt(raw_instruction),
        max_output_tokens=600,
    )
    return ParsedInstructionPayload.model_validate(data)
