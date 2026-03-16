from __future__ import annotations

from app.services.core_cast_support import (
    bind_character_to_core_slot,
    build_core_cast_state,
    core_cast_guidance_for_chapter,
    materialize_anchored_core_cast,
    summarize_core_cast_state,
    update_core_cast_after_chapter,
)
from app.services.prompt_support import summarize_story_bible


def test_build_core_cast_state_varies_count_by_background() -> None:
    payload = {
        "genre": "宗门修仙",
        "premise": "主角进入宗门后在同门竞争和势力夹缝中求生。",
        "protagonist_name": "陆沉",
        "style_preferences": {"factions": ["外门", "内门", "执法堂", "世家", "黑市"]},
    }

    state = build_core_cast_state(payload)

    assert state["profile"] in {"group", "multi_faction"}
    assert 5 <= state["target_count"] <= 9
    assert len(state["slots"]) == state["target_count"]
    assert state["anchored_target_count"] in {1, 2}
    assert len(state["anchored_characters"]) == state["anchored_target_count"]
    assert all(slot["entry_chapter_window"][0] <= slot["entry_chapter_window"][1] for slot in state["slots"])


def test_bind_character_to_core_slot_sets_long_term_plan_on_card() -> None:
    story_bible = {
        "core_cast_state": build_core_cast_state(
            {
                "genre": "凡人求生修仙",
                "premise": "主角在边城靠残破机缘苟活。",
                "protagonist_name": "方尘",
                "style_preferences": {},
            }
        ),
        "story_domains": {
            "characters": {
                "方尘": {"name": "方尘", "role_type": "protagonist"},
                "陈掌柜": {"name": "陈掌柜", "role_type": "supporting", "importance_tier": "重要配角", "narrative_priority": 72},
            }
        },
        "control_console": {"character_cards": {"陈掌柜": {"name": "陈掌柜", "role_type": "supporting"}}},
    }

    slot_id = bind_character_to_core_slot(
        story_bible,
        character_name="陈掌柜",
        chapter_no=2,
        note="资源线上的互助角色",
        protagonist_name="方尘",
    )

    card = story_bible["story_domains"]["characters"]["陈掌柜"]
    assert slot_id
    assert card["core_cast_slot_id"] == slot_id
    assert card["entry_phase"]
    assert card["long_term_relation_line"]
    assert card["appearance_frequency"] in {"高频", "中频", "低频"}


def test_core_cast_guidance_tracks_due_slots_and_active_characters() -> None:
    state = build_core_cast_state(
        {
            "genre": "凡人求生修仙",
            "premise": "主角在边城靠残破机缘苟活。",
            "protagonist_name": "方尘",
            "style_preferences": {},
        }
    )
    story_bible = {
        "core_cast_state": state,
        "story_domains": {"characters": {"柳七": {"name": "柳七", "role_type": "supporting", "narrative_priority": 72}}},
        "control_console": {"character_cards": {"柳七": {"name": "柳七", "role_type": "supporting"}}},
    }
    bind_character_to_core_slot(story_bible, character_name="柳七", chapter_no=2, protagonist_name="方尘")
    update_core_cast_after_chapter(story_bible, chapter_no=3, onstage_characters=["方尘", "柳七"])

    guidance = core_cast_guidance_for_chapter(story_bible, chapter_no=4, focus_name="柳七")
    summary = summarize_story_bible(story_bible)

    assert guidance["active_core_characters"]
    assert guidance["active_core_characters"][0]["character"] == "柳七"
    assert "core_cast_state" in summary
    assert summary["core_cast_state"]["target_count"] == state["target_count"]
    assert summarize_core_cast_state(story_bible["core_cast_state"], chapter_no=4)["slots"]


def test_materialized_anchored_core_cast_prefers_reserved_slot_when_bound() -> None:
    state = build_core_cast_state(
        {
            "genre": "宗门修仙",
            "premise": "主角在外门和黑市之间求活。",
            "protagonist_name": "陆沉",
            "style_preferences": {"factions": ["外门", "执法堂", "黑市", "丹房", "世家"]},
        }
    )
    story_bible = {
        "core_cast_state": state,
        "story_domains": {"characters": {"陆沉": {"name": "陆沉", "role_type": "protagonist"}}},
        "control_console": {"character_cards": {"陆沉": {"name": "陆沉", "role_type": "protagonist"}}},
        "template_library": {"character_templates": []},
    }

    created = materialize_anchored_core_cast(story_bible, protagonist_name="陆沉")

    assert created
    reserved_name = state["anchored_characters"][0]["name"]
    reserved_slot_id = state["anchored_characters"][0]["slot_id"]
    assert reserved_name in story_bible["story_domains"]["characters"]
    assert story_bible["story_domains"]["characters"][reserved_name]["core_cast_anchor"] is True

    bound_slot_id = bind_character_to_core_slot(
        story_bible,
        character_name=reserved_name,
        chapter_no=3,
        note="该人物进入主线并和主角形成长期拉扯。",
        protagonist_name="陆沉",
    )

    assert bound_slot_id == reserved_slot_id
    assert story_bible["story_domains"]["characters"][reserved_name]["core_cast_slot_id"] == reserved_slot_id
