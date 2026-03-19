from app.services.openai_story_engine_review import _normalize_scene_continuity_review_payload


def test_scene_continuity_missing_sequence_is_synthesized_from_ai_core_fields():
    payload = {
        "must_continue_same_scene": True,
        "recommended_scene_count": 2,
        "transition_mode": "continue_same_scene",
        "allowed_transition": "resolve_then_cut",
        "opening_anchor": "先接住上一章残留的交易压力",
        "must_carry_over": ["对方尚未松口"],
        "cut_plan": [
            {
                "cut_after_scene_no": 1,
                "reason": "先拿到谈判阶段结果再切",
                "required_result": "逼出对方底牌",
                "transition_anchor": "带着对方松口后的余波切到下一场",
            }
        ],
        "review_note": "先续场再推进更顺。",
    }
    chapter_plan = {
        "goal": "拿到进入藏经阁的资格",
        "conflict": "掌事长老仍在压价试探",
        "opening_beat": "主角先接住上一章留下的谈判压力",
        "mid_turn": "长老突然抬高条件，逼主角亮出额外筹码",
        "closing_image": "资格到手，但藏经阁内出现更大的疑点",
        "main_scene": "藏经阁外院",
    }
    result = _normalize_scene_continuity_review_payload(payload, {}, chapter_plan)
    assert result.recommended_scene_count == 2
    assert len(result.scene_sequence_plan) == 2
    assert result.scene_sequence_plan[0]["transition_in"] == "主角先接住上一章留下的谈判压力"
    assert len(result.cut_plan) == 1


def test_scene_continuity_invalid_cut_plan_is_synthesized_to_match_scene_count():
    payload = {
        "must_continue_same_scene": False,
        "recommended_scene_count": 3,
        "transition_mode": "soft_cut",
        "allowed_transition": "time_skip_allowed",
        "opening_anchor": "从主角确认线索后切入新场景",
        "must_carry_over": ["残缺阵图的线索还没吃透"],
        "cut_plan": [],
        "scene_sequence_plan": [
            {
                "scene_no": 1,
                "scene_name": "确认线索",
                "scene_role": "opening",
                "purpose": "确认阵图线索是否可信",
                "transition_in": "先接住上一章得到的线索",
                "target_result": "确认这条线值得继续追",
            },
            {
                "scene_no": 2,
                "scene_name": "转入调查",
                "scene_role": "main",
                "purpose": "去藏经阁深处验证线索",
                "transition_in": "带着已确认的线索继续深入",
                "target_result": "发现阵图记录确实缺了一角",
            },
            {
                "scene_no": 3,
                "scene_name": "收束留钩",
                "scene_role": "ending",
                "purpose": "收在新的疑点上",
                "transition_in": "把缺角问题带入结尾",
                "target_result": "意识到有人提前动过这份记录",
            },
        ],
    }
    result = _normalize_scene_continuity_review_payload(payload, {}, {})
    assert len(result.scene_sequence_plan) == 3
    assert len(result.cut_plan) == 2
    assert result.cut_plan[0]["cut_after_scene_no"] == 1
    assert result.cut_plan[1]["cut_after_scene_no"] == 2
