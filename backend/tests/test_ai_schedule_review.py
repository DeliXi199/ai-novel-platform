from app.services.card_indexing import soft_sort_card_index_payload
from app.services.openai_story_engine import (
    CharacterRelationScheduleReviewPayload,
    _heuristic_character_relation_schedule_review,
    apply_schedule_review_to_packet,
)


def _planning_packet() -> dict:
    return {
        "selected_elements": {
            "characters": ["陈砚", "林秋雨", "周执事", "沈三"],
            "focus_character": "林秋雨",
        },
        "character_relation_schedule": {
            "appearance_schedule": {
                "due_characters": ["陈砚", "林秋雨", "周执事"],
                "resting_characters": ["沈三"],
                "priority_characters": [
                    {"name": "陈砚", "due_status": "本章默认在场", "schedule_score": 100},
                    {"name": "林秋雨", "due_status": "本章焦点", "schedule_score": 95},
                    {"name": "周执事", "due_status": "该回场", "schedule_score": 88},
                    {"name": "沈三", "due_status": "刚出场过", "schedule_score": 52},
                ],
            },
            "relationship_schedule": {
                "due_relations": ["陈砚::林秋雨", "陈砚::周执事"],
                "priority_relations": [
                    {
                        "relation_id": "陈砚::林秋雨",
                        "due_status": "本章应动",
                        "schedule_score": 90,
                        "interaction_depth": "深互动",
                        "push_direction": "合作推进",
                    },
                    {
                        "relation_id": "陈砚::周执事",
                        "due_status": "该推进",
                        "schedule_score": 82,
                        "interaction_depth": "中互动",
                        "push_direction": "拉扯推进",
                    },
                    {
                        "relation_id": "林秋雨::沈三",
                        "due_status": "轻触或略过",
                        "schedule_score": 50,
                        "interaction_depth": "轻互动",
                        "push_direction": "轻推一格",
                    },
                ],
            },
        },
        "relevant_cards": {
            "characters": {
                "陈砚": {"card_id": "C001", "title": "陈砚"},
                "林秋雨": {"card_id": "C002", "title": "林秋雨"},
                "周执事": {"card_id": "C003", "title": "周执事"},
                "沈三": {"card_id": "C004", "title": "沈三"},
            },
            "relations": [
                {"card_id": "REL001", "relation_id": "陈砚::林秋雨", "title": "陈砚::林秋雨"},
                {"card_id": "REL002", "relation_id": "陈砚::周执事", "title": "陈砚::周执事"},
                {"card_id": "REL003", "relation_id": "林秋雨::沈三", "title": "林秋雨::沈三"},
            ],
        },
        "chapter_stage_casting_hint": {
            "planned_action": "role_refresh",
            "planned_target": "周执事",
            "should_execute_planned_action": True,
            "do_not_force_action": False,
            "recommended_action": "execute_role_refresh",
            "chapter_hint": "本章原计划让周执事换一种更能带剧情的作用位。",
        },
        "card_index": {
            "characters": [
                {"card_id": "C001", "title": "陈砚", "summary": "主角", "tags": ["主角"], "importance_score": 100, "entity_type": "character"},
                {"card_id": "C002", "title": "林秋雨", "summary": "焦点药师", "tags": ["药师", "合作"], "importance_score": 88, "entity_type": "character"},
                {"card_id": "C003", "title": "周执事", "summary": "宗门执事", "tags": ["压迫", "规矩"], "importance_score": 76, "entity_type": "character"},
                {"card_id": "C004", "title": "沈三", "summary": "街头耳目", "tags": ["消息"], "importance_score": 60, "entity_type": "character"},
            ],
            "resources": [],
            "factions": [],
            "relations": [
                {"card_id": "REL001", "title": "陈砚::林秋雨", "key": "陈砚::林秋雨", "summary": "互信升温", "tags": ["合作", "绑定"], "importance_score": 85, "entity_type": "relation"},
                {"card_id": "REL002", "title": "陈砚::周执事", "key": "陈砚::周执事", "summary": "规矩压迫", "tags": ["拉扯", "压迫"], "importance_score": 72, "entity_type": "relation"},
                {"card_id": "REL003", "title": "林秋雨::沈三", "key": "林秋雨::沈三", "summary": "边缘线", "tags": ["轻触"], "importance_score": 42, "entity_type": "relation"},
            ],
        },
    }


def test_heuristic_schedule_review_prefers_focus_and_due_items() -> None:
    packet = _planning_packet()
    review = _heuristic_character_relation_schedule_review(
        {"goal": "和林秋雨联手查账", "flow_template_name": "合作破局"},
        packet,
    )
    assert "陈砚" in review.focus_characters
    assert "林秋雨" in review.focus_characters
    assert "陈砚::林秋雨" in review.main_relation_ids
    assert review.review_note


def test_apply_schedule_review_to_packet_keeps_normalized_payload() -> None:
    packet = _planning_packet()
    review = CharacterRelationScheduleReviewPayload(
        focus_characters=["林秋雨", "陌生人", "陈砚"],
        supporting_characters=["周执事", "陈砚"],
        defer_characters=["沈三"],
        main_relation_ids=["陈砚::林秋雨", "不存在::关系"],
        light_touch_relation_ids=["陈砚::周执事"],
        defer_relation_ids=["林秋雨::沈三"],
        interaction_depth_overrides={"陈砚::林秋雨": "深互动", "假的::关系": "深互动"},
        relation_push_overrides={"陈砚::周执事": "拉扯推进"},
        stage_casting_verdict="defer_to_next",
        should_execute_stage_casting_action=False,
        do_not_force_stage_casting_action=True,
        stage_casting_reason="虽然窗口允许，但这章更适合先让周执事继续当压迫源，别急着换挡。",
        review_note="本章主推陈砚与林秋雨，周执事只作掣肘。",
    )
    updated = apply_schedule_review_to_packet(packet, review)
    ai = updated["character_relation_schedule_ai"]
    assert ai["focus_characters"][0] == "陈砚"
    assert "林秋雨" in ai["focus_characters"]
    assert "陌生人" not in ai["focus_characters"]
    assert ai["main_relation_ids"] == ["陈砚::林秋雨"]
    assert updated["selected_elements"]["ai_main_relations"] == ["陈砚::林秋雨"]
    hint = updated["chapter_stage_casting_hint"]
    assert hint["ai_stage_casting_verdict"] == "defer_to_next"
    assert hint["final_should_execute_planned_action"] is False
    assert hint["final_do_not_force_action"] is True


def test_soft_card_ranking_uses_ai_review_as_extra_signal() -> None:
    packet = _planning_packet()
    packet["character_relation_schedule_ai"] = {
        "focus_characters": ["陈砚", "周执事"],
        "supporting_characters": ["林秋雨"],
        "defer_characters": ["沈三"],
        "main_relation_ids": ["陈砚::周执事"],
        "light_touch_relation_ids": ["陈砚::林秋雨"],
        "defer_relation_ids": ["林秋雨::沈三"],
    }
    ranked = soft_sort_card_index_payload(
        packet["card_index"],
        chapter_plan={"goal": "应付执事查账", "conflict": "周执事逼近", "flow_template_name": "压力逼近"},
        planning_packet=packet,
    )
    char_titles = [item["title"] for item in ranked["characters"]]
    rel_titles = [item["title"] for item in ranked["relations"]]
    assert char_titles.index("周执事") < char_titles.index("沈三")
    assert rel_titles[0] == "陈砚::周执事"


def test_soft_card_ranking_respects_ai_casting_deferral() -> None:
    packet = _planning_packet()
    packet["character_relation_schedule_ai"] = {
        "focus_characters": ["陈砚", "林秋雨"],
        "supporting_characters": ["周执事"],
        "defer_characters": [],
        "main_relation_ids": ["陈砚::林秋雨"],
        "light_touch_relation_ids": ["陈砚::周执事"],
        "defer_relation_ids": [],
        "stage_casting_verdict": "defer_to_next",
        "should_execute_stage_casting_action": False,
        "do_not_force_stage_casting_action": True,
        "stage_casting_reason": "本章更适合先压住周执事，不急着给他换功能。",
    }
    packet["chapter_stage_casting_hint"]["final_should_execute_planned_action"] = False
    packet["chapter_stage_casting_hint"]["final_do_not_force_action"] = True
    packet["chapter_stage_casting_hint"]["final_recommended_action"] = "defer_to_next"
    ranked = soft_sort_card_index_payload(
        packet["card_index"],
        chapter_plan={"goal": "先扛住执事压力", "conflict": "周执事步步紧逼", "flow_template_name": "压力逼近"},
        planning_packet=packet,
    )
    char_rows = {item["title"]: item for item in ranked["characters"]}
    assert "本章换功能" not in (char_rows["周执事"].get("soft_reason_tags") or [])
