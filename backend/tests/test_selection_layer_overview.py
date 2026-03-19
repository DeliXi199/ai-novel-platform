from app.services import openai_story_engine_selection as selection_engine


def test_selection_layer_overview_exposes_raw_shortlist_and_focused_counts():
    packet = {
        "payoff_candidate_index": {
            "candidates": [
                {"card_id": "p1", "name": "回手一击", "family": "反压"},
                {"card_id": "p2", "name": "暗里落子", "family": "暗手"},
                {"card_id": "p3", "name": "当众重估", "family": "反压"},
            ]
        },
        "foreshadowing_candidate_index": {
            "parent_cards": [
                {"card_id": "parent_secret", "name": "宗门旧案"},
                {"card_id": "parent_body", "name": "体质隐线"},
            ],
            "child_cards": [
                {"child_id": "child_map", "parent_id": "parent_secret", "name": "残缺阵图"},
                {"child_id": "child_elder", "parent_id": "parent_secret", "name": "失踪长老"},
                {"child_id": "child_body", "parent_id": "parent_body", "name": "灵体异动"},
            ],
            "candidates": [
                {"candidate_id": "plant::阵图", "parent_card_id": "parent_secret", "child_card_id": "child_map", "source_hook": "阵图"},
                {"candidate_id": "touch::旧案", "parent_card_id": "parent_secret", "child_card_id": "child_elder", "source_hook": "旧案"},
                {"candidate_id": "plant::灵体", "parent_card_id": "parent_body", "child_card_id": "child_body", "source_hook": "灵体"},
            ],
        },
    }
    shortlist = {
        "payoff_candidate_ids": ["p1", "p3"],
        "foreshadowing_parent_card_ids": ["parent_secret"],
        "foreshadowing_child_card_ids": ["child_map"],
        "foreshadowing_candidate_ids": ["plant::阵图"],
    }

    overview = selection_engine._selection_layer_overview(packet, shortlist)

    assert overview["payoff"]["family_layer"]["raw_count"] == 2
    assert overview["payoff"]["candidate_layer"]["raw_count"] == 3
    assert overview["payoff"]["candidate_layer"]["shortlist_count"] == 2
    assert overview["payoff"]["candidate_layer"]["focused_count"] == 2

    assert overview["foreshadowing"]["parent_layer"]["raw_count"] == 2
    assert overview["foreshadowing"]["parent_layer"]["shortlist_count"] == 1
    assert overview["foreshadowing"]["parent_layer"]["focused_count"] == 1
    assert overview["foreshadowing"]["child_layer"]["raw_count"] == 3
    assert overview["foreshadowing"]["child_layer"]["shortlist_count"] == 1
    assert overview["foreshadowing"]["candidate_layer"]["raw_count"] == 3
    assert overview["foreshadowing"]["candidate_layer"]["shortlist_count"] == 1
    assert overview["foreshadowing"]["candidate_layer"]["focused_count"] == 1
    assert overview["foreshadowing"]["candidate_layer"]["focused_preview"][0].startswith("plant::阵图")


def test_foreshadowing_focus_path_prefers_candidate_shortlist_over_parent_expansion():
    packet = {
        "foreshadowing_candidate_index": {
            "parent_cards": [
                {"card_id": "parent_secret", "name": "宗门旧案"},
            ],
            "child_cards": [
                {"child_id": "child_map", "parent_id": "parent_secret", "name": "残缺阵图"},
                {"child_id": "child_elder", "parent_id": "parent_secret", "name": "失踪长老"},
            ],
            "candidates": [
                {"candidate_id": "plant::阵图", "parent_card_id": "parent_secret", "child_card_id": "child_map", "source_hook": "阵图"},
                {"candidate_id": "touch::旧案", "parent_card_id": "parent_secret", "child_card_id": "child_elder", "source_hook": "旧案"},
            ],
        },
    }
    shortlist = {
        "foreshadowing_parent_card_ids": ["parent_secret"],
        "foreshadowing_child_card_ids": ["child_map"],
        "foreshadowing_candidate_ids": ["plant::阵图"],
    }

    focused = selection_engine._focused_foreshadowing_candidate_index(packet, shortlist)

    assert [row["candidate_id"] for row in focused["candidates"]] == ["plant::阵图"]
    assert focused["focus_path"]["candidate_filter_mode"] == "shortlist_candidate_ids"
    assert focused["focus_path"]["single_parent_locked"] is True
    assert focused["focus_path"]["single_child_locked"] is True
