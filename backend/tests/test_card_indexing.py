from __future__ import annotations

from app.services.card_indexing import apply_card_selection_to_packet, apply_soft_card_ranking_to_packet, build_card_index_payload
from app.services.openai_story_engine import choose_chapter_card_selection
from app.services.prompt_templates import _chapter_body_plan_packet_summary


def test_card_index_payload_builds_short_entries() -> None:
    relevant_cards = {
        "characters": {
            "林凡": {
                "card_id": "C001",
                "name": "林凡",
                "role_type": "protagonist",
                "importance_tier": "核心主角",
                "relation_level": "self",
                "current_goal": "查清账簿里的旧线索",
                "small_tell": "说到关键时会停半拍",
                "importance_score": 100,
            }
        },
        "resources": {
            "旧账簿": {
                "card_id": "R001",
                "name": "旧账簿",
                "display_name": "旧账簿",
                "resource_type": "账簿",
                "status": "planned",
                "ability_summary": "可对照出旧势力资金往来",
                "importance_score": 72,
            }
        },
        "factions": {},
        "relations": [
            {
                "card_id": "REL001",
                "relation_id": "林凡::乌骨会",
                "subject": "林凡",
                "target": "乌骨会",
                "relation_type": "互相试探",
                "status": "刚建立",
                "importance_score": 61,
            }
        ],
    }

    payload = build_card_index_payload(relevant_cards)

    assert payload["characters"][0]["card_id"] == "C001"
    assert payload["characters"][0]["title"] == "林凡"
    assert payload["resources"][0]["card_id"] == "R001"
    assert payload["relations"][0]["card_id"] == "REL001"
    assert len(payload["characters"][0]["summary"]) <= 48


def test_apply_card_selection_keeps_only_selected_full_cards() -> None:
    packet = {
        "selected_elements": {
            "characters": ["林凡", "林秋雨"],
            "focus_character": "林秋雨",
            "resources": ["旧账簿", "黑纹令牌"],
            "factions": [],
            "relations": ["林凡::林秋雨"],
        },
        "relevant_cards": {
            "characters": {
                "林凡": {"card_id": "C001", "name": "林凡"},
                "林秋雨": {"card_id": "C002", "name": "林秋雨"},
            },
            "resources": {
                "旧账簿": {"card_id": "R001", "name": "旧账簿"},
                "黑纹令牌": {"card_id": "R002", "name": "黑纹令牌"},
            },
            "factions": {},
            "relations": [{"card_id": "REL001", "relation_id": "林凡::林秋雨", "subject": "林凡", "target": "林秋雨"}],
        },
    }

    updated = apply_card_selection_to_packet(packet, ["C002", "R001"], selection_note="只保留本章真会动到的卡。")

    assert list(updated["relevant_cards"]["characters"].keys()) == ["林秋雨"]
    assert list(updated["relevant_cards"]["resources"].keys()) == ["旧账簿"]
    assert updated["relevant_cards"]["relations"] == []
    assert updated["card_selection"]["selected_card_ids"] == ["C002", "R001"]


def test_choose_chapter_card_selection_heuristic_picks_focus_and_new_resource() -> None:
    planning_packet = {
        "selected_elements": {"focus_character": "林秋雨"},
        "card_index": {
            "characters": [
                {"card_id": "C001", "title": "林凡", "summary": "主角，谨慎，查线索", "tags": ["主角", "谨慎"], "status": "active", "importance_score": 100},
                {"card_id": "C002", "title": "林秋雨", "summary": "药师少女，对主角仍在试探合作", "tags": ["药师", "试探"], "status": "active", "importance_score": 82},
            ],
            "resources": [
                {"card_id": "R001", "title": "旧账簿", "summary": "账簿，能查旧线索，planned", "tags": ["账簿", "线索"], "status": "planned", "importance_score": 70},
                {"card_id": "R002", "title": "黑纹令牌", "summary": "令牌，暂时不会动到", "tags": ["令牌"], "status": "active", "importance_score": 50},
            ],
            "factions": [],
            "relations": [],
        },
    }
    chapter_plan = {
        "title": "陌生账本",
        "goal": "和林秋雨一起查看旧账簿，确认旧线索",
        "conflict": "两人还在互相提防",
        "supporting_character_focus": "林秋雨",
        "new_resources": ["旧账簿"],
    }

    payload = choose_chapter_card_selection(chapter_plan=chapter_plan, planning_packet=planning_packet, request_timeout_seconds=1)

    assert "C001" in payload.selected_card_ids
    assert "C002" in payload.selected_card_ids
    assert "R001" in payload.selected_card_ids


def test_plan_packet_summary_keeps_card_index_and_selection() -> None:
    summary = _chapter_body_plan_packet_summary(
        {
            "planning_packet": {
                "card_index": {"characters": [{"card_id": "C001", "title": "林凡"}]},
                "card_selection": {"selected_card_ids": ["C001"], "selection_note": "主角卡必留。"},
                "relevant_cards": {"characters": {"林凡": {"card_id": "C001", "name": "林凡"}}},
            }
        }
    )

    assert summary["card_index"]["characters"][0]["card_id"] == "C001"
    assert summary["card_selection"]["selected_card_ids"] == ["C001"]


def test_soft_card_ranking_keeps_all_candidates_but_moves_relevant_ones_forward() -> None:
    packet = {
        "selected_elements": {"focus_character": "林秋雨"},
        "card_index": {
            "characters": [
                {"card_id": "C001", "title": "林凡", "entity_type": "character", "summary": "主角，谨慎，查线索", "tags": ["主角", "谨慎"], "status": "active", "importance_score": 100},
                {"card_id": "C002", "title": "林秋雨", "entity_type": "character", "summary": "药师少女，对主角仍在试探合作", "tags": ["药师", "试探合作"], "status": "active", "importance_score": 72},
            ],
            "resources": [
                {"card_id": "R002", "title": "黑纹令牌", "entity_type": "resource", "summary": "令牌，暂时不会动到", "tags": ["令牌"], "status": "active", "importance_score": 60},
                {"card_id": "R001", "title": "旧账簿", "entity_type": "resource", "summary": "账簿，能查旧线索，planned", "tags": ["账簿", "线索"], "status": "planned", "importance_score": 55},
            ],
            "factions": [],
            "relations": [],
        },
    }
    chapter_plan = {
        "goal": "和林秋雨一起查看旧账簿，确认旧线索",
        "supporting_character_focus": "林秋雨",
        "new_resources": ["旧账簿"],
    }

    ranked = apply_soft_card_ranking_to_packet(packet, chapter_plan=chapter_plan)

    assert [item["card_id"] for item in ranked["card_index"]["characters"]] == ["C002", "C001"]
    assert [item["card_id"] for item in ranked["card_index"]["resources"]] == ["R001", "R002"]
    assert len(ranked["card_index"]["resources"]) == 2
    assert ranked["card_index"]["resources"][0]["soft_priority"] in {"high", "medium"}
    assert "card_soft_sort_rule" in ranked["input_policy"]


def test_soft_card_ranking_reads_importance_activation_and_exploration_scores() -> None:
    packet = {
        "selected_elements": {"focus_character": "林秋雨"},
        "importance_runtime": {"selection_lanes": {"characters": {"selected_by_lane": {"activation": ["林秋雨"], "exploration": ["赵六"]}}}},
        "card_index": {
            "characters": [
                {"card_id": "C001", "title": "林凡", "entity_type": "character", "summary": "主角，谨慎，查线索", "tags": ["主角"], "status": "active", "importance_score": 100, "importance_mainline_rank_score": 120, "importance_activation_rank_score": 80, "importance_exploration_score": 20},
                {"card_id": "C002", "title": "林秋雨", "entity_type": "character", "summary": "药师少女，对主角仍在试探合作", "tags": ["药师", "试探合作"], "status": "active", "importance_score": 72, "importance_mainline_rank_score": 92, "importance_activation_rank_score": 118, "importance_exploration_score": 45},
                {"card_id": "C003", "title": "赵六", "entity_type": "character", "summary": "低频地头蛇，知道边城黑巷的旧门路", "tags": ["地头蛇", "黑巷"], "status": "planned", "importance_score": 48, "importance_mainline_rank_score": 58, "importance_activation_rank_score": 66, "importance_exploration_score": 88},
            ],
            "resources": [],
            "factions": [],
            "relations": [],
        },
    }
    chapter_plan = {
        "goal": "和林秋雨一起查看旧账簿，再顺手摸一摸黑巷的路数",
        "supporting_character_focus": "林秋雨",
    }

    ranked = apply_soft_card_ranking_to_packet(packet, chapter_plan=chapter_plan)
    assert ranked["card_index"]["characters"][0]["card_id"] == "C002"
    assert ranked["card_index"]["characters"][1]["card_id"] == "C001"
    assert ranked["card_index"]["characters"][2]["card_id"] == "C003"
