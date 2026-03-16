from app.services.openai_story_engine import (
    ArcCastingLayoutReviewPayload,
    apply_arc_casting_layout_review,
    review_arc_casting_layout,
    review_stage_characters,
)
from app.services.prompt_templates import arc_casting_layout_review_user_prompt
from app.services.stage_review_support import build_stage_character_review_snapshot, store_stage_character_review, summarize_arc_casting_layout_review


def _story_bible() -> dict:
    return {
        "retrospective_state": {"scheduled_review_interval": 5, "last_stage_review_chapter": 0},
        "control_console": {
            "chapter_retrospectives": [
                {"chapter_no": 1, "title": "起手", "core_problem": "配角戏份偏薄", "next_chapter_correction": "把关键配角私心写实"},
                {"chapter_no": 2, "title": "试探", "core_problem": "关系推进偏慢", "next_chapter_correction": "把合作关系再推一格"},
                {"chapter_no": 3, "title": "换路", "core_problem": "周执事出场偏少", "next_chapter_correction": "让周执事回场施压"},
                {"chapter_no": 4, "title": "查账", "core_problem": "林秋雨有工具人风险", "next_chapter_correction": "补她的判断和顾虑"},
                {"chapter_no": 5, "title": "压境", "core_problem": "主角线和关系线有点脱节", "next_chapter_correction": "把查账压力和人物线绑一起"},
            ],
            "character_relation_schedule": {
                "appearance_schedule": {
                    "priority_characters": [
                        {"name": "陈砚", "due_status": "本章默认在场", "schedule_score": 100},
                        {"name": "林秋雨", "due_status": "该回场", "schedule_score": 92},
                        {"name": "周执事", "due_status": "该回场", "schedule_score": 88},
                    ]
                },
                "relationship_schedule": {
                    "priority_relations": [
                        {"relation_id": "陈砚::林秋雨", "due_status": "本章应动", "schedule_score": 90, "interaction_depth": "深互动", "push_direction": "合作推进"},
                        {"relation_id": "陈砚::周执事", "due_status": "该推进", "schedule_score": 82, "interaction_depth": "中互动", "push_direction": "拉扯推进"},
                    ]
                },
            },
            "stage_casting_resolution_history": [
                {
                    "chapter_no": 4,
                    "planned_action": "role_refresh",
                    "planned_target": "林秋雨",
                    "ai_stage_casting_verdict": "defer_to_next",
                    "ai_stage_casting_reason": "这章冲突太满，旧角色换功能会抢掉危机线。",
                    "execution_status": "deferred_after_review",
                },
                {
                    "chapter_no": 5,
                    "planned_action": "role_refresh",
                    "planned_target": "林秋雨",
                    "ai_stage_casting_verdict": "defer_to_next",
                    "ai_stage_casting_reason": "这章更像危机爆发，先别把角色换挡动作硬塞进来。",
                    "execution_status": "deferred_after_review",
                },
            ],
        },
        "core_cast_state": {
            "slots": [
                {"slot_id": "CC01", "bound_character": "林秋雨", "appearance_frequency": "高频", "long_term_relation_line": "互助绑定", "last_appeared_chapter": 4},
                {"slot_id": "CC02", "bound_character": "周执事", "appearance_frequency": "中频", "long_term_relation_line": "长期拉扯", "last_appeared_chapter": 2},
                {"slot_id": "CC03", "bound_character": "", "entry_phase": "中前期", "entry_chapter_window": [6, 8], "binding_pattern": "先敌后友", "first_entry_mission": "带出新势力", "appearance_frequency": "中频"},
            ]
        },
    }


def _store_review(story_bible: dict) -> None:
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review.update(
        {
            "casting_strategy": "prefer_refresh_existing",
            "should_introduce_character": False,
            "candidate_slot_ids": [],
            "should_refresh_role_functions": True,
            "role_refresh_targets": ["林秋雨"],
            "max_new_core_entries": 0,
            "max_role_refreshes": 1,
        }
    )
    store_stage_character_review(story_bible, review, current_chapter_no=5)


def test_arc_casting_layout_review_prompt_includes_stage_diagnostics() -> None:
    story_bible = _story_bible()
    _store_review(story_bible)
    arc_bundle = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 8,
        "focus": "稳住查账压力",
        "bridge_note": "把人物线和查账线绑一起。",
        "chapters": [
            {"chapter_no": 6, "title": "压风", "chapter_type": "turning_point", "event_type": "危机爆发", "goal": "硬扛查账", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"},
            {"chapter_no": 7, "title": "缓气", "chapter_type": "progress", "event_type": "关系推进类", "goal": "补一段合作细节"},
            {"chapter_no": 8, "title": "回手", "chapter_type": "progress", "event_type": "交易类", "goal": "借一笔账目试探对手"},
        ],
    }
    prompt = arc_casting_layout_review_user_prompt(
        payload={"genre": "修仙", "premise": "边城求生", "protagonist_name": "陈砚", "style_preferences": {}},
        story_bible=story_bible,
        global_outline={"acts": []},
        recent_summaries=[{"chapter_no": 5, "title": "压境", "event_summary": "查账压力逼近"}],
        arc_bundle=arc_bundle,
    )
    assert "人物投放排法" in prompt
    assert "casting_defer_diagnostics" in prompt
    assert "当前小弧线拍表" in prompt
    assert "章法不顺" in prompt or "窗口太满" in prompt


def test_review_arc_casting_layout_heuristic_moves_refresh_off_crisis_chapter() -> None:
    story_bible = _story_bible()
    _store_review(story_bible)
    arc_bundle = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 8,
        "focus": "稳住查账压力",
        "bridge_note": "把人物线和查账线绑一起。",
        "chapters": [
            {"chapter_no": 6, "title": "压风", "chapter_type": "turning_point", "event_type": "危机爆发", "goal": "硬扛查账", "conflict": "对手逼近", "main_scene": "账房", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"},
            {"chapter_no": 7, "title": "缓气", "chapter_type": "progress", "event_type": "关系推进类", "goal": "补一段合作细节", "conflict": "仍要彼此试探", "main_scene": "后院"},
            {"chapter_no": 8, "title": "回手", "chapter_type": "progress", "event_type": "交易类", "goal": "借一笔账目试探对手", "conflict": "要防止暴露", "main_scene": "小库房"},
        ],
    }
    review = review_arc_casting_layout(
        payload={"genre": "修仙", "premise": "边城求生", "protagonist_name": "陈砚", "style_preferences": {}},
        story_bible=story_bible,
        global_outline={"acts": []},
        recent_summaries=[{"chapter_no": 5, "title": "压境", "event_summary": "查账压力逼近"}],
        arc_bundle=arc_bundle,
    )
    assert isinstance(review, ArcCastingLayoutReviewPayload)
    decisions = {(item.chapter_no, item.decision, item.stage_casting_action) for item in review.chapter_adjustments}
    assert (6, "drop", "role_refresh") in decisions
    assert any(item.chapter_no in {7, 8} and item.decision == "move_here" and item.stage_casting_action == "role_refresh" for item in review.chapter_adjustments)


def test_apply_arc_casting_layout_review_updates_bundle() -> None:
    bundle = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 8,
        "chapters": [
            {"chapter_no": 6, "title": "压风", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "stage_casting_note": "原计划本章换功能"},
            {"chapter_no": 7, "title": "缓气"},
        ],
    }
    review = ArcCastingLayoutReviewPayload.model_validate(
        {
            "window_verdict": "shift_actions",
            "chapter_adjustments": [
                {"chapter_no": 6, "decision": "drop", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "note": "这一章先别硬塞。"},
                {"chapter_no": 7, "decision": "move_here", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "note": "这一章承接更顺。"},
            ],
            "review_note": "把旧角色换功能挪到更顺的章节。",
        }
    )
    updated = apply_arc_casting_layout_review(bundle, review)
    chapter6 = next(ch for ch in updated["chapters"] if ch["chapter_no"] == 6)
    chapter7 = next(ch for ch in updated["chapters"] if ch["chapter_no"] == 7)
    assert "stage_casting_action" not in chapter6
    assert chapter7["stage_casting_action"] == "role_refresh"
    assert updated["casting_layout_review"]["window_verdict"] == "shift_actions"


def test_summarize_arc_casting_layout_review_pairs_move_summary() -> None:
    bundle = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 8,
        "casting_layout_review": {
            "window_verdict": "shift_actions",
            "review_note": "把人物投放动作挪到更顺的章节。",
            "chapter_adjustments": [
                {"chapter_no": 6, "decision": "drop", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "note": "危机章先别硬塞。"},
                {"chapter_no": 7, "decision": "move_here", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "note": "这一章承接更顺。"},
            ],
        },
    }
    summary = summarize_arc_casting_layout_review(bundle)
    assert summary["window_verdict"] == "shift_actions"
    assert summary["moved_actions"][0]["from_chapter"] == 6
    assert summary["moved_actions"][0]["to_chapter"] == 7
    assert any("第6章→第7章" in line for line in summary["display_lines"])
