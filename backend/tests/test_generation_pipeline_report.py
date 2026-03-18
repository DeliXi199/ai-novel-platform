from __future__ import annotations

from types import SimpleNamespace

from app.services.chapter_generation_report import (
    attach_generation_pipeline_report,
    build_generation_pipeline_report,
    compact_generation_pipeline_report,
)


def test_build_generation_pipeline_report_captures_pipeline_chain() -> None:
    summary = SimpleNamespace(
        event_summary="方尘确认古镜会吃灵力，但也暴露了自己。",
        open_hooks=["废铁堆后有人盯上了他"],
        new_clues=["古镜边缘会在特定灵力节奏下亮起灰纹"],
    )
    report = build_generation_pipeline_report(
        chapter_no=3,
        chapter_title="废料区试手",
        content="方尘试了三轮，镜背终于浮出一丝灰纹。",
        plan={
            "flow_template_id": "probe_gain_pressure",
            "flow_template_tag": "试探-获益-风险",
            "flow_template_name": "试探获益再抬压",
        },
        chapter_plan_packet={
            "preparation_selection": {
                "diagnostics": {
                    "readable_lines": ["扫描全量卡片。", "AI 预筛后缩到 shortlist。", "最终完成统一仲裁。"],
                    "selected_outputs": {
                        "selected_cards": 4,
                        "selected_scene_templates": 2,
                        "selected_prompt_strategies": 3,
                        "selected_flow_template": "probe_gain_pressure",
                        "selected_payoff_card": "payoff-7",
                    },
                    "pipeline_totals": {
                        "selector_count": 7,
                        "llm_calls": 7,
                        "duration_ms": 2480,
                        "waited_ms": 120,
                        "prompt_chars": 6200,
                        "response_chars": 2100,
                    },
                }
            }
        },
        execution_brief={
            "scene_execution_card": {
                "scene_count": 2,
                "transition_mode": "handoff",
                "must_continue_same_scene": False,
            },
            "scene_outline": [
                {"scene_no": 1, "purpose": "试镜"},
                {"scene_no": 2, "purpose": "确认回报并留风险"},
            ],
        },
        context_stats={
            "context_mode": "local_strict",
            "payload_chars_before": 8800,
            "payload_chars_after": 6400,
            "budget": 7000,
            "recent_summary_count": 2,
            "active_intervention_count": 1,
        },
        attempt_meta={
            "attempt_count": 2,
            "body_segments": 2,
            "continuation_rounds": 1,
            "body_stop_reason": "ready_for_closing",
            "closing_reason": "below_target_min",
            "quality_rejections": [{"code": "TAIL_WEAK"}],
        },
        length_targets={"target_visible_chars_min": 1600, "target_visible_chars_max": 2600},
        payoff_delivery={
            "delivery_level": "medium",
            "delivery_score": 78,
            "verdict": "兑现到位但后劲还能再压强一些。",
        },
        title_refinement={
            "original_title": "废料区试手",
            "final_title": "灰纹初现",
            "candidates": [{"title": "灰纹初现"}, {"title": "镜背微凉"}],
            "joint_call": True,
        },
        serial_delivery={
            "delivery_mode": "live_publish",
            "is_published": True,
            "published_through": 3,
            "latest_available_chapter": 3,
        },
        llm_trace=[
            {"stage": "chapter_prepare_shortlist", "status": "ok", "duration_ms": 400, "response_chars": 220},
            {"stage": "chapter_generation_body", "status": "ok", "duration_ms": 1600, "response_chars": 980},
            {"stage": "chapter_summary_title_package", "status": "ok", "duration_ms": 520, "response_chars": 340},
        ],
        duration_ms=5210,
        summary=summary,
    )

    assert report["chapter_no"] == 3
    assert report["preparation"]["selected_outputs"]["selected_cards"] == 4
    assert report["context_budget"]["utilization_ratio"] == 0.914
    assert report["llm_trace"]["total_calls"] == 3
    assert report["title_refinement"]["final_title"] == "灰纹初现"
    assert report["story_effect"]["open_hooks"] == ["废铁堆后有人盯上了他"]


def test_attach_and_compact_generation_pipeline_report_keeps_recent_history() -> None:
    story_bible = {}
    first = {"chapter_no": 2, "chapter_title": "旧标题", "duration_ms": 3100, "payoff_delivery": {"delivery_level": "low"}, "title_refinement": {"final_title": "旧标题"}}
    second = {
        "chapter_no": 3,
        "chapter_title": "废料区试手",
        "summary_line": "方尘确认古镜会吃灵力。",
        "duration_ms": 5200,
        "preparation": {
            "readable_lines": ["扫描全量卡片。", "AI 预筛后缩到 shortlist。", "最终完成统一仲裁。"],
            "selected_outputs": {
                "selected_cards": 4,
                "selected_scene_templates": 2,
                "selected_prompt_strategies": 3,
                "selected_flow_template": "probe_gain_pressure",
                "selected_payoff_card": "payoff-7",
            },
        },
        "payoff_delivery": {"delivery_level": "medium", "delivery_score": 78, "verdict": "兑现到位"},
        "title_refinement": {"original_title": "废料区试手", "final_title": "灰纹初现", "candidate_count": 2},
        "llm_trace": {"total_calls": 9, "total_duration_ms": 4300, "stage_order": ["chapter_prepare_shortlist", "chapter_generation_body"]},
    }

    attach_generation_pipeline_report(story_bible, first, history_limit=4)
    updated = attach_generation_pipeline_report(story_bible, second, history_limit=4)
    compact = compact_generation_pipeline_report(updated["story_workspace"]["last_generation_report"])

    assert len(updated["story_workspace"]["generation_report_history"]) == 2
    assert updated["story_workspace"]["generation_report_history"][-1]["final_title"] == "灰纹初现"
    assert updated["story_workspace"]["generation_report_history"][-1]["llm_calls"] == 9
    assert compact["chapter_no"] == 3
    assert compact["selected_outputs"]["selected_cards"] == 4
    assert compact["llm_trace"]["stage_order"] == ["chapter_prepare_shortlist", "chapter_generation_body"]
    assert compact["trends"]["window"] == 2

    compact_with_history = compact_generation_pipeline_report({**updated["story_workspace"]["last_generation_report"], "history": updated["story_workspace"]["generation_report_history"]})
    assert compact_with_history["history"][-1]["final_title"] == "灰纹初现"
    assert compact_with_history["trends"]["delivery"]["latest_level"] == "medium"


def test_compact_generation_pipeline_report_keeps_runtime_stats() -> None:
    compact = compact_generation_pipeline_report(
        {
            "chapter_no": 9,
            "chapter_title": "井底听风",
            "summary_line": "主角确认井底回声会暴露方位。",
            "duration_ms": 9100,
            "context_budget": {"mode": "local_strict", "payload_chars_after": 6200, "budget": 7000, "utilization_ratio": 0.886},
            "drafting": {"attempt_count": 2, "continuation_rounds": 1, "quality_rejections": 1, "body_stop_reason": "ready_for_closing"},
            "scene_plan": {"scene_count": 3, "transition_mode": "handoff", "must_continue_same_scene": True},
            "payoff_delivery": {"delivery_level": "medium", "delivery_score": 81, "verdict": "兑现到位"},
            "title_refinement": {"original_title": "井底听风", "final_title": "回声露口", "candidate_count": 3},
            "llm_trace": {
                "total_calls": 4,
                "total_duration_ms": 4800,
                "stage_order": ["chapter_prepare_shortlist", "chapter_generation_body", "chapter_summary_title_package"],
                "stages": [
                    {"stage": "chapter_prepare_shortlist", "calls": 1, "duration_ms": 420, "status": "ok"},
                    {"stage": "chapter_generation_body", "calls": 2, "duration_ms": 3500, "status": "ok"},
                ],
            },
        }
    )

    assert compact["context_budget"]["budget"] == 7000
    assert compact["drafting"]["attempt_count"] == 2
    assert compact["scene_plan"]["scene_count"] == 3
    assert compact["llm_trace"]["stage_totals"][1]["stage"] == "chapter_generation_body"


def test_compact_generation_pipeline_report_builds_recent_trends() -> None:
    compact = compact_generation_pipeline_report(
        {
            "chapter_no": 12,
            "chapter_title": "山门夜火",
            "history": [
                {"chapter_no": 8, "chapter_title": "旧一", "final_title": "旧一", "delivery_level": "low", "delivery_score": 60, "duration_ms": 11200, "llm_calls": 8, "context_utilization_ratio": 0.93, "selected_cards": 5, "selected_prompt_strategies": 3},
                {"chapter_no": 9, "chapter_title": "旧二", "final_title": "旧二", "delivery_level": "medium", "delivery_score": 74, "duration_ms": 10400, "llm_calls": 7, "context_utilization_ratio": 0.91, "selected_cards": 4, "selected_prompt_strategies": 3},
                {"chapter_no": 10, "chapter_title": "旧三", "final_title": "旧三", "delivery_level": "medium", "delivery_score": 79, "duration_ms": 9800, "llm_calls": 7, "context_utilization_ratio": 0.88, "selected_cards": 4, "selected_prompt_strategies": 2},
                {"chapter_no": 11, "chapter_title": "旧四", "final_title": "旧四", "delivery_level": "high", "delivery_score": 86, "duration_ms": 9100, "llm_calls": 6, "context_utilization_ratio": 0.86, "selected_cards": 3, "selected_prompt_strategies": 2},
                {"chapter_no": 12, "chapter_title": "山门夜火", "final_title": "山门夜火", "delivery_level": "high", "delivery_score": 91, "duration_ms": 8400, "llm_calls": 5, "context_utilization_ratio": 0.84, "selected_cards": 3, "selected_prompt_strategies": 2},
            ],
        }
    )

    assert compact["trends"]["window"] == 5
    assert compact["trends"]["delivery"]["direction"] == "up"
    assert compact["trends"]["performance"]["duration_direction"] == "down"
    assert compact["trends"]["context"]["high_pressure_count"] == 2
    assert compact["trends"]["selection"]["latest_selected_cards"] == 3


def test_compact_generation_pipeline_report_builds_recent_alerts() -> None:
    compact = compact_generation_pipeline_report(
        {
            "chapter_no": 14,
            "chapter_title": "矿道闷响",
            "history": [
                {"chapter_no": 10, "chapter_title": "旧一", "final_title": "旧一", "delivery_level": "medium", "delivery_score": 76, "duration_ms": 6200, "llm_calls": 6, "context_utilization_ratio": 0.82, "selected_cards": 3, "selected_prompt_strategies": 2},
                {"chapter_no": 11, "chapter_title": "旧二", "final_title": "旧二", "delivery_level": "low", "delivery_score": 64, "duration_ms": 7600, "llm_calls": 7, "context_utilization_ratio": 0.91, "selected_cards": 4, "selected_prompt_strategies": 2},
                {"chapter_no": 12, "chapter_title": "旧三", "final_title": "旧三", "delivery_level": "low", "delivery_score": 58, "duration_ms": 9800, "llm_calls": 10, "context_utilization_ratio": 0.93, "selected_cards": 6, "selected_prompt_strategies": 4},
                {"chapter_no": 13, "chapter_title": "旧四", "final_title": "旧四", "delivery_level": "low", "delivery_score": 52, "duration_ms": 11800, "llm_calls": 12, "context_utilization_ratio": 0.95, "selected_cards": 7, "selected_prompt_strategies": 5},
                {"chapter_no": 14, "chapter_title": "矿道闷响", "final_title": "矿道闷响", "delivery_level": "low", "delivery_score": 48, "duration_ms": 14300, "llm_calls": 15, "context_utilization_ratio": 0.96, "selected_cards": 8, "selected_prompt_strategies": 6},
            ],
        }
    )

    assert compact["alerts"]["count"] >= 4
    assert compact["alerts"]["highest_severity"] == "high"
    codes = [item["code"] for item in compact["alerts"]["items"]]
    assert "delivery_low_streak" in codes
    assert "context_pressure_streak" in codes
