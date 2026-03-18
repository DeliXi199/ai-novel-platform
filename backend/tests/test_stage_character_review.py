import pytest

from app.services.openai_story_engine import review_stage_characters
from app.services.prompt_templates import arc_outline_user_prompt, chapter_draft_user_prompt, stage_character_review_user_prompt
from app.services.stage_review_support import (
    apply_role_refresh_execution,
    build_chapter_stage_casting_hint,
    record_stage_casting_resolution,
    build_stage_character_review_snapshot,
    build_stage_review_window_progress,
    should_run_stage_character_review,
    stage_character_review_for_window,
    store_stage_character_review,
)


def _story_bible() -> dict:
    return {
        "retrospective_state": {"scheduled_review_interval": 5, "last_stage_review_chapter": 0},
        "story_workspace": {
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
        },
        "core_cast_state": {
            "slots": [
                {"slot_id": "CC01", "bound_character": "林秋雨", "appearance_frequency": "高频", "long_term_relation_line": "互助绑定", "last_appeared_chapter": 4},
                {"slot_id": "CC02", "bound_character": "周执事", "appearance_frequency": "中频", "long_term_relation_line": "长期拉扯", "last_appeared_chapter": 2},
                {"slot_id": "CC03", "bound_character": "", "entry_phase": "中前期", "entry_chapter_window": [6, 8], "binding_pattern": "先敌后友", "first_entry_mission": "带出新势力", "appearance_frequency": "中频"},
            ]
        },
    }


def test_stage_review_due_every_five_chapters() -> None:
    story_bible = _story_bible()
    assert should_run_stage_character_review(story_bible, current_chapter_no=5) is True
    story_bible["retrospective_state"]["last_stage_review_chapter"] = 5
    assert should_run_stage_character_review(story_bible, current_chapter_no=5) is False
    assert should_run_stage_character_review(story_bible, current_chapter_no=6) is False


def test_store_stage_character_review_exposes_current_window_review() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(
        story_bible,
        current_chapter_no=5,
        recent_summaries=[{"chapter_no": 5, "title": "压境", "event_summary": "周执事重新压上来"}],
    )
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    stored = store_stage_character_review(story_bible, review, current_chapter_no=5)

    assert stored["next_window_start"] == 6
    assert stored["focus_characters"]
    assert "should_refresh_role_functions" in stored
    assert stored["casting_strategy"] in {"prefer_refresh_existing", "introduce_one_new", "balanced_light", "hold_steady"}
    assert stage_character_review_for_window(story_bible, current_chapter_no=5)["review_chapter"] == 5
    assert story_bible["retrospective_state"]["last_stage_review_chapter"] == 5


def test_arc_outline_prompt_reads_stage_review_as_front_guidance() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    store_stage_character_review(story_bible, review, current_chapter_no=5)

    prompt = arc_outline_user_prompt(
        payload={"genre": "修仙", "premise": "在边城求生", "protagonist_name": "陈砚", "style_preferences": {}},
        story_bible=story_bible,
        global_outline={"acts": []},
        recent_summaries=[{"chapter_no": 5, "title": "压境", "event_summary": "周执事重新压上来"}],
        start_chapter=6,
        end_chapter=10,
        arc_no=2,
    )

    assert "阶段性人物复盘" in prompt
    assert "林秋雨" in prompt or "周执事" in prompt
    assert "前置建议" in prompt
    assert "casting_strategy" in prompt



def test_stage_review_snapshot_contains_role_refresh_candidates() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)

    assert snapshot["role_refresh_candidates"]
    assert any(item.get("name") == "林秋雨" for item in snapshot["role_refresh_candidates"])


def test_arc_outline_prompt_reads_role_refresh_guidance() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review["should_refresh_role_functions"] = True
    review["role_refresh_targets"] = ["林秋雨"]
    review["role_refresh_suggestions"] = [{"character": "林秋雨", "suggested_function": "行动搭档", "reason": "别再只做提醒位"}]
    store_stage_character_review(story_bible, review, current_chapter_no=5)

    prompt = arc_outline_user_prompt(
        payload={"genre": "修仙", "premise": "在边城求生", "protagonist_name": "陈砚", "style_preferences": {}},
        story_bible=story_bible,
        global_outline={"acts": []},
        recent_summaries=[{"chapter_no": 5, "title": "压境", "event_summary": "周执事重新压上来"}],
        start_chapter=6,
        end_chapter=10,
        arc_no=2,
    )

    assert "role_refresh_targets" in prompt
    assert "换一种更能带剧情的作用位" in prompt


def test_stage_review_prefers_refresh_over_new_when_cast_is_crowded() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")

    assert review["casting_strategy"] == "prefer_refresh_existing"
    assert review["should_introduce_character"] is False
    assert review["max_new_core_entries"] == 0
    assert review["max_role_refreshes"] in {0, 1}


def test_stage_review_can_prefer_one_new_slot_when_refresh_pressure_is_low() -> None:
    story_bible = _story_bible()
    story_bible["story_workspace"]["chapter_retrospectives"] = [
        {"chapter_no": 1, "title": "起手", "core_problem": "世界格局刚展开", "next_chapter_correction": "准备接新线"},
        {"chapter_no": 2, "title": "试探", "core_problem": "需要扩势力触角", "next_chapter_correction": "给新关系留入口"},
        {"chapter_no": 3, "title": "换路", "core_problem": "中前期缺新接口", "next_chapter_correction": "安排新势力接口"},
        {"chapter_no": 4, "title": "查账", "core_problem": "旧角色功能正常", "next_chapter_correction": "先别硬改旧角色"},
        {"chapter_no": 5, "title": "压境", "core_problem": "下一阶段需要新人接线", "next_chapter_correction": "补一个新核心位"},
    ]
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    snapshot["role_refresh_candidates"] = []
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")

    assert review["casting_strategy"] in {"introduce_one_new", "hold_steady"}
    if review["casting_strategy"] == "introduce_one_new":
        assert review["should_introduce_character"] is True
        assert review["max_new_core_entries"] == 1
        assert len(review["candidate_slot_ids"]) <= 1
        assert review["should_refresh_role_functions"] is False



def test_stage_review_tracks_window_progress_and_limits() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review["casting_strategy"] = "balanced_light"
    review["max_new_core_entries"] = 1
    review["max_role_refreshes"] = 1
    review["should_introduce_character"] = True
    review["should_refresh_role_functions"] = True
    review["candidate_slot_ids"] = ["CC03"]
    review["role_refresh_targets"] = ["林秋雨"]
    store_stage_character_review(story_bible, review, current_chapter_no=5)

    story_bible["active_arc"] = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 10,
        "chapters": [
            {"chapter_no": 6, "title": "落位", "stage_casting_action": "new_core_entry", "stage_casting_target": "CC03"},
            {"chapter_no": 8, "title": "换挡", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"},
        ],
    }
    progress = build_stage_review_window_progress(story_bible, stage_character_review_for_window(story_bible, current_chapter_no=5))

    assert progress["planned_new_core_entries"] == 1
    assert progress["planned_role_refreshes"] == 1
    assert progress["new_core_limit_status"] == "full"
    assert progress["role_refresh_limit_status"] == "full"



def test_apply_role_refresh_execution_records_history() -> None:
    story_bible = _story_bible()
    story_bible.setdefault("story_domains", {}).setdefault("characters", {})["林秋雨"] = {"name": "林秋雨", "current_plot_function": "提醒位"}
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review["should_refresh_role_functions"] = True
    review["role_refresh_targets"] = ["林秋雨"]
    review["role_refresh_suggestions"] = [{"character": "林秋雨", "suggested_function": "行动搭档", "reason": "别再只做提醒位"}]
    store_stage_character_review(story_bible, review, current_chapter_no=5)

    applied = apply_role_refresh_execution(
        story_bible,
        chapter_no=8,
        plan={"stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "stage_casting_note": "切到行动搭档"},
    )

    assert applied and applied["character"] == "林秋雨"
    assert story_bible["story_workspace"]["role_refresh_history"][-1]["suggested_function"] == "行动搭档"
    assert story_bible["story_domains"]["characters"]["林秋雨"]["current_plot_function"] == "行动搭档"


def test_chapter_stage_casting_hint_respects_window_limits() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review.update({
        "casting_strategy": "balanced_light",
        "max_new_core_entries": 1,
        "max_role_refreshes": 1,
        "should_introduce_character": True,
        "should_refresh_role_functions": True,
        "candidate_slot_ids": ["CC03"],
        "role_refresh_targets": ["林秋雨"],
    })
    store_stage_character_review(story_bible, review, current_chapter_no=5)
    story_bible["active_arc"] = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 10,
        "chapters": [
            {"chapter_no": 6, "title": "落位", "stage_casting_action": "new_core_entry", "stage_casting_target": "CC03"},
        ],
    }

    hint = build_chapter_stage_casting_hint(
        story_bible,
        chapter_no=7,
        plan={"chapter_no": 7, "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"},
    )

    assert hint["role_refresh_limit_status"] == "open"
    assert hint["should_execute_planned_action"] is True
    assert hint["recommended_action"] == "execute_role_refresh"

    story_bible["active_arc"]["chapters"].append({"chapter_no": 7, "title": "换挡", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"})
    blocked = build_chapter_stage_casting_hint(
        story_bible,
        chapter_no=8,
        plan={"chapter_no": 8, "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"},
    )

    assert blocked["role_refresh_limit_status"] == "full"
    assert blocked["should_execute_planned_action"] is False
    assert blocked["do_not_force_action"] is True


def test_chapter_draft_prompt_includes_stage_casting_hint() -> None:
    chapter_plan = {
        "chapter_no": 7,
        "goal": "让林秋雨换挡",
        "conflict": "她不愿继续只当提醒位",
        "event_type": "关系推进类",
        "progress_kind": "关系推进",
        "supporting_character_focus": "林秋雨",
        "planning_packet": {
            "selected_elements": {"focus_character": "林秋雨"},
            "character_relation_schedule": {"appearance_schedule": {"due_characters": ["林秋雨"]}},
            "character_relation_schedule_ai": {"focus_characters": ["陈砚", "林秋雨"], "main_relation_ids": ["陈砚::林秋雨"]},
            "chapter_stage_casting_hint": {
                "planned_action": "role_refresh",
                "planned_target": "林秋雨",
                "should_execute_planned_action": True,
                "do_not_force_action": False,
                "recommended_action": "execute_role_refresh",
                "chapter_hint": "本章承担旧角色换功能任务。",
            },
        },
    }
    prompt = chapter_draft_user_prompt(
        novel_context={"story_memory": {}},
        chapter_plan=chapter_plan,
        last_chapter={"title": "前章", "tail_excerpt": "风还没停。"},
        recent_summaries=[{"chapter_no": 6, "title": "前章", "event_summary": "林秋雨再次提醒陈砚。"}],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1800,
        target_visible_chars_max=3200,
    )

    assert "本章人物投放提示" in prompt
    assert "should_execute_planned_action" in prompt
    assert "do_not_force_action" in prompt


def test_stage_review_window_progress_tracks_ai_review_and_execution_history() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review.update({
        "casting_strategy": "balanced_light",
        "max_new_core_entries": 1,
        "max_role_refreshes": 1,
        "should_introduce_character": True,
        "should_refresh_role_functions": True,
        "candidate_slot_ids": ["CC03"],
        "role_refresh_targets": ["林秋雨"],
        "role_refresh_suggestions": [{"character": "林秋雨", "suggested_function": "行动搭档", "reason": "别再只做提醒位"}],
    })
    store_stage_character_review(story_bible, review, current_chapter_no=5)
    story_bible["active_arc"] = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 10,
        "chapters": [
            {"chapter_no": 6, "title": "延后落位", "stage_casting_action": "new_core_entry", "stage_casting_target": "CC03"},
            {"chapter_no": 7, "title": "旧人换挡", "stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨"},
        ],
    }

    record_stage_casting_resolution(
        story_bible,
        chapter_no=6,
        plan={
            "chapter_no": 6,
            "stage_casting_action": "new_core_entry",
            "stage_casting_target": "CC03",
            "planning_packet": {
                "chapter_stage_casting_hint": {
                    "planned_action": "new_core_entry",
                    "planned_target": "CC03",
                    "should_execute_planned_action": True,
                    "do_not_force_action": False,
                    "recommended_action": "execute_new_core_entry",
                    "ai_stage_casting_verdict": "defer_to_next",
                    "ai_stage_casting_reason": "这一章先别挤新人",
                    "ai_should_execute_planned_action": False,
                    "ai_do_not_force_action": True,
                    "final_should_execute_planned_action": False,
                    "final_do_not_force_action": True,
                    "final_recommended_action": "defer_to_next",
                    "final_action_priority": "avoid",
                }
            },
        },
    )

    story_bible.setdefault("story_domains", {}).setdefault("characters", {})["林秋雨"] = {"name": "林秋雨", "current_plot_function": "提醒位"}
    apply_role_refresh_execution(
        story_bible,
        chapter_no=7,
        plan={"stage_casting_action": "role_refresh", "stage_casting_target": "林秋雨", "stage_casting_note": "切到行动搭档"},
    )
    record_stage_casting_resolution(
        story_bible,
        chapter_no=7,
        plan={
            "chapter_no": 7,
            "stage_casting_action": "role_refresh",
            "stage_casting_target": "林秋雨",
            "planning_packet": {
                "chapter_stage_casting_hint": {
                    "planned_action": "role_refresh",
                    "planned_target": "林秋雨",
                    "should_execute_planned_action": True,
                    "do_not_force_action": False,
                    "recommended_action": "execute_role_refresh",
                    "ai_stage_casting_verdict": "execute_now",
                    "ai_stage_casting_reason": "这章适合让旧人换挡",
                    "ai_should_execute_planned_action": True,
                    "ai_do_not_force_action": False,
                    "final_should_execute_planned_action": True,
                    "final_do_not_force_action": False,
                    "final_recommended_action": "execute_role_refresh",
                    "final_action_priority": "must_execute",
                }
            },
        },
    )

    progress = build_stage_review_window_progress(story_bible, stage_character_review_for_window(story_bible, current_chapter_no=5))

    assert progress["reviewed_new_core_deferred"] == 1
    assert progress["reviewed_role_refresh_execute_now"] == 1
    assert any(item["chapter_no"] == 6 and item["execution_status"] == "deferred_after_review" for item in progress["casting_resolution_history"])
    assert any(item["chapter_no"] == 7 and item["execution_status"] == "executed" for item in progress["casting_resolution_history"])


def test_arc_outline_prompt_exposes_casting_resolution_history() -> None:
    story_bible = _story_bible()
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")
    review.update({
        "casting_strategy": "balanced_light",
        "max_new_core_entries": 1,
        "max_role_refreshes": 1,
        "candidate_slot_ids": ["CC03"],
    })
    store_stage_character_review(story_bible, review, current_chapter_no=5)
    story_bible["active_arc"] = {
        "arc_no": 2,
        "start_chapter": 6,
        "end_chapter": 10,
        "chapters": [
            {"chapter_no": 6, "title": "延后落位", "stage_casting_action": "new_core_entry", "stage_casting_target": "CC03"},
        ],
    }
    record_stage_casting_resolution(
        story_bible,
        chapter_no=6,
        plan={
            "chapter_no": 6,
            "stage_casting_action": "new_core_entry",
            "stage_casting_target": "CC03",
            "planning_packet": {
                "chapter_stage_casting_hint": {
                    "planned_action": "new_core_entry",
                    "planned_target": "CC03",
                    "should_execute_planned_action": True,
                    "do_not_force_action": False,
                    "recommended_action": "execute_new_core_entry",
                    "ai_stage_casting_verdict": "defer_to_next",
                    "ai_stage_casting_reason": "这一章先别挤新人",
                    "ai_should_execute_planned_action": False,
                    "ai_do_not_force_action": True,
                    "final_should_execute_planned_action": False,
                    "final_do_not_force_action": True,
                    "final_recommended_action": "defer_to_next",
                    "final_action_priority": "avoid",
                }
            },
        },
    )

    prompt = arc_outline_user_prompt(
        payload={"genre": "修仙", "premise": "在边城求生", "protagonist_name": "陈砚", "style_preferences": {}},
        story_bible=story_bible,
        global_outline={"acts": []},
        recent_summaries=[{"chapter_no": 5, "title": "压境", "event_summary": "周执事重新压上来"}],
        start_chapter=6,
        end_chapter=10,
        arc_no=2,
    )

    assert "casting_resolution_history" in prompt
    assert "defer_to_next" in prompt


def test_stage_review_snapshot_contains_casting_defer_diagnostics() -> None:
    story_bible = _story_bible()
    record_stage_casting_resolution(
        story_bible,
        chapter_no=4,
        plan={
            "chapter_no": 4,
            "stage_casting_action": "new_core_entry",
            "stage_casting_target": "CC03",
            "planning_packet": {
                "chapter_stage_casting_hint": {
                    "planned_action": "new_core_entry",
                    "planned_target": "CC03",
                    "should_execute_planned_action": True,
                    "do_not_force_action": False,
                    "recommended_action": "execute_new_core_entry",
                    "new_core_limit_status": "open",
                    "ai_stage_casting_verdict": "defer_to_next",
                    "ai_stage_casting_reason": "这一章先别挤新人",
                    "ai_should_execute_planned_action": False,
                    "ai_do_not_force_action": True,
                    "final_should_execute_planned_action": False,
                    "final_do_not_force_action": True,
                    "final_recommended_action": "defer_to_next",
                    "final_action_priority": "avoid",
                }
            },
        },
    )
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)

    diagnostics = snapshot["casting_defer_diagnostics"]
    assert diagnostics["recent_deferred_count"] >= 1
    assert diagnostics["dominant_defer_cause"] in {"budget_pressure", "chapter_fit", "pacing_mismatch"}
    assert diagnostics["summary"]


def test_stage_review_heuristic_slows_new_entries_after_repeated_defer() -> None:
    story_bible = _story_bible()
    for chapter_no in [4, 5]:
        record_stage_casting_resolution(
            story_bible,
            chapter_no=chapter_no,
            plan={
                "chapter_no": chapter_no,
                "stage_casting_action": "new_core_entry",
                "stage_casting_target": "CC03",
                "planning_packet": {
                    "chapter_stage_casting_hint": {
                        "planned_action": "new_core_entry",
                        "planned_target": "CC03",
                        "should_execute_planned_action": True,
                        "do_not_force_action": False,
                        "recommended_action": "execute_new_core_entry",
                        "new_core_limit_status": "open",
                        "ai_stage_casting_verdict": "defer_to_next",
                        "ai_stage_casting_reason": "这一章先别挤新人",
                        "ai_should_execute_planned_action": False,
                        "ai_do_not_force_action": True,
                        "final_should_execute_planned_action": False,
                        "final_do_not_force_action": True,
                        "final_recommended_action": "defer_to_next",
                        "final_action_priority": "avoid",
                    }
                },
            },
        )

    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    review = review_stage_characters(snapshot=snapshot).model_dump(mode="python")

    assert review["casting_strategy"] in {"prefer_refresh_existing", "hold_steady"}
    assert review["should_introduce_character"] is False
    assert any("延后" in item or "别挤新人" in item or "窗口" in item for item in review["next_window_tasks"] + review["watchouts"])


def test_stage_review_prompt_reads_casting_defer_diagnostics() -> None:
    story_bible = _story_bible()
    record_stage_casting_resolution(
        story_bible,
        chapter_no=4,
        plan={
            "chapter_no": 4,
            "stage_casting_action": "new_core_entry",
            "stage_casting_target": "CC03",
            "planning_packet": {
                "chapter_stage_casting_hint": {
                    "planned_action": "new_core_entry",
                    "planned_target": "CC03",
                    "should_execute_planned_action": True,
                    "do_not_force_action": False,
                    "recommended_action": "execute_new_core_entry",
                    "new_core_limit_status": "open",
                    "ai_stage_casting_verdict": "defer_to_next",
                    "ai_stage_casting_reason": "这一章先别挤新人",
                    "ai_should_execute_planned_action": False,
                    "ai_do_not_force_action": True,
                    "final_should_execute_planned_action": False,
                    "final_do_not_force_action": True,
                    "final_recommended_action": "defer_to_next",
                    "final_action_priority": "avoid",
                }
            },
        },
    )
    snapshot = build_stage_character_review_snapshot(story_bible, current_chapter_no=5)
    prompt = stage_character_review_user_prompt(snapshot)

    assert "casting_defer_diagnostics" in prompt
    assert "窗口太满 / 章法不顺 / 投放节奏安排不对" in prompt
    assert "recent_resolution_history" in prompt




def test_stage_review_uses_single_fixed_timeout_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = build_stage_character_review_snapshot(_story_bible(), current_chapter_no=5)
    calls: list[dict[str, int]] = []

    monkeypatch.setattr("app.services.openai_story_engine_review.is_openai_enabled", lambda: True)

    def _fake_call_json_response(**kwargs):
        calls.append({
            "timeout_seconds": int(kwargs.get("timeout_seconds") or 0),
            "max_output_tokens": int(kwargs.get("max_output_tokens") or 0),
        })
        return {
            "focus_characters": ["林秋雨"],
            "casting_strategy": "prefer_refresh_existing",
            "max_new_core_entries": 0,
            "max_role_refreshes": 1,
            "should_introduce_character": False,
            "candidate_slot_ids": [],
            "should_refresh_role_functions": True,
            "role_refresh_targets": ["林秋雨"],
            "role_refresh_suggestions": [{"character": "林秋雨", "suggested_function": "行动搭档", "reason": "别再只做提醒位"}],
            "next_window_tasks": ["抬旧人顶功能"],
            "watchouts": ["别把人物池塞太满"],
            "review_note": "下一窗口先抬旧人。",
        }

    monkeypatch.setattr("app.services.openai_story_engine_review.call_json_response", _fake_call_json_response)

    payload = review_stage_characters(snapshot=snapshot)

    assert payload.focus_characters == ["林秋雨"]
    assert len(calls) == 1
    assert calls[0]["timeout_seconds"] == 60
    assert calls[0]["max_output_tokens"] == 520


def test_stage_review_raises_after_single_timeout_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.generation_exceptions import ErrorCodes, GenerationError

    snapshot = build_stage_character_review_snapshot(_story_bible(), current_chapter_no=5)
    calls = {"count": 0}

    monkeypatch.setattr("app.services.openai_story_engine_review.is_openai_enabled", lambda: True)

    def _always_timeout(**kwargs):
        calls["count"] += 1
        raise GenerationError(
            code=ErrorCodes.API_TIMEOUT,
            message="timeout",
            stage="stage_character_review",
            retryable=True,
            http_status=503,
            provider="deepseek",
        )

    monkeypatch.setattr("app.services.openai_story_engine_review.call_json_response", _always_timeout)

    with pytest.raises(GenerationError) as exc_info:
        review_stage_characters(snapshot=snapshot)

    assert exc_info.value.code == ErrorCodes.API_TIMEOUT
    assert calls["count"] == 1

@pytest.fixture(autouse=True)
def _mock_stage_review_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.openai_story_engine.is_openai_enabled", lambda: True)
    monkeypatch.setattr("app.services.openai_story_engine.call_json_response", lambda **kwargs: {})
