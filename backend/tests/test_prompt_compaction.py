from app.services.prompt_support import compact_data, compact_json, soft_sort_prompt_sections, summarize_story_bible
from app.services.prompt_templates import chapter_draft_user_prompt, global_outline_user_prompt


def test_compact_data_clips_large_nested_payload() -> None:
    payload = {
        "alpha": "x" * 400,
        "beta": [{"note": "y" * 300, "extra": "z" * 300} for _ in range(10)],
        "gamma": {f"k{i}": i for i in range(20)},
    }
    compacted = compact_data(payload, max_depth=2, max_items=3, text_limit=40)

    assert len(compacted["alpha"]) <= 40
    assert len(compacted["beta"]) <= 4
    assert "_omitted_keys" in compacted or "_omitted_items" in compacted["beta"][-1]


def test_global_outline_prompt_uses_compact_story_bible_snapshot() -> None:
    story_bible = {
        "story_engine_diagnosis": {"primary_story_engine": "低位求生 + 资源争取 + 谨慎试探"},
        "story_strategy_card": {"story_promise": "慢热但章章有结果"},
        "story_domains": {
            "characters": {f"角色{i}": {"bio": "甲" * 300} for i in range(20)},
            "resources": {f"资源{i}": {"detail": "乙" * 300} for i in range(20)},
            "factions": {f"势力{i}": {"detail": "丙" * 300} for i in range(20)},
            "relations": [{"detail": "丁" * 300} for _ in range(20)],
        },
    }
    prompt = global_outline_user_prompt({"genre": "修仙"}, story_bible, total_acts=4)

    assert "character_count" in prompt
    assert "resource_count" in prompt
    assert "甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲" not in prompt


def test_chapter_draft_prompt_keeps_rules_but_clips_huge_context() -> None:
    huge = "设定" * 600
    prompt = chapter_draft_user_prompt(
        novel_context={
            "project_card": {"genre_positioning": "修仙", "protagonist": {"name": "方尘"}},
            "story_memory": {
                "execution_brief": {"long_note": huge},
                "hard_fact_guard": {"rules": huge},
            },
        },
        chapter_plan={
            "title": "第四章",
            "hook_style": "信息反转",
            "planning_packet": {"relevant_cards": {"characters": {"方尘": {"note": huge}}}},
        },
        last_chapter={"continuity_bridge": {"opening_anchor": "院门没有关死。"}},
        recent_summaries=[],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2800,
    )

    assert "主角不能只被动应对" in prompt
    assert "【轻量小说记忆】" in prompt
    assert len(prompt) < 9000
    assert huge[:200] not in prompt


def test_soft_sort_prompt_sections_reorders_without_dropping_sections() -> None:
    sections = [
        {"title": "最近章节摘要", "body": "A", "tags": ["最近摘要"], "stages": ["chapter_draft_full"], "priority": "medium"},
        {"title": "本章拍表", "body": "B", "tags": ["计划", "流程"], "stages": ["chapter_draft_full"], "priority": "must"},
        {"title": "当前生效的读者干预", "body": "C", "tags": ["干预"], "stages": ["chapter_draft_full"], "priority": "low"},
    ]

    ranked = soft_sort_prompt_sections(sections, stage="chapter_draft_full", context={"goal": "按计划推进", "flow": "流程"})

    assert [item["title"] for item in ranked] == ["本章拍表", "最近章节摘要", "当前生效的读者干预"]
    assert len(ranked) == 3
    assert ranked[0]["soft_sort_score"] >= ranked[-1]["soft_sort_score"]
