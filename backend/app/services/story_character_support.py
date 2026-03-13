from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.story_fact_ledger import _now_iso

SUPPORTING_ROLE_TEMPLATES = [
    {
        "role_archetype": "精于算计型",
        "speech_style": "说话短，喜欢留半句，常把真正意图压在后面。",
        "work_style": "先看筹码与退路，再决定站队，不会轻易把话说死。",
        "private_goal": "先稳住自己的好处，再看要不要借主角这股势。",
        "pressure_response": "表面越温和，心里算得越细。",
        "small_tell": "说到关键处会轻轻敲指节或拨一下杯沿。",
        "taboo": "讨厌别人直接掀底牌，最忌被当场逼表态。",
    },
    {
        "role_archetype": "粗暴威慑型",
        "speech_style": "话直、句短、压迫感强，喜欢把问题摊在台面上。",
        "work_style": "偏好先施压后分辨，宁可错打一遍，也不愿慢慢试探。",
        "private_goal": "尽快把眼前麻烦按住，别让上面怪罪到自己头上。",
        "pressure_response": "一受刺激就会把声音压低或突然逼近。",
        "small_tell": "说重话前会先扯衣袖、捏拳或拿东西敲桌角。",
        "taboo": "最烦别人装糊涂、拖时间或拿规矩反压自己。",
    },
    {
        "role_archetype": "表面温和型",
        "speech_style": "语气平稳，常先给台阶，再顺着台阶套话。",
        "work_style": "习惯先安抚、再观察、最后突然收网。",
        "private_goal": "把风险留在别人身上，自己维持体面和安全。",
        "pressure_response": "真正不耐烦时反而会笑得更淡。",
        "small_tell": "听到要紧处会不动声色地整理袖口或摆正器物。",
        "taboo": "最忌自己失去体面，也怕被人看穿真实立场。",
    },
]

def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _supporting_voice_template(name: str, note: str = "") -> dict[str, Any]:
    seed = sum(ord(ch) for ch in f"{name}{note}")
    template = deepcopy(SUPPORTING_ROLE_TEMPLATES[seed % len(SUPPORTING_ROLE_TEMPLATES)])
    template["name"] = _text(name)
    if note:
        template["accent_note"] = _text(note)
    return template


def _character_voice_pack(card: dict[str, Any] | None) -> dict[str, Any]:
    payload = card or {}
    pack = {
        "name": _text(payload.get("name")),
        "role_archetype": _text(payload.get("role_archetype")),
        "speech_style": _text(payload.get("speech_style")),
        "work_style": _text(payload.get("work_style")),
        "current_desire": _text(payload.get("current_desire") or payload.get("core_desire")),
        "pressure_response": _text(payload.get("pressure_response")),
        "small_tell": _text(payload.get("small_tell")),
        "taboo": _text(payload.get("taboo")),
        "do_not_break": _safe_list(payload.get("do_not_break"))[:3],
    }
    return {key: value for key, value in pack.items() if value not in ("", [], {}, None)}


def _recent_retrospective_feedback(console: dict[str, Any]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for item in (console.get("chapter_retrospectives") or [])[-2:]:
        if not isinstance(item, dict):
            continue
        feedback.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "problem": _text(item.get("core_problem")),
                "correction": _text(item.get("next_chapter_correction")),
                "event_type": _text(item.get("event_type")),
                "agency_mode": _text(item.get("agency_mode")),
            }
        )
    return [item for item in feedback if item.get("problem") or item.get("correction")]


def _build_chapter_retrospective(
    *,
    chapter_no: int,
    chapter_title: str,
    plan: dict[str, Any],
    summary: Any,
    console: dict[str, Any],
) -> dict[str, Any]:
    event_type = _text(plan.get("event_type"), "试探类")
    progress_kind = _text(plan.get("progress_kind"), "信息推进")
    proactive_move = _text(plan.get("proactive_move"), "")
    agency_mode = _text(plan.get("agency_mode_label") or plan.get("agency_mode"), "")
    payoff_or_pressure = _text(plan.get("payoff_or_pressure"), "")
    hook_kind = _text(plan.get("hook_kind"), "更大谜团")
    support_note = _text(plan.get("supporting_character_note"), "")
    recent_events = [
        _text(item.get("event_type"))
        for item in (console.get("chapter_retrospectives") or [])[-2:]
        if isinstance(item, dict)
    ]
    repetition_risk = "low"
    if len(recent_events) >= 2 and recent_events[-1] == event_type and recent_events[-2] == event_type:
        repetition_risk = "high"
    elif recent_events and recent_events[-1] == event_type:
        repetition_risk = "medium"

    agency_status = "pass"
    if not proactive_move or any(token in proactive_move for token in ["谨慎应对", "被动", "观察局势"]):
        agency_status = "warn"

    payoff_status = "pressure"
    if any(token in payoff_or_pressure for token in ["拿到", "换到", "得到", "掌握", "确认", "获得"]):
        payoff_status = "payoff"
    elif any(token in payoff_or_pressure for token in ["暴露", "盯上", "风险", "危机", "追查", "敌意"]):
        payoff_status = "pressure"
    elif progress_kind in {"资源推进", "信息推进", "关系推进", "实力推进"}:
        payoff_status = "payoff"

    hook_status = "strong"
    if hook_kind in {"", "余味收束"}:
        hook_status = "soft"

    character_flatness_risk = "low"
    if plan.get("supporting_character_focus") and (not support_note or len(support_note) < 8):
        character_flatness_risk = "high"
    elif plan.get("supporting_character_focus"):
        character_flatness_risk = "medium"

    corrections: list[str] = []
    if repetition_risk != "low":
        corrections.append("下一章必须主动换主事件类型，不要再沿用同一种试探/盘问结构。")
    if agency_status != "pass":
        if agency_mode:
            corrections.append(f"下一章继续保留‘{agency_mode}’的主动性，但要把动作写实，不要只剩概念。")
        else:
            corrections.append("下一章把主角主动动作写实，至少安排一次主动试探、争资源或误导。")
    if character_flatness_risk != "low":
        corrections.append("下一章把关键配角写出私心、说话习惯和忌讳，不能只留功能。")
    if hook_status == "soft":
        corrections.append("下一章的结尾拉力要更具体，最好落在新威胁、新发现或关键人物动作上。")
    if not corrections:
        corrections.append("下一章在保持承接的同时，把兑现和人物差异再往前推半步。")

    core_problem = corrections[0]
    summary_text = _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), chapter_title))
    return {
        "chapter_no": int(chapter_no),
        "title": chapter_title,
        "event_type": event_type,
        "progress_kind": progress_kind,
        "agency_mode": agency_mode,
        "agency_status": agency_status,
        "payoff_status": payoff_status,
        "hook_status": hook_status,
        "repetition_risk": repetition_risk,
        "character_flatness_risk": character_flatness_risk,
        "core_problem": core_problem,
        "next_chapter_correction": " ".join(corrections[:2]),
        "summary": summary_text,
        "created_at": _now_iso(),
    }


