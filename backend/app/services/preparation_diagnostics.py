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
    foreshadowing_index = packet.get("foreshadowing_candidate_index") or {}
    scene_index = packet.get("scene_continuity_index") or packet.get("scene_template_index") or {}
    prompt_index = packet.get("writing_card_index") or packet.get("prompt_strategy_index") or []
    flow_index = packet.get("flow_card_index") or packet.get("flow_template_index") or []
    return {
        "schedule": {
            "appearance_candidates": len(schedule_index.get("appearance_candidates") or []),
            "relation_candidates": len(schedule_index.get("relation_candidates") or []),
        },
        "cards": _card_counts(card_index),
        "payoff": {"candidates": len(payoff_index.get("candidates") or [])},
        "foreshadowing": {
            "parent_cards": len(foreshadowing_index.get("parent_cards") or []),
            "child_cards": len(foreshadowing_index.get("child_cards") or []),
            "candidates": len(foreshadowing_index.get("candidates") or []),
        },
        "scene": {"scene_templates": len(scene_index.get("scene_templates") or []), "scene_count": _safe_int(scene_index.get("scene_count"), 0), "planned_cuts": len(scene_index.get("cut_plan") or [])},
        "writing_cards": {
            "flow_cards": len([item for item in flow_index if isinstance(item, dict)]),
            "writing_cards": len([item for item in prompt_index if isinstance(item, dict)]),
            "flow_child_cards": len([item for item in (packet.get("flow_child_card_index") or []) if isinstance(item, dict)]),
            "writing_child_cards": len([item for item in (packet.get("writing_child_card_index") or []) if isinstance(item, dict)]),
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
    foreshadowing = outputs.get("foreshadowing") or {}
    scene = outputs.get("scene") or {}
    prompt = outputs.get("prompt") or {}
    return {
        "focus_characters": len(schedule.get("focus_characters") or []),
        "main_relations": len(schedule.get("main_relations") or []),
        "selected_cards": len(cards.get("selected_card_ids") or []),
        "selected_scene_templates": 0,
        "selected_foreshadowing_supporting": len(foreshadowing.get("selected_supporting_candidate_ids") or []),
        "selected_writing_cards": len(prompt.get("selected_writing_card_ids") or prompt.get("selected_strategy_ids") or []),
        "selected_writing_child_cards": len(prompt.get("selected_writing_child_card_ids") or []),
        "selected_flow_card": _text(prompt.get("selected_flow_card_id") or prompt.get("selected_flow_template_id")),
        "selected_flow_child_card": _text(prompt.get("selected_flow_child_card_id")),
        "selected_payoff_card": _text(payoff.get("selected_card_id")),
        "selected_foreshadowing_primary": _text(foreshadowing.get("selected_primary_candidate_id")),
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


def _preview_text(items: list[str] | None, *, limit: int = 3) -> str:
    values = [_text(item) for item in (items or []) if _text(item)]
    if not values:
        return ""
    shown = values[:limit]
    suffix = " 等" if len(values) > limit else ""
    return "、".join(shown) + suffix


def _layer_count(layer: dict[str, Any] | None, key: str) -> int:
    return _safe_int((layer or {}).get(key), 0)


def build_preparation_diagnostics(*, planning_packet: dict[str, Any], selection_trace: dict[str, Any] | None) -> dict[str, Any]:
    trace = selection_trace or {}
    shortlist_stage = trace.get("shortlist_stage") or {}
    shortlist_result = shortlist_stage.get("result") or {}
    selection_scope = trace.get("selection_scope") or {}
    selector_outputs = trace.get("selector_outputs") or {}
    candidate_overview = trace.get("candidate_overview") or {}
    selection_layers = trace.get("selection_layers") or {}

    selectors = {
        "shortlist": _selector_summary(shortlist_stage),
        "schedule": _selector_summary(trace.get("schedule_trace") or {}),
        "cards": _selector_summary(trace.get("cards_trace") or {}),
        "payoff": _selector_summary(trace.get("payoff_trace") or {}),
        "foreshadowing": _selector_summary(trace.get("foreshadowing_trace") or {}),
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
        "foreshadowing_parent_card_ids": len(shortlist_result.get("foreshadowing_parent_card_ids") or []),
        "foreshadowing_child_card_ids": len(shortlist_result.get("foreshadowing_child_card_ids") or []),
        "foreshadowing_candidate_ids": len(shortlist_result.get("foreshadowing_candidate_ids") or []),
        "scene_template_ids": len(shortlist_result.get("scene_template_ids") or []),
        "flow_template_ids": len(shortlist_result.get("flow_template_ids") or []),
        "flow_child_card_ids": len(shortlist_result.get("flow_child_card_ids") or []),
        "prompt_strategy_ids": len(shortlist_result.get("prompt_strategy_ids") or []),
        "writing_child_card_ids": len(shortlist_result.get("writing_child_card_ids") or []),
    }
    chosen = _selector_outputs_summary(selector_outputs)
    payoff_overview = candidate_overview.get("payoff") or {}
    foreshadowing_overview = candidate_overview.get("foreshadowing") or {}
    payoff_layers = selection_layers.get("payoff") or {}
    foreshadowing_layers = selection_layers.get("foreshadowing") or {}
    payoff_ids = [item for item in (payoff_overview.get("candidate_ids") or []) if _text(item)]
    foreshadowing_ids = [item for item in (foreshadowing_overview.get("candidate_ids") or []) if _text(item)]
    foreshadowing_parent_ids = [item for item in (foreshadowing_overview.get("parent_ids") or []) if _text(item)]
    foreshadowing_child_ids = [item for item in (foreshadowing_overview.get("child_ids") or []) if _text(item)]
    payoff_family_preview = [item for item in (payoff_overview.get("families") or []) if _text(item)]
    foreshadowing_path = (foreshadowing_overview.get("path_summary") or {}) if isinstance(foreshadowing_overview, dict) else {}
    readable_lines = [
        (
            "章节准备共扫描："
            f"人物出场 {full_counts['schedule']['appearance_candidates']}，关系 {full_counts['schedule']['relation_candidates']}，"
            f"卡片 {sum(full_counts['cards'].values())}，爽点 {full_counts['payoff']['candidates']}，伏笔候选 {full_counts['foreshadowing']['candidates']}，"
            f"场景规划 {full_counts['scene']['scene_count']} 段 / {full_counts['scene']['planned_cuts']} 次切场，写法母卡 {full_counts['writing_cards']['writing_cards']}，流程母卡 {full_counts['writing_cards']['flow_cards']}，"
            f"写法子卡 {full_counts['writing_cards']['writing_child_cards']}，流程子卡 {full_counts['writing_cards']['flow_child_cards']}。"
        ),
        (
            "AI 预筛后保留："
            f"人物 {shortlisted_counts['focus_characters']}，关系 {shortlisted_counts['main_relation_ids']}，"
            f"卡片 {shortlisted_counts['card_candidate_ids']}，爽点 {shortlisted_counts['payoff_candidate_ids']}，伏笔候选 {shortlisted_counts['foreshadowing_candidate_ids']}，"
            f"场景连续性由独立 AI 评审，写法母卡 {shortlisted_counts['prompt_strategy_ids']}，流程母卡 {shortlisted_counts['flow_template_ids']}，"
            f"写法子卡 {shortlisted_counts['writing_child_card_ids']}，流程子卡 {shortlisted_counts['flow_child_card_ids']}。"
        ),
        (
            "分层联动："
            f"爽点家族 {_layer_count(payoff_layers.get('family_layer'), 'raw_count')}→{_layer_count(payoff_layers.get('family_layer'), 'focused_count')}，"
            f"爽点候选 {_layer_count(payoff_layers.get('candidate_layer'), 'raw_count')}→{_layer_count(payoff_layers.get('candidate_layer'), 'shortlist_count')}→{_layer_count(payoff_layers.get('candidate_layer'), 'focused_count')}；"
            f"伏笔母卡 {_layer_count(foreshadowing_layers.get('parent_layer'), 'raw_count')}→{_layer_count(foreshadowing_layers.get('parent_layer'), 'shortlist_count')}→{_layer_count(foreshadowing_layers.get('parent_layer'), 'focused_count')}，"
            f"子卡 {_layer_count(foreshadowing_layers.get('child_layer'), 'raw_count')}→{_layer_count(foreshadowing_layers.get('child_layer'), 'shortlist_count')}→{_layer_count(foreshadowing_layers.get('child_layer'), 'focused_count')}，"
            f"动作 {_layer_count(foreshadowing_layers.get('candidate_layer'), 'raw_count')}→{_layer_count(foreshadowing_layers.get('candidate_layer'), 'shortlist_count')}→{_layer_count(foreshadowing_layers.get('candidate_layer'), 'focused_count')}。"
        ),
        (
            "聚焦候选："
            f"爽点 {payoff_overview.get('candidate_count', 0)} 条"
            f"{f'（{', '.join(payoff_ids[:3])}{' 等' if len(payoff_ids) > 3 else ''}）' if payoff_ids else ''}"
            f"{f'，家族 {', '.join(payoff_family_preview[:3])}{' 等' if len(payoff_family_preview) > 3 else ''}' if payoff_family_preview else ''}"
            f"{'，已自动锁定 ' + _text(payoff_overview.get('auto_selected_id')) if payoff_overview.get('auto_selected') and _text(payoff_overview.get('auto_selected_id')) else ''}；"
            f"伏笔母卡 {foreshadowing_overview.get('parent_count', 0)} 条"
            f"{f'（{', '.join(foreshadowing_parent_ids[:2])}{' 等' if len(foreshadowing_parent_ids) > 2 else ''}）' if foreshadowing_parent_ids else ''}，"
            f"子卡 {foreshadowing_overview.get('child_count', 0)} 条"
            f"{f'（{', '.join(foreshadowing_child_ids[:2])}{' 等' if len(foreshadowing_child_ids) > 2 else ''}）' if foreshadowing_child_ids else ''}，"
            f"动作 {foreshadowing_overview.get('candidate_count', 0)} 条"
            f"{f'（{', '.join(foreshadowing_ids[:2])}{' 等' if len(foreshadowing_ids) > 2 else ''}）' if foreshadowing_ids else ''}"
            f"{'，已自动锁定 ' + _text(foreshadowing_overview.get('auto_selected_id')) if foreshadowing_overview.get('auto_selected') and _text(foreshadowing_overview.get('auto_selected_id')) else ''}。"
        ),
        (
            "层级明细："
            f"爽点聚焦[{_preview_text((payoff_layers.get('candidate_layer') or {}).get('focused_preview')) or '无'}]；"
            f"伏笔母卡[{_preview_text((foreshadowing_layers.get('parent_layer') or {}).get('focused_preview')) or '无'}]；"
            f"伏笔子卡[{_preview_text((foreshadowing_layers.get('child_layer') or {}).get('focused_preview')) or '无'}]；"
            f"伏笔动作[{_preview_text((foreshadowing_layers.get('candidate_layer') or {}).get('focused_preview'), limit=2) or '无'}]；"
            f"收窄路径[{_text(foreshadowing_path.get('parent_filter_mode')) or '无'} → {_text(foreshadowing_path.get('child_filter_mode')) or '无'} → {_text(foreshadowing_path.get('candidate_filter_mode')) or '无'}]。"
        ),
        (
            "最终选择："
            f"人物 {chosen['focus_characters']}，主关系 {chosen['main_relations']}，"
            f"卡片 {chosen['selected_cards']}，主伏笔 {chosen['selected_foreshadowing_primary'] or '无'}，场景连续性由 AI 主判，"
            f"写法母卡 {chosen['selected_writing_cards']}，写法子卡 {chosen['selected_writing_child_cards']}，总 LLM 调用 {totals['llm_calls']} 次。"
        ),
    ]
    return {
        "full_input_counts": full_counts,
        "focused_input_counts": focused_counts,
        "shortlisted_counts": shortlisted_counts,
        "selected_outputs": chosen,
        "candidate_overview": candidate_overview,
        "selection_layers": selection_layers,
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
        "preparation_selected_scene_templates": 0,
        "preparation_selected_writing_cards": _safe_int(selected.get("selected_writing_cards"), 0),
        "preparation_selected_writing_child_cards": _safe_int(selected.get("selected_writing_child_cards"), 0),
        "preparation_selected_prompt_strategies": _safe_int(selected.get("selected_writing_cards"), 0),
        "preparation_selected_payoff_card": _text(selected.get("selected_payoff_card")),
        "preparation_selected_foreshadowing_primary": _text(selected.get("selected_foreshadowing_primary")),
        "preparation_selected_flow_card": _text(selected.get("selected_flow_card")),
        "preparation_selected_flow_child_card": _text(selected.get("selected_flow_child_card")),
        "preparation_selected_flow_template": _text(selected.get("selected_flow_card")),
        "preparation_summary_lines": list(data.get("readable_lines") or [])[:5],
    }
