from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _truncate_text(value: Any, limit: int = 72) -> str:
    text = _text(value)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def _compact_value(value: Any, *, text_limit: int = 64, max_items: int = 6) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, text_limit=text_limit, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                break
            compact[str(key)] = _compact_value(item, text_limit=text_limit, max_items=max_items)
        return compact
    return _truncate_text(value, text_limit)


def _sum_int(items: list[dict[str, Any]], key: str) -> int:
    return sum(_safe_int(item.get(key), 0) for item in items if isinstance(item, dict))


def _mean_int(values: list[int]) -> int:
    if not values:
        return 0
    return int(round(sum(values) / max(len(values), 1)))


def _mean_float(values: list[float], digits: int = 3) -> float:
    if not values:
        return 0.0
    return round(sum(values) / max(len(values), 1), digits)


def _trend_direction(values: list[float] | list[int], *, tolerance_ratio: float = 0.08, absolute_floor: float = 1.0) -> str:
    numeric = [float(value) for value in values if value is not None]
    if len(numeric) < 2:
        return "flat"
    baseline = max(sum(abs(item) for item in numeric) / max(len(numeric), 1), absolute_floor)
    delta = numeric[-1] - numeric[0]
    if abs(delta) <= baseline * tolerance_ratio:
        return "flat"
    return "up" if delta > 0 else "down"


def _delivery_level_rank(value: Any) -> int:
    text = _text(value).lower()
    return {
        "low": 1,
        "medium": 2,
        "mid": 2,
        "high": 3,
        "peak": 4,
    }.get(text, 0)


def _build_generation_trends(history_rows: list[dict[str, Any]] | None, *, window: int = 5) -> dict[str, Any]:
    rows = [dict(item) for item in (history_rows or []) if isinstance(item, dict)]
    recent = [row for row in rows[-max(int(window or 1), 1) :] if _safe_int(row.get("chapter_no")) > 0]
    if not recent:
        return {}

    duration_values = [_safe_int(row.get("duration_ms")) for row in recent if _safe_int(row.get("duration_ms")) > 0]
    llm_values = [_safe_int(row.get("llm_calls")) for row in recent if _safe_int(row.get("llm_calls")) > 0]
    score_values = [_safe_int(row.get("delivery_score")) for row in recent if _safe_int(row.get("delivery_score")) > 0]
    utilization_values = [
        _safe_float(row.get("context_utilization_ratio"))
        for row in recent
        if _safe_float(row.get("context_utilization_ratio")) > 0
    ]
    selected_card_values = [_safe_int(row.get("selected_cards")) for row in recent if _safe_int(row.get("selected_cards")) > 0]
    prompt_strategy_values = [
        _safe_int(row.get("selected_prompt_strategies"))
        for row in recent
        if _safe_int(row.get("selected_prompt_strategies")) > 0
    ]
    delivery_rank_values = [_delivery_level_rank(row.get("delivery_level")) for row in recent if _delivery_level_rank(row.get("delivery_level")) > 0]
    low_delivery_count = sum(1 for row in recent if _text(row.get("delivery_level")).lower() == "low")
    high_pressure_count = sum(1 for value in utilization_values if value >= 0.9)

    compact_recent = [
        {
            "chapter_no": _safe_int(row.get("chapter_no")),
            "final_title": _truncate_text(row.get("final_title") or row.get("chapter_title"), 24),
            "delivery_level": _truncate_text(row.get("delivery_level"), 12),
            "duration_ms": _safe_int(row.get("duration_ms")),
            "llm_calls": _safe_int(row.get("llm_calls")),
            "delivery_score": _safe_int(row.get("delivery_score")),
            "context_utilization_ratio": _safe_float(row.get("context_utilization_ratio")),
            "selected_cards": _safe_int(row.get("selected_cards")),
            "selected_prompt_strategies": _safe_int(row.get("selected_prompt_strategies")),
        }
        for row in recent
    ]

    return {
        "window": len(recent),
        "chapters": compact_recent,
        "delivery": {
            "latest_level": _text(recent[-1].get("delivery_level")),
            "latest_score": _safe_int(recent[-1].get("delivery_score")),
            "avg_score": _mean_int(score_values),
            "low_count": low_delivery_count,
            "direction": _trend_direction(score_values, tolerance_ratio=0.1, absolute_floor=8.0),
            "level_direction": _trend_direction(delivery_rank_values, tolerance_ratio=0.15, absolute_floor=1.0),
        },
        "performance": {
            "avg_duration_ms": _mean_int(duration_values),
            "latest_duration_ms": _safe_int(recent[-1].get("duration_ms")),
            "duration_direction": _trend_direction(duration_values, tolerance_ratio=0.12, absolute_floor=1200.0),
            "avg_llm_calls": _mean_float([float(value) for value in llm_values], digits=1),
            "latest_llm_calls": _safe_int(recent[-1].get("llm_calls")),
            "llm_calls_direction": _trend_direction(llm_values, tolerance_ratio=0.15, absolute_floor=1.0),
        },
        "context": {
            "avg_utilization_ratio": _mean_float(utilization_values, digits=3),
            "latest_utilization_ratio": _safe_float(recent[-1].get("context_utilization_ratio")),
            "high_pressure_count": high_pressure_count,
        },
        "selection": {
            "avg_selected_cards": _mean_float([float(value) for value in selected_card_values], digits=1),
            "avg_prompt_strategies": _mean_float([float(value) for value in prompt_strategy_values], digits=1),
            "latest_selected_cards": _safe_int(recent[-1].get("selected_cards")),
            "latest_prompt_strategies": _safe_int(recent[-1].get("selected_prompt_strategies")),
        },
    }


def _latest_streak(rows: list[dict[str, Any]], predicate) -> int:
    streak = 0
    for row in reversed(rows):
        try:
            matched = bool(predicate(row))
        except Exception:
            matched = False
        if not matched:
            break
        streak += 1
    return streak


def _push_alert(bucket: list[dict[str, Any]], *, code: str, severity: str, title: str, message: str, metric: Any = None) -> None:
    bucket.append(
        {
            "code": _text(code),
            "severity": _text(severity) or "low",
            "title": _text(title),
            "message": _text(message),
            "metric": metric,
        }
    )


def _build_generation_alerts(
    history_rows: list[dict[str, Any]] | None,
    *,
    trends_payload: dict[str, Any] | None = None,
    window: int = 5,
) -> dict[str, Any]:
    rows = [dict(item) for item in (history_rows or []) if isinstance(item, dict)]
    recent = [row for row in rows[-max(int(window or 1), 1) :] if _safe_int(row.get("chapter_no")) > 0]
    if not recent:
        return {}

    trends = trends_payload if isinstance(trends_payload, dict) and trends_payload else _build_generation_trends(recent, window=window)
    delivery = trends.get("delivery") or {}
    performance = trends.get("performance") or {}
    context = trends.get("context") or {}
    selection = trends.get("selection") or {}
    alerts: list[dict[str, Any]] = []

    low_streak = _latest_streak(recent, lambda row: _text(row.get("delivery_level")).lower() == "low")
    if low_streak >= 2:
        severity = "high" if low_streak >= 3 else "medium"
        _push_alert(
            alerts,
            code="delivery_low_streak",
            severity=severity,
            title="爽点兑现连续走低",
            message=f"最近连续 {low_streak} 章处于 low 兑现，下一章应提高兑现优先级或减少继续蓄压。",
            metric=low_streak,
        )

    latest_score = _safe_int(delivery.get("latest_score"))
    avg_score = _safe_int(delivery.get("avg_score"))
    if _text(delivery.get("direction")) == "down" and latest_score > 0 and avg_score > 0 and latest_score <= avg_score - 8:
        severity = "medium" if latest_score <= avg_score - 15 else "low"
        _push_alert(
            alerts,
            code="delivery_score_down",
            severity=severity,
            title="兑现分在下滑",
            message=f"最近窗口平均兑现分约 {avg_score}，最新一章掉到 {latest_score}，需要检查爽点安排和追账力度。",
            metric=latest_score,
        )

    pressure_streak = _latest_streak(recent, lambda row: _safe_float(row.get("context_utilization_ratio")) >= 0.9)
    if pressure_streak >= 2:
        severity = "high" if pressure_streak >= 3 else "medium"
        _push_alert(
            alerts,
            code="context_pressure_streak",
            severity=severity,
            title="上下文持续高压",
            message=f"最近连续 {pressure_streak} 章上下文利用率 ≥ 90%，该减载或继续压缩章节准备输入包。",
            metric=pressure_streak,
        )
    elif _safe_int(context.get("high_pressure_count")) >= 3 and _safe_int(trends.get("window")) >= 4:
        _push_alert(
            alerts,
            code="context_pressure_frequent",
            severity="low",
            title="上下文压力偏高",
            message="近几章高压命中次数偏多，建议检查 context budget 和卡片筛选规模。",
            metric=_safe_int(context.get("high_pressure_count")),
        )

    avg_llm_calls = _safe_float(performance.get("avg_llm_calls"), 0.0)
    latest_llm_calls = _safe_int(performance.get("latest_llm_calls"))
    if avg_llm_calls > 0 and latest_llm_calls >= max(int(round(avg_llm_calls * 1.35)), int(avg_llm_calls) + 2) and _text(performance.get("llm_calls_direction")) == "up":
        severity = "medium" if latest_llm_calls >= max(int(round(avg_llm_calls * 1.6)), int(avg_llm_calls) + 4) else "low"
        _push_alert(
            alerts,
            code="llm_calls_bloat",
            severity=severity,
            title="LLM 调用数在变胖",
            message=f"最近平均 LLM 调用约 {avg_llm_calls} 次，最新一章涨到 {latest_llm_calls} 次，适合检查哪个阶段开始发福。",
            metric=latest_llm_calls,
        )

    avg_duration_ms = _safe_int(performance.get("avg_duration_ms"))
    latest_duration_ms = _safe_int(performance.get("latest_duration_ms"))
    if avg_duration_ms > 0 and latest_duration_ms >= max(int(round(avg_duration_ms * 1.3)), avg_duration_ms + 1800) and _text(performance.get("duration_direction")) == "up":
        severity = "medium" if latest_duration_ms >= max(int(round(avg_duration_ms * 1.55)), avg_duration_ms + 4000) else "low"
        _push_alert(
            alerts,
            code="duration_bloat",
            severity=severity,
            title="章节耗时在变长",
            message=f"最近平均耗时约 {avg_duration_ms}ms，最新一章拉到 {latest_duration_ms}ms，建议检查慢阶段和等待时间。",
            metric=latest_duration_ms,
        )

    avg_cards = _safe_float(selection.get("avg_selected_cards"), 0.0)
    latest_cards = _safe_int(selection.get("latest_selected_cards"))
    avg_prompts = _safe_float(selection.get("avg_prompt_strategies"), 0.0)
    latest_prompts = _safe_int(selection.get("latest_prompt_strategies"))
    if (avg_cards > 0 and latest_cards >= max(int(round(avg_cards * 1.5)), int(avg_cards) + 2)) or (
        avg_prompts > 0 and latest_prompts >= max(int(round(avg_prompts * 1.5)), int(avg_prompts) + 2)
    ):
        _push_alert(
            alerts,
            code="selection_bloat",
            severity="low",
            title="筛选规模开始膨胀",
            message=f"最新一章用卡 {latest_cards}、写法卡 {latest_prompts}，已经高于最近窗口均值，可能会继续推高上下文和调用成本。",
            metric={"cards": latest_cards, "prompt_strategies": latest_prompts},
        )

    severity_rank = {"low": 1, "medium": 2, "high": 3}
    highest = ""
    if alerts:
        highest = max(alerts, key=lambda item: severity_rank.get(_text(item.get("severity")), 0)).get("severity") or "low"
    return {
        "window": len(recent),
        "count": len(alerts),
        "highest_severity": highest,
        "items": alerts[:6],
    }


def summarize_llm_trace(trace: list[dict[str, Any]] | None) -> dict[str, Any]:
    events = [dict(item) for item in (trace or []) if isinstance(item, dict)]
    total_calls = len([item for item in events if _text(item.get("stage"))])
    stage_order: list[str] = []
    stage_totals: dict[str, dict[str, Any]] = {}
    for item in events:
        stage = _text(item.get("stage"))
        if not stage:
            continue
        if stage not in stage_order:
            stage_order.append(stage)
        stage_payload = stage_totals.setdefault(
            stage,
            {
                "stage": stage,
                "calls": 0,
                "status": _text(item.get("status")) or "ok",
                "duration_ms": 0,
                "waited_ms": 0,
                "response_chars": 0,
            },
        )
        stage_payload["calls"] = _safe_int(stage_payload.get("calls"), 0) + 1
        stage_payload["duration_ms"] = _safe_int(stage_payload.get("duration_ms"), 0) + _safe_int(item.get("duration_ms"), 0)
        stage_payload["waited_ms"] = _safe_int(stage_payload.get("waited_ms"), 0) + _safe_int(item.get("waited_ms"), 0)
        stage_payload["response_chars"] = _safe_int(stage_payload.get("response_chars"), 0) + _safe_int(item.get("response_chars"), 0)
        status = _text(item.get("status"))
        if status:
            stage_payload["status"] = status
    stages = [stage_totals[name] for name in stage_order]
    return {
        "total_calls": total_calls,
        "total_duration_ms": _sum_int(events, "duration_ms"),
        "total_waited_ms": _sum_int(events, "waited_ms"),
        "total_response_chars": _sum_int(events, "response_chars"),
        "stages": stages,
        "stage_order": stage_order,
    }


def build_generation_pipeline_report(
    *,
    chapter_no: int,
    chapter_title: str,
    content: str,
    plan: dict[str, Any] | None,
    chapter_plan_packet: dict[str, Any] | None,
    execution_brief: dict[str, Any] | None,
    context_stats: dict[str, Any] | None,
    attempt_meta: dict[str, Any] | None,
    length_targets: dict[str, Any] | None,
    payoff_delivery: dict[str, Any] | None,
    title_refinement: dict[str, Any] | None,
    serial_delivery: dict[str, Any] | None,
    llm_trace: list[dict[str, Any]] | None,
    duration_ms: int | None,
    summary: Any,
) -> dict[str, Any]:
    packet = chapter_plan_packet or {}
    plan_payload = plan or {}
    execution = execution_brief or {}
    diagnostics = (((packet.get("preparation_selection") or {}).get("diagnostics")) or {}) if isinstance(packet, dict) else {}
    selected_outputs = (diagnostics.get("selected_outputs") or {}) if isinstance(diagnostics, dict) else {}
    pipeline_totals = (diagnostics.get("pipeline_totals") or {}) if isinstance(diagnostics, dict) else {}
    readable_lines = list(diagnostics.get("readable_lines") or [])[:3] if isinstance(diagnostics, dict) else []
    scene_outline = (execution.get("scene_outline") or []) if isinstance(execution, dict) else []
    scene_card = (execution.get("scene_execution_card") or {}) if isinstance(execution, dict) else {}
    llm_summary = summarize_llm_trace(llm_trace)
    attempt_payload = attempt_meta or {}
    title_payload = title_refinement or {}
    payoff_payload = payoff_delivery or {}
    serial_payload = serial_delivery or {}
    context_payload = context_stats or {}
    target_payload = length_targets or {}
    summary_line = _text(getattr(summary, "event_summary", None) or (summary.get("event_summary") if isinstance(summary, dict) else ""))
    open_hooks = list(getattr(summary, "open_hooks", None) or (summary.get("open_hooks") if isinstance(summary, dict) else []) or [])
    new_clues = list(getattr(summary, "new_clues", None) or (summary.get("new_clues") if isinstance(summary, dict) else []) or [])
    budget = max(_safe_int(context_payload.get("budget"), 1), 1)
    return {
        "chapter_no": _safe_int(chapter_no),
        "chapter_title": _text(chapter_title),
        "report_phase": "generation_completed",
        "summary_line": summary_line,
        "flow_template": {
            "id": _text(plan_payload.get("flow_template_id")),
            "tag": _text(plan_payload.get("flow_template_tag")),
            "name": _text(plan_payload.get("flow_template_name")),
        },
        "preparation": {
            "readable_lines": readable_lines,
            "selected_outputs": {
                "focus_characters": _safe_int(selected_outputs.get("focus_characters")),
                "main_relations": _safe_int(selected_outputs.get("main_relations")),
                "selected_cards": _safe_int(selected_outputs.get("selected_cards")),
                "selected_scene_templates": 0,
                "selected_prompt_strategies": _safe_int(selected_outputs.get("selected_prompt_strategies")),
                "selected_flow_template": _text(selected_outputs.get("selected_flow_template")),
                "selected_payoff_card": _text(selected_outputs.get("selected_payoff_card")),
            },
            "pipeline_totals": {
                "selector_count": _safe_int(pipeline_totals.get("selector_count")),
                "llm_calls": _safe_int(pipeline_totals.get("llm_calls")),
                "duration_ms": _safe_int(pipeline_totals.get("duration_ms")),
                "waited_ms": _safe_int(pipeline_totals.get("waited_ms")),
                "prompt_chars": _safe_int(pipeline_totals.get("prompt_chars")),
                "response_chars": _safe_int(pipeline_totals.get("response_chars")),
            },
        },
        "context_budget": {
            "mode": _text(context_payload.get("context_mode")),
            "payload_chars_before": _safe_int(context_payload.get("payload_chars_before")),
            "payload_chars_after": _safe_int(context_payload.get("payload_chars_after")),
            "budget": _safe_int(context_payload.get("budget")),
            "utilization_ratio": round(_safe_float(context_payload.get("payload_chars_after")) / budget, 3),
            "recent_summary_count": _safe_int(context_payload.get("recent_summary_count")),
            "active_intervention_count": _safe_int(context_payload.get("active_intervention_count")),
        },
        "drafting": {
            "attempt_count": _safe_int(attempt_payload.get("attempt_count") or len(attempt_payload.get("attempts") or []), 0),
            "body_segments": _safe_int(attempt_payload.get("body_segments")),
            "continuation_rounds": _safe_int(attempt_payload.get("continuation_rounds")),
            "body_stop_reason": _text(attempt_payload.get("body_stop_reason")),
            "closing_reason": _text(attempt_payload.get("closing_reason")),
            "quality_rejections": len(attempt_payload.get("quality_rejections") or []),
        },
        "length": {
            "content_chars": len(content or ""),
            "target_visible_chars_min": _safe_int(target_payload.get("target_visible_chars_min")),
            "target_visible_chars_max": _safe_int(target_payload.get("target_visible_chars_max")),
        },
        "payoff_delivery": {
            "delivery_level": _text(payoff_payload.get("delivery_level")),
            "delivery_score": _safe_int(payoff_payload.get("delivery_score")),
            "verdict": _text(payoff_payload.get("verdict")),
            "should_compensate_next_chapter": bool(payoff_payload.get("should_compensate_next_chapter")),
            "compensation_priority": _text(payoff_payload.get("compensation_priority")),
        },
        "title_refinement": {
            "final_title": _text(title_payload.get("final_title") or chapter_title),
            "original_title": _text(title_payload.get("original_title") or chapter_title),
            "candidate_count": len(title_payload.get("candidates") or []),
            "joint_call": bool(title_payload.get("joint_call")),
        },
        "scene_plan": {
            "scene_count": _safe_int(scene_card.get("scene_count") or len(scene_outline)),
            "transition_mode": _text(scene_card.get("transition_mode") or scene_card.get("scene_transition_mode")),
            "must_continue_same_scene": bool(scene_card.get("must_continue_same_scene")),
            "outline": _compact_value(scene_outline, text_limit=72, max_items=3),
        },
        "serial_delivery": {
            "mode": _text(serial_payload.get("delivery_mode")),
            "is_published": bool(serial_payload.get("is_published")),
            "published_through": _safe_int(serial_payload.get("published_through")),
            "latest_available_chapter": _safe_int(serial_payload.get("latest_available_chapter")),
        },
        "story_effect": {
            "new_clues": [_truncate_text(item, 56) for item in new_clues[:3]],
            "open_hooks": [_truncate_text(item, 56) for item in open_hooks[:3]],
        },
        "llm_trace": llm_summary,
        "duration_ms": _safe_int(duration_ms),
    }


def attach_generation_pipeline_report(
    story_bible: dict[str, Any] | None,
    report: dict[str, Any] | None,
    *,
    history_limit: int = 8,
) -> dict[str, Any]:
    payload = story_bible if isinstance(story_bible, dict) else {}
    data = report if isinstance(report, dict) else {}
    if not data:
        return payload
    workspace = payload.setdefault("story_workspace", {})
    workspace["last_generation_report"] = data
    history = workspace.setdefault("generation_report_history", [])
    payoff = data.get("payoff_delivery") or {}
    title_refinement = data.get("title_refinement") or {}
    llm_trace = data.get("llm_trace") or {}
    context_budget = data.get("context_budget") or {}
    selected_outputs = ((data.get("preparation") or {}).get("selected_outputs") or {}) if isinstance(data.get("preparation"), dict) else {}
    history.append(
        {
            "chapter_no": _safe_int(data.get("chapter_no")),
            "chapter_title": _text(data.get("chapter_title")),
            "duration_ms": _safe_int(data.get("duration_ms")),
            "delivery_level": _text(payoff.get("delivery_level")),
            "delivery_score": _safe_int(payoff.get("delivery_score")),
            "final_title": _text(title_refinement.get("final_title")) or _text(data.get("chapter_title")),
            "llm_calls": _safe_int(llm_trace.get("total_calls")),
            "context_utilization_ratio": _safe_float(context_budget.get("utilization_ratio")),
            "selected_cards": _safe_int(selected_outputs.get("selected_cards")),
            "selected_prompt_strategies": _safe_int(selected_outputs.get("selected_prompt_strategies")),
        }
    )
    trimmed_history = history[-max(int(history_limit or 1), 1) :]
    workspace["generation_report_history"] = trimmed_history
    latest_report = dict(data)
    latest_report["history"] = [dict(item) for item in trimmed_history]
    latest_report["trends"] = _build_generation_trends(trimmed_history)
    latest_report["alerts"] = _build_generation_alerts(trimmed_history, trends_payload=latest_report.get("trends"))
    workspace["last_generation_report"] = latest_report
    return payload


def compact_generation_pipeline_report(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    preparation = payload.get("preparation") or {}
    selected_outputs = preparation.get("selected_outputs") or {}
    payoff = payload.get("payoff_delivery") or {}
    title_refinement = payload.get("title_refinement") or {}
    llm_trace = payload.get("llm_trace") or {}
    context_budget = payload.get("context_budget") or {}
    drafting = payload.get("drafting") or {}
    scene_plan = payload.get("scene_plan") or {}
    stage_rows = [item for item in (llm_trace.get("stages") or []) if isinstance(item, dict)]
    history_rows = [item for item in (payload.get("history") or []) if isinstance(item, dict)]
    trends_payload = payload.get("trends") if isinstance(payload.get("trends"), dict) else _build_generation_trends(history_rows)
    alerts_payload = payload.get("alerts") if isinstance(payload.get("alerts"), dict) else _build_generation_alerts(history_rows, trends_payload=trends_payload)
    compact = {
        "chapter_no": _safe_int(payload.get("chapter_no")),
        "chapter_title": _truncate_text(payload.get("chapter_title"), 28),
        "summary_line": _truncate_text(payload.get("summary_line"), 120),
        "duration_ms": _safe_int(payload.get("duration_ms")),
        "preparation_summary": [_truncate_text(item, 120) for item in (preparation.get("readable_lines") or [])[:5] if _text(item)],
        "selected_outputs": {
            "selected_cards": _safe_int(selected_outputs.get("selected_cards")),
            "selected_scene_templates": 0,
            "selected_prompt_strategies": _safe_int(selected_outputs.get("selected_prompt_strategies")),
            "selected_flow_template": _text(selected_outputs.get("selected_flow_template")),
            "selected_payoff_card": _text(selected_outputs.get("selected_payoff_card")),
        },
        "context_budget": {
            "mode": _text(context_budget.get("mode")),
            "payload_chars_after": _safe_int(context_budget.get("payload_chars_after")),
            "budget": _safe_int(context_budget.get("budget")),
            "utilization_ratio": _safe_float(context_budget.get("utilization_ratio"), 0.0),
        },
        "drafting": {
            "attempt_count": _safe_int(drafting.get("attempt_count")),
            "continuation_rounds": _safe_int(drafting.get("continuation_rounds")),
            "quality_rejections": _safe_int(drafting.get("quality_rejections")),
            "body_stop_reason": _truncate_text(drafting.get("body_stop_reason"), 28),
        },
        "scene_plan": {
            "scene_count": _safe_int(scene_plan.get("scene_count")),
            "transition_mode": _text(scene_plan.get("transition_mode")),
            "must_continue_same_scene": bool(scene_plan.get("must_continue_same_scene")),
        },
        "payoff_delivery": {
            "delivery_level": _text(payoff.get("delivery_level")),
            "delivery_score": _safe_int(payoff.get("delivery_score")),
            "verdict": _truncate_text(payoff.get("verdict"), 72),
        },
        "title_refinement": {
            "original_title": _truncate_text(title_refinement.get("original_title"), 28),
            "final_title": _truncate_text(title_refinement.get("final_title"), 28),
            "candidate_count": _safe_int(title_refinement.get("candidate_count")),
        },
        "llm_trace": {
            "total_calls": _safe_int(llm_trace.get("total_calls")),
            "total_duration_ms": _safe_int(llm_trace.get("total_duration_ms")),
            "stage_order": [_truncate_text(item, 36) for item in (llm_trace.get("stage_order") or [])[:8] if _text(item)],
            "stage_totals": [
                {
                    "stage": _truncate_text(item.get("stage"), 36),
                    "calls": _safe_int(item.get("calls")),
                    "duration_ms": _safe_int(item.get("duration_ms")),
                    "status": _text(item.get("status")) or "ok",
                }
                for item in stage_rows[:6]
                if _text(item.get("stage"))
            ],
        },
        "history": [
            {
                "chapter_no": _safe_int(item.get("chapter_no")),
                "chapter_title": _truncate_text(item.get("chapter_title"), 24),
                "final_title": _truncate_text(item.get("final_title"), 24),
                "delivery_level": _truncate_text(item.get("delivery_level"), 12),
                "duration_ms": _safe_int(item.get("duration_ms")),
                "llm_calls": _safe_int(item.get("llm_calls")),
                "delivery_score": _safe_int(item.get("delivery_score")),
            }
            for item in history_rows[-5:]
            if _safe_int(item.get("chapter_no")) > 0
        ],
        "trends": {
            "window": _safe_int(trends_payload.get("window")),
            "delivery": {
                "latest_level": _text((trends_payload.get("delivery") or {}).get("latest_level")),
                "latest_score": _safe_int((trends_payload.get("delivery") or {}).get("latest_score")),
                "avg_score": _safe_int((trends_payload.get("delivery") or {}).get("avg_score")),
                "low_count": _safe_int((trends_payload.get("delivery") or {}).get("low_count")),
                "direction": _text((trends_payload.get("delivery") or {}).get("direction")),
                "level_direction": _text((trends_payload.get("delivery") or {}).get("level_direction")),
            },
            "performance": {
                "avg_duration_ms": _safe_int((trends_payload.get("performance") or {}).get("avg_duration_ms")),
                "latest_duration_ms": _safe_int((trends_payload.get("performance") or {}).get("latest_duration_ms")),
                "duration_direction": _text((trends_payload.get("performance") or {}).get("duration_direction")),
                "avg_llm_calls": _safe_float((trends_payload.get("performance") or {}).get("avg_llm_calls"), 0.0),
                "latest_llm_calls": _safe_int((trends_payload.get("performance") or {}).get("latest_llm_calls")),
                "llm_calls_direction": _text((trends_payload.get("performance") or {}).get("llm_calls_direction")),
            },
            "context": {
                "avg_utilization_ratio": _safe_float((trends_payload.get("context") or {}).get("avg_utilization_ratio"), 0.0),
                "latest_utilization_ratio": _safe_float((trends_payload.get("context") or {}).get("latest_utilization_ratio"), 0.0),
                "high_pressure_count": _safe_int((trends_payload.get("context") or {}).get("high_pressure_count")),
            },
            "selection": {
                "avg_selected_cards": _safe_float((trends_payload.get("selection") or {}).get("avg_selected_cards"), 0.0),
                "avg_prompt_strategies": _safe_float((trends_payload.get("selection") or {}).get("avg_prompt_strategies"), 0.0),
                "latest_selected_cards": _safe_int((trends_payload.get("selection") or {}).get("latest_selected_cards")),
                "latest_prompt_strategies": _safe_int((trends_payload.get("selection") or {}).get("latest_prompt_strategies")),
            },
        },
        "alerts": {
            "window": _safe_int(alerts_payload.get("window")),
            "count": _safe_int(alerts_payload.get("count")),
            "highest_severity": _text(alerts_payload.get("highest_severity")),
            "items": [
                {
                    "code": _text(item.get("code")),
                    "severity": _text(item.get("severity")) or "low",
                    "title": _truncate_text(item.get("title"), 24),
                    "message": _truncate_text(item.get("message"), 96),
                }
                for item in (alerts_payload.get("items") or [])[:5]
                if isinstance(item, dict) and (_text(item.get("title")) or _text(item.get("message")))
            ],
        },
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}
