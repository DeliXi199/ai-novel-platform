from app.services.novel_bootstrap import build_base_story_bible
from app.services.prompt_templates import (
    arc_outline_user_prompt,
    chapter_draft_user_prompt,
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
        last_chapter={},
        recent_summaries=[],
        active_interventions=[],
        target_words=2500,
        target_visible_chars_min=1800,
        target_visible_chars_max=3200,
    )
    assert "林凡的情绪" in prompt
    assert "金手指修仙" in prompt or "机缘兑现" in prompt
    assert "不要自行把剧情锁定成“药铺-掌柜-残页-坊市-夜探”这一固定组合" in prompt
