from app.services.novel_bootstrap import build_base_story_bible
from app.services.prompt_templates import (
    arc_outline_user_prompt,
    chapter_draft_user_prompt,
    chapter_extension_user_prompt,
    global_outline_user_prompt,
)
from app.schemas.novel import NovelCreate



def _payload() -> NovelCreate:
    return NovelCreate(
        genre="金手指修仙",
        premise="主角得到一件会成长的古镜，从边城一路成长到宗门核心。",
        protagonist_name="林凡",
        style_preferences={"tone": "成长爽感中带代价", "story_engine": "前期较早兑现机缘，但要写清副作用与竞争"},
    )



def test_outline_prompts_are_not_hardcoded_to_residual_page_opening() -> None:
    payload = _payload().model_dump(mode="python")
    prompt = global_outline_user_prompt(payload, {"genre": payload["genre"]}, total_acts=4)
    arc_prompt = arc_outline_user_prompt(
        payload=payload,
        story_bible={"genre": payload["genre"]},
        global_outline={"acts": []},
        recent_summaries=[],
        start_chapter=1,
        end_chapter=3,
        arc_no=1,
    )
    assert "药铺后的旧纸页" not in prompt
    assert "药铺后的旧纸页" not in arc_prompt
    assert "主角想试探残页" not in arc_prompt
    assert "前期较早兑现机缘" in prompt



def test_story_bible_and_chapter_prompt_use_actual_protagonist_and_genre_guidance() -> None:
    payload = _payload()
    story_bible = build_base_story_bible(payload)
    assert story_bible["protagonist_emotion_rules"][0].startswith("林凡")
    assert "机缘兑现" in story_bible["pacing_rules"]["overall"]

    prompt = chapter_draft_user_prompt(
        novel_context={
            "project_card": {
                "genre_positioning": payload.genre,
                "protagonist": {"name": payload.protagonist_name},
            }
        },
        chapter_plan={"title": "第一章", "hook_style": "信息反转"},
        last_chapter={
            "continuity_bridge": {
                "last_two_paragraphs": ["林凡收起古镜，指节还微微发凉。"],
                "last_scene_card": {"main_scene": "药铺后院", "chapter_hook": "墙外忽然传来脚步声"},
                "unresolved_action_chain": ["墙外脚步声逼近"],
            }
        },
        recent_summaries=[],
        active_interventions=[],
        target_words=2500,
        target_visible_chars_min=1800,
        target_visible_chars_max=3200,
    )
    assert "林凡的情绪" in prompt
    assert "金手指修仙" in prompt or "机缘兑现" in prompt
    assert "不要自行把剧情锁定成“药铺-掌柜-残页-坊市-夜探”这一固定组合" in prompt



def test_chapter_prompt_includes_strong_continuity_bridge_rules() -> None:
    prompt = chapter_draft_user_prompt(
        novel_context={"project_card": {"genre_positioning": "修仙", "protagonist": {"name": "林玄"}}},
        chapter_plan={"title": "第二章", "hook_style": "危险逼近"},
        last_chapter={
            "continuity_bridge": {
                "last_two_paragraphs": ["门外脚步声停在了屋檐下。"],
                "last_scene_card": {"main_scene": "破庙夜谈", "chapter_hook": "门外脚步声更近了"},
                "unresolved_action_chain": ["门外脚步声更近了"],
                "onstage_characters": ["林玄", "老周"],
            }
        },
        recent_summaries=[],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
    )
    assert "continuity_bridge / last_two_paragraphs / last_scene_card" in prompt
    assert "开头两段必须优先承接它的 opening_anchor / last_two_paragraphs / unresolved_action_chain" in prompt
    assert "hard_fact_guard" in prompt
    assert "境界、生死、伤势、身份暴露和关键物件归属" in prompt



def test_arc_outline_prompt_requires_variety_and_proactive_move() -> None:
    payload = _payload().model_dump(mode="python")
    prompt = arc_outline_user_prompt(
        payload=payload,
        story_bible={"genre": payload["genre"]},
        global_outline={"acts": []},
        recent_summaries=[],
        start_chapter=4,
        end_chapter=6,
        arc_no=2,
    )
    assert "event_type" in prompt
    assert "proactive_move" in prompt
    assert "连续三章都在“被怀疑—应付—隐藏”" in prompt


def test_chapter_prompt_includes_effective_progress_and_agency_constraints() -> None:
    prompt = chapter_draft_user_prompt(
        novel_context={"project_card": {"genre_positioning": "修仙", "protagonist": {"name": "方尘"}}},
        chapter_plan={"title": "第三章", "hook_style": "信息反转"},
        last_chapter={"continuity_bridge": {"opening_anchor": "门外脚步声停在檐下。"}},
        recent_summaries=[],
        active_interventions=[],
        target_words=2500,
        target_visible_chars_min=1800,
        target_visible_chars_max=3000,
    )
    assert "主角不能只被动应对" in prompt
    assert "前两段内必须让主角先做一个可见动作或判断" in prompt
    assert "主角先手 -> 外界反应 -> 主角顺势调整或加码" in prompt
    assert "【本章推进结果】" in prompt
    assert "禁止只写气氛、顾虑、怀疑、压迫感或回忆，而不把结果落地" in prompt
    assert "本章必须有明确推进" in prompt
    assert "禁止用“回去休息了/暂时压下念头/明日再看/夜色沉沉事情暂告一段落”这类平钩子收尾" in prompt


def test_chapter_prompt_includes_agency_mode_block_when_plan_has_mode() -> None:
    prompt = chapter_draft_user_prompt(
        novel_context={"project_card": {"genre_positioning": "修仙", "protagonist": {"name": "方尘"}}},
        chapter_plan={
            "title": "第四章",
            "hook_style": "信息反转",
            "agency_mode": "strategic_setup",
            "agency_mode_label": "谋划设局型",
            "agency_style_summary": "主角表面克制，实际通过误导和留钩控制信息差。",
            "agency_opening_instruction": "开场让主角先藏一步，再顺势诱导对方先暴露。",
            "agency_mid_instruction": "受阻后要继续借势，不要退回纯观察位。",
            "agency_avoid": ["只有分析没有布置", "把克制写成纯站桩"],
        },
        last_chapter={"continuity_bridge": {"opening_anchor": "院门没有关死。"}},
        recent_summaries=[],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2800,
    )
    assert "【本章主动方式】" in prompt
    assert "谋划设局型" in prompt
    assert "主动性的定义：不是更频繁地猛冲" in prompt
    assert "只有分析没有布置" in prompt



def test_chapter_extension_prompt_only_includes_tail_excerpt_not_full_text() -> None:
    existing = "前文" * 700 + "\n\n" + "尾段" * 80
    prompt = chapter_extension_user_prompt(
        chapter_plan={"title": "第五章", "hook_style": "危险逼近"},
        existing_content=existing,
        reason="补齐截断结尾并自然收束",
        target_visible_chars_min=1600,
        target_visible_chars_max=2400,
    )
    assert "【全文长度】" in prompt
    assert "【已有正文结尾片段】" in prompt
    assert "前文前文前文前文前文前文前文前文前文前文" not in prompt
    assert "尾段尾段尾段" in prompt
