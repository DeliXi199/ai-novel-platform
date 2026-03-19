from app.services.foreshadowing_cards import (
    build_foreshadowing_candidate_index,
    realize_foreshadowing_selection_from_index,
)


def test_build_foreshadowing_candidate_index_contains_open_and_plant_candidates():
    story_bible = {
        "story_workspace": {
            "foreshadowing": [
                {
                    "name": "资格条件没说全",
                    "introduced_in_chapter": 8,
                    "surface_info": "资格条件没说全",
                    "status": "open",
                }
            ]
        }
    }
    plan = {
        "chapter_no": 11,
        "goal": "追查资格争夺规则",
        "conflict": "宁烬棠仍有隐瞒",
        "ending_hook": "资格线背后另有旧账",
    }
    index = build_foreshadowing_candidate_index(story_bible=story_bible, plan=plan, recent_summaries=[])
    candidate_ids = [item["candidate_id"] for item in index["candidates"]]
    legacy_ids = [item.get("legacy_candidate_id") for item in index["candidates"]]
    assert candidate_ids == [f"fcand_{i:03d}" for i in range(1, len(candidate_ids) + 1)]
    assert all(item.get("selector_key", "").startswith("foreshadow_") for item in index["candidates"])
    assert any(str(item).startswith("touch::") for item in legacy_ids)
    assert any(str(item).startswith("resolve::") for item in legacy_ids)
    assert any(str(item).startswith("plant::") for item in legacy_ids)
    assert index["diagnostics"]["compression_mode"] == "compact_foreshadowing_index"


def test_realize_foreshadowing_selection_from_index_builds_instance_cards():
    candidate_index = {
        "diagnostics": {"chapter_no": 12},
        "candidates": [
            {
                "candidate_id": "touch::a",
                "action_type": "touch",
                "parent_card_id": "f_parent_information_gap",
                "parent_card_name": "信息缺口型",
                "child_card_id": "f_child_info_gap_half_truth",
                "child_card_name": "给半真消息，不给完整答案",
                "source_hook": "宁烬棠没把条件说全",
                "opening_move": "先让主角听到半句",
                "mid_shift": "中段确认确有缺口",
                "ending_drop": "结尾逼出下一步验证",
                "avoid": "不要一次讲穿",
            },
            {
                "candidate_id": "plant::b",
                "action_type": "plant",
                "parent_card_id": "f_parent_hidden_scheme",
                "parent_card_name": "幕后筹谋型",
                "child_card_id": "f_child_hidden_scheme_fragment",
                "child_card_name": "碎片化暗示幕后联动",
                "source_hook": "有人提前动过名单",
                "opening_move": "先出现旧线索照应",
                "mid_shift": "中段意识到并非偶然",
                "ending_drop": "只留有人提前布置过",
                "avoid": "不要直接点主谋",
            },
        ],
    }
    runtime = realize_foreshadowing_selection_from_index(
        story_bible={},
        plan={"chapter_no": 12},
        foreshadowing_candidate_index=candidate_index,
        selected_primary_candidate_id="touch::a",
        selected_supporting_candidate_ids=["plant::b"],
        selection_note="本章先碰旧缺口，再埋一条幕后新线。",
    )
    assert runtime["selected_primary_candidate"]["candidate_id"] == "touch::a"
    assert len(runtime["selected_instance_cards"]) == 2
    assert runtime["selected_instance_cards"][0]["priority"] == "primary"
