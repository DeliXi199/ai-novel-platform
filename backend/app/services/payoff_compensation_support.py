from __future__ import annotations

from copy import deepcopy
from typing import Any


def _text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


PAYOFF_WINDOW_EVENT_BIAS_MAP: dict[str, dict[str, Any]] = {
    "primary_repay": {
        "preferred_event_types": ["资源获取类", "交易类", "反制类", "关系推进类"],
        "limited_event_types": ["发现类", "试探类", "逃避类"],
        "preferred_progress_kinds": ["资源推进", "关系推进", "实力推进"],
        "limited_progress_kinds": ["风险升级"],
        "event_bias_note": "追回章节优先安排能落袋、能反压、能让回报看得见的事件型。",
    },
    "stabilize_after_repay": {
        "preferred_event_types": ["关系推进类", "反制类", "发现类", "外部任务类"],
        "limited_event_types": ["逃避类"],
        "preferred_progress_kinds": ["关系推进", "信息推进", "资源推进"],
        "limited_progress_kinds": ["风险升级"],
        "event_bias_note": "稳余波章节优先保留回收感与后续动作，别立刻滑回纯蓄压。",
    },
}


def payoff_window_event_bias(role: str | None, *, priority: str | None = None) -> dict[str, Any]:
    payload = deepcopy(PAYOFF_WINDOW_EVENT_BIAS_MAP.get(_text(role, "primary_repay"), PAYOFF_WINDOW_EVENT_BIAS_MAP["primary_repay"]))
    payload["window_role"] = _text(role, "primary_repay")
    payload["priority"] = _text(priority, "medium").lower() or "medium"
    if payload["priority"] == "high" and payload["window_role"] == "primary_repay":
        preferred = list(payload.get("preferred_event_types") or [])
        ordered = []
        for item in ["反制类", "资源获取类", "交易类", "关系推进类", *preferred]:
            if item and item not in ordered:
                ordered.append(item)
        payload["preferred_event_types"] = ordered[:4]
    return payload


PRESSURE_HEAVY_EVENT_TYPES = {"试探类", "发现类", "逃避类"}


def _pick_preferred_event_type(preferred_event_types: list[str], recent_event_types: list[str]) -> str:
    recent = [_text(item) for item in recent_event_types if _text(item)]
    if not preferred_event_types:
        return ""
    if not recent:
        return preferred_event_types[0]
    last = recent[-1]
    for item in preferred_event_types:
        if item != last:
            return item
    return preferred_event_types[0]



def apply_payoff_window_event_bias_to_plan(
    plan: dict[str, Any],
    *,
    role: str | None,
    priority: str | None = None,
    note: str | None = None,
    recent_event_types: list[str] | None = None,
) -> dict[str, Any]:
    updated = dict(plan or {})
    bias = payoff_window_event_bias(role, priority=priority)
    recent = [_text(item) for item in (recent_event_types or []) if _text(item)]
    current_event_type = _text(updated.get("event_type"))
    current_progress = _text(updated.get("progress_kind"))
    preferred_event_types = list(bias.get("preferred_event_types") or [])
    limited_event_types = set(bias.get("limited_event_types") or [])
    preferred_progress_kinds = list(bias.get("preferred_progress_kinds") or [])
    limited_progress_kinds = set(bias.get("limited_progress_kinds") or [])

    should_shift_event = (
        not current_event_type
        or current_event_type in limited_event_types
        or (current_event_type in PRESSURE_HEAVY_EVENT_TYPES and bias.get("window_role") == "primary_repay")
        or (len(recent) >= 2 and recent[-1] == current_event_type == recent[-2])
    )
    if should_shift_event and preferred_event_types:
        updated["event_type"] = _pick_preferred_event_type(preferred_event_types, recent)

    if (not current_progress or current_progress in limited_progress_kinds) and preferred_progress_kinds:
        updated["progress_kind"] = preferred_progress_kinds[0]

    if _text(updated.get("chapter_type")) == "probe" and bias.get("window_role") == "primary_repay":
        updated["chapter_type"] = "progress"

    bias_note = _text(note) or _text(bias.get("event_bias_note"))
    updated["payoff_window_event_bias"] = {
        "window_role": _text(bias.get("window_role"), "primary_repay"),
        "priority": _text(bias.get("priority"), "medium"),
        "preferred_event_types": preferred_event_types,
        "limited_event_types": list(limited_event_types),
        "preferred_progress_kinds": preferred_progress_kinds,
        "limited_progress_kinds": list(limited_progress_kinds),
        "event_bias_note": bias_note,
    }

    writing_note = _text(updated.get("writing_note"))
    if bias_note and bias_note not in writing_note:
        updated["writing_note"] = f"{writing_note}；{bias_note}" if writing_note else bias_note
    return updated
