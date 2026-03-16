from __future__ import annotations

from app.models.novel import Novel
from app.services.story_architecture import ensure_story_architecture



def test_ensure_story_architecture_upgrades_legacy_story_bible_to_v2_foundation() -> None:
    novel = Novel(
        title="旧档测试",
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
    legacy_story_bible = {
        "story_bible_meta": {"schema_version": 1, "architecture": "legacy"},
        "world_bible": {"factions": ["青岩帮", "散修市集"]},
        "cultivation_system": {"realms": ["炼气", "筑基"]},
        "control_console": {
            "protagonist_state": {
                "current_realm": "炼气",
                "current_goal": "先在边城站稳",
                "current_resources": ["残缺地图", "下品灵石"],
                "exposure_risk": "一旦古镜暴露就会被盯上。",
            },
            "character_cards": {
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
            "relation_tracks": [
                {"subject": "方尘", "target": "陈掌柜", "chapter_no": 2, "change": "从互相提防变成暂时合作。"}
            ],
        },
    }

    upgraded = ensure_story_architecture(legacy_story_bible, novel)

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
    assert anchored_name in upgraded["control_console"]["character_cards"]
    assert "残缺地图" in upgraded["story_domains"]["resources"]
    assert "青岩帮" in upgraded["story_domains"]["factions"]
    assert "方尘::陈掌柜" in upgraded["story_domains"]["relations"]
    assert "character" in upgraded["entity_registry"]["by_type"]
    assert "continuity_packet_cache" in upgraded["planner_state"]
    assert "rolling_continuity_history" in upgraded["planner_state"]
    assert "resource_capability_plan_cache" in upgraded["planner_state"]
    assert "constraint_reasoning_state" in upgraded
