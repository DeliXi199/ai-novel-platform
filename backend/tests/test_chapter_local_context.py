import pytest

from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.chapter_context_support import build_chapter_plan_packet, serialize_local_novel_context
from app.services.novel_bootstrap import build_base_story_bible
from app.services.prompt_templates import chapter_draft_user_prompt
from app.services.story_architecture import ensure_story_architecture




def _patch_ai_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.importance_evaluator._ai_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.importance_evaluator.call_json_response",
        lambda **kwargs: {"evaluations": []},
    )
    monkeypatch.setattr("app.services.constraint_reasoning._ai_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.constraint_reasoning.call_json_response",
        lambda **kwargs: {"result": {}, "reason": "测试桩返回", "confidence": "high", "constraint_checks": ["ok"]},
    )

def _build_novel() -> Novel:
    payload = NovelCreate(
        genre="金手指修仙",
        premise="主角凭一面古镜在边城夹缝求生。",
        protagonist_name="林凡",
        style_preferences={"current_resources": ["残缺古镜", "三块灵石"], "factions": ["黑市", "青岚宗"]},
    )
    novel = Novel(
        id=1,
        title="古镜边城",
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences,
        story_bible=build_base_story_bible(payload),
        current_chapter_no=2,
        status="active",
    )
    novel.story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    return novel



def test_build_chapter_plan_packet_selects_local_story_elements(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    plan = {
        "chapter_no": 3,
        "title": "夜市试探",
        "goal": "林凡带着残缺古镜去黑市试探消息，同时观察顾青河的真实立场。",
        "conflict": "黑市里有人盯上了古镜，顾青河也未必可信。",
        "ending_hook": "林凡意识到青岚宗已经有人先一步问过这面古镜。",
        "main_scene": "边城黑市",
        "supporting_character_focus": "顾青河",
        "supporting_character_note": "嘴上冷淡，实则很会观察人，会在关键句前停半拍。",
    }
    serialized_last = {
        "tail_excerpt": "林凡收起古镜，转身前看见顾青河站在灯影下。",
        "continuity_bridge": {
            "opening_anchor": "顾青河的影子被灯笼拉得很长。",
            "onstage_characters": ["林凡", "顾青河", "老周"],
            "unresolved_action_chain": ["顾青河为什么跟来"],
            "carry_over_clues": ["有人也在查古镜来历"],
        },
    }
    recent_summaries = [
        {"chapter_no": 1, "event_summary": "林凡第一次试出古镜异动。", "open_hooks": ["古镜为何发热"]},
        {"chapter_no": 2, "event_summary": "顾青河现身并提出交易。", "open_hooks": ["顾青河的真实目的"]},
    ]

    packet = build_chapter_plan_packet(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=recent_summaries,
    )

    assert packet["selected_elements"]["focus_character"] == "顾青河"
    assert "林凡" in packet["selected_elements"]["characters"]
    assert "顾青河" in packet["selected_elements"]["characters"]
    assert "残缺古镜" in packet["selected_elements"]["resources"]
    assert "黑市" in packet["selected_elements"]["factions"]
    assert packet["continuity_window"]["opening_anchor"] == "顾青河的影子被灯笼拉得很长。"
    assert packet["opening_reveal_guidance"]["in_opening_phase"] is True
    assert packet["core_cast_guidance"]["anchored_target_count"] >= 1
    assert packet["core_cast_guidance"]["anchored_upcoming_characters"]
    assert packet["opening_reveal_guidance"]["power_system_focus"]
    assert packet["character_template_guidance"]["characters"]
    assert packet["recent_continuity_plan"]["current_chapter_bridge"]["must_continue"]
    assert packet["recent_continuity_plan"]["lookahead_handoff"]["handoff_rule"]
    assert "顾青河" in packet["new_cards_created"]["characters"]
    assert novel.story_bible["planner_state"]["selected_entities_by_chapter"]["3"]["characters"][0] == "林凡"
    assert novel.story_bible["planner_state"]["continuity_packet_cache"]["3"]["carry_in"]["focus_targets"][0] == "林凡"



def test_serialize_local_novel_context_keeps_local_context_over_full_pool() -> None:
    novel = _build_novel()
    packet = {
        "selected_elements": {"characters": ["林凡", "顾青河"], "resources": ["残缺古镜"], "factions": ["黑市"]},
        "recent_continuity_plan": {
            "recent_progression": [{"chapter_no": 1, "event_summary": "古镜发热"}],
            "current_chapter_bridge": {"must_continue": ["顾青河为什么跟来"]},
        },
        "relevant_cards": {"characters": {"林凡": {"speech_style": "简短"}}, "resources": {"残缺古镜": {"status": "持有中"}}},
        "continuity_window": {
            "recent_chapter_summaries": [{"chapter_no": 1, "event_summary": "古镜发热"}],
            "last_chapter_tail_excerpt": "林凡把古镜按回袖中。",
            "last_two_paragraphs": ["顾青河没有马上说话。"],
        },
    }
    context = serialize_local_novel_context(
        novel=novel,
        next_no=3,
        recent_summaries=[{"chapter_no": 1, "event_summary": "古镜发热"}],
        chapter_plan_packet=packet,
        execution_brief={"chapter_execution_card": {"chapter_function": "试探黑市消息"}},
    )

    assert context["context_mode"] == "planned_local"
    assert "chapter_local_context" in context["story_memory"]
    assert context["story_memory"]["context_strategy"]["mode"] == "planned_local"
    assert context["story_memory"]["context_strategy"]["source_order"][1] == "近章承接规划"
    assert context["story_memory"]["opening_reveal_guidance"]["in_opening_phase"] is True
    assert "near_7_chapter_outline" not in context["story_memory"]
    assert context["story_memory"]["chapter_local_context"]["selected_elements"]["resources"] == ["残缺古镜"]



def test_chapter_prompt_mentions_planning_packet_and_local_continuity_order() -> None:
    prompt = chapter_draft_user_prompt(
        novel_context={
            "story_memory": {
                "project_card": {"genre_positioning": "修仙"},
                "current_volume_card": {"volume_name": "第一卷"},
                "execution_brief": {"chapter_execution_card": {"chapter_function": "试探"}},
                "chapter_local_context": {"selected_elements": {"characters": ["林凡", "顾青河"]}},
            }
        },
        chapter_plan={
            "title": "第三章",
            "hook_style": "信息反转",
            "planning_packet": {
                "recent_continuity_plan": {"current_chapter_bridge": {"must_continue": ["门外的人是谁"]}},
                "selected_elements": {"characters": ["林凡", "顾青河"]},
                "continuity_window": {"last_chapter_tail_excerpt": "林凡把古镜按回袖中。"},
            },
        },
        last_chapter={"continuity_bridge": {"opening_anchor": "门外有人停住脚步。"}},
        recent_summaries=[{"chapter_no": 1, "event_summary": "古镜发热"}, {"chapter_no": 2, "event_summary": "顾青河现身"}],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2800,
    )

    assert "【本章规划包】" in prompt
    assert "正文输入顺序固定为：本章拍表 -> 近章承接规划 -> 本章规划包 -> 最近几章摘要 -> 上一章末尾正文片段" in prompt
    assert "opening_reveal_guidance" in prompt
    assert "recent_continuity_plan 负责把最近两三章接成一条连续线" in prompt
    assert "selected_elements / relevant_cards 之外的角色、资源、势力" in prompt
    assert "character_template_guidance" in prompt
