from __future__ import annotations

from app.services.novel_bootstrap import _apply_payoff_compensation_window_to_bundle
from app.services.story_architecture import (
    _build_pending_payoff_compensation_payload,
    _roll_pending_payoff_compensation,
    refresh_planning_views,
)


def test_high_priority_compensation_builds_two_chapter_window() -> None:
    payload = _build_pending_payoff_compensation_payload(
        source_chapter_no=5,
        priority="high",
        note="上一章兑现偏虚，接下来两章要追回一次明确回报。",
    )

    assert payload["target_chapter_no"] == 6
    assert payload["window_end_chapter_no"] == 7
    assert [item["chapter_no"] for item in payload["chapter_biases"]] == [6, 7]
    assert payload["chapter_biases"][0]["bias"] == "primary_repay"
    assert payload["chapter_biases"][1]["bias"] == "stabilize_after_repay"


def test_roll_pending_payoff_compensation_advances_when_repay_still_soft() -> None:
    payload = _build_pending_payoff_compensation_payload(
        source_chapter_no=5,
        priority="high",
        note="上一章兑现偏虚，接下来两章要追回一次明确回报。",
    )

    rolled = _roll_pending_payoff_compensation(
        payload,
        chapter_no=6,
        payoff_delivery={"delivery_level": "medium"},
    )

    assert rolled["target_chapter_no"] == 7
    assert [item["chapter_no"] for item in rolled["chapter_biases"]] == [7]
    assert rolled["priority"] == "medium"


def test_roll_pending_payoff_compensation_clears_after_strong_repay() -> None:
    payload = _build_pending_payoff_compensation_payload(
        source_chapter_no=5,
        priority="high",
        note="上一章兑现偏虚，接下来两章要追回一次明确回报。",
    )

    rolled = _roll_pending_payoff_compensation(
        payload,
        chapter_no=6,
        payoff_delivery={"delivery_level": "high"},
    )

    assert rolled == {}


def test_apply_payoff_compensation_window_to_bundle_marks_first_two_plans() -> None:
    story_bible = {
        "retrospective_state": {
            "pending_payoff_compensation": _build_pending_payoff_compensation_payload(
                source_chapter_no=5,
                priority="high",
                note="上一章兑现偏虚，这一小段要优先追回读者回报。",
            )
        }
    }
    bundle = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 8,
        "bridge_note": "先把局势接稳。",
        "chapters": [
            {"chapter_no": 6, "title": "先追回", "goal": "拿回主动", "ending_hook": "新线索浮出", "payoff_or_pressure": "先确认对手意图"},
            {"chapter_no": 7, "title": "稳余波", "goal": "稳住风向", "ending_hook": "后患逼近", "payoff_or_pressure": "继续探查"},
            {"chapter_no": 8, "title": "正常推进", "goal": "继续主线", "ending_hook": "下一步动作", "payoff_or_pressure": "再抬一点风险"},
        ],
    }

    updated = _apply_payoff_compensation_window_to_bundle(bundle, story_bible, start_chapter=6, end_chapter=8)
    first, second, third = updated["chapters"]

    assert first["payoff_compensation"]["target_chapter_no"] == 6
    assert first["payoff_window_bias"] == "primary_repay"
    assert "明确回报落袋" in first["payoff_or_pressure"]
    assert second["payoff_window_bias"] == "stabilize_after_repay"
    assert "至少保留一次可感回收" in second["payoff_or_pressure"]
    assert "payoff_compensation" not in third
    assert updated["planning_payoff_compensation"]["overlapping_chapters"][0]["chapter_no"] == 6


def test_refresh_planning_views_overlays_pending_payoff_compensation_on_queue() -> None:
    story_bible = {
        "active_arc": {
            "arc_no": 1,
            "start_chapter": 6,
            "end_chapter": 8,
            "chapters": [
                {"chapter_no": 6, "title": "追回一手", "goal": "拿回资源", "ending_hook": "被人记住", "payoff_or_pressure": "先追回一手"},
                {"chapter_no": 7, "title": "稳住余波", "goal": "压住后患", "ending_hook": "新的交易口子", "payoff_or_pressure": "继续盘局"},
            ],
        },
        "retrospective_state": {
            "pending_payoff_compensation": _build_pending_payoff_compensation_payload(
                source_chapter_no=5,
                priority="high",
                note="上一章兑现偏虚，接下来两章要给回报让路。",
            )
        },
    }

    refreshed = refresh_planning_views(story_bible, current_chapter_no=5)
    queue = refreshed["story_workspace"]["chapter_card_queue"]

    assert queue[0]["payoff_compensation"]["priority"] == "high"
    assert queue[0]["payoff_window_bias"] == "primary_repay"
    assert queue[1]["payoff_window_bias"] == "stabilize_after_repay"
    planning_status = refreshed["story_workspace"]["planning_status"]
    assert planning_status["pending_payoff_compensation"]["window_end_chapter_no"] == 7
