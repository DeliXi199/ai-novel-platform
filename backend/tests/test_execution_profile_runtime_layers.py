from app.schemas.novel import NovelCreate
from app.services.prompt_templates_drafting import chapter_draft_user_prompt
from app.services.story_architecture import build_execution_brief, refresh_planning_views
from app.services.story_blueprint_builders import build_story_workspace
from app.services.story_character_support import _build_chapter_retrospective


def _payload() -> NovelCreate:
    return NovelCreate(
        genre="凡人流修仙",
        premise="主角在矿场夹缝里求生，并逐步摸出规则异常。",
        protagonist_name="林砚",
        style_preferences={"tone": "克制"},
    )


def _base_story_bible() -> dict:
    payload = _payload()
    workspace = build_story_workspace(payload)
    return {
        "project_card": {"genre_positioning": payload.genre},
        "book_execution_profile": {
            "positioning_summary": "低位求生，先试探再反压，稳推渐压。",
            "flow_family_priority": {"high": ["探查", "交易"], "medium": ["成长"], "low": ["关系"]},
            "payoff_priority": {"high": ["误判翻盘"], "medium": ["捡漏反压"], "low": ["公开打脸"]},
            "foreshadowing_priority": {"primary": ["规则异常型"], "secondary": ["身份真相型"]},
            "writing_strategy_priority": {"high": ["danger_pressure", "goal_chain_clarity"]},
            "rhythm_bias": {"opening_pace": "稳推", "hook_strength": "中强", "payoff_interval": "中短", "pressure_curve": "渐压"},
            "demotion_rules": ["不要连续重复同一试探结构"],
        },
        "volume_cards": [{"volume_no": 1, "start_chapter": 1, "end_chapter": 20, "main_conflict": "立足与藏锋", "cool_point": "第一次真正反制"}],
        "story_workspace": workspace,
        "serial_rules": {"fact_priority": ["已发布正文", "长期状态"]},
        "long_term_state": {"chapter_release_state": {"delivery_mode": "stockpile", "published_through": 0, "latest_available_chapter": 0}},
        "continuity_rules": ["不能重复同类桥段。"],
        "active_arc": {
            "arc_no": 1,
            "start_chapter": 1,
            "end_chapter": 5,
            "focus": "先确认规则异常，再想办法占到一点便宜。",
            "chapters": [
                {"chapter_no": 1, "title": "矿灯试探", "goal": "试探规则异常", "conflict": "一旦问深就会惹来盯梢", "ending_hook": "异常更近一步", "event_type": "试探类", "progress_kind": "信息推进"},
                {"chapter_no": 2, "title": "当场追回", "goal": "追回一次明确回报", "conflict": "对手要反咬", "ending_hook": "局面要翻", "event_type": "交易类", "progress_kind": "资源推进"},
            ],
        },
        "retrospective_state": {
            "pending_payoff_compensation": {
                "enabled": True,
                "source_chapter_no": 0,
                "target_chapter_no": 1,
                "priority": "high",
                "note": "开局先补一次明确兑现，不要连续只蓄压。",
            }
        },
    }


def test_refresh_planning_views_builds_window_bias_and_card_layers() -> None:
    story_bible = refresh_planning_views(_base_story_bible(), 0)
    window_bias = story_bible["story_workspace"]["window_execution_bias"]
    assert window_bias["window_mode"] == "repay"
    assert story_bible["story_workspace"]["planning_status"]["card_system_profile"]["version"] == "card_layers_v1"
    assert story_bible["initialization_packet"]["window_execution_bias_brief"]
    assert story_bible["initialization_packet"]["card_system_profile_brief"]


def test_execution_brief_carries_book_profile_window_bias_and_card_profile() -> None:
    story_bible = refresh_planning_views(_base_story_bible(), 0)
    plan = {
        "goal": "先试探再追回一口便宜",
        "event_type": "交易类",
        "progress_kind": "资源推进",
        "proactive_move": "故意抛出半真消息压价",
        "payoff_or_pressure": "追回一次明确回报，并让旁人改口风",
        "hook_kind": "新发现",
    }
    brief = build_execution_brief(story_bible=story_bible, next_chapter_no=1, plan=plan, last_chapter_tail="矿灯轻轻晃了一下。")
    assert brief["book_execution_profile"]["positioning_summary"].startswith("低位求生")
    assert brief["window_execution_bias"]["window_mode"] == "repay"
    assert brief["card_system_profile"]["version"] == "card_layers_v1"
    assert brief["chapter_execution_card"]["window_execution_note"]
    assert brief["daily_workbench"]["window_execution_bias"]


def test_chapter_draft_prompt_explicitly_mentions_long_term_profile_and_window_bias() -> None:
    story_bible = refresh_planning_views(_base_story_bible(), 0)
    novel_context = {
        "story_memory": {
            "project_card": story_bible.get("project_card"),
            "current_volume_card": story_bible.get("volume_cards", [])[0],
            "execution_brief": {"chapter_execution_card": {"chapter_function": "追回一次回报"}},
            "book_execution_profile": story_bible.get("book_execution_profile"),
            "window_execution_bias": story_bible["story_workspace"].get("window_execution_bias"),
            "card_system_profile": story_bible.get("card_system_profile"),
            "hard_fact_guard": {},
        },
        "protagonist_name": "林砚",
    }
    chapter_plan = {
        "goal": "追回一次回报",
        "event_type": "交易类",
        "progress_kind": "资源推进",
        "proactive_move": "故意压价试探",
        "payoff_or_pressure": "追回便宜并带出余波",
        "planning_packet": {},
    }
    prompt = chapter_draft_user_prompt(novel_context, chapter_plan, {}, [], [], 2400, 1800, 3200)
    assert "【本书长期气质与阶段偏置】" in prompt
    assert "window_execution_bias" in prompt
    assert "book_execution_profile" in prompt


def test_retrospective_marks_alignment_drift_when_plan_ignores_long_term_profile() -> None:
    story_bible = refresh_planning_views(_base_story_bible(), 0)
    retrospective = _build_chapter_retrospective(
        chapter_no=1,
        chapter_title="空转一章",
        plan={
            "event_type": "关系推进类",
            "progress_kind": "关系推进",
            "proactive_move": "谨慎应对",
            "payoff_or_pressure": "大家只是继续观望",
            "flow_template_name": "关系拉扯",
            "supporting_character_focus": "陈掌柜",
            "supporting_character_note": "",
        },
        summary=type("S", (), {"event_summary": "这一章大体还在观望。"})(),
        workspace_state=story_bible["story_workspace"],
        story_bible=story_bible,
    )
    assert retrospective["book_execution_alignment"] in {"mixed", "drift"}
    assert retrospective["next_chapter_correction"]
