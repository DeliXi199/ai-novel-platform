from app.services.openai_story_engine import ChapterPlan
from app.services.prompt_templates import arc_outline_user_prompt, _chapter_body_plan_summary


def test_chapter_plan_accepts_new_entity_hints() -> None:
    chapter = ChapterPlan(
        chapter_no=3,
        title="黑市来客",
        goal="接住新的交换机会",
        ending_hook="乌骨会留下新的盯梢",
        new_resources=["黑纹令牌", "旧账簿"],
        new_factions=["乌骨会"],
        new_relations=[
            {
                "subject": "林凡",
                "target": "乌骨会",
                "relation_type": "互相试探",
                "status": "刚建立",
                "recent_trigger": "因为账簿交易第一次挂上关系",
            }
        ],
    )

    assert chapter.new_resources == ["黑纹令牌", "旧账簿"]
    assert chapter.new_factions == ["乌骨会"]
    assert chapter.new_relations is not None
    assert chapter.new_relations[0].subject == "林凡"
    assert chapter.new_relations[0].target == "乌骨会"


def test_arc_outline_prompt_mentions_new_entity_hint_keys() -> None:
    prompt = arc_outline_user_prompt(
        payload={"title": "测试书", "genre": "修仙"},
        story_bible={"template_library": {"flow_templates": []}, "flow_control": {"recent_flow_ids": []}},
        global_outline={"acts": []},
        recent_summaries=[],
        start_chapter=1,
        end_chapter=3,
        arc_no=1,
    )

    assert "new_resources" in prompt
    assert "new_factions" in prompt
    assert "new_relations" in prompt


def test_chapter_body_plan_summary_keeps_new_entity_hints() -> None:
    payload = _chapter_body_plan_summary(
        {
            "chapter_no": 6,
            "title": "陌生账本",
            "goal": "确认对方想拿什么",
            "new_resources": ["旧账簿"],
            "new_factions": ["乌骨会"],
            "new_relations": [{"subject": "林凡", "target": "乌骨会", "relation_type": "互相试探"}],
        }
    )

    assert payload["new_resources"] == ["旧账簿"]
    assert payload["new_factions"] == ["乌骨会"]
    assert payload["new_relations"][0]["target"] == "乌骨会"
