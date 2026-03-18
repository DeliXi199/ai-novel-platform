from __future__ import annotations

from app.services.novel_bootstrap import _apply_payoff_compensation_window_to_bundle
from app.services.payoff_compensation_support import apply_payoff_window_event_bias_to_plan
from app.services.prompt_templates import _planning_payoff_compensation_prompt_payload
from app.services.story_architecture import _build_pending_payoff_compensation_payload, refresh_planning_views


def test_apply_payoff_window_event_bias_to_plan_shifts_pressure_heavy_event() -> None:
    plan = {
        "chapter_no": 6,
        "chapter_type": "probe",
        "event_type": "发现类",
        "progress_kind": "风险升级",
        "writing_note": "先稳住气氛。",
    }

    updated = apply_payoff_window_event_bias_to_plan(
        plan,
        role="primary_repay",
        priority="high",
        note="这一章要优先追回一次明确回报。",
        recent_event_types=["发现类", "发现类"],
    )

    assert updated["event_type"] in {"反制类", "资源获取类", "交易类", "关系推进类"}
    assert updated["event_type"] != "发现类"
    assert updated["progress_kind"] == "资源推进"
    assert updated["chapter_type"] == "progress"
    assert updated["payoff_window_event_bias"]["window_role"] == "primary_repay"
    assert "追回一次明确回报" in updated["writing_note"]



def test_planning_payoff_compensation_payload_exposes_event_guidance() -> None:
    story_bible = {
        "retrospective_state": {
            "pending_payoff_compensation": _build_pending_payoff_compensation_payload(
                source_chapter_no=5,
                priority="high",
                note="上一章兑现偏虚，接下来两章要给回报让路。",
            )
        }
    }

    payload = _planning_payoff_compensation_prompt_payload(story_bible, start_chapter=6, end_chapter=8)

    assert payload["overlapping_chapters"][0]["preferred_event_types"][0] == "反制类"
    assert "优先安排" in payload["event_guidance"][0]



def test_apply_payoff_compensation_window_to_bundle_adjusts_event_type_distribution() -> None:
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
            {"chapter_no": 6, "title": "先追回", "goal": "拿回主动", "event_type": "发现类", "progress_kind": "风险升级", "ending_hook": "新线索浮出", "payoff_or_pressure": "先确认对手意图"},
            {"chapter_no": 7, "title": "稳余波", "goal": "稳住风向", "event_type": "逃避类", "progress_kind": "风险升级", "ending_hook": "后患逼近", "payoff_or_pressure": "继续探查"},
            {"chapter_no": 8, "title": "正常推进", "goal": "继续主线", "event_type": "发现类", "progress_kind": "信息推进", "ending_hook": "下一步动作", "payoff_or_pressure": "再抬一点风险"},
        ],
    }

    updated = _apply_payoff_compensation_window_to_bundle(bundle, story_bible, start_chapter=6, end_chapter=8)
    first, second, third = updated["chapters"]

    assert first["event_type"] in {"反制类", "资源获取类", "交易类", "关系推进类"}
    assert first["progress_kind"] == "资源推进"
    assert second["event_type"] in {"关系推进类", "反制类", "发现类", "外部任务类"}
    assert second["event_type"] != "逃避类"
    assert third["event_type"] == "发现类"
    assert "第6章优先安排" in updated["bridge_note"]



def test_refresh_planning_views_exposes_payoff_window_event_bias_on_queue() -> None:
    story_bible = {
        "active_arc": {
            "arc_no": 1,
            "start_chapter": 6,
            "end_chapter": 8,
            "chapters": [
                {"chapter_no": 6, "title": "追回一手", "goal": "拿回资源", "ending_hook": "被人记住", "payoff_or_pressure": "先追回一手", "event_type": "发现类"},
                {"chapter_no": 7, "title": "稳住余波", "goal": "压住后患", "ending_hook": "新的交易口子", "payoff_or_pressure": "继续盘局", "event_type": "发现类"},
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

    assert queue[0]["payoff_window_event_bias"]["preferred_event_types"][0] == "反制类"
    assert queue[1]["payoff_window_event_bias"]["window_role"] == "stabilize_after_repay"
    planning_status = refreshed["story_workspace"]["planning_status"]
    assert planning_status["pending_payoff_compensation"]["chapter_biases"][0]["event_bias"]["preferred_progress_kinds"][0] == "资源推进"
