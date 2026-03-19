from app.services.openai_story_engine_bootstrap import (
    ChapterPlan,
    _apply_book_execution_profile_to_chapter,
    _choose_flow_template_for_chapter,
)
from app.services.prompt_templates_bootstrap import arc_outline_user_prompt


def _story_bible() -> dict:
    return {
        "book_execution_profile": {
            "positioning_summary": "低位求生，稳推开场，优先探查与补兑现。",
            "template_pool_policy": "修仙模板池全量开放，章级AI终选。",
            "flow_family_priority": {"high": ["探查"], "medium": ["成长"], "low": ["关系"]},
            "scene_template_priority": {"high": ["线索验证场"]},
            "payoff_priority": {"high": ["误判翻盘"], "medium": ["捡漏反压"], "low": ["公开打脸"]},
            "foreshadowing_priority": {"primary": ["身份真相型"], "secondary": ["规则异常型"], "hold_back": ["关系失衡型"]},
            "writing_strategy_priority": {"high": ["danger_pressure"], "medium": ["goal_chain_clarity"], "low": ["emotional_undertow"]},
            "rhythm_bias": {
                "opening_pace": "稳推",
                "world_reveal_density": "中低",
                "relationship_weight": "低",
                "hook_strength": "中强",
                "payoff_interval": "中短",
                "pressure_curve": "渐压",
            },
            "demotion_rules": ["不要连续重复同一试探结构"],
        },
        "template_library": {
            "flow_templates": [
                {
                    "flow_id": "flow_rel",
                    "family": "关系",
                    "name": "关系拉扯",
                    "label": "关系拉扯",
                    "preferred_event_types": ["试探类"],
                    "preferred_progress_kinds": ["信息推进"],
                    "preferred_hook_styles": ["人物选择"],
                    "keyword_hints": ["试探", "验证"],
                },
                {
                    "flow_id": "flow_probe",
                    "family": "探查",
                    "name": "秘密验证",
                    "label": "秘密验证",
                    "preferred_event_types": ["试探类"],
                    "preferred_progress_kinds": ["信息推进"],
                    "preferred_hook_styles": ["危险逼近"],
                    "keyword_hints": ["试探", "验证"],
                },
            ]
        },
        "flow_control": {"recent_flow_ids": []},
    }


def test_arc_outline_prompt_explicitly_carries_book_execution_profile_into_planning() -> None:
    prompt = arc_outline_user_prompt(
        payload={"genre": "凡人流修仙", "premise": "矿场求生", "protagonist_name": "陈砚", "style_preferences": {"tone": "克制"}},
        story_bible=_story_bible(),
        global_outline={"acts": [{"act_no": 1, "title": "入局", "purpose": "建立处境", "target_chapter_end": 12, "summary": "卷入更大局势"}]},
        recent_summaries=[{"chapter_no": 1, "summary": "先立足。"}],
        start_chapter=2,
        end_chapter=6,
        arc_no=1,
    )
    assert "【本书长期运行画像（本窗口必须遵守）】" in prompt
    assert "book_execution_profile 是这段近纲的长期写法约束" in prompt
    assert "goal / conflict / proactive_move / payoff_or_pressure / hook_style / writing_note" in prompt
    assert "demotion_rules 视为长期禁忌" in prompt


def test_flow_template_choice_respects_book_execution_profile_during_planning() -> None:
    chapter = ChapterPlan(
        chapter_no=3,
        title="矿洞试探",
        goal="验证异常来源",
        ending_hook="危险逼近",
        event_type="试探类",
        progress_kind="信息推进",
        hook_style="危险逼近",
        conflict="试探时暴露风险",
        proactive_move="主动引人试探",
    )
    chosen = _choose_flow_template_for_chapter(chapter, _story_bible())
    assert chosen["flow_id"] == "flow_probe"
    assert chosen["family"] == "探查"


def test_apply_book_execution_profile_enriches_chapter_plan_writing_guidance() -> None:
    chapter = ChapterPlan(
        chapter_no=4,
        title="夜探矿脉",
        goal="摸清异常波动",
        ending_hook="线索更近一步",
    )
    _apply_book_execution_profile_to_chapter(chapter, _story_bible(), chapter_offset=1)
    assert chapter.opening_beat is not None and "稳推" in chapter.opening_beat
    assert chapter.mid_turn is not None and "渐压" in chapter.mid_turn
    assert chapter.discovery is not None and "中低" in chapter.discovery
    assert chapter.flow_variation_note is not None and "探查" in chapter.flow_variation_note
    assert chapter.writing_note is not None and "长期气质" in chapter.writing_note
    assert "避免：不要连续重复同一试探结构" in chapter.writing_note
