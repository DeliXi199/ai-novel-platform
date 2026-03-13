from __future__ import annotations

from copy import deepcopy
from typing import Any

AGENCY_MODES: dict[str, dict[str, Any]] = {
    "aggressive_probe": {
        "label": "进攻试探型",
        "summary": "主角通过先手试探、逼反应、拿小风险换信息来夺回主动，而不是等局势把答案送到脸上。",
        "default_move": "主动先手试探并逼出回应",
        "opening": "开场就让主角先做一个试探动作、亮半张牌或压前半步，先逼环境或他人回应。",
        "mid": "中段若受阻，不退回观察位，而是立刻换角度追问、施压、试出破绽或抢先一步。",
        "discovery": "发现最好来自主角亲手试出来、逼出来、换出来，而不是站着等别人交代。",
        "closing": "收尾落在主角先手试探造成的新风险、新筹码或对手新动作上。",
        "avoid": ["先站着听别人说完", "整段只写观察和揣测", "临结尾才补一个勉强动作"],
        "progress_kinds": {"信息推进", "风险升级", "地点推进"},
        "event_types": {"试探类", "冲突类", "危机爆发", "发现类", "潜入类"},
        "genre_bias": ("热血", "升级", "爽", "修仙", "金手指", "冒险"),
        "signal_markers": ("试探", "逼", "抢先", "压前", "追问", "探口风", "逼得", "拦住"),
    },
    "strategic_setup": {
        "label": "谋划设局型",
        "summary": "主角表面克制，实际通过留钩子、误导、顺水推舟、提前埋条件来控制信息差。",
        "default_move": "主动埋下条件并诱导对方先露破绽",
        "opening": "开场可以不外放，但要让主角先藏一步、留一句、换一个细节，让局势顺着他的布置走。",
        "mid": "受阻后不要只想，要用误导、转移、借势、留白或调换顺序继续拿信息差。",
        "discovery": "发现来自主角提前埋下的试纸、对照、套话或局部布局被触发。",
        "closing": "结尾落在主角布下的小局开始回响，而不是单纯气氛发虚。",
        "avoid": ["只有心里分析没有任何布置", "明明谨慎却完全不动手", "把克制写成纯站桩"],
        "progress_kinds": {"信息推进", "关系推进", "风险升级"},
        "event_types": {"反制类", "身份伪装类", "试探类", "潜入类", "发现类"},
        "genre_bias": ("权谋", "悬疑", "低调", "苟", "谨慎", "凡人"),
        "signal_markers": ("故意", "装作", "借着", "顺势", "留半句", "误导", "设局", "不动声色"),
    },
    "transactional_push": {
        "label": "交易改规型",
        "summary": "主角不接受现成条件，而是主动交换筹码、重写规则、逼对方表态来拿主动权。",
        "default_move": "主动改写条件并逼对方表态",
        "opening": "开场就让主角先开价、先压价、先提条件，直接把局面从被安排改成谈判桌。",
        "mid": "中段若谈不拢，要继续换筹码、换说法、改顺序、收回部分承诺，而不是闷着吃亏。",
        "discovery": "发现来自交易中的让步、要价、试价或条件交换暴露出的真实需求。",
        "closing": "结尾落在新条件生效后的后果、隐藏代价或关系重排上。",
        "avoid": ["被动接受规则", "只抱怨价高事难", "别人说完条件后才想起还价"],
        "progress_kinds": {"资源推进", "关系推进", "风险升级"},
        "event_types": {"交易类", "关系推进类", "资源获取类", "外部任务类"},
        "genre_bias": ("宗门", "商", "门派", "人情", "关系", "资源"),
        "signal_markers": ("条件", "交换", "代价", "筹码", "压价", "还价", "答应", "让步"),
    },
    "curiosity_driven": {
        "label": "求知验证型",
        "summary": "主角通过追问、实验、比对、拆解、验证猜测来推动剧情，主动性来自求证而不是蛮冲。",
        "default_move": "主动验证异常并追索因果",
        "opening": "开场先让主角做一个验证动作：比对、触碰、试一遍、拆开、复盘、重演。",
        "mid": "中段若验证失败，不是发愣，而是立刻换样本、换方法、换问题继续追索。",
        "discovery": "发现必须能看出是主角亲手验证出来的结果，而不是听别人讲完才明白。",
        "closing": "结尾落在一个被验证的新事实、新疑点或下一轮实验入口上。",
        "avoid": ["只觉得不对劲却不验证", "只有推测没有动作", "把求知写成背景旁白"],
        "progress_kinds": {"信息推进", "实力推进", "地点推进"},
        "event_types": {"发现类", "资源获取类", "试探类", "外部任务类"},
        "genre_bias": ("探索", "设定", "科幻", "修真", "机缘", "古镜"),
        "signal_markers": ("验证", "比对", "试了试", "拆开", "摸清", "确认", "印证", "复盘"),
    },
    "emotional_initiative": {
        "label": "情感表态型",
        "summary": "主角主动表态、划边界、修复关系或切断关系，用情绪上的先手改变人与人的距离和站位。",
        "default_move": "主动表态并改写关系边界",
        "opening": "开场先让主角说一句该说的话、认一个该认的事，或干脆把界线划清，不要一直憋着。",
        "mid": "中段若对方回避、顶撞或误会，主角仍要再推进一步：解释、拒绝、安抚、摊牌或追问。",
        "discovery": "发现来自主动表态后对方的真实反应、旧伤、立场或隐藏需求被掀出来。",
        "closing": "结尾落在关系温度、信任结构或团队位置发生变化上。",
        "avoid": ["有情绪但完全不说不做", "只靠内心独白承受", "关系戏写成机械抛信息"],
        "progress_kinds": {"关系推进", "风险升级", "信息推进"},
        "event_types": {"关系推进类", "外部任务类", "冲突类"},
        "genre_bias": ("群像", "师徒", "感情", "团队", "同门"),
        "signal_markers": ("先开口", "摊开", "表态", "道歉", "拒绝", "答应", "划清", "不再"),
    },
    "reverse_pressure_choice": {
        "label": "逆势押注型",
        "summary": "局势压着主角走时，他主动选一个更难、更贵、更危险但能换回主动权的选项。",
        "default_move": "主动押上一部分退路换回主动权",
        "opening": "开场就让主角看见压力后作出代价明确的选择，而不是只写难受和被迫。",
        "mid": "中段若代价显形，主角还要再咬牙推进一步，显示这不是一时冲动，而是有意押注。",
        "discovery": "发现来自主角承担代价后换到的新路径、新情报或新立场。",
        "closing": "结尾落在押注后的后果：退路变少、筹码变硬、敌意升级或机会真正打开。",
        "avoid": ["只写局势压人不写选择", "挨打后原地发愣", "危险很大但主角毫无决断"],
        "progress_kinds": {"风险升级", "资源推进", "实力推进"},
        "event_types": {"危机爆发", "冲突类", "资源获取类", "外部任务类"},
        "genre_bias": ("危机", "逆风", "逃亡", "绝境", "试炼"),
        "signal_markers": ("明知", "仍", "索性", "干脆", "押上", "退路", "硬着头皮", "扛下"),
    },
}

_GENERIC_MOVES = {
    "主动做出判断并推动局势前进",
    "主动做出判断并推动局势前进。",
    "谨慎应对",
    "主动应对",
    "观察局势",
    "先看看情况",
}


def recent_agency_modes(recent_plan_meta: list[dict[str, Any]] | None, *, limit: int = 3) -> list[str]:
    result: list[str] = []
    for item in recent_plan_meta or []:
        if not isinstance(item, dict):
            continue
        mode = str(item.get("agency_mode") or "").strip()
        if mode:
            result.append(mode)
    return result[-limit:]


def select_agency_mode(
    plan: dict[str, Any] | None,
    *,
    genre_text: str = "",
    premise_text: str = "",
    style_preferences: dict[str, Any] | None = None,
    protagonist_name: str = "",
    recent_plan_meta: list[dict[str, Any]] | None = None,
    preferred_mode: str | None = None,
    exclude_modes: set[str] | None = None,
) -> dict[str, Any]:
    current = dict(plan or {})
    existing = str(current.get("agency_mode") or "").strip()
    if existing and existing in AGENCY_MODES and not preferred_mode and not exclude_modes:
        return {"key": existing, **deepcopy(AGENCY_MODES[existing])}

    text_blob = " ".join(
        part
        for part in [
            genre_text,
            premise_text,
            protagonist_name,
            str((style_preferences or {}).get("tone") or ""),
            str((style_preferences or {}).get("story_engine") or ""),
            str((style_preferences or {}).get("opening_mode") or ""),
            str(current.get("goal") or ""),
            str(current.get("conflict") or ""),
            str(current.get("ending_hook") or ""),
            str(current.get("payoff_or_pressure") or ""),
        ]
        if part
    )
    progress_kind = str(current.get("progress_kind") or "").strip()
    event_type = str(current.get("event_type") or "").strip()
    desired = str((style_preferences or {}).get("agency_preference") or current.get("agency_mode_hint") or "").strip()
    recent = recent_agency_modes(recent_plan_meta)
    exclude = set(exclude_modes or set())

    scores: list[tuple[float, str]] = []
    for key, spec in AGENCY_MODES.items():
        if key in exclude:
            continue
        score = 1.0
        if preferred_mode and key == preferred_mode:
            score += 5.0
        if desired and (desired == key or desired == spec["label"]):
            score += 3.0
        if progress_kind and progress_kind in spec["progress_kinds"]:
            score += 2.2
        if event_type and event_type in spec["event_types"]:
            score += 2.0
        if any(token in text_blob for token in spec.get("genre_bias", ())):
            score += 1.2
        if existing and existing == key:
            score += 0.2
        if recent:
            if recent[-1] == key:
                score -= 2.4
            if len(recent) >= 2 and recent[-2] == key:
                score -= 1.0
            if len(recent) >= 3 and recent[-3] == key:
                score -= 0.6
        scores.append((score, key))

    if not scores:
        key = "curiosity_driven"
        return {"key": key, **deepcopy(AGENCY_MODES[key])}

    scores.sort(key=lambda item: (-item[0], item[1]))
    chosen_key = scores[0][1]
    return {"key": chosen_key, **deepcopy(AGENCY_MODES[chosen_key]), "score": round(scores[0][0], 3), "recent_modes": recent}


def _append_unique_sentence(base: str, addition: str) -> str:
    base_text = str(base or "").strip()
    extra = str(addition or "").strip()
    if not extra:
        return base_text
    if not base_text:
        return extra
    if extra in base_text:
        return base_text
    joiner = "；" if not base_text.endswith(("。", "！", "？", "；")) else ""
    return f"{base_text}{joiner}{extra}".strip("；")


def apply_agency_mode_to_plan(
    plan: dict[str, Any],
    mode_spec: dict[str, Any],
    *,
    recent_plan_meta: list[dict[str, Any]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    enriched = dict(plan or {})
    key = str(mode_spec.get("key") or "curiosity_driven")
    label = str(mode_spec.get("label") or key)
    recent = recent_agency_modes(recent_plan_meta)

    current_move = str(enriched.get("proactive_move") or "").strip()
    if force or not current_move or current_move in _GENERIC_MOVES or len(current_move) < 6:
        enriched["proactive_move"] = str(mode_spec.get("default_move") or current_move or "主动推进")

    enriched["agency_mode"] = key
    enriched["agency_mode_label"] = label
    enriched["agency_style_summary"] = str(mode_spec.get("summary") or "")
    enriched["agency_opening_instruction"] = str(mode_spec.get("opening") or "")
    enriched["agency_mid_instruction"] = str(mode_spec.get("mid") or "")
    enriched["agency_discovery_instruction"] = str(mode_spec.get("discovery") or "")
    enriched["agency_closing_instruction"] = str(mode_spec.get("closing") or "")
    enriched["agency_avoid"] = list(mode_spec.get("avoid") or [])
    enriched["agency_signal_markers"] = list(mode_spec.get("signal_markers") or [])

    rotation_note = ""
    if recent:
        if recent[-1] == key:
            rotation_note = f"上一章已经用过‘{label}’，这次要换动作路径和句式，不要重复同一种先手方式。"
        elif len(recent) >= 2 and recent[-2] == key:
            rotation_note = f"最近两章里出现过‘{label}’，本章保留核心主动性即可，别把开头和中段写成同一模子。"
    if rotation_note:
        enriched["agency_rotation_note"] = rotation_note

    opening = str(enriched.get("opening_beat") or "").strip()
    mid = str(enriched.get("mid_turn") or "").strip()
    discovery = str(enriched.get("discovery") or "").strip()
    closing = str(enriched.get("closing_image") or enriched.get("ending_hook") or "").strip()
    note = str(enriched.get("writing_note") or "").strip()
    enriched["opening_beat"] = _append_unique_sentence(opening, str(mode_spec.get("opening") or ""))
    enriched["mid_turn"] = _append_unique_sentence(mid, str(mode_spec.get("mid") or ""))
    enriched["discovery"] = _append_unique_sentence(discovery, str(mode_spec.get("discovery") or ""))
    enriched["closing_image"] = _append_unique_sentence(closing, str(mode_spec.get("closing") or ""))

    mode_note = f"本章主动方式采用“{label}”，主动不等于猛冲，而是要让主角主动改变局势、信息差、关系结构或选择条件。"
    if rotation_note:
        mode_note = f"{mode_note}{rotation_note}"
    enriched["writing_note"] = _append_unique_sentence(note, mode_note)
    return enriched
