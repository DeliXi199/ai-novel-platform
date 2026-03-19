from __future__ import annotations

from types import SimpleNamespace

from app.services.scene_templates import build_scene_handoff_card, build_scene_templates, choose_scene_sequence_for_chapter, realize_scene_continuity_plan
from app.services.story_blueprint_builders import build_template_library


def test_build_scene_templates_has_expected_size() -> None:
    templates = build_scene_templates()

    assert len(templates) >= 20
    assert any(item.get("scene_id") == "same_scene_continuation" for item in templates)
    assert any(item.get("scene_role") == "ending" for item in templates)


def test_build_template_library_includes_scene_templates() -> None:
    from app.schemas.novel import NovelCreate

    payload = NovelCreate(genre="凡人修仙", premise="边城求生", protagonist_name="林凡", style_preferences={})
    library = build_template_library(payload)

    assert len(library.get("scene_templates") or []) >= 20
    assert library["roadmap"]["current_scene_template_count"] == len(library.get("scene_templates") or [])


def test_choose_scene_sequence_supports_continuation_and_multi_scene() -> None:
    story_bible = {"template_library": {"scene_templates": build_scene_templates(), "roadmap": {}}}
    plan = {
        "chapter_no": 6,
        "main_scene": "药铺后间继续试探掌柜",
        "goal": "确认对方和失踪线是否有关",
        "conflict": "掌柜装傻，外面还有人盯梢",
        "opening_beat": "紧接上一章药铺后间的僵持继续往下压",
        "mid_turn": "主角借药渣试对方，外面脚步声逼近",
        "ending_hook": "盯梢者身份露出一角",
        "event_type": "调查类",
        "progress_kind": "信息推进",
        "payoff_mode": "明确兑现",
        "hook_style": "更大谜团",
    }
    serialized_last = {
        "continuity_bridge": {
            "opening_anchor": "掌柜把茶盏往前推了半寸，目光还停在药包上。",
            "unresolved_action_chain": ["药渣来源未验证", "门外盯梢者还没处理"],
            "carry_over_clues": ["异常药包"],
            "last_scene_card": {"main_scene": "药铺后间对峙试探", "chapter_hook": "对方显然知道更多"},
        }
    }

    runtime = choose_scene_sequence_for_chapter(
        story_bible=story_bible,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=[],
    )

    sequence = runtime.get("scene_sequence_plan") or []
    scene_card = runtime.get("scene_execution_card") or {}

    assert len(sequence) >= 2
    assert sequence[0]["scene_template_id"] == "same_scene_continuation"
    assert scene_card.get("must_continue_same_scene") is True


def test_build_scene_handoff_card_marks_open_scene_and_candidates() -> None:
    story_bible = {"template_library": {"scene_templates": build_scene_templates(), "roadmap": {}}}
    plan = {
        "main_scene": "药铺后间继续试探掌柜",
        "goal": "确认掌柜背后的人",
        "conflict": "门外脚步逼近，掌柜还在拖时间",
        "ending_hook": "门外的人终于推门",
        "hook_style": "危险逼近",
        "event_type": "调查类",
        "progress_kind": "信息推进",
        "payoff_mode": "明确兑现",
        "supporting_character_focus": "药铺掌柜",
    }
    scene_runtime = {
        "scene_execution_card": {"must_continue_same_scene": True, "opening_anchor": "门外的脚步声忽然停在门槛前。"},
        "scene_sequence_plan": [
            {"scene_no": 1, "scene_template_id": "same_scene_continuation", "scene_name": "同场景续接场", "scene_role": "opening"},
            {"scene_no": 2, "scene_template_id": "hanging_pressure", "scene_name": "压力悬停场", "scene_role": "ending", "must_carry_over": ["异常药包"]},
        ],
    }
    summary = SimpleNamespace(
        open_hooks=["门外闯入者身份未明", "掌柜还没交代药包来路"],
        new_clues=["异常药包"],
        character_updates={"药铺掌柜": "明显在拖时间"},
    )

    handoff = build_scene_handoff_card(
        story_bible=story_bible,
        plan=plan,
        scene_runtime=scene_runtime,
        summary=summary,
        content="掌柜的话还没说完，门外脚步猛地停住。下一瞬，门板被人从外面推响。",
        protagonist_name="林凡",
    )

    assert handoff["scene_status_at_end"] in {"open", "interrupted"}
    assert handoff["must_continue_same_scene"] is True
    assert handoff["allowed_transition"] == "none"
    assert any(item["scene_template_id"] == "same_scene_continuation" for item in handoff.get("next_scene_candidates") or [])


def test_choose_scene_sequence_prefers_handoff_anchor_and_time_skip() -> None:
    story_bible = {"template_library": {"scene_templates": build_scene_templates(), "roadmap": {}}}
    plan = {
        "chapter_no": 7,
        "main_scene": "回到住处盘点药包和线索",
        "goal": "消化上一章的收获并定下下一步",
        "conflict": "必须决定要不要连夜追查",
        "opening_beat": "次日清晨，主角在住处翻出昨夜带回的药包。",
        "mid_turn": "主角比对药渣，确认线索方向",
        "ending_hook": "决定连夜去找旧账簿",
        "event_type": "调查类",
        "progress_kind": "信息推进",
        "payoff_mode": "明确兑现",
        "hook_style": "更大谜团",
    }
    serialized_last = {
        "continuity_bridge": {
            "opening_anchor": "他把药包压在桌上，天色已经快亮了。",
            "scene_handoff_card": {
                "scene_status_at_end": "closed",
                "must_continue_same_scene": False,
                "allowed_transition": "time_skip",
                "next_opening_anchor": "次日清晨，桌上的药包还带着昨夜的潮气。",
                "carry_over_items": ["异常药包"],
            },
            "unresolved_action_chain": [],
            "carry_over_clues": ["异常药包"],
            "last_scene_card": {"main_scene": "药铺后间收尾", "chapter_hook": "该验证药包来路了"},
        }
    }

    runtime = choose_scene_sequence_for_chapter(
        story_bible=story_bible,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=[],
    )

    scene_card = runtime.get("scene_execution_card") or {}

    assert scene_card.get("must_continue_same_scene") is False
    assert scene_card.get("allowed_transition") == "time_skip_allowed"
    assert "次日清晨" in (scene_card.get("opening_anchor") or "")
    assert "异常药包" in (scene_card.get("must_carry_over") or [])


def test_realize_scene_continuity_plan_accepts_ai_review_override() -> None:
    story_bible = {"template_library": {"scene_templates": build_scene_templates(), "roadmap": {}}}
    plan = {
        "chapter_no": 8,
        "main_scene": "院中对峙后转去藏书阁核对旧卷",
        "goal": "先接住门前对峙，再去验证卷宗",
        "conflict": "若现在硬切场，会把刚压出来的关系变化切断",
        "opening_beat": "接着上一章院中对峙继续压下去",
        "mid_turn": "拿到一句关键判断后，再转去藏书阁确认旧卷",
        "ending_hook": "卷宗里的时间顺序对不上",
        "closing_image": "旧卷末页上的缺口和昨夜痕迹重合",
    }
    serialized_last = {
        "continuity_bridge": {
            "opening_anchor": "她指尖还按在剑鞘上，院里风声没停。",
            "unresolved_action_chain": ["院中对峙未收住"],
            "carry_over_clues": ["昨夜留下的残页"],
            "scene_handoff_card": {
                "next_opening_anchor": "她指尖还按在剑鞘上，院里风声没停。",
                "carry_over_items": ["昨夜留下的残页"],
            },
        }
    }

    runtime = realize_scene_continuity_plan(
        story_bible=story_bible,
        plan=plan,
        serialized_last=serialized_last,
        recent_summaries=[],
        scene_continuity_review={
            "must_continue_same_scene": True,
            "recommended_scene_count": 2,
            "transition_mode": "continue_same_scene",
            "allowed_transition": "resolve_then_cut",
            "opening_anchor": "她指尖还按在剑鞘上，院里风声没停。",
            "must_carry_over": ["院中对峙未收住", "昨夜留下的残页"],
            "cut_plan": [
                {
                    "cut_after_scene_no": 1,
                    "reason": "先让院中对峙拿到阶段结果，再切去查卷。",
                    "required_result": "对方先松口半句",
                    "transition_anchor": "切去藏书阁时要显式带上残页和刚得到的判断。",
                }
            ],
            "review_note": "这一章先续场再切场，读感会更顺。",
        },
    )

    scene_card = runtime.get("scene_execution_card") or {}
    continuity_index = runtime.get("scene_continuity_index") or {}

    assert scene_card.get("scene_count") == 2
    assert scene_card.get("must_continue_same_scene") is True
    assert scene_card.get("allowed_transition") == "resolve_then_cut"
    assert scene_card.get("planning_basis") == "scene_continuity_ai_only"
    assert continuity_index.get("cut_plan")[0]["cut_after_scene_no"] == 1
    assert continuity_index.get("ai_review", {}).get("review_note")
