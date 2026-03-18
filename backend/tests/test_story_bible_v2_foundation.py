from __future__ import annotations

from app.models.novel import Novel
from app.services.story_architecture import ensure_story_architecture



def test_ensure_story_architecture_builds_v2_foundation_from_partial_story_bible() -> None:
    novel = Novel(
        title="地基测试",
        genre="金手指修仙",
        premise="主角在边城里靠一面古镜求生。",
        protagonist_name="方尘",
        style_preferences={
            "tone": "冷峻克制",
            "initial_realm": "炼气",
            "current_resources": ["残缺地图", "下品灵石"],
        },
        current_chapter_no=2,
    )
    partial_story_bible = {
        "story_bible_meta": {"schema_version": 2, "architecture": "v2_foundation"},
        "world_bible": {"factions": ["青岩帮", "散修市集"]},
        "cultivation_system": {"realms": ["炼气", "筑基"]},
        "story_domains": {
            "characters": {
                "方尘": {
                    "name": "方尘",
                    "role_type": "protagonist",
                    "camp": "主角阵营",
                    "current_strength": "炼气",
                    "current_desire": "活下去",
                    "speech_style": "说话少，留后手。",
                    "work_style": "先观察，再试探。",
                },
                "陈掌柜": {
                    "name": "陈掌柜",
                    "role_type": "supporting",
                    "camp": "散修市集",
                    "current_strength": "凡俗",
                    "current_desire": "保住药铺和账面体面。",
                    "speech_style": "笑着说话，但总在关键处套信息。",
                    "work_style": "先安抚，再观察。",
                },
            },
            "resources": {
                "残缺地图": {"name": "残缺地图", "owner": "方尘", "resource_type": "当前资源", "status": "持有中", "quantity": 1},
                "下品灵石": {"name": "下品灵石", "owner": "方尘", "resource_type": "当前资源", "status": "持有中", "quantity": 1},
            },
            "relations": {
                "方尘::陈掌柜": {
                    "relation_id": "方尘::陈掌柜",
                    "left": "方尘",
                    "right": "陈掌柜",
                    "relation_type": "与主角关系",
                    "current_level": "从互相提防变成暂时合作。",
                }
            },
            "factions": {
                "青岩帮": {"name": "青岩帮", "entity_type": "faction"},
                "散修市集": {"name": "散修市集", "entity_type": "faction"},
            },
        },
        "story_workspace": {
            "protagonist_profile": {
                "current_realm": "炼气",
                "current_goal": "先在边城站稳",
                "current_resources": ["残缺地图", "下品灵石"],
                "exposure_risk": "一旦古镜暴露就会被盯上。",
            }
        },
    }

    upgraded = ensure_story_architecture(partial_story_bible, novel)

    assert upgraded["story_bible_meta"]["schema_version"] >= 3
    assert upgraded["story_bible_meta"]["architecture"] == "story_bible_v2_foundation"
    assert upgraded["power_system"]["realm_system"]["realms"][:2] == ["炼气", "筑基"]
    assert upgraded["opening_constraints"]["opening_phase_chapter_range"] == [1, 20]
    assert upgraded["opening_constraints"]["power_system_reveal_plan"]
    assert upgraded["template_library"]["roadmap"]["flow_template_target_count"] == 20
    assert upgraded["template_library"]["roadmap"]["current_character_template_count"] >= 30
    assert upgraded["core_cast_state"]["anchored_target_count"] >= 1
    assert upgraded["core_cast_state"]["anchored_characters"]
    assert "方尘" in upgraded["story_domains"]["characters"]
    assert "陈掌柜" in upgraded["story_domains"]["characters"]
    anchored_name = upgraded["core_cast_state"]["anchored_characters"][0]["name"]
    assert anchored_name in upgraded["story_domains"]["characters"]
    assert anchored_name in upgraded["story_workspace"]["cast_cards"]
    assert "残缺地图" in upgraded["story_domains"]["resources"]
    assert "青岩帮" in upgraded["story_domains"]["factions"]
    assert upgraded["story_domains"]["relations"]["方尘::陈掌柜"]["current_level"]
    assert "character" in upgraded["entity_registry"]["by_type"]
    assert "continuity_packet_cache" in upgraded["planner_state"]
    assert "rolling_continuity_history" in upgraded["planner_state"]
    assert "resource_capability_plan_cache" in upgraded["planner_state"]
    assert "constraint_reasoning_state" in upgraded
