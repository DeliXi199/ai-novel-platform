from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sum_ints(values: list[int]) -> int:
    return sum(_safe_int(item) for item in values)


def _card_counts(card_index: dict[str, Any]) -> dict[str, int]:
    buckets = {}
    for bucket in ["characters", "resources", "factions", "relations"]:
        buckets[bucket] = len([item for item in (card_index.get(bucket) or []) if isinstance(item, dict)])
    return buckets


def _full_input_counts(planning_packet: dict[str, Any]) -> dict[str, Any]:
    packet = planning_packet or {}
    schedule_index = packet.get("schedule_candidate_index") or {}
    card_index = packet.get("card_index") or {}
    payoff_index = packet.get("payoff_candidate_index") or {}
    scene_index = packet.get("scene_template_index") or {}
    prompt_index = packet.get("prompt_strategy_index") or []
    flow_index = packet.get("flow_template_index") or []
    return {
        "schedule": {
            "appearance_candidates": len(schedule_index.get("appearance_candidates") or []),
            "relation_candidates": len(schedule_index.get("relation_candidates") or []),
        },
        "cards": _card_counts(card_index),
        "payoff": {"candidates": len(payoff_index.get("candidates") or [])},
        "scene": {"scene_templates": len(scene_index.get("scene_templates") or [])},
        "prompt": {
            "flow_templates": len([item for item in flow_index if isinstance(item, dict)]),
            "prompt_strategies": len([item for item in prompt_index if isinstance(item, dict)]),
        },
    }


def _trace_runtime(trace: list[dict[str, Any]] | None) -> dict[str, int]:
    events = [item for item in (trace or []) if isinstance(item, dict)]
    return {
        "llm_calls": len(events),
        "duration_ms": _sum_ints([item.get("duration_ms") for item in events]),
        "waited_ms": _sum_ints([item.get("waited_ms") for item in events]),
        "response_chars": _sum_ints([item.get("response_chars") for item in events]),
    }


def _selector_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    trace_stats = _trace_runtime(data.get("trace"))
    return {
        "attempt": _safe_int(data.get("attempt"), 0),
        "compact_mode": bool(data.get("compact_mode")),
        "timeout_seconds": _safe_int(data.get("timeout_seconds"), 0),
        "prompt_chars": _safe_int(data.get("prompt_chars"), 0),
        **trace_stats,
    }


def _selector_outputs_summary(selector_outputs: dict[str, Any] | None) -> dict[str, Any]:
    outputs = selector_outputs or {}
    schedule = outputs.get("schedule") or {}
    cards = outputs.get("cards") or {}
    payoff = outputs.get("payoff") or {}
    scene = outputs.get("scene") or {}
    prompt = outputs.get("prompt") or {}
    return {
        "focus_characters": len(schedule.get("focus_characters") or []),
        "main_relations": len(schedule.get("main_relations") or []),
        "selected_cards": len(cards.get("selected_card_ids") or []),
        "selected_scene_templates": len(scene.get("selected_scene_template_ids") or []),
        "selected_prompt_strategies": len(prompt.get("selected_strategy_ids") or []),
        "selected_flow_template": _text(prompt.get("selected_flow_template_id")),
        "selected_payoff_card": _text(payoff.get("selected_card_id")),
    }


def _pipeline_totals(selectors: dict[str, dict[str, Any]]) -> dict[str, int]:
    prompt_chars = _sum_ints([item.get("prompt_chars") for item in selectors.values()])
    timeout_seconds = _sum_ints([item.get("timeout_seconds") for item in selectors.values()])
    llm_calls = _sum_ints([item.get("llm_calls") for item in selectors.values()])
    duration_ms = _sum_ints([item.get("duration_ms") for item in selectors.values()])
    waited_ms = _sum_ints([item.get("waited_ms") for item in selectors.values()])
    response_chars = _sum_ints([item.get("response_chars") for item in selectors.values()])
    return {
        "selector_count": len(selectors),
        "prompt_chars": prompt_chars,
        "timeout_seconds": timeout_seconds,
        "llm_calls": llm_calls,
        "duration_ms": duration_ms,
        "waited_ms": waited_ms,
        "response_chars": response_chars,
    }


def build_preparation_diagnostics(*, planning_packet: dict[str, Any], selection_trace: dict[str, Any] | None) -> dict[str, Any]:
    trace = selection_trace or {}
    shortlist_stage = trace.get("shortlist_stage") or {}
    shortlist_result = shortlist_stage.get("result") or {}
    selection_scope = trace.get("selection_scope") or {}
    selector_outputs = trace.get("selector_outputs") or {}

    selectors = {
        "shortlist": _selector_summary(shortlist_stage),
        "schedule": _selector_summary(trace.get("schedule_trace") or {}),
        "cards": _selector_summary(trace.get("cards_trace") or {}),
        "payoff": _selector_summary(trace.get("payoff_trace") or {}),
        "scene": _selector_summary(trace.get("scene_trace") or {}),
        "prompt": _selector_summary(trace.get("prompt_trace") or {}),
        "merge": _selector_summary(trace.get("merge_trace") or {}),
    }
    selectors = {key: value for key, value in selectors.items() if any(val not in (0, False, "", None) for val in value.values())}
    totals = _pipeline_totals(selectors)
    full_counts = _full_input_counts(planning_packet)
    focused_counts = (selection_scope.get("stats") or {}) if isinstance(selection_scope, dict) else {}
    shortlisted_counts = {
        "focus_characters": len(shortlist_result.get("focus_characters") or []),
        "main_relation_ids": len(shortlist_result.get("main_relation_ids") or []),
        "card_candidate_ids": len(shortlist_result.get("card_candidate_ids") or []),
        "payoff_candidate_ids": len(shortlist_result.get("payoff_candidate_ids") or []),
        "scene_template_ids": len(shortlist_result.get("scene_template_ids") or []),
        "flow_template_ids": len(shortlist_result.get("flow_template_ids") or []),
        "prompt_strategy_ids": len(shortlist_result.get("prompt_strategy_ids") or []),
    }
    chosen = _selector_outputs_summary(selector_outputs)
    readable_lines = [
        (
            "章节准备共扫描："
            f"人物出场 {full_counts['schedule']['appearance_candidates']}，关系 {full_counts['schedule']['relation_candidates']}，"
            f"卡片 {sum(full_counts['cards'].values())}，爽点 {full_counts['payoff']['candidates']}，"
            f"场景模板 {full_counts['scene']['scene_templates']}，prompt策略 {full_counts['prompt']['prompt_strategies']}，流程模板 {full_counts['prompt']['flow_templates']}。"
        ),
        (
            "AI 预筛后保留："
            f"人物 {shortlisted_counts['focus_characters']}，关系 {shortlisted_counts['main_relation_ids']}，"
            f"卡片 {shortlisted_counts['card_candidate_ids']}，爽点 {shortlisted_counts['payoff_candidate_ids']}，"
            f"场景 {shortlisted_counts['scene_template_ids']}，策略 {shortlisted_counts['prompt_strategy_ids']}。"
        ),
        (
            "最终选择："
            f"人物 {chosen['focus_characters']}，主关系 {chosen['main_relations']}，"
            f"卡片 {chosen['selected_cards']}，场景模板 {chosen['selected_scene_templates']}，"
            f"策略 {chosen['selected_prompt_strategies']}，总 LLM 调用 {totals['llm_calls']} 次。"
        ),
    ]
    return {
        "full_input_counts": full_counts,
        "focused_input_counts": focused_counts,
        "shortlisted_counts": shortlisted_counts,
        "selected_outputs": chosen,
        "selectors": selectors,
        "pipeline_totals": totals,
        "shortlist_note": _text(shortlist_result.get("shortlist_note")),
        "readable_lines": readable_lines,
    }


def build_preparation_runtime_extra(diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    data = diagnostics or {}
    totals = data.get("pipeline_totals") or {}
    selected = data.get("selected_outputs") or {}
    return {
        "preparation_llm_calls": _safe_int(totals.get("llm_calls"), 0),
        "preparation_duration_ms": _safe_int(totals.get("duration_ms"), 0),
        "preparation_waited_ms": _safe_int(totals.get("waited_ms"), 0),
        "preparation_selected_cards": _safe_int(selected.get("selected_cards"), 0),
        "preparation_selected_scene_templates": _safe_int(selected.get("selected_scene_templates"), 0),
        "preparation_selected_prompt_strategies": _safe_int(selected.get("selected_prompt_strategies"), 0),
        "preparation_selected_payoff_card": _text(selected.get("selected_payoff_card")),
        "preparation_selected_flow_template": _text(selected.get("selected_flow_template")),
        "preparation_summary_lines": list(data.get("readable_lines") or [])[:3],
    }
