from app.schemas.novel import NovelCreate
from app.services.story_architecture import build_control_console, build_execution_brief
def _payload() -> NovelCreate:
    return NovelCreate(
        genre="金手指修仙",
        premise="主角得到古镜后，被迫在边城里和各色人物周旋。",
        protagonist_name="方尘",
        style_preferences={"tone": "冷峻克制"},
    )
def test_execution_brief_includes_character_voice_pack_and_retrospective_feedback() -> None:
    payload = _payload()
    console = build_control_console(payload)
    console["character_cards"]["陈掌柜"] = {
        "name": "陈掌柜",
        "role_type": "supporting",
        "role_archetype": "表面温和型",
        "speech_style": "说话平稳，喜欢顺着话头套信息。",
        "work_style": "先安抚，再观察，最后突然收口。",
        "current_desire": "先把药铺的麻烦挡在门外。",
        "pressure_response": "越急越笑得淡。",
        "small_tell": "说到要紧处会把算盘珠拨慢半拍。",
        "taboo": "最怕失去体面。",
        "do_not_break": ["不能写成功能化掌柜"],
    }
    console["chapter_retrospectives"] = [
        {
            "chapter_no": 5,
            "core_problem": "上一章主角有点太被动。",
            "next_chapter_correction": "下一章要让主角主动试探陈掌柜。",
            "event_type": "试探类",
        }
    ]
    story_bible = {
        "project_card": {"genre_positioning": payload.genre},
        "volume_cards": [{"volume_no": 1, "start_chapter": 1, "end_chapter": 20, "main_conflict": "立足与藏锋", "cool_point": "第一次真正反制"}],
        "control_console": console,
        "serial_rules": {"fact_priority": ["已发布正文", "长期状态"]},
        "long_term_state": {"chapter_release_state": {"delivery_mode": "stockpile", "published_through": 3, "latest_available_chapter": 5}},
        "continuity_rules": ["不能重复同类桥段。"],
    }
    plan = {
        "goal": "主角主动试探陈掌柜的真实立场",
        "event_type": "试探类",
        "progress_kind": "关系推进",
        "proactive_move": "方尘故意抛出半真半假的线索",
        "payoff_or_pressure": "摸到陈掌柜真正害怕的人",
        "hook_kind": "关键人物动作",
        "supporting_character_focus": "陈掌柜",
    }
    brief = build_execution_brief(
        story_bible=story_bible,
        next_chapter_no=6,
        plan=plan,
        last_chapter_tail="门外的风停了一瞬。",
    )
    assert brief["character_voice_pack"]["name"] == "陈掌柜"
    assert "算盘珠" in brief["character_voice_pack"]["small_tell"]
    assert brief["chapter_retrospective_feedback"][0]["correction"].startswith("下一章")
def test_execution_brief_exposes_stage_casting_runtime_when_action_was_moved() -> None:
    payload = _payload()
    console = build_control_console(payload)
    story_bible = {
        "project_card": {"genre_positioning": payload.genre},
        "volume_cards": [{"volume_no": 1, "start_chapter": 1, "end_chapter": 20, "main_conflict": "立足与藏锋", "cool_point": "第一次真正反制"}],
        "control_console": console,
        "serial_rules": {"fact_priority": ["已发布正文", "长期状态"]},
        "long_term_state": {"chapter_release_state": {"delivery_mode": "stockpile", "published_through": 3, "latest_available_chapter": 5}},
        "continuity_rules": ["不能重复同类桥段。"],
        "active_arc": {
            "arc_no": 2,
            "start_chapter": 6,
            "end_chapter": 10,
            "chapters": [{"chapter_no": 6, "title": "照旧", "goal": "稳住局势"}, {"chapter_no": 7, "title": "换章落人", "goal": "把新人落稳", "stage_casting_action": "new_core_entry", "stage_casting_target": "slot_merchant"}],
            "casting_layout_review": {
                "window_verdict": "rearranged",
                "review_note": "补新人更适合放在局势稍缓的一章。",
                "chapter_adjustments": [
                    {"chapter_no": 6, "decision": "drop", "stage_casting_action": "new_core_entry", "stage_casting_target": "slot_merchant", "note": "这一章承压更重，人物投放先挪开。"},
                    {"chapter_no": 7, "decision": "move_here", "stage_casting_action": "new_core_entry", "stage_casting_target": "slot_merchant", "note": "这一章更适合自然落地人物投放动作。"},
                ],
            },
        },
    }
    plan = {
        "goal": "让新线索人物自然落地",
        "event_type": "布局类",
        "progress_kind": "人物投放",
        "stage_casting_action": "new_core_entry",
        "stage_casting_target": "slot_merchant",
        "stage_casting_review_note": "AI 把补新人从上一章挪到了这一章。",
        "planning_packet": {
            "chapter_stage_casting_hint": {
                "planned_action": "new_core_entry",
                "planned_target": "slot_merchant",
                "final_should_execute_planned_action": True,
                "final_do_not_force_action": False,
                "final_recommended_action": "execute_now",
                "chapter_hint": "本章可以自然落新核心位。",
            }
        },
    }
    brief = build_execution_brief(
        story_bible=story_bible,
        next_chapter_no=7,
        plan=plan,
        last_chapter_tail="夜色终于慢了下来。",
    )
    runtime = brief["chapter_execution_card"]["stage_casting_runtime"]
    assert runtime["carried_from_layout_review"] is True
    assert runtime["moved_from_chapter"] == 6
    assert "本章承接被挪来的补新人" in runtime["runtime_note"]
    assert "第6章→第7章" in "\n".join(brief["daily_workbench"]["chapter_stage_casting_runtime"]["display_lines"])
