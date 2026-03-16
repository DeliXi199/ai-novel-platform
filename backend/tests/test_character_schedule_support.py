from __future__ import annotations

from app.services.card_indexing import apply_soft_card_ranking_to_packet
from app.services.character_schedule_support import (
    build_character_relation_schedule_guidance,
    sort_character_names_by_schedule,
    sort_relation_names_by_schedule,
    update_character_relation_schedule_after_chapter,
)


def test_schedule_guidance_marks_due_characters_and_relations() -> None:
    story_bible = {
        "story_domains": {
            "characters": {
                "方尘": {"name": "方尘", "role_type": "protagonist", "importance_tier": "核心主角", "importance_score": 100},
                "柳七": {
                    "name": "柳七",
                    "role_type": "supporting",
                    "importance_tier": "核心配角",
                    "importance_score": 86,
                    "appearance_frequency": "高频",
                    "last_onstage_chapter": 1,
                    "protagonist_relation_level": "试探合作",
                },
                "陈掌柜": {
                    "name": "陈掌柜",
                    "role_type": "supporting",
                    "importance_tier": "重要配角",
                    "importance_score": 72,
                    "appearance_frequency": "低频",
                    "last_onstage_chapter": 4,
                },
            },
            "relations": {
                "方尘::柳七": {
                    "relation_id": "方尘::柳七",
                    "subject": "方尘",
                    "target": "柳七",
                    "relation_type": "试探合作",
                    "level": "未稳固",
                    "importance_tier": "重要级",
                    "importance_score": 74,
                    "last_touched_chapter": 2,
                }
            },
        }
    }

    guidance = build_character_relation_schedule_guidance(
        story_bible,
        protagonist_name="方尘",
        chapter_no=6,
        focus_name="柳七",
        plan={"goal": "和柳七一起查清账册里的旧线索"},
    )

    assert guidance["appearance_schedule"]["due_characters"][0] == "方尘" or "柳七" in guidance["appearance_schedule"]["due_characters"]
    assert "方尘::柳七" in guidance["relationship_schedule"]["due_relations"]
    assert story_bible["story_domains"]["relations"]["方尘::柳七"]["interaction_depth"] in {"中互动", "深互动"}


def test_schedule_sort_moves_due_character_and_relation_forward() -> None:
    story_bible = {
        "story_domains": {
            "characters": {
                "方尘": {"name": "方尘", "role_type": "protagonist", "importance_tier": "核心主角", "importance_score": 100},
                "柳七": {"name": "柳七", "importance_tier": "核心配角", "importance_score": 84, "appearance_frequency": "高频", "last_onstage_chapter": 1},
                "陈掌柜": {"name": "陈掌柜", "importance_tier": "重要配角", "importance_score": 76, "appearance_frequency": "低频", "last_onstage_chapter": 5},
            },
            "relations": {
                "方尘::柳七": {"relation_id": "方尘::柳七", "subject": "方尘", "target": "柳七", "relation_type": "试探合作", "importance_tier": "重要级", "importance_score": 70, "last_touched_chapter": 1},
                "方尘::陈掌柜": {"relation_id": "方尘::陈掌柜", "subject": "方尘", "target": "陈掌柜", "relation_type": "交易", "importance_tier": "阶段级", "importance_score": 62, "last_touched_chapter": 5},
            },
        }
    }
    guidance = build_character_relation_schedule_guidance(
        story_bible,
        protagonist_name="方尘",
        chapter_no=6,
        focus_name="柳七",
        plan={"goal": "柳七和方尘继续推进旧线索"},
    )

    chars = sort_character_names_by_schedule(story_bible["story_domains"]["characters"], ["方尘", "陈掌柜", "柳七"], guidance=guidance, protagonist_name="方尘")
    rels = sort_relation_names_by_schedule(story_bible["story_domains"]["relations"], ["方尘::陈掌柜", "方尘::柳七"], guidance=guidance)

    assert chars[:2] == ["方尘", "柳七"]
    assert rels[0] == "方尘::柳七"


def test_soft_card_ranking_respects_schedule_without_hard_filtering() -> None:
    packet = {
        "selected_elements": {"focus_character": "柳七"},
        "character_relation_schedule": {
            "appearance_schedule": {"due_characters": ["柳七"], "resting_characters": ["陈掌柜"]},
            "relationship_schedule": {"due_relations": ["方尘::柳七"]},
        },
        "card_index": {
            "characters": [
                {"card_id": "C001", "title": "方尘", "summary": "主角", "tags": ["主角"], "status": "active", "importance_score": 100},
                {"card_id": "C002", "title": "陈掌柜", "summary": "掌柜", "tags": ["低频"], "status": "active", "importance_score": 80},
                {"card_id": "C003", "title": "柳七", "summary": "核心配角", "tags": ["高频"], "status": "active", "importance_score": 75},
            ],
            "resources": [],
            "factions": [],
            "relations": [
                {"card_id": "REL001", "title": "方尘-陈掌柜", "key": "方尘::陈掌柜", "summary": "交易", "tags": ["交易"], "status": "active", "importance_score": 62},
                {"card_id": "REL002", "title": "方尘-柳七", "key": "方尘::柳七", "summary": "试探合作", "tags": ["合作"], "status": "active", "importance_score": 60},
            ],
        },
    }

    ranked = apply_soft_card_ranking_to_packet(packet, chapter_plan={"goal": "柳七和方尘继续推进旧线索"})

    ordered_character_ids = [item["card_id"] for item in ranked["card_index"]["characters"]]
    assert ordered_character_ids.index("C003") < ordered_character_ids.index("C002")
    assert ranked["card_index"]["relations"][0]["card_id"] == "REL002"
    assert len(ranked["card_index"]["characters"]) == 3


def test_update_character_relation_schedule_after_chapter_records_history() -> None:
    story_bible = {
        "story_domains": {
            "characters": {
                "方尘": {"name": "方尘"},
                "柳七": {"name": "柳七"},
            },
            "relations": {
                "方尘::柳七": {"relation_id": "方尘::柳七", "subject": "方尘", "target": "柳七"}
            },
        }
    }

    update_character_relation_schedule_after_chapter(
        story_bible,
        chapter_no=3,
        onstage_characters=["方尘", "柳七"],
        focus_name="柳七",
        plan={"new_relations": [{"subject": "方尘", "target": "柳七"}]},
    )

    assert story_bible["story_domains"]["characters"]["柳七"]["last_onstage_chapter"] == 3
    assert story_bible["story_domains"]["relations"]["方尘::柳七"]["last_touched_chapter"] == 3
