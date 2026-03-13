from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.agency_modes import AGENCY_MODES
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
    chapter_draft_system_prompt,
    chapter_draft_user_prompt,
    chapter_extension_system_prompt,
    chapter_extension_user_prompt,
    global_outline_system_prompt,
    global_outline_user_prompt,
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


class ChapterPlan(BaseModel):
    chapter_no: int
    title: str
    goal: str
    ending_hook: str
    chapter_type: str | None = None
    event_type: str | None = None
    progress_kind: str | None = None
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
    writing_note: str | None = None
    agency_mode: str | None = None
    agency_mode_label: str | None = None
    agency_style_summary: str | None = None
    agency_opening_instruction: str | None = None
    agency_mid_instruction: str | None = None
    agency_discovery_instruction: str | None = None
    agency_closing_instruction: str | None = None
    agency_avoid: list[str] | None = None


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


class ChapterSummaryPayload(BaseModel):
    event_summary: str
    character_updates: dict[str, Any] = Field(default_factory=dict)
    new_clues: list[str] = Field(default_factory=list)
    open_hooks: list[str] = Field(default_factory=list)
    closed_hooks: list[str] = Field(default_factory=list)


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
        if not ch.writing_note:
            ch.writing_note = "正文阶段避免模板句，保持单场景推进、主角主动性和自然收束。"
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
    outline.chapters = normalized
    outline.arc_no = arc_no
    outline.start_chapter = start_chapter
    outline.end_chapter = end_chapter
    return outline


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
    text = call_text_response(
        stage="chapter_generation",
        system_prompt=chapter_draft_system_prompt(),
        user_prompt=chapter_draft_user_prompt(
            novel_context=novel_context,
            chapter_plan=chapter_plan,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            active_interventions=active_interventions,
            target_words=target_words,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
        ),
        max_output_tokens=current_chapter_max_output_tokens(),
        timeout_seconds=request_timeout_seconds,
    )
    content = _clean_plain_chapter_text(text, expected_title=chapter_plan.get("title"))
    data = {
        "title": (chapter_plan.get("title") or "").strip() or f"第{chapter_plan.get('chapter_no', '')}章",
        "content": content,
    }
    return ChapterDraftPayload.model_validate(data)


def extend_chapter_text(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    request_timeout_seconds: int | None = None,
) -> str:
    text = call_text_response(
        stage="chapter_extension",
        system_prompt=chapter_extension_system_prompt(),
        user_prompt=chapter_extension_user_prompt(
            chapter_plan=chapter_plan,
            existing_content=existing_content,
            reason=reason,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
        ),
        max_output_tokens=min(max(current_chapter_max_output_tokens() // 3, 320), 700),
        timeout_seconds=request_timeout_seconds,
    )
    return _clean_plain_chapter_text(text, expected_title=None)


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
