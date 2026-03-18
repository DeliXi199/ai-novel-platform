from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.agency_modes import AGENCY_MODES
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, extract_json, provider_name
from app.services.prompt_templates import (
    arc_outline_system_prompt,
    arc_outline_user_prompt,
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


class ThirtyChapterPhase(BaseModel):
    range: str
    stage_mission: str
    reader_hook: str
    frequent_elements: list[str] = Field(default_factory=list)
    limited_elements: list[str] = Field(default_factory=list)
    relationship_tasks: list[str] = Field(default_factory=list)
    phase_result: str


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


def parse_instruction_with_openai(raw_instruction: str) -> ParsedInstructionPayload:
    data = call_json_response(
        stage="instruction_parse",
        system_prompt=instruction_parse_system_prompt(),
        user_prompt=instruction_parse_user_prompt(raw_instruction),
        max_output_tokens=600,
    )
    return ParsedInstructionPayload.model_validate(data)
