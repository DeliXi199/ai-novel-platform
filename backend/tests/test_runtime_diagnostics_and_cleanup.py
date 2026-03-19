from __future__ import annotations

from pathlib import Path

from app.services.chapter_generation_report import attach_generation_pipeline_report
from app.services.prompt_templates_drafting import chapter_draft_user_prompt
from app.services.runtime_diagnostics import build_runtime_diagnostics, build_runtime_diagnostics_brief


ROOT = Path(__file__).resolve().parents[1]


def _story_bible() -> dict:
    return {
        "book_execution_profile": {
            "positioning_summary": "低位求生，先试探再反压，稳推渐压。",
            "flow_family_priority": {"high": ["探查", "交易"], "medium": ["成长"], "low": ["关系"]},
            "payoff_priority": {"high": ["误判翻盘"], "medium": ["捡漏反压"], "low": ["公开打脸"]},
            "foreshadowing_priority": {"primary": ["规则异常型"], "secondary": ["身份真相型"]},
            "writing_strategy_priority": {"high": ["danger_pressure", "goal_chain_clarity"]},
            "rhythm_bias": {"opening_pace": "稳推", "hook_strength": "中强", "payoff_interval": "中短", "pressure_curve": "渐压"},
            "demotion_rules": ["不要连续重复同一试探结构"],
        },
        "card_system_profile": {"version": "card_layers_v1"},
        "story_workspace": {
            "planning_status": {
                "planned_until": 5,
                "ready_chapter_cards": [1, 2, 3, 4, 5],
            },
            "chapter_card_queue": [
                {"chapter_no": 1, "title": "矿灯试探", "goal": "试探规则异常", "event_type": "试探类", "payoff_or_pressure": "先确认异常，再压住盯梢。"},
                {"chapter_no": 2, "title": "当场追回", "goal": "追回一次明确回报", "event_type": "交易类", "payoff_or_pressure": "追回好处并带出余波。"},
            ],
            "window_execution_bias": {
                "window_mode": "repay",
                "focus": "这一窗口先追回回报，再抬一层新风险。",
                "payoff_bias": ["明确落袋", "余波紧接"],
                "foreshadowing_bias": ["规则异常型"],
                "notes": ["不要继续纯蓄压。"],
            },
        },
        "workflow_state": {
            "current_pipeline": {"target_chapter_no": 1, "last_live_stage": "drafting", "last_live_note": "第 1 章正文生成中。"},
            "live_runtime": {"target_chapter_no": 1, "stage": "drafting", "note": "第 1 章正文生成中。"},
            "live_runtime_events": [
                {"updated_at": "2026-03-18T10:00:00Z", "target_chapter_no": 1, "stage": "planning_refresh_completed", "note": "近5章规划已更新", "summary": {"queue_size": 5, "planned_until": 5}},
                {"updated_at": "2026-03-18T10:00:10Z", "target_chapter_no": 1, "stage": "chapter_preparation_selected", "note": "本章 AI 选卡已完成", "summary": {"queue_size": 5}},
                {"updated_at": "2026-03-18T10:00:18Z", "target_chapter_no": 1, "stage": "drafting", "note": "第 1 章正文生成中。", "summary": {"queue_size": 5}},
            ],
        },
    }


def test_source_cleanup_removes_legacy_initialization_cards_and_updates_pool_mode() -> None:
    source = (ROOT / "app/services/novel_bootstrap.py").read_text()
    assert "_legacy_initialization_cards_from_execution_profile" not in source
    assert '"selection_mode": "global_pool_with_direct_ai_selection"' in source
    assert '"initialization_cards"' not in source


def test_runtime_diagnostics_exposes_timeline_profiles_and_alerts() -> None:
    story_bible = _story_bible()
    report = {
        "chapter_no": 1,
        "chapter_title": "矿灯试探",
        "summary_line": "林砚确认矿灯会对异常气息起反应。",
        "duration_ms": 8600,
        "preparation": {"selected_outputs": {"selected_cards": 4, "selected_payoff_card": "payoff-1"}},
        "payoff_delivery": {"delivery_level": "low", "delivery_score": 58, "verdict": "兑现偏虚"},
        "title_refinement": {"final_title": "矿灯试探"},
        "history": [
            {"chapter_no": 1, "chapter_title": "矿灯试探", "final_title": "矿灯试探", "delivery_level": "low", "delivery_score": 58, "duration_ms": 8600, "llm_calls": 8, "context_utilization_ratio": 0.91, "selected_cards": 4, "selected_prompt_strategies": 3},
            {"chapter_no": 2, "chapter_title": "当场追回", "final_title": "当场追回", "delivery_level": "low", "delivery_score": 54, "duration_ms": 9300, "llm_calls": 9, "context_utilization_ratio": 0.93, "selected_cards": 5, "selected_prompt_strategies": 4},
            {"chapter_no": 3, "chapter_title": "旧三", "final_title": "旧三", "delivery_level": "low", "delivery_score": 50, "duration_ms": 10100, "llm_calls": 10, "context_utilization_ratio": 0.95, "selected_cards": 6, "selected_prompt_strategies": 4},
            {"chapter_no": 4, "chapter_title": "旧四", "final_title": "旧四", "delivery_level": "low", "delivery_score": 46, "duration_ms": 11100, "llm_calls": 11, "context_utilization_ratio": 0.96, "selected_cards": 7, "selected_prompt_strategies": 5},
        ],
    }
    story_bible = attach_generation_pipeline_report(story_bible, report)
    diagnostics = build_runtime_diagnostics(
        story_bible,
        active_tasks=[{"id": 7, "task_type": "generate_next_chapter", "status": "running", "chapter_no": 1, "progress_message": "第 1 章正文生成中。"}],
        recent_tasks=[{"id": 7, "task_type": "generate_next_chapter", "status": "running", "chapter_no": 1}],
    )

    assert diagnostics["overview"]["current_stage"] == "drafting"
    assert diagnostics["book_profile"]["positioning_summary"].startswith("低位求生")
    assert diagnostics["window_bias"]["window_mode"] == "repay"
    assert diagnostics["timeline"][-1]["stage"] == "drafting"
    assert diagnostics["alerts"]["count"] >= 1
    brief = build_runtime_diagnostics_brief(story_bible)
    assert brief["current_stage"] == "drafting"
    assert brief["alert_count"] >= 1


def test_prompt_and_runtime_diagnostics_share_same_book_and_window_tone() -> None:
    story_bible = _story_bible()
    novel_context = {
        "story_memory": {
            "project_card": {"genre_positioning": "凡人流修仙"},
            "current_volume_card": {"volume_no": 1, "main_conflict": "立足与藏锋"},
            "execution_brief": {"chapter_execution_card": {"chapter_function": "先试探再追回一口便宜"}},
            "book_execution_profile": story_bible.get("book_execution_profile"),
            "window_execution_bias": story_bible["story_workspace"].get("window_execution_bias"),
            "card_system_profile": story_bible.get("card_system_profile"),
            "hard_fact_guard": {},
        },
        "protagonist_name": "林砚",
    }
    chapter_plan = {
        "goal": "先试探再追回一口便宜",
        "event_type": "交易类",
        "progress_kind": "资源推进",
        "proactive_move": "故意抛出半真消息压价",
        "payoff_or_pressure": "追回一次明确回报，并让旁人改口风",
        "planning_packet": {},
    }
    prompt = chapter_draft_user_prompt(novel_context, chapter_plan, {}, [], [], 2400, 1800, 3200)
    diagnostics = build_runtime_diagnostics(story_bible)

    assert "【本书长期气质与阶段偏置】" in prompt
    assert diagnostics["book_profile"]["positioning_summary"].startswith("低位求生")
    assert diagnostics["window_bias"]["window_mode"] == "repay"
