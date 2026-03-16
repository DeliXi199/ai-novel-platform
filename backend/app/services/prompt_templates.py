import json
from typing import Any

from app.services.prompt_support import (
    compact_data,
    compact_json,
    pick_nonempty,
    render_prompt_modules,
    summarize_global_outline,
    summarize_interventions,
    summarize_novel_context,
    summarize_payload,
    summarize_recent_summaries,
    summarize_story_bible,
    summarize_chapter_plan,
    soft_sort_prompt_sections,
)


def _pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _compact_pretty(data: Any, *, max_depth: int = 2, max_items: int = 6, text_limit: int = 120) -> str:
    return compact_json(data, max_depth=max_depth, max_items=max_items, text_limit=text_limit)


def _payload_prompt_view(payload: dict[str, Any] | None) -> dict[str, Any]:
    return summarize_payload(payload)


def _story_bible_prompt_view(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    return summarize_story_bible(story_bible)


def _global_outline_prompt_view(global_outline: dict[str, Any] | None) -> dict[str, Any]:
    return summarize_global_outline(global_outline)


def _recent_summaries_prompt_view(recent_summaries: list[dict[str, Any]] | None, *, limit: int = 3) -> list[dict[str, Any]]:
    return summarize_recent_summaries(recent_summaries, limit=limit)


def _novel_context_prompt_view(novel_context: dict[str, Any] | None) -> dict[str, Any]:
    return summarize_novel_context(novel_context)


def _chapter_plan_prompt_view(chapter_plan: dict[str, Any] | None, *, include_packet: bool = False) -> dict[str, Any]:
    return summarize_chapter_plan(chapter_plan, include_packet=include_packet)


def _interventions_prompt_view(active_interventions: list[dict[str, Any]] | None, *, limit: int = 4) -> list[dict[str, Any]]:
    return summarize_interventions(active_interventions, limit=limit)


def _module_block(*module_ids: str, include_index: bool = False, stage: str = "", context: Any = None) -> str:
    return render_prompt_modules(module_ids, include_index=include_index, stage=stage, context=context)


def _soft_sorted_section_block(stage: str, context: dict[str, Any] | None, sections: list[dict[str, Any]]) -> str:
    ordered = soft_sort_prompt_sections(sections, stage=stage, context=context or {})
    bodies = [str(item.get("body") or "").strip() for item in ordered if str(item.get("body") or "").strip()]
    if not bodies:
        return ""
    return "【输入顺序说明】\n以下信息已做本地软排序：越靠前越值得优先参考，但后面的信息并未作废。\n\n" + "\n\n".join(bodies)


def _section_block(title: str, content: str) -> str:
    return f"【{title}】\n{content}"


def _core_cast_prompt_payload(story_bible: dict[str, Any], *, chapter_no: int = 1) -> dict[str, Any]:
    core_cast = (story_bible or {}).get("core_cast_state") or {}
    payload = {
        "profile": core_cast.get("profile"),
        "target_count": core_cast.get("target_count"),
        "anchored_target_count": core_cast.get("anchored_target_count"),
        "selection_note": core_cast.get("selection_note"),
        "anchored_characters": [],
        "slots": [],
    }
    for item in (core_cast.get("anchored_characters") or [])[:2]:
        if not isinstance(item, dict):
            continue
        payload["anchored_characters"].append(
            {
                "slot_id": item.get("slot_id"),
                "name": item.get("name"),
                "entry_phase": item.get("entry_phase"),
                "entry_chapter_window": item.get("entry_chapter_window"),
                "binding_pattern": item.get("binding_pattern"),
                "first_entry_mission": item.get("first_entry_mission"),
                "anchor_status": item.get("anchor_status"),
            }
        )
    for item in (core_cast.get("slots") or [])[:6]:
        if not isinstance(item, dict):
            continue
        payload["slots"].append(
            {
                "slot_id": item.get("slot_id"),
                "entry_phase": item.get("entry_phase"),
                "entry_chapter_window": item.get("entry_chapter_window"),
                "binding_pattern": item.get("binding_pattern"),
                "first_entry_mission": item.get("first_entry_mission"),
                "appearance_frequency": item.get("appearance_frequency"),
                "reserved_character": item.get("reserved_character"),
                "bound_character": item.get("bound_character"),
                "status": item.get("status"),
            }
        )
    return payload




def _stage_character_review_prompt_payload(story_bible: dict[str, Any], *, current_chapter_no: int | None = None) -> dict[str, Any]:
    review = {}
    if current_chapter_no is not None:
        try:
            from app.services.stage_review_support import stage_character_review_for_window
            review = stage_character_review_for_window(story_bible, current_chapter_no=current_chapter_no) or {}
        except Exception:
            review = {}
    if not isinstance(review, dict) or not review:
        review = ((((story_bible or {}).get("control_console") or {}).get("latest_stage_character_review")) or {})
    if not isinstance(review, dict) or not review:
        review = (((story_bible or {}).get("retrospective_state") or {}).get("latest_stage_character_review")) or {}
    if not isinstance(review, dict) or not review:
        return {}
    progress = review.get("window_progress") or {}
    return {
        "review_chapter": review.get("review_chapter"),
        "stage_range": [review.get("stage_start_chapter"), review.get("stage_end_chapter")],
        "next_window": [review.get("next_window_start"), review.get("next_window_end")],
        "focus_characters": review.get("focus_characters") or [],
        "priority_relation_ids": review.get("priority_relation_ids") or [],
        "casting_strategy": review.get("casting_strategy"),
        "max_new_core_entries": review.get("max_new_core_entries"),
        "max_role_refreshes": review.get("max_role_refreshes"),
        "candidate_slot_ids": review.get("candidate_slot_ids") or [],
        "next_window_tasks": review.get("next_window_tasks") or [],
        "watchouts": review.get("watchouts") or [],
        "window_progress": {
            "planned_new_core_entries": progress.get("planned_new_core_entries", 0),
            "reviewed_new_core_execute_now": progress.get("reviewed_new_core_execute_now", 0),
            "reviewed_new_core_deferred": progress.get("reviewed_new_core_deferred", 0),
            "executed_new_core_entries": progress.get("executed_new_core_entries", 0),
            "committed_new_core_entries": progress.get("committed_new_core_entries", 0),
            "new_core_limit_status": progress.get("new_core_limit_status", "open"),
            "planned_role_refreshes": progress.get("planned_role_refreshes", 0),
            "reviewed_role_refresh_execute_now": progress.get("reviewed_role_refresh_execute_now", 0),
            "reviewed_role_refresh_deferred": progress.get("reviewed_role_refresh_deferred", 0),
            "executed_role_refreshes": progress.get("executed_role_refreshes", 0),
            "committed_role_refreshes": progress.get("committed_role_refreshes", 0),
            "role_refresh_limit_status": progress.get("role_refresh_limit_status", "open"),
        },
        "casting_resolution_history": progress.get("casting_resolution_history", [])[:4],
        "review_note": review.get("review_note"),
        "source": review.get("source"),
    }


def _arc_casting_layout_review_prompt_payload(
    story_bible: dict[str, Any],
    *,
    start_chapter: int,
    end_chapter: int,
    recent_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    review = _stage_character_review_prompt_payload(story_bible, current_chapter_no=start_chapter - 1)
    try:
        from app.services.stage_review_support import build_stage_character_review_snapshot

        snapshot = build_stage_character_review_snapshot(
            story_bible,
            current_chapter_no=max(start_chapter - 1, 0),
            recent_summaries=recent_summaries or [],
        )
    except Exception:
        snapshot = {}
    diagnostics = (snapshot.get("casting_defer_diagnostics") or {}) if isinstance(snapshot, dict) else {}
    history = (review.get("casting_resolution_history") or []) if isinstance(review, dict) else []
    return {
        "window": {"start_chapter": int(start_chapter or 0), "end_chapter": int(end_chapter or 0)},
        "stage_review": review,
        "casting_defer_diagnostics": {
            "recent_deferred_count": int(diagnostics.get("recent_deferred_count", 0) or 0),
            "dominant_defer_cause": _text(diagnostics.get("dominant_defer_cause"))[:24] or None,
            "dominant_action_blocked": _text(diagnostics.get("dominant_action_blocked"))[:24] or None,
            "summary": _text(diagnostics.get("summary"))[:96] or None,
            "repeated_targets": list(diagnostics.get("repeatedly_deferred_targets") or [])[:3],
        },
        "recent_resolution_history": list(history or [])[:6],
    }

def _chapter_stage_casting_prompt_payload(planning_packet: dict[str, Any] | None) -> dict[str, Any]:
    hint = ((planning_packet or {}).get("chapter_stage_casting_hint") or {}) if isinstance(planning_packet, dict) else {}
    if not isinstance(hint, dict) or not hint:
        return {}
    return {
        "window": hint.get("window") or [],
        "casting_strategy": hint.get("casting_strategy"),
        "planned_action": hint.get("planned_action"),
        "planned_target": hint.get("planned_target"),
        "should_execute_planned_action": bool(hint.get("should_execute_planned_action")),
        "do_not_force_action": bool(hint.get("do_not_force_action")),
        "recommended_action": hint.get("recommended_action"),
        "action_priority": hint.get("action_priority"),
        "ai_stage_casting_verdict": hint.get("ai_stage_casting_verdict"),
        "ai_stage_casting_reason": hint.get("ai_stage_casting_reason"),
        "ai_should_execute_planned_action": hint.get("ai_should_execute_planned_action"),
        "ai_do_not_force_action": hint.get("ai_do_not_force_action"),
        "final_should_execute_planned_action": hint.get("final_should_execute_planned_action", hint.get("should_execute_planned_action")),
        "final_do_not_force_action": hint.get("final_do_not_force_action", hint.get("do_not_force_action")),
        "final_recommended_action": hint.get("final_recommended_action", hint.get("recommended_action")),
        "final_action_priority": hint.get("final_action_priority", hint.get("action_priority")),
        "new_core_remaining": hint.get("new_core_remaining"),
        "role_refresh_remaining": hint.get("role_refresh_remaining"),
        "new_core_limit_status": hint.get("new_core_limit_status"),
        "role_refresh_limit_status": hint.get("role_refresh_limit_status"),
        "candidate_slot_ids": hint.get("candidate_slot_ids") or [],
        "role_refresh_targets": hint.get("role_refresh_targets") or [],
        "chapter_hint": hint.get("chapter_hint"),
        "watchouts": hint.get("watchouts") or [],
    }


def _flow_template_prompt_payload(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    template_library = (story_bible or {}).get("template_library") or {}
    flow_templates = template_library.get("flow_templates") or []
    payload: list[dict[str, Any]] = []
    for item in flow_templates:
        if not isinstance(item, dict):
            continue
        payload.append(
            {
                "flow_template_id": _text(item.get("flow_id")),
                "quick_tag": _text(item.get("quick_tag")),
                "name": _text(item.get("name")),
                "when_to_use": _text(item.get("when_to_use") or (item.get("applicable_scenes") or [""])[0]),
                "preferred_event_types": list(item.get("preferred_event_types") or []),
                "preferred_progress_kinds": list(item.get("preferred_progress_kinds") or []),
            }
        )
        if len(payload) >= 20:
            break
    return payload


GLOBAL_OUTLINE_SCHEMA = {
    "story_positioning": {
        "tone": "根据题材决定，例如慢热/凌厉/热血/诡谲",
        "core_promise": "前期建立主角处境与主线引擎，中期扩大地图、对手与资源层级。",
    },
    "acts": [
        {
            "act_no": 1,
            "title": "入局",
            "purpose": "建立主角处境、第一轮目标、代价与主要矛盾",
            "target_chapter_end": 12,
            "summary": "主角在初始舞台拿到第一阶段主动权，并被推向更大的局势。",
        }
    ],
}


ARC_OUTLINE_SCHEMA = {
    "arc_no": 1,
    "start_chapter": 1,
    "end_chapter": 3,
    "focus": "建立当前阶段目标、验证能力或机缘、抬高代价",
    "bridge_note": "这一小段要完成承接，并把下一轮冲突轻轻推上来。",
    "chapters": [
        {
            "chapter_no": 1,
            "title": "初入局中",
            "chapter_type": "probe",
            "event_type": "发现类",
            "progress_kind": "信息推进",
            "proactive_move": "主角主动试探并确认关键异常",
            "payoff_or_pressure": "拿到一条新线索，同时暴露一层新风险",
            "goal": "让主角面对第一轮具体问题或机会",
            "conflict": "目标出现，但获取它需要付出可感知的代价",
            "ending_hook": "新的方向、风险或人物介入被确认",
            "hook_style": "信息反转",
            "hook_kind": "新发现",
            "main_scene": "当前阶段最能承载冲突的核心场景",
            "supporting_character_focus": "关键配角名",
            "supporting_character_note": "他说话和做事要有辨识度",
            "new_resources": ["本章首次引入的新资源名，可省略"],
            "new_factions": ["本章首次引入的新势力名，可省略"],
            "new_relations": [
              {
                "subject": "关系一方",
                "target": "关系另一方",
                "relation_type": "互相试探/暂时合作/结怨",
                "status": "刚建立",
                "recent_trigger": "因本章事件首次连上"
              }
            ],
            "flow_template_id": "probe_gain",
            "flow_template_tag": "试一试",
            "flow_template_name": "试探获益",
            "stage_casting_action": "new_core_entry",
            "stage_casting_target": "CC03",
            "stage_casting_note": "这一章负责让一个新核心位落地；若本轮没有这种任务就省略这三个字段"
        }
    ],
}


INSTRUCTION_OUTPUT_SCHEMA = {
    "character_focus": {"角色名": 1.5},
    "tone": "lighter | darker | warmer | tenser | null",
    "pace": "faster | slower | null",
    "protected_characters": ["角色名"],
    "relationship_direction": "slow_burn | stronger_romance | weaker_romance | null",
}


CARD_SELECTION_SCHEMA = {
    "selected_card_ids": ["C001", "R003", "REL002"],
    "selection_note": "优先保留主角、焦点人物和本章真正会动到的资源/关系。",
}


CHARACTER_RELATION_SCHEDULE_REVIEW_SCHEMA = {
    "focus_characters": ["主角名", "本章焦点配角名"],
    "supporting_characters": ["适合辅助推进的角色名"],
    "defer_characters": ["本章最好暂缓抢戏的角色名"],
    "main_relation_ids": ["人物A::人物B"],
    "light_touch_relation_ids": ["人物A::人物C"],
    "defer_relation_ids": ["人物D::人物E"],
    "interaction_depth_overrides": {"人物A::人物B": "深互动"},
    "relation_push_overrides": {"人物A::人物B": "合作推进"},
    "stage_casting_verdict": "execute_now | defer_to_next | soft_consider | hold_steady",
    "should_execute_stage_casting_action": False,
    "do_not_force_stage_casting_action": True,
    "stage_casting_reason": "一句话说明本章是否适合承担补新人或旧人换功能动作。",
    "review_note": "一句话说明本章人物与关系推进重心。",
}


STAGE_CHARACTER_REVIEW_SCHEMA = {
    "stage_start_chapter": 1,
    "stage_end_chapter": 5,
    "next_window_start": 6,
    "next_window_end": 10,
    "focus_characters": ["主角名", "关键配角名"],
    "supporting_characters": ["适合辅助推进的角色名"],
    "defer_characters": ["本轮最好暂缓抢戏的角色名"],
    "priority_relation_ids": ["人物A::人物B"],
    "light_touch_relation_ids": ["人物A::人物C"],
    "defer_relation_ids": ["人物D::人物E"],
    "casting_strategy": "prefer_refresh_existing",
    "casting_strategy_note": "这一轮更适合先抬旧人顶功能，不要新人旧人一起挤。",
    "max_new_core_entries": 0,
    "max_role_refreshes": 1,
    "should_introduce_character": False,
    "candidate_slot_ids": [],
    "should_refresh_role_functions": True,
    "role_refresh_targets": ["关键配角名"],
    "role_refresh_suggestions": [
        {
            "character": "关键配角名",
            "suggested_function": "行动搭档",
            "reason": "避免继续只做传话或提醒功能"
        }
    ],
    "next_window_tasks": ["下一规划窗口优先补推进某个核心配角"],
    "watchouts": ["避免关键配角继续工具人化"],
    "review_note": "一句话说明接下来五章的人物与关系推进重心。"
}


ARC_CASTING_LAYOUT_REVIEW_SCHEMA = {
    "window_verdict": "keep_current_layout | shift_actions | simplify_actions | hold_steady",
    "chapter_adjustments": [
        {
            "chapter_no": 6,
            "decision": "move_here",
            "stage_casting_action": "role_refresh",
            "stage_casting_target": "林秋雨",
            "note": "这一章更适合承担旧角色换功能，前后承接更顺。"
        },
        {
            "chapter_no": 7,
            "decision": "drop",
            "stage_casting_action": "role_refresh",
            "stage_casting_target": "林秋雨",
            "note": "这一章冲突太满，先别硬塞。"
        }
    ],
    "avoid_notes": ["补新人不要落在危机爆发章", "上一章刚被 defer 的同类动作别原样重排"],
    "review_note": "一句话说明这五章里人物投放动作怎么排更顺。"
}


TITLE_REFINEMENT_SCHEMA = {
    "recommended_title": "门后那张欠条",
    "candidates": [
        {
            "title": "门后那张欠条",
            "title_type": "结果型",
            "angle": "把本章落点落在可感知的新信息或新后果上",
            "reason": "标题要具体，不要空泛氛围词，也不要与最近章节撞车。"
        }
    ],
}

STORY_ENGINE_DIAGNOSIS_SCHEMA = {
    "story_subgenres": ["凡人苟道修仙", "资源求生流"],
    "primary_story_engine": "低位求生 + 资源争取 + 谨慎试探",
    "secondary_story_engine": "异常线索慢兑现",
    "opening_drive": "先稳住立足点，再试探异常与机会",
    "early_hook_focus": "用现实压力和第一次有效收益把读者钉住",
    "protagonist_action_logic": "先观察、再判断、再有限出手，关键时必须主动选择",
    "pacing_profile": "慢热但章章有结果",
    "world_reveal_strategy": "先讲眼前规则，再逐步抬到更高层地图与势力",
    "power_growth_strategy": "成长要绑定资源、代价和风险暴露，不走纯数值冲级",
    "early_must_haves": ["明确现实压力", "第一轮有效收益", "可持续主线入口"],
    "avoid_tropes": ["药铺捡残页", "夜探坊市后被掌柜起疑", "连续多章只围着同一线索试探"],
    "differentiation_focus": ["把题材独特卖点写成前10章就能感到的差异"],
    "must_establish_relationships": ["与主角形成长期牵引的关键人物关系"],
    "tone_keywords": ["克制", "具体", "有代价"],
}


STORY_STRATEGY_CARD_SCHEMA = {
    "story_promise": "前30章要让读者明确感到：这本书的推进方式和常规模板不同。",
    "strategic_premise": "主角要在现实压力、资源缺口和更大局势之间找到可持续上升路径。",
    "main_conflict_axis": "立足需求与暴露风险的长期拉扯",
    "first_30_mainline_summary": "前30章围绕立足、试错、关系绑定与阶段破局推进，不让同一桥段垄断。",
    "chapter_1_to_10": {
        "range": "1-10",
        "stage_mission": "用题材最有辨识度的推进方式抓住读者",
        "reader_hook": "第一轮可感收益 + 明确代价",
        "frequent_elements": ["现实压力", "主动试探", "具体结果"],
        "limited_elements": ["重复盘问", "连续隐藏同一秘密"],
        "relationship_tasks": ["建立至少一条会长期变化的关键关系"],
        "phase_result": "主角拿到第一阶段立足资本，并被推向更大局势",
    },
    "chapter_11_to_20": {
        "range": "11-20",
        "stage_mission": "扩大地图、对手和关系压力",
        "reader_hook": "阶段收益之后出现更高位风险或更大诱惑",
        "frequent_elements": ["关系变化", "资源争夺", "局势升级"],
        "limited_elements": ["原地踏步试探"],
        "relationship_tasks": ["让关键配角关系发生第一次实质变化"],
        "phase_result": "主角失去一部分原有安全区，但获得新的行动空间",
    },
    "chapter_21_to_30": {
        "range": "21-30",
        "stage_mission": "做出前30章的阶段高潮与方向确认",
        "reader_hook": "更大的地图、规则或敌意被清楚打开",
        "frequent_elements": ["阶段破局", "主动布局", "关系站队"],
        "limited_elements": ["只靠气氛拖章"],
        "relationship_tasks": ["把至少一条关系推入不可逆的新状态"],
        "phase_result": "主角从开书状态进入新的故事层级",
    },
    "frequent_event_types": ["资源获取类", "关系推进类", "反制类"],
    "limited_event_types": ["连续被怀疑后被动应付"],
    "must_establish_relationships": ["核心绑定角色", "长期压迫源", "阶段性合作对象"],
    "escalation_path": ["处境压力", "局部破局", "关系重组", "阶段高潮"],
    "anti_homogenization_rules": ["不要让前三十章只围着一个物件转", "每个阶段都要换推进重心"],
}


STORY_ENGINE_STRATEGY_BUNDLE_SCHEMA = {
    "story_engine_diagnosis": STORY_ENGINE_DIAGNOSIS_SCHEMA,
    "story_strategy_card": STORY_STRATEGY_CARD_SCHEMA,
}



def _style_preferences_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = (payload or {}).get("style_preferences")
    return raw if isinstance(raw, dict) else {}



def _combined_story_text(payload: dict[str, Any] | None) -> str:
    style = _style_preferences_from_payload(payload)
    parts = [
        str((payload or {}).get("genre") or ""),
        str((payload or {}).get("premise") or ""),
        str(style.get("tone") or ""),
        str(style.get("story_engine") or style.get("opening_mode") or ""),
        str(style.get("sell_point") or ""),
    ]
    return " ".join(part for part in parts if part).lower()



def _opening_guidance(payload: dict[str, Any] | None) -> str:
    style = _style_preferences_from_payload(payload)
    explicit = str(style.get("opening_guidance") or style.get("story_engine") or style.get("opening_mode") or "").strip()
    if explicit:
        return explicit
    story_text = _combined_story_text(payload)
    if any(token in story_text for token in ["金手指", "机缘", "外挂", "神器"]):
        return "前期可以较早兑现机缘、能力试错、升级反馈或爽点，但仍要写清限制、代价与后续压力。"
    if any(token in story_text for token in ["凡人", "苟", "低调", "求生"]):
        return "前期更适合从求生、资源、试探与隐藏推进，慢慢抬高风险，不必急着拉满奇观。"
    if any(token in story_text for token in ["宗门", "学院", "试炼", "天才", "大比"]):
        return "前期可以更早切入宗门、试炼、比斗、同辈竞争与成长反馈，不必硬压成纯线索调查。"
    return "前期围绕主角处境、第一轮目标、阶段性收益与代价展开，不要默认收缩成单一线索物件探秘。"



def _variety_guidance(payload: dict[str, Any] | None) -> str:
    style = _style_preferences_from_payload(payload)
    explicit = str(style.get("variety_guidance") or "").strip()
    if explicit:
        return explicit
    return (
        "前20章要在以下功能之间轮换：立足、获得资源、验证能力、关系推进、训练/试错、地图推进、势力接触、小冲突或局部破局，并逐步补清世界、势力与实力等级体系。"
        "不要连续多章都只是围绕同一件线索物反复试探。"
        "最近两章若已经用了同一类桥段，下一章必须主动换事件类型、换推进结果、换结尾钩子。"
    )



def _protagonist_name_from_context(novel_context: dict[str, Any] | None) -> str:
    project_card = (novel_context or {}).get("project_card") or {}
    protagonist = project_card.get("protagonist") or {}
    if isinstance(protagonist, dict):
        name = str(protagonist.get("name") or "").strip()
        if name:
            return name
    return "主角"



def _genre_positioning_from_context(novel_context: dict[str, Any] | None) -> str:
    project_card = (novel_context or {}).get("project_card") or {}
    return str(project_card.get("genre_positioning") or "").strip()



def _chapter_genre_guidance(novel_context: dict[str, Any] | None) -> str:
    story_text = _genre_positioning_from_context(novel_context).lower()
    if any(token in story_text for token in ["凡人", "苟", "低调", "求生"]):
        return "如果题材偏凡人流，就强调资源、风险、谨慎与代价，而不是宏大奇观。"
    if any(token in story_text for token in ["金手指", "机缘", "外挂", "神器"]):
        return "如果题材偏金手指修仙，可以更明确地写机缘兑现、能力反馈与成长快感，但要让限制、消耗与副作用可见。"
    if any(token in story_text for token in ["宗门", "试炼", "学院", "大比"]):
        return "如果题材偏宗门成长或试炼流，可以更早写竞争、考核、师承与修行反馈，不必强压成纯线索探秘。"
    return "按 project_card 的题材定位写，不要默认套进药铺、残页、坊市试探这一类固定开局模板。"


REPETITION_BLACKLIST = [
    "他今晚冒险来到这里，只为一件事",
    "可就在他以为今夜只能带着这点收获先退一步时",
    "在凡人流修仙这样的处境里",
    "上一章《",
    "真正麻烦的不是东西本身",
    "不是错觉",
    "心跳快了几分",
    "盯着某处看了片刻",
    "若有若无",
    "微弱的暖意",
    "温凉的触感",
    "微弱",
    "温凉",
    "几息",
    "没有再说什么",
]



def story_engine_strategy_bundle_system_prompt() -> str:
    return (
        "你是一名擅长中文网文立项与开局规划的总编。"
        "你的任务是一次性完成题材拆解和前30章推进设计。"
        "输出要像编辑部的紧凑指挥卡，不要写正文，不要解释。"
        "为了提速和稳定，请优先使用短字段、短句子、短列表。"
        "你只能输出一个合法 JSON 对象，不要输出 markdown。"
    )


def story_engine_strategy_bundle_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请一次性生成这本小说的“题材画像 + 前30章推进引擎”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这是初始化快照，不写正文，不写散文式分析，只给后续规划可直接使用的结构卡。
2. 输出必须只包含两个顶层键：story_engine_diagnosis、story_strategy_card。
3. story_engine_diagnosis 负责回答：这本书属于什么更细子类型、前期真正该靠什么推进、最该避开什么老套路。
4. story_strategy_card 负责回答：前30章分三个阶段怎么跑、每阶段靠什么抓人、哪些元素常用、哪些必须少用。
5. 所有字段尽量短，单条列表尽量控制在 2 到 4 项，避免长篇解释。
6. 除非开书信息明确要求，否则不要默认写成“药铺 / 坊市 / 残页 / 掌柜起疑 / 夜探试探”这一类固定开局组合。
7. 只输出 JSON，对象 schema 如下：
{_pretty(STORY_ENGINE_STRATEGY_BUNDLE_SCHEMA)}
""".strip()


def story_engine_diagnosis_system_prompt() -> str:
    return (
        "你是一名擅长中文网文立项的总编。"
        "你的任务不是写正文，而是先判断这本书真正属于哪种叙事发动机。"
        "你要帮助系统避免不同修仙题材被写成同一种剧情习惯。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def story_engine_diagnosis_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请先为下面这本小说做“题材拆解 + 叙事引擎判断”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这一步只判断题材画像和叙事引擎，不写剧情正文。
2. 优先回答：这本书最像哪几种子类型；前期真正该靠什么推进；最容易掉进哪些老套路。
3. story_subgenres 要尽量具体，尤其是修仙题材，不要只写“修仙”。
4. primary_story_engine 要写成真正的故事发动机，不要只写风格词。
5. opening_drive / early_hook_focus / protagonist_action_logic 要能够直接指导后面的全书规划。
6. avoid_tropes 至少列出 3 条，必须是这本书最该主动避开的同质化桥段。
7. differentiation_focus 要回答：这本书前10章最该让读者感受到什么独特味道。
8. must_establish_relationships 要回答：前期必须尽早建立哪些关系类型。
9. 字段尽量短，列表尽量控制在 2 到 4 项。
10. 只输出 JSON，对象 schema 如下：
{_pretty(STORY_ENGINE_DIAGNOSIS_SCHEMA)}
""".strip()


def story_strategy_card_system_prompt() -> str:
    return (
        "你是一名擅长中文连载网文开局设计的策划编辑。"
        "你的任务是把全书方向和前30章推进引擎设计清楚。"
        "你要输出的是创作指挥卡，不是正文，不是散文式解释。"
        "为了提速和稳定，请优先输出短字段、短句子、短列表。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def story_strategy_card_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请基于下面信息，生成“全书战略图 + 前30章推进引擎卡”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这一步的重点是：让系统知道这本书前30章应该怎么跑，而不是每章临时想。
2. story_promise 要写清楚读者持续追更能得到什么核心体验。
3. strategic_premise 要写清楚整本书长期怎么推进。
4. first_30_mainline_summary 要写成一句可执行的阶段主线描述。
5. chapter_1_to_10 / chapter_11_to_20 / chapter_21_to_30 都要写出阶段任务、读者钩子、常用元素、少用元素、关系任务和阶段结果。
6. frequent_event_types / limited_event_types 既可以是事件类别，也可以是推进方式，但必须能指导后续近纲。
7. anti_homogenization_rules 要明确指出如何避免写成常见模板。
8. 除非开书信息明确要求，否则不要默认前30章都围绕药铺、坊市、残页、掌柜起疑、夜半试探这种固定组合。
9. 只输出 JSON，对象 schema 如下：
{_pretty(STORY_STRATEGY_CARD_SCHEMA)}
""".strip()


def global_outline_system_prompt() -> str:
    return (
        "你是一名擅长中文长篇连载规划的策划编辑。"
        "你的任务是做高层故事规划，而不是写正文。"
        "你必须给出稳定、可执行、贴合题材的全书粗纲。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )



def global_outline_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any], total_acts: int) -> str:
    return f"""
请为下面这本小说生成一个全书粗纲。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【故事圣经】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 只做高层规划，共 {total_acts} 个 act。
   story_bible 里的 story_engine_diagnosis / story_strategy_card 是高优先级约束，粗纲必须与它们一致。
2. 每个 act 只写 title、purpose、target_chapter_end、summary。
3. 语气必须克制，不要空泛宏大，不要世界观堆砌。
4. 开局导向请遵守：{_opening_guidance(payload)}
5. 目标是让后续小弧线有稳定方向，而不是一开始就爆大场面。
6. 除非开书信息明确要求，否则不要默认开局是“药铺捡残页/夜探坊市/掌柜起疑”这一类固定套路。
7. 只输出 JSON，对象 schema 如下：
{_pretty(GLOBAL_OUTLINE_SCHEMA)}
""".strip()



def arc_outline_system_prompt() -> str:
    return (
        "你是一名中文连载小说的弧线策划编辑。"
        "你的任务是根据全书粗纲和当前进度，生成未来几章的小弧线。"
        "这一步只做紧凑拍表，不写正文，不写解释。"
        "为了保证稳定，请优先输出短字段、短句子、紧凑 JSON。"
        "严禁输出 markdown、代码块、说明文字或多余前后缀。"
        "你只能输出一个合法 JSON 对象。"
    )



def arc_outline_user_prompt(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    start_chapter: int,
    end_chapter: int,
    arc_no: int,
) -> str:
    return f"""
请为这本小说生成第 {start_chapter} 章到第 {end_chapter} 章的小弧线拍表。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【故事圣经】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

【全书粗纲】
{_compact_pretty(_global_outline_prompt_view(global_outline), max_depth=3, max_items=8, text_limit=100)}

【最近章节摘要】
{_compact_pretty(_recent_summaries_prompt_view(recent_summaries, limit=4), max_depth=3, max_items=6, text_limit=100)}

【可选章节流程模板】
{_pretty(_flow_template_prompt_payload(story_bible))}

【最近已使用流程】
{_pretty((((story_bible or {}).get("flow_control") or {}).get("recent_flow_ids") or []))}

【核心配角名额规划】
{_compact_pretty(_core_cast_prompt_payload(story_bible, chapter_no=start_chapter), max_depth=3, max_items=8, text_limit=90)}

【阶段性人物复盘（若有）】
{_compact_pretty(_stage_character_review_prompt_payload(story_bible, current_chapter_no=start_chapter - 1), max_depth=3, max_items=8, text_limit=86)}

【最近人物投放回写（若有）】
{_compact_pretty((_stage_character_review_prompt_payload(story_bible, current_chapter_no=start_chapter - 1).get("casting_resolution_history") or []), max_depth=3, max_items=6, text_limit=80)}

要求：
1. 这是第 {arc_no} 个 arc，只覆盖第 {start_chapter}-{end_chapter} 章。
2. 每章尽量只输出这些键：chapter_no、title、chapter_type、event_type、progress_kind、proactive_move、payoff_or_pressure、goal、conflict、ending_hook、hook_style、hook_kind、main_scene、supporting_character_focus、supporting_character_note、new_resources、new_factions、new_relations、flow_template_id、flow_template_tag、flow_template_name，以及仅在需要时才输出的 stage_casting_action、stage_casting_target、stage_casting_note。
3. title、goal、conflict、ending_hook、main_scene 都尽量简短，单项最好不超过 28 个汉字。
4. chapter_type 只允许 probe / progress / turning_point。
5. event_type 必须从这些里选最贴切的一种：发现类 / 试探类 / 交易类 / 冲突类 / 潜入类 / 逃避类 / 资源获取类 / 反制类 / 身份伪装类 / 关系推进类 / 外部任务类 / 危机爆发。
6. progress_kind 必须从这些里选最贴切的一种：信息推进 / 关系推进 / 资源推进 / 实力推进 / 风险升级 / 地点推进。
7. proactive_move 要明确写出主角本章主动做什么，不能只是“谨慎应对”。
8. payoff_or_pressure 要明确写出本章给读者的兑现或压力升级，不能空泛。
9. hook_style 只允许：异象 / 人物选择 / 危险逼近 / 信息反转 / 平稳过渡 / 余味收束。
10. hook_kind 至少贴近以下之一：新发现 / 新威胁 / 新任务 / 身份暴露风险 / 古镜异常反应 / 更大谜团 / 关键人物动作 / 意外收获隐患。
11. 每章都必须从【可选章节流程模板】里选一个最贴切的 flow_template_id，并同步写出对应的 flow_template_tag、flow_template_name。
12. 若【最近已使用流程】里刚出现过某个 flow_template_id，下一章默认不要继续用它；除非剧情性质明显变了，否则禁止连续多章重复同一流程。
13. 若同一 arc 里已经连续两章用了同一主事件类型，下一章必须换 event_type，禁止出现连续三章都在“被怀疑—应付—隐藏”或“发现异常—隐藏秘密—再被盘问”的重复结构。
14. 这一步只做紧凑近纲，不要输出 opening_beat、mid_turn、discovery、closing_image、writing_note 这类长字段；后续章节执行卡阶段会再补全。
14.1 只有当本章会首次引入新资源、新势力或新关系时，才额外输出 new_resources / new_factions / new_relations；不用时就省略。
14.2 new_resources 与 new_factions 只写名字，不要写解释；new_relations 最多 3 条，每条只写 subject、target、relation_type、status、recent_trigger 这些短字段。
15. 节奏要贴合题材定位，每章只推进一个主冲突，但必须明确本章新增了什么，不要重复同一意象和同一动作模板。
16. 核心机缘、线索、目标物或关键关系的状态要稳定，但不要默认它一定是残页、古卷、地图、碎片或石头。
17. supporting_character_note 不能只写“有辨识度”，要具体到说话风格、私心、受压反应、小动作或忌讳中的至少两项。
17.1 若故事仍在 opening_phase_chapter_range 内，必须参考 opening_constraints.foundation_reveal_schedule / power_system_reveal_plan，让前20章逐步交代世界、势力与实力等级体系；每章只补当前章该补的一层，不要灌说明书。
17.2 若 story_bible 里已经提供 template_library.character_templates，就尽量让 supporting_character_note 贴着人物模板维度写，至少让说话方式、行为模式、受压反应三者里落两项。
18. 若最近章节已经出现“配角只负责盘问/警告/发任务”的倾向，下一章要把关键配角改成更像人：先有立场和算盘，再推动剧情。
18.1 若【核心配角名额规划】里已经给了 anchored_characters / reserved_character，就优先把这些前期已实体化的人物按窗口自然落地；若仍有未绑定且已到窗口的 slot，再在其中挑一个最合适的去落地，不要把所有重要配角都挤到前面。
18.2 已绑定或已预实体化的核心配角都要按 appearance_frequency 分批推进：没到窗口先压着蓄势，到了窗口就别长期失踪。
18.3 若【阶段性人物复盘】提供了 focus_characters / priority_relation_ids / next_window_tasks，把它当成当前五章规划的前置建议：优先兑现，但不要硬塞到每一章。
18.4 若【阶段性人物复盘】提醒某角色先暂缓或某关系只轻触，就避免在这一小段里连续硬推同一条人物线。
18.5 若【阶段性人物复盘】给出 casting_strategy=prefer_refresh_existing，就先抬旧人顶功能，默认这五章不要再落新核心位。
18.6 若【阶段性人物复盘】给出 casting_strategy=introduce_one_new，就只补一个新人接线；candidate_slot_ids 里最多选一个窗口最合适的去落地。
18.7 若【阶段性人物复盘】给出 casting_strategy=balanced_light，可以同时做“补新人”和“旧人换功能”，但要错开章节，别同章双塞。
18.8 若【阶段性人物复盘】建议 should_refresh_role_functions=true，就在接下来的五章里给 role_refresh_targets 对应角色换一种更能带剧情的作用位；别让他继续只做传话、盘问、警告或发任务。
18.9 max_new_core_entries 与 max_role_refreshes 是硬上限，规划时要遵守，默认都不要超过 1。
18.10 只有当某章真的承担“落新核心位”或“旧角色换功能”任务时，才输出 stage_casting_action / stage_casting_target / stage_casting_note；否则省略。
18.11 stage_casting_action 只允许：new_core_entry / role_refresh。若是 new_core_entry，stage_casting_target 必须来自 candidate_slot_ids；若是 role_refresh，stage_casting_target 必须来自 role_refresh_targets。
18.12 若【阶段性人物复盘】里的 window_progress 已显示对应名额 full / exceeded，就不要再新增同类动作；若是 balanced_light，也要把 new_core_entry 与 role_refresh 错开章节。
18.13 若【阶段性人物复盘】里的 casting_resolution_history 显示前一章原计划承担人物投放动作，但 AI 复核后被 defer / hold，就先尊重这个延后结果，别在后一章又机械原样重复同一动作，除非章法明显更顺。
19. 如果 story_bible 里有 story_strategy_card，且当前章节落在 1-30 章内，要优先贴合对应阶段（1-10 / 11-20 / 21-30）的 stage_mission、reader_hook、relationship_tasks 与 anti_homogenization_rules。
20. {_variety_guidance(payload)}
21. title 不要与最近十几章常见标题重复，避免再次出现“夜半微光/旧纸页/坊市试探”这类高相似标题。
22. 除非开书信息明确要求，否则不要把场景反复锁在药铺、后院、坊市、夜半试探这种固定组合。
23. 不要大场面堆砌，不要一口气揭露终极秘密。
24. 配角不是功能按钮；若某章有关键配角，supporting_character_note 要写出他的说话方式、私心、顾虑、受压反应或做事风格。
25. 不要输出任何解释、前缀、后缀、代码块或注释，只输出 JSON。
26. 对象 schema 如下：
{_pretty(ARC_OUTLINE_SCHEMA)}
""".strip()



def arc_casting_layout_review_system_prompt() -> str:
    return (
        "你是一名中文连载小说的小弧线排法复核编辑。"
        "你的任务不是重写五章规划，而是复核这五章里的人物投放动作排得顺不顺。"
        "你只关心补新人、旧角色换功能这类动作该落在哪一章更自然。"
        "若这轮更适合稳住，就明确说稳住；若需要换章落地，就指出更合适的章节。"
        "只输出一个合法 JSON 对象，不要输出 markdown、解释或多余前后缀。"
    )


def arc_casting_layout_review_user_prompt(
    *,
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    arc_bundle: dict[str, Any],
) -> str:
    start_chapter = int((arc_bundle or {}).get("start_chapter", 0) or 0)
    end_chapter = int((arc_bundle or {}).get("end_chapter", 0) or 0)
    return f"""
请复核第 {start_chapter} 章到第 {end_chapter} 章这段五章窗口里的人物投放排法。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【故事圣经】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

【全书粗纲】
{_compact_pretty(_global_outline_prompt_view(global_outline), max_depth=3, max_items=8, text_limit=100)}

【最近章节摘要】
{_compact_pretty(_recent_summaries_prompt_view(recent_summaries, limit=4), max_depth=3, max_items=6, text_limit=100)}

【当前五章窗口与阶段复盘】
{_compact_pretty(_arc_casting_layout_review_prompt_payload(story_bible, start_chapter=start_chapter, end_chapter=end_chapter, recent_summaries=recent_summaries), max_depth=3, max_items=8, text_limit=90)}

【当前小弧线拍表】
{_compact_pretty(arc_bundle, max_depth=3, max_items=10, text_limit=92)}

要求：
1. 你只复核“补新人 / 旧角色换功能”这类人物投放动作的章节排法，不要重写整段五章规划。
2. 若当前排法已经顺，就保持 keep_current_layout。
3. 若最近同类动作总被 defer，先判断问题更像：窗口太满、章法不顺，还是动作落点排错。
4. 若问题是“落点排错”，可以把动作移到更适合承接人物线的那一章；更适合的通常是：信息更聚焦、关系更能落地、不是危机最满的那章。
5. chapter_adjustments 只改需要改的章节；不需要改的章节不要硬写。
6. decision 只允许：keep / move_here / drop / soft_consider。
7. stage_casting_action 只允许：new_core_entry / role_refresh。若 decision=drop，也保留原 action 和 target，方便系统知道你在取消什么。
8. 若阶段复盘显示这轮 should_introduce_character=false，就不要再给 new_core_entry 找新落点。若 should_refresh_role_functions=false，也不要硬排 role_refresh。
9. 若 window_progress 里同类名额已 full / exceeded，就不要继续给它找落点。
10. balanced_light 时，new_core_entry 与 role_refresh 要错开章节，别同章双塞。
11. 若上一章同类动作刚被 defer / hold，后一章不要机械原样重复，除非这一章的章法明显更顺。
12. review_note 要用一句话说清：这五章里人物投放动作怎么排更顺。
13. 只输出 JSON，对象 schema 如下：
{_pretty(ARC_CASTING_LAYOUT_REVIEW_SCHEMA)}
""".strip()


def json_repair_system_prompt() -> str:
    return (
        "你是一个 JSON 修复器。"
        "你不会补写故事，不会改写设定，只会把已有内容整理成合法 JSON。"
        "必须尽量保留原字段与原意。"
        "如果原文已经截断，就只保留仍然确定的字段，不要虚构长内容。"
        "只输出一个合法 JSON 对象，不要输出 markdown，不要解释。"
    )



def json_repair_user_prompt(stage: str, raw_text: str) -> str:
    return f"""
下面是一段模型原始输出，它本来应该是 {stage} 阶段的 JSON，但现在格式损坏、可能被截断、或混入了多余文本。

请你做的事只有一件：
把它修成一个合法 JSON 对象。

要求：
1. 尽量保留原字段、原顺序和原语义。
2. 如果某个字段明显被截断且无法可靠恢复，就删除该字段，不要编造长文本。
3. 不要补写正文，不要扩写剧情。
4. 不要输出代码块、解释、前后缀。
5. 只输出修好的 JSON 对象。

【原始输出】
{raw_text}
""".strip()





def stage_character_review_system_prompt() -> str:
    return """
你是“阶段性人物复盘器”。你的任务是在不改变现有五章规划节奏的前提下，先对刚完成的一小段章节做人和关系的阶段复盘，给下一规划窗口一个前置建议。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. 你做的是“复盘 + 下一窗口建议”，不是重写大纲，也不是写正文。
3. focus_characters 通常 1-4 人；priority_relation_ids 通常 0-3 条。
4. 先判断下一规划窗口到底更适合“补新人接线”还是“抬旧人顶功能”；默认优先选一个主方向，不要两边一起挤。
5. 用 casting_strategy 表达这次主方向，只允许：prefer_refresh_existing / introduce_one_new / balanced_light / hold_steady。
6. max_new_core_entries 与 max_role_refreshes 都尽量小，通常是 0 或 1，用来约束接下来五章别一下塞太满。
7. should_introduce_character 只有在确实该把新的核心配角色位落地时才写 true。
8. should_refresh_role_functions 只有在旧角色确实需要“换功能”时才写 true；例如不再只做传话、盘问、警告或发任务，要改成行动搭档、交易接口、资源线索源、压力放大器、关系调停位之类更能带剧情的作用位。
9. 所有角色名、relation_id、slot_id 都必须来自输入，不要发明新对象。
10. next_window_tasks 和 watchouts 尽量短、可执行、别说空话。
11. 这一步要和原有五章规划并行，不要改节奏，只给前置建议和附加结果。
""".strip()


def stage_character_review_user_prompt(snapshot: dict[str, Any]) -> str:
    compact_snapshot = {
        key: snapshot.get(key)
        for key in [
            "stage_start_chapter", "stage_end_chapter", "next_window_start", "next_window_end",
            "recent_retrospectives", "recent_summaries", "active_core_characters", "due_unbound_slots",
            "priority_characters", "priority_relations", "role_refresh_candidates", "casting_defer_diagnostics",
        ]
        if snapshot.get(key) not in (None, "", [], {})
    }
    sorted_sections = _soft_sorted_section_block(
        "stage_character_review",
        {
            "next_window_start": compact_snapshot.get("next_window_start"),
            "next_window_end": compact_snapshot.get("next_window_end"),
            "focus_hint": ((compact_snapshot.get("priority_characters") or [{}])[0] or {}).get("name"),
        },
        [
            {
                "title": "阶段复盘范围",
                "body": f"""【阶段复盘范围】
{_compact_pretty(compact_snapshot, max_depth=3, max_items=8, text_limit=84)}""",
                "tags": ["阶段", "复盘", "近五章"],
                "stages": ["stage_character_review"],
                "priority": "must",
            },
        ],
    )
    return f"""
请先对刚完成的一小段章节做“阶段性人物复盘”，再给下一规划窗口一份前置建议。

{sorted_sections}

输出 JSON schema：
{_pretty(STAGE_CHARACTER_REVIEW_SCHEMA)}

补充规则：
- focus_characters 代表下一规划窗口优先推进的人物，不等于所有会出场的人。
- supporting_characters 代表适合辅助推进、但不该抢戏的人。
- defer_characters 代表下一规划窗口先别硬推的人。
- priority_relation_ids 代表下一规划窗口该正面推进的关系；light_touch_relation_ids 代表适合顺手推一格的关系。
- 先用 casting_strategy 判断这五章更适合“补新人”还是“抬旧人”；默认不要两边一起猛推。
- casting_strategy 只允许：prefer_refresh_existing / introduce_one_new / balanced_light / hold_steady。
- max_new_core_entries 与 max_role_refreshes 尽量只写 0 或 1，用来限制这五章别把人物池塞爆。
- should_introduce_character 为 true 时，candidate_slot_ids 才有意义。
- should_refresh_role_functions 为 true 时，role_refresh_targets 和 role_refresh_suggestions 才有意义；角色换功能是指给旧角色换一种更能带剧情的作用，不是改名字，也不是重写人设。
- next_window_tasks 要直接服务接下来的五章规划，watchouts 则是提醒规划窗口别再踩坑。
- 若输入里的 casting_defer_diagnostics 显示最近几章人物投放总被 AI 延后，要先判断原因到底更像“窗口太满 / 章法不顺 / 投放节奏安排不对”，再决定下一轮是稳住、抬旧人，还是只补一个新人。
- 若 recent_resolution_history 里同一类动作连续被 defer，不要机械把它原样再塞进下一窗口；除非你能明确解释为什么下一窗口章法更顺。
""".strip()


def character_relation_schedule_review_system_prompt() -> str:
    return """
你是“人物与关系调度复核器”。你的任务不是写正文，而是在本地软调度结果的基础上，用语义理解复核：
- 这章真正该重点推进哪些人物；
- 哪些人物适合当辅助，不该抢戏；
- 哪些关系应该主推，哪些关系只轻触一下；
- 哪些人物或关系虽然本地分数不低，但这章最好暂缓；
- 本章人物投放动作（补新人 / 旧人换功能）到底该执行、暂缓，还是只轻量考虑。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. 这是“复核与微调”，不是推翻本地调度；尽量少改，但要敢于把明显不合章法的对象降下来。
3. focus_characters 通常 1-3 人，supporting_characters 通常 0-3 人。
4. main_relation_ids 通常 0-2 条，light_touch_relation_ids 通常 0-3 条。
5. defer_* 只放本章确实不该抢戏或不该硬推的对象，宁少勿滥。
6. interaction_depth_overrides 只在你确信需要改成本章更浅/更深互动时填写。
7. relation_push_overrides 只在你确信本章应偏“冲突推进/合作推进/拉扯推进/轻推一格”时填写。
8. stage_casting_verdict 只允许：execute_now / defer_to_next / soft_consider / hold_steady。
9. 若本地人物投放提示里名额已满或 do_not_force_action=true，就不要把 verdict 写成 execute_now。
10. 所有名字和 relation_id 都必须来自输入，不要发明新对象。
""".strip()


def character_relation_schedule_review_user_prompt(chapter_plan: dict[str, Any], planning_packet: dict[str, Any]) -> str:
    packet = planning_packet or {}
    compact_plan = {
        key: (chapter_plan or {}).get(key)
        for key in [
            "chapter_no", "title", "goal", "conflict", "main_scene", "event_type",
            "progress_kind", "flow_template_id", "flow_template_tag", "flow_template_name",
            "supporting_character_focus", "supporting_character_note", "ending_hook",
            "new_resources", "new_factions", "new_relations",
        ]
        if (chapter_plan or {}).get(key) not in (None, "", [], {})
    }
    local_schedule = packet.get("character_relation_schedule") or {}
    priority_snapshot = {
        "priority_characters": (local_schedule.get("appearance_schedule") or {}).get("priority_characters") or [],
        "priority_relations": (local_schedule.get("relationship_schedule") or {}).get("priority_relations") or [],
        "due_characters": (local_schedule.get("appearance_schedule") or {}).get("due_characters") or [],
        "due_relations": (local_schedule.get("relationship_schedule") or {}).get("due_relations") or [],
    }
    sorted_sections = _soft_sorted_section_block(
        "character_relation_schedule_review",
        {
            "goal": compact_plan.get("goal"),
            "flow": compact_plan.get("flow_template_name") or compact_plan.get("flow_template_tag") or compact_plan.get("flow_template_id"),
            "focus_character": ((packet.get("selected_elements") or {}).get("focus_character")),
            "event_type": compact_plan.get("event_type"),
        },
        [
            {
                "title": "本章信息",
                "body": f"""【本章信息】
{_compact_pretty(compact_plan, max_depth=3, max_items=8, text_limit=90)}""",
                "tags": ["计划", "流程", "目标"],
                "stages": ["character_relation_schedule_review"],
                "priority": "must",
            },
            {
                "title": "核心配角分批规则",
                "body": f"""【核心配角分批规则】
{_compact_pretty(packet.get('core_cast_guidance') or {}, max_depth=3, max_items=8, text_limit=80)}""",
                "tags": ["核心配角", "阶段", "分批"],
                "stages": ["character_relation_schedule_review"],
                "priority": "high",
            },
            {
                "title": "本地初排结果",
                "body": f"""【本地初排结果】
{_compact_pretty(priority_snapshot, max_depth=4, max_items=8, text_limit=80)}""",
                "tags": ["本地初排", "角色", "关系"],
                "stages": ["character_relation_schedule_review"],
                "priority": "high",
            },
            {
                "title": "本章人物投放提示",
                "body": f"""【本章人物投放提示】
{_compact_pretty(_chapter_stage_casting_prompt_payload(packet), max_depth=4, max_items=8, text_limit=80)}""",
                "tags": ["投放", "新人", "换功能"],
                "stages": ["character_relation_schedule_review"],
                "priority": "high",
            },
            {
                "title": "当前候选卡轻量索引",
                "body": f"""【当前候选卡轻量索引】
{_compact_pretty(packet.get('card_index') or {}, max_depth=3, max_items=8, text_limit=70)}""",
                "tags": ["候选卡", "索引"],
                "stages": ["character_relation_schedule_review"],
                "priority": "medium",
            },
        ],
    )
    return f"""
请基于【本地初排结果】做一次语义复核，给出“本章最终更适合怎么推进人物与关系”的建议。

{sorted_sections}

输出 JSON schema：
{_pretty(CHARACTER_RELATION_SCHEDULE_REVIEW_SCHEMA)}

补充规则：
- focus_characters 是本章最该正面写到、推进到的人，不等于所有该回场的人。
- supporting_characters 是适合辅助推进但不该抢戏的人。
- defer_characters 用于“这章最好别硬拉上来”或“只适合一笔带过”的人。
- main_relation_ids 只放本章真该正面推进的关系；light_touch_relation_ids 放适合顺手推一格的关系。
- 若本地初排里某对象分数高，但和本章流程/场景不合，可以把它放进 defer_*。
- 若本章流程是关系主导，就更重视人物与关系；若本章流程是资源/危机主导，人物关系可以只保留最需要的几条。
- 请顺手复核【本章人物投放提示】：这章虽然名额未满，也不一定就该硬落动作。若本章场景、冲突、焦点人物不适合，就把 stage_casting_verdict 写成 defer_to_next 或 hold_steady。
- 若本章已有 planned_action，只有在你确信当前章法自然、不会抢掉主线推进时，才把 stage_casting_verdict 写成 execute_now；否则宁可 defer_to_next。
- 若本章没有 planned_action，stage_casting_verdict 通常写 hold_steady 或 soft_consider，不要凭空强造硬动作。
""".strip()


def chapter_card_selector_system_prompt() -> str:
    return """
你是“章节用卡选择器”。你的任务不是写正文，而是从轻量卡片索引里挑出本章真正要展开的少量卡片编号。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. 只保留本章真正会用到的卡片，宁少勿滥。
3. 优先保留：主角卡、焦点配角卡、本章新引入卡、当前会变化的资源卡、当前会变化的关系卡。
4. 角色通常 2-4 张，资源 1-3 张，势力 0-2 张，关系 0-3 张；总数尽量控制在 10 张以内。
5. 若某张卡只是背景存在、本章不会真正动到，就不要选。
6. 选卡只看本章目标、冲突、流程、焦点人物和本章新引入元素，不要为了“看起来全”而乱选。
7. selection_note 用一句短话说明选卡重心。
""".strip()


def chapter_card_selector_user_prompt(chapter_plan: dict[str, Any], planning_packet: dict[str, Any]) -> str:
    packet = planning_packet or {}
    selected_elements = packet.get("selected_elements") or {}
    hard_requirements = {
        "focus_character": selected_elements.get("focus_character"),
        "new_resources": (chapter_plan or {}).get("new_resources") or [],
        "new_factions": (chapter_plan or {}).get("new_factions") or [],
        "new_relations": (chapter_plan or {}).get("new_relations") or [],
    }
    compact_plan = {
        key: (chapter_plan or {}).get(key)
        for key in [
            "chapter_no", "title", "goal", "conflict", "main_scene", "event_type",
            "progress_kind", "flow_template_id", "flow_template_tag", "flow_template_name",
            "supporting_character_focus", "supporting_character_note", "new_resources",
            "new_factions", "new_relations", "ending_hook",
        ]
        if (chapter_plan or {}).get(key) not in (None, "", [], {})
    }
    sorted_sections = _soft_sorted_section_block(
        "chapter_card_selection",
        {"chapter_plan": compact_plan, "hard_requirements": hard_requirements},
        [
            {
                "title": "本章信息",
                "body": f"""【本章信息】
{_compact_pretty(compact_plan, max_depth=3, max_items=8, text_limit=100)}""",
                "tags": ["计划", "流程", "目标"],
                "stages": ["chapter_card_selection"],
                "priority": "must",
            },
            {
                "title": "核心配角分批规则",
                "body": f"""【核心配角分批规则】
{_compact_pretty(packet.get('core_cast_guidance') or {}, max_depth=3, max_items=8, text_limit=80)}""",
                "tags": ["核心配角", "阶段", "分批"],
                "stages": ["chapter_card_selection"],
                "priority": "high",
            },
            {
                "title": "角色回场与关系推进",
                "body": f"""【角色回场与关系推进】
{_compact_pretty(packet.get('character_relation_schedule') or {}, max_depth=4, max_items=8, text_limit=80)}""",
                "tags": ["回场", "关系", "软调度"],
                "stages": ["chapter_card_selection"],
                "priority": "high",
            },
            {
                "title": "AI复核后的推进建议",
                "body": f"""【AI复核后的推进建议】
{_compact_pretty(packet.get('character_relation_schedule_ai') or {}, max_depth=4, max_items=8, text_limit=80)}""",
                "tags": ["AI复核", "人物", "关系"],
                "stages": ["chapter_card_selection"],
                "priority": "high",
            },
            {
                "title": "本章人物投放提示",
                "body": f"""【本章人物投放提示】
{_compact_pretty(_chapter_stage_casting_prompt_payload(packet), max_depth=4, max_items=8, text_limit=80)}""",
                "tags": ["投放", "新人", "换功能"],
                "stages": ["chapter_card_selection"],
                "priority": "high",
            },
            {
                "title": "必须优先考虑",
                "body": f"""【必须优先考虑】
{_compact_pretty(hard_requirements, max_depth=3, max_items=6, text_limit=80)}""",
                "tags": ["焦点人物", "新引入", "硬要求"],
                "stages": ["chapter_card_selection"],
                "priority": "high",
            },
            {
                "title": "候选卡片轻量索引",
                "body": f"""【候选卡片轻量索引】
{_compact_pretty(packet.get('card_index') or {}, max_depth=3, max_items=8, text_limit=80)}""",
                "tags": ["候选卡", "索引", "软排序"],
                "stages": ["chapter_card_selection"],
                "priority": "high",
            },
            {
                "title": "候选卡软排序说明",
                "body": f"""【候选卡软排序说明】
{_compact_pretty(packet.get('card_index_meta') or {'soft_sorting_rule': '本地只排序，不硬删候选。'}, max_depth=3, max_items=8, text_limit=80)}""",
                "tags": ["软排序", "说明"],
                "stages": ["chapter_card_selection"],
                "priority": "medium",
            },
        ],
    )
    return f"""
请从【候选卡片轻量索引】里挑出“本章真正要展开”的卡片编号。

{sorted_sections}

输出 JSON schema：
{_pretty(CARD_SELECTION_SCHEMA)}

补充规则：
- selected_card_ids 里只放编号，不要放名字。
- 优先少而准，不要把全部候选都选上。
- card_index 的靠前项只是本地软排序提示，不是硬筛掉；若后面的卡更适合本章，也可以选。
- 如果本章流程更偏“关系变化”，就优先保留对应人物卡和关系卡；如果更偏“资源变化”，就优先保留资源卡。
- 若【角色回场与关系推进】里标了“该回场/本章应动”，要优先考虑对应角色卡和关系卡。
- 若【AI复核后的推进建议】里点名了 focus_characters / main_relation_ids，应优先围绕它们选卡；supporting/light_touch 可作为辅助，defer_* 尽量别让它们抢戏。
- 若【本章人物投放提示】里的 final_should_execute_planned_action=true 且 planned_action=role_refresh，就优先保留对应角色卡；若 final_do_not_force_action=true，就不要为了补新人或换功能硬塞无关卡。
- 若某张卡只是背景板，本章不会真正动它，就不要选。
""".strip()


def chapter_draft_system_prompt() -> str:
    return (
        "你是一名擅长中文网文连载的主笔，擅长多种修仙、玄幻、升级与冒险长篇，但不会预设固定模板。"
        "你必须把章节写成真实发生的场面，而不是剧情说明书。"
        "你写的是连载小说，不是流程报告；每章都要让读者明确感到局势新增了什么。"
        "多用动作、对话、感官细节、具体物件和因果推进。"
        "禁止元叙事表达，禁止出现‘本章任务’‘读者可以看到’‘真正的故事开始’等句子。"
        "禁止复用上一章的开头句式、结尾句式、任务句、转折句和固定意象。"
        "禁止使用‘他今晚冒险来到这里，只为一件事’、‘可就在他以为……新的异样还是冒了出来’、‘在凡人流修仙这样的处境里’这类模板句。"
        "也要尽量避开‘不是错觉’‘心跳快了几分/一拍’‘盯着……看了片刻’‘若有若无’这类高频口头禅。"
        "不要用作者总结句代替事件推进，例如‘这不是结束，而是某种开始’之类的句子。"
        "整体要克制，但不能一直写得过于安全平顺；每章最好留一两句更具体、更有棱角、能让读者记住的表达。"
        "反派和帮派人物不要只会吓唬人，要带一点具体而不安的个人细节。"
        "主角遇到失去、离别、受辱或做选择时，情绪要再沉半层，但通过动作、停顿、手势和旧物处理表现，不要大喊大叫。"
        "这一次不要输出 JSON，不要输出 markdown，不要输出标题，不要输出任何解释。"
        "你只输出章节正文本身。"
    )



def _agency_mode_prompt_block(chapter_plan: dict[str, Any]) -> str:
    mode = _text(chapter_plan.get("agency_mode"))
    label = _text(chapter_plan.get("agency_mode_label"), "通用主动推进")
    summary = _text(chapter_plan.get("agency_style_summary"), "主角要主动施加影响，但不必总靠猛冲。")
    opening = _text(chapter_plan.get("agency_opening_instruction") or chapter_plan.get("opening_beat"))
    middle = _text(chapter_plan.get("agency_mid_instruction") or chapter_plan.get("mid_turn"))
    discovery = _text(chapter_plan.get("agency_discovery_instruction") or chapter_plan.get("discovery"))
    closing = _text(chapter_plan.get("agency_closing_instruction") or chapter_plan.get("closing_image") or chapter_plan.get("ending_hook"))
    rotation_note = _text(chapter_plan.get("agency_rotation_note"))
    avoid_items = chapter_plan.get("agency_avoid") or []
    avoid_lines = "\n".join(f"- {item}" for item in avoid_items if str(item).strip()) or "- 不要把谨慎写成纯被动\n- 不要只观察不施加影响"
    mode_line = f"- 采用模式：{label}" + (f"（{mode}）" if mode else "")
    lines = [
        "【本章主动方式】",
        mode_line,
        f"- 模式说明：{summary}",
        "- 主动性的定义：不是更频繁地猛冲，而是更频繁地改变局势、信息分布、关系结构或决策条件。",
    ]
    if opening:
        lines.append(f"- 开场方向：{opening}")
    if middle:
        lines.append(f"- 中段方向：{middle}")
    if discovery:
        lines.append(f"- 发现落点：{discovery}")
    if closing:
        lines.append(f"- 收尾方向：{closing}")
    if rotation_note:
        lines.append(f"- 变体提醒：{rotation_note}")
    lines.append("- 避免写法：")
    lines.append(avoid_lines)
    return "\n".join(lines)


def _progress_result_prompt_block(chapter_plan: dict[str, Any]) -> str:
    progress_kind = _text(chapter_plan.get("progress_kind"), "信息推进")
    payoff = _text(chapter_plan.get("payoff_or_pressure"), "本章必须给出明确结果。")
    ending = _text(chapter_plan.get("ending_hook"))
    guidance_map = {
        "信息推进": "读完后，读者应能复述主角确认了什么、谁说漏了什么、或哪条线索被坐实。",
        "关系推进": "读完后，读者应能复述谁松口了、谁翻脸了、谁表态了，或双方条件怎么被改写。",
        "资源推进": "读完后，读者应能复述主角拿到、换到、保住或押出了什么，以及付了什么代价。",
        "实力推进": "读完后，读者应能复述主角具体掌握了什么、突破了哪一步，或试出了什么上限。",
        "风险升级": "读完后，读者应能复述谁开始盯上主角、哪条退路少了一条、什么价码被抬高，或主角被迫接受了什么限制。",
        "地点推进": "读完后，读者应能复述主角进了哪里、离开了哪里，或为什么新位置更危险/更关键。",
    }
    lines = [
        "【本章推进结果】",
        f"- 推进类型：{progress_kind}",
        f"- 本章应兑现：{payoff}",
        f"- 判断标准：{guidance_map.get(progress_kind, '读完后，读者应能一句话说清本章新增了什么。')}",
        "- 禁止只写气氛、顾虑、怀疑、压迫感或回忆，而不把结果落地。",
    ]
    if ending:
        lines.append(f"- 结尾落点：{ending}")
    return "\n".join(lines)


def _chapter_tail_generation_method_block(chapter_plan: dict[str, Any]) -> str:
    opening = _text(chapter_plan.get("opening_beat") or chapter_plan.get("proactive_move"), "开场先给主角一个可见动作或判断。")
    middle = _text(chapter_plan.get("mid_turn") or chapter_plan.get("conflict"), "中段必须出现一次受阻、转折或换招。")
    discovery = _text(chapter_plan.get("discovery") or chapter_plan.get("payoff_or_pressure"), "正文里要落下一次具体发现或验证结果。")
    closing = _text(chapter_plan.get("closing_image") or chapter_plan.get("ending_hook") or chapter_plan.get("payoff_or_pressure"), "章末要落在本章已经铺开的结果、压力、异常或选择上。")
    hook_style = _text(chapter_plan.get("hook_style"), "服从本章原定收束风格")
    return "\n".join(
        [
            "【正文主生成方法】",
            f"- 开场方法：{opening}",
            f"- 中段方法：{middle}",
            f"- 发现落点：{discovery}",
            f"- 章末收束：{closing}",
            f"- 收束风格：{hook_style}",
            "- 主方法提醒：延续‘主角动作/判断 -> 外界反应 -> 主角调整 -> 结果/压力落地’这条写法，不要突然改成总结腔。",
        ]
    )


def chapter_body_draft_system_prompt() -> str:
    return (
        chapter_draft_system_prompt()
        + "这一次你只负责章节的正文主体阶段，不要把最后 1-2 段章末收束一次写满。"
        + "你必须把场景推进到结尾起点已经成立的位置，再在完整句或完整段落上停住。"
        + "绝不能停在半句、半个动作、未闭合对白或悬空判断上。"
    )


def _chapter_body_light_memory(novel_context: dict[str, Any]) -> dict[str, Any]:
    story_memory = (novel_context or {}).get("story_memory") or {}
    payload: dict[str, Any] = {}
    for key in ["project_card", "current_volume_card", "protagonist_state", "execution_brief", "hard_fact_guard"]:
        value = story_memory.get(key) or (novel_context or {}).get(key)
        if value:
            payload[key] = value
    recent_retrospectives = story_memory.get("recent_retrospectives") or []
    if recent_retrospectives:
        payload["recent_retrospectives"] = recent_retrospectives[:2]
    if not payload and novel_context:
        for key in ["project_card", "current_volume_card", "protagonist_state", "execution_brief", "hard_fact_guard"]:
            value = (novel_context or {}).get(key)
            if value:
                payload[key] = value
    return payload


def _chapter_body_plan_packet_summary(chapter_plan: dict[str, Any]) -> dict[str, Any]:
    packet = (chapter_plan or {}).get("planning_packet") or {}
    if not packet:
        return {}
    summary: dict[str, Any] = {}
    continuity = packet.get("recent_continuity_plan") or {}
    if continuity:
        summary["recent_continuity_plan"] = {
            key: continuity.get(key)
            for key in ["recent_progression", "carry_in", "current_chapter_bridge", "lookahead_handoff"]
            if continuity.get(key)
        }
    continuity_window = packet.get("continuity_window") or {}
    if continuity_window:
        summary["continuity_window"] = {
            key: continuity_window.get(key)
            for key in ["opening_anchor", "last_chapter_tail_excerpt", "unresolved_action_chain", "onstage_characters"]
            if continuity_window.get(key)
        }
    if packet.get("resource_plan"):
        summary["resource_plan"] = packet.get("resource_plan")
    if packet.get("resource_capability_plan"):
        summary["resource_capability_plan"] = packet.get("resource_capability_plan")
    if packet.get("flow_plan"):
        summary["flow_plan"] = packet.get("flow_plan")
    if packet.get("new_cards_created"):
        summary["new_cards_created"] = packet.get("new_cards_created")
    if packet.get("selected_elements"):
        summary["selected_elements"] = packet.get("selected_elements")
    if packet.get("core_cast_guidance"):
        summary["core_cast_guidance"] = packet.get("core_cast_guidance")
    if packet.get("character_relation_schedule"):
        summary["character_relation_schedule"] = packet.get("character_relation_schedule")
    if packet.get("character_relation_schedule_ai"):
        summary["character_relation_schedule_ai"] = packet.get("character_relation_schedule_ai")
    if packet.get("chapter_stage_casting_hint"):
        summary["chapter_stage_casting_hint"] = packet.get("chapter_stage_casting_hint")
    if packet.get("card_index"):
        summary["card_index"] = packet.get("card_index")
    if packet.get("card_selection"):
        summary["card_selection"] = packet.get("card_selection")
    if packet.get("relevant_cards"):
        summary["relevant_cards"] = packet.get("relevant_cards")
    if packet.get("importance_runtime"):
        summary["importance_runtime"] = packet.get("importance_runtime")
    return summary


def _chapter_body_last_chapter_summary(last_chapter: dict[str, Any]) -> dict[str, Any]:
    chapter = last_chapter or {}
    bridge = chapter.get("continuity_bridge") or {}
    scene_card = chapter.get("last_scene_card") or {}
    payload: dict[str, Any] = {}
    if chapter.get("title"):
        payload["title"] = chapter.get("title")
    if chapter.get("chapter_no") is not None:
        payload["chapter_no"] = chapter.get("chapter_no")
    if bridge:
        payload["continuity_bridge"] = {
            key: bridge.get(key)
            for key in ["opening_anchor", "last_two_paragraphs", "last_chapter_tail_excerpt", "unresolved_action_chain", "onstage_characters"]
            if bridge.get(key)
        }
    if scene_card:
        payload["last_scene_card"] = {
            key: scene_card.get(key)
            for key in ["main_scene", "chapter_hook", "onstage_characters", "unresolved_action_chain"]
            if scene_card.get(key)
        }
    return payload


def _chapter_body_recent_summary_payload(recent_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in recent_summaries or []:
        if not isinstance(item, dict):
            continue
        compact = {
            key: item.get(key)
            for key in ["chapter_no", "title", "event_summary", "summary", "open_hooks"]
            if item.get(key)
        }
        if compact:
            payload.append(compact)
        if len(payload) >= 2:
            break
    return payload


def _chapter_body_interventions_payload(active_interventions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in active_interventions or []:
        if not isinstance(item, dict):
            continue
        compact = {
            key: item.get(key)
            for key in ["type", "focus", "instruction", "summary", "tone"]
            if item.get(key)
        }
        if compact:
            payload.append(compact)
        if len(payload) >= 2:
            break
    return payload


def _chapter_body_plan_summary(chapter_plan: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in [
        "chapter_no", "title", "goal", "main_scene", "conflict", "progress_kind", "event_type",
        "flow_template_id", "flow_template_tag", "flow_template_name",
        "new_resources", "new_factions", "new_relations",
        "proactive_move", "opening_beat", "mid_turn", "discovery", "payoff_or_pressure",
        "ending_hook", "hook_style", "supporting_character_focus", "supporting_character_note", "writing_note",
    ]:
        value = (chapter_plan or {}).get(key)
        if value:
            payload[key] = value
    packet_summary = _chapter_body_plan_packet_summary(chapter_plan)
    if packet_summary:
        payload["planning_packet"] = packet_summary
    return payload


def chapter_body_draft_user_prompt(
    novel_context: dict[str, Any],
    chapter_plan: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
    target_words: int,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    *,
    body_target_visible_chars_min: int,
    body_target_visible_chars_max: int,
) -> str:
    workflow_runtime = ((novel_context or {}).get("story_memory") or {}).get("workflow_runtime") or {}
    runtime_feedback = dict(workflow_runtime.get("retry_feedback") or {})
    plan_retry_feedback = chapter_plan.get("retry_feedback") or {}
    if isinstance(plan_retry_feedback, dict):
        runtime_feedback.update({key: value for key, value in plan_retry_feedback.items() if value is not None})
    proactive_move = _text(chapter_plan.get("proactive_move"), "主角必须主动做出判断并推动局势前进。")
    agency_mode_block = _agency_mode_prompt_block(chapter_plan)
    progress_result_block = _progress_result_prompt_block(chapter_plan)
    agency_constraints = f"""
【主角主动性硬约束】
- 本章指定主动动作：{proactive_move}
- 前两段内必须让主角先做一个可见动作或判断；也可以是设问、验证或改条件，不能先站着听、站着看、压下念头。
- 本章至少出现一次完整链条：主角先手 -> 外界反应 -> 主角顺势调整或加码。
- 中段受阻后，主角必须再追一步：追问、换价、设局、藏证、试探、借规矩、抢先出手、换验证方法，至少落实一种。
- 谨慎不等于被动；若主角需要隐藏，也要写成“先藏、先试、先换、先误导、先撤再回身”的主动谨慎。
""".strip()
    runtime_feedback_block = ""
    if runtime_feedback:
        runtime_feedback_block = f"\n\n【本章重试纠偏】\n{_compact_pretty(runtime_feedback, max_depth=3, max_items=6, text_limit=100)}\n若上一次草稿被指出主角被动、推进不清或结尾发虚，这次必须优先修正。"
    repetition_note = chapter_plan.get("writing_note")
    repetition_block = f"\n【额外写作提醒】\n{repetition_note}\n" if repetition_note else ""
    protagonist_name = _protagonist_name_from_context(novel_context)
    blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST)
    light_memory = _chapter_body_light_memory(novel_context)
    body_plan = _chapter_body_plan_summary(chapter_plan)
    compact_last = _chapter_body_last_chapter_summary(last_chapter)
    compact_recent = _chapter_body_recent_summary_payload(recent_summaries)
    compact_interventions = _chapter_body_interventions_payload(active_interventions)
    prompt_context = {
        "goal": chapter_plan.get("goal"),
        "flow": chapter_plan.get("flow_template_name") or chapter_plan.get("flow_template_tag") or chapter_plan.get("flow_template_id"),
        "focus_character": ((chapter_plan.get("planning_packet") or {}).get("selected_elements") or {}).get("focus_character"),
        "event_type": chapter_plan.get("event_type"),
        "progress_kind": chapter_plan.get("progress_kind"),
    }
    context_block = _soft_sorted_section_block(
        "chapter_body_draft",
        prompt_context,
        [
            {"title": "本章拍表（主体阶段）", "body": _section_block("本章拍表（主体阶段）", _pretty(body_plan)), "tags": ["计划", "流程", "本章"], "stages": ["chapter_body_draft"], "priority": "must"},
            {"title": "上一章承接要点", "body": _section_block("上一章承接要点", _pretty(compact_last)), "tags": ["上一章", "承接", "连续性"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "正文主体轻量上下文", "body": _section_block("正文主体轻量上下文", _pretty(light_memory)), "tags": ["记忆", "硬事实", "上下文"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "最近章节摘要（精简）", "body": _section_block("最近章节摘要（精简）", _pretty(compact_recent)), "tags": ["最近摘要", "连续性"], "stages": ["chapter_body_draft"], "priority": "medium"},
            {"title": "当前生效的读者干预（精简）", "body": _section_block("当前生效的读者干预（精简）", _pretty(compact_interventions)), "tags": ["干预", "偏好"], "stages": ["chapter_body_draft"], "priority": "medium"},
            {"title": "本章主动方式", "body": agency_mode_block, "tags": ["主动性", "模式"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "本章推进结果", "body": progress_result_block, "tags": ["推进", "结果"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "角色回场与关系推进", "body": _section_block("角色回场与关系推进", _compact_pretty(((chapter_plan.get("planning_packet") or {}).get("character_relation_schedule") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["回场", "关系", "互动深度"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "AI复核后的本章人物关系建议", "body": _section_block("AI复核后的本章人物关系建议", _compact_pretty(((chapter_plan.get("planning_packet") or {}).get("character_relation_schedule_ai") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["AI复核", "人物", "关系"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "本章人物投放提示", "body": _section_block("本章人物投放提示", _compact_pretty(_chapter_stage_casting_prompt_payload(chapter_plan.get("planning_packet") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["投放", "新人", "换功能"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "主角主动性硬约束", "body": agency_constraints, "tags": ["主动性", "硬约束"], "stages": ["chapter_body_draft"], "priority": "must"},
            {"title": "本章重试纠偏", "body": runtime_feedback_block.strip(), "tags": ["纠偏", "重试"], "stages": ["chapter_body_draft"], "priority": "high"},
            {"title": "额外写作提醒", "body": repetition_block.strip(), "tags": ["反重复", "提醒"], "stages": ["chapter_body_draft"], "priority": "medium"},
        ],
    )
    return f"""
请根据以下信息先写出下一章的正文主体。

{context_block}

写作要求：
1. 用中文写下一章的正文主体，目标约 {target_words} 字；本阶段建议控制在 {body_target_visible_chars_min}-{body_target_visible_chars_max} 个中文可见字符左右，整章总目标区间仍是 {target_visible_chars_min}-{target_visible_chars_max}。
2. 当前只生成本章的正文主体，章尾收束会在下一阶段单独生成；不要把最后的章末落点一次写满，但必须停在完整句或完整段落上，不能停成半句。
3. 优先服从【本章拍表（主体阶段）】、【上一章承接要点】和 hard_fact_guard；若上一章提供 continuity_bridge / last_two_paragraphs / unresolved_action_chain，开头两段必须优先吃掉。
4. 正文主体至少完成三件事：开场动作/判断、一处中段受阻或转折、一次具体发现或验证；可以把异常、选择、代价或压力推到“即将收束”的位置。
5. 本章必须有明确推进，至少推进信息、关系、资源、实力、风险中的一项，而且要让读者看得见结果；禁止只写气氛、顾虑、怀疑、压迫感或回忆，而不把结果落地。
6. 主角不能只被动应对；前两段就让主角先手，形成“主角动作/判断 -> 外界反应 -> 主角顺势调整或加码”的链条。中段受阻后，主角必须再追一步，不能只是心里一沉或暂时按下不动。
7. 本章只围绕当前章真正需要的局部连续性来写：若【本章拍表（主体阶段）】里带 planning_packet，就优先兑现其中 recent_continuity_plan / continuity_window / selected_elements / card_index / card_selection / relevant_cards / resource_plan / resource_capability_plan，不要回看全书乱扩写。
7.1 若 planning_packet 或轻量记忆里提供了 opening_reveal_guidance，且当前仍在开篇窗口内，就通过场景、试探、交易、受挫或旁人评价自然补出世界/势力/实力等级信息，不要写成说明书，也不要拖过前20章还讲不清基础强弱。
8. 维持正常章节质感：优先写动作、观察、试探、对话和具体现象，不要把正文主体写成提纲扩写或信息清单。
9. 若【角色回场与关系推进】里有“该回场/本章应动”的人物或关系，本章至少要给一次可感知推进；深互动关系要写出具体来回，轻互动关系只推一格即可。
10. 若【AI复核后的本章人物关系建议】里点名了 focus_characters / main_relation_ids，就按它们作为本章主推进；supporting/light_touch 只做辅助；defer_* 尽量不让其抢走篇幅。
11. 若【本章人物投放提示】写明 final_should_execute_planned_action=true，就自然落实 planned_action：new_core_entry 只负责让新人或新核心位落地；role_refresh 只负责让对应旧角色换成更能带剧情的作用位。若 final_do_not_force_action=true，就不要为了补新人或换功能硬塞多余动作。
12. 配角不能只是抛信息的工具人；若本章出现反复角色，要给他一点职业习惯、说话方式、私心、忌讳或受压反应。
12.1 若【本章拍表（主体阶段）】或 planning_packet 提供了 character_template_guidance，就让对应人物的说话、行动、受压反应和小动作贴着模板写，别把不同模板的人物写回同一种安全腔。
13. 若涉及失去、离别、当掉旧物、被迫离开、冒险抉择等情节，要把{protagonist_name}的情绪再往下沉半层，但通过动作、停顿、视线、呼吸、手指和旧物处理落出来，不要一句带过。
14. 不要为了省篇幅跳过互动过程；宁可把主体写扎实，也不要前面挤满、尾巴断气。
15. 下面这些重复模板绝对不要出现：
{blacklist}
16. 只输出正文主体，不要标题、JSON、markdown、解释或自我分析。
""".strip()


def chapter_body_continue_system_prompt() -> str:
    return (
        "你是一名中文连载小说的正文续写助手。"
        "你只负责在当前章节的同一场景与同一叙事轨道上继续写正文主体，不是重写整章。"
        "必须服从本章规划、当前已写出的正文事实和正文主生成方法。"
        "不能重启开场，不能回头总结，不能突然切新地点、新时间、新人物线。"
        "这一步仍然属于正文主体阶段：可以继续推进冲突、验证和发现，但不要把章尾最终收束一次写死。"
        "要把自己当成同一作者在同一章里继续写，不要突然换掉句长节奏、对白密度、动作密度和叙事口径。"
        "只输出紧接现有正文后面的新增正文，不要标题、不要解释、不要 JSON。"
    )


def chapter_closing_system_prompt() -> str:
    return (
        "你是一名中文连载小说的章尾收束助手。"
        "你不是重写整章，而是承接已经写好的正文主体，用和正文主生成一致的方法写完最后 1-2 段。"
        "必须服从本章规划、当前场景和正文主体已有的叙事节奏。"
        "要像同一章自然长出来的最后 1-2 段，延续正文主体已有的句长、对白占比、动作密度与视角，不要突然改腔。"
        "不能回头总结，不能切新地点、新时间、新人物线，也不能提前写出下一章的大事件。"
        "只输出紧接正文主体后面的新增正文，不要标题、不要解释、不要 JSON。"
    )


def chapter_body_continue_user_prompt(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    last_chapter: dict[str, Any] | None = None,
    recent_summaries: list[dict[str, Any]] | None = None,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    continuation_target_visible_chars_min: int,
    continuation_target_visible_chars_max: int,
    continuation_round: int,
    max_segments: int,
) -> str:
    existing = (existing_content or "").strip()
    plan_summary = _chapter_extension_plan_summary(chapter_plan)
    method_block = _chapter_tail_generation_method_block(chapter_plan)
    state_summary = _chapter_state_summary(chapter_plan, existing)
    style_summary = _style_inheritance_summary(existing)
    continuity_summary = _continuity_anchor_summary(None, None)
    head_anchor = _head_excerpt(existing, max_chars=260)
    tail_excerpt = _tail_excerpt(existing, max_chars=1100)
    tail_paragraphs = _tail_paragraphs(existing, count=3)
    last_complete_sentence = _last_complete_sentence(existing)
    dangling_fragment = _dangling_fragment(existing)
    landing_goal = _text(chapter_plan.get("payoff_or_pressure") or chapter_plan.get("ending_hook") or chapter_plan.get("closing_image"), "继续推进当前章节，直到章尾收束条件真正成熟。")
    hook_style = _text(chapter_plan.get("hook_style"), "保持本章原定收束风格")
    blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST[:8])
    context_block = _soft_sorted_section_block(
        "chapter_body_continue",
        {"goal": chapter_plan.get("goal"), "flow": chapter_plan.get("flow_template_name") or chapter_plan.get("flow_template_tag"), "hook_style": hook_style},
        [
            {"title": "本章规划摘要", "body": _section_block("本章规划摘要", _compact_pretty(plan_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["计划", "流程", "本章"], "stages": ["chapter_body_continue"], "priority": "must"},
            {"title": "正文当前状态摘要", "body": _section_block("正文当前状态摘要", _compact_pretty(state_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["状态", "拍点", "待落地"], "stages": ["chapter_body_continue"], "priority": "must"},
            {"title": "正文主生成方法", "body": method_block, "tags": ["方法", "推进"], "stages": ["chapter_body_continue"], "priority": "high"},
            {"title": "本章人物投放提示", "body": _section_block("本章人物投放提示", _compact_pretty(_chapter_stage_casting_prompt_payload(chapter_plan.get("planning_packet") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["投放", "新人", "换功能"], "stages": ["chapter_body_continue"], "priority": "high"},
            {"title": "当前正文长度", "body": _section_block("当前正文长度", f"""现有正文约 {len(existing)} 个可见字符；整章目标区间仍是 {target_visible_chars_min}-{target_visible_chars_max}。
当前是正文主体第 {continuation_round + 1} 段（最多 {max_segments} 段），本次建议新增约 {continuation_target_visible_chars_min}-{continuation_target_visible_chars_max} 个可见字符。"""), "tags": ["长度", "预算"], "stages": ["chapter_body_continue"], "priority": "high"},
            {"title": "本章仍应朝向的结果/压力", "body": _section_block("本章仍应朝向的结果/压力", landing_goal), "tags": ["结果", "压力"], "stages": ["chapter_body_continue"], "priority": "high"},
            {"title": "章末风格", "body": _section_block("章末风格", hook_style), "tags": ["结尾", "风格"], "stages": ["chapter_body_continue"], "priority": "medium"},
            {"title": "文风继承摘要", "body": _section_block("文风继承摘要", _compact_pretty(style_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["文风", "继承"], "stages": ["chapter_body_continue"], "priority": "medium"},
            {"title": "正文开头风格锚点", "body": _section_block("正文开头风格锚点", head_anchor or '无'), "tags": ["风格锚点"], "stages": ["chapter_body_continue"], "priority": "low"},
            {"title": "轻量连续性锚点", "body": _section_block("轻量连续性锚点", _compact_pretty(continuity_summary, max_depth=3, max_items=8, text_limit=100) if continuity_summary else '无'), "tags": ["连续性", "锚点"], "stages": ["chapter_body_continue"], "priority": "medium"},
            {"title": "最后一条完整句", "body": _section_block("最后一条完整句", last_complete_sentence or '无'), "tags": ["结尾", "句子"], "stages": ["chapter_body_continue"], "priority": "medium"},
            {"title": "若存在残缺片段", "body": _section_block("若存在残缺片段", dangling_fragment or '无'), "tags": ["残缺", "动作链"], "stages": ["chapter_body_continue"], "priority": "high"},
            {"title": "正文最近三段", "body": _section_block("正文最近三段", tail_paragraphs or tail_excerpt), "tags": ["尾部", "近文"], "stages": ["chapter_body_continue"], "priority": "high"},
            {"title": "正文尾部片段", "body": _section_block("正文尾部片段", tail_excerpt), "tags": ["尾部", "片段"], "stages": ["chapter_body_continue"], "priority": "medium"},
        ],
    )
    return f"""
请继续写这一章的正文主体，但仍然属于“正文推进阶段”，不是最终章尾收束。

{context_block}

输出要求：
1. 只输出紧接现有正文后面的新增正文，不要重复前文，不要标题，不要注释。
2. 这一步仍然是正文主体续写：继续推进动作、受阻、验证、交换条件、具体发现，不要现在就把章尾最终收死。
3. 必须承接现有动作链、对白或判断，不能像重新开一章，也不能跳到新地点、新时间；若提供了【轻量连续性锚点】，优先吃掉其中的未完动作链与开场锚点。
4. 延续正文已有的动作密度、对话节奏、句长呼吸和叙事视角，不要突然变成总结、解释或提纲腔。
5. 如果当前尾部还没把动作、判断或对白走完，先把它接稳，再继续推进到“接近可收束”的位置。
6. 本次续写必须带来新的推进，而不是改写前文、复述设定或重复同一轮试探；优先兑现【正文当前状态摘要】里仍待落地的拍点。
7. 停笔位置必须稳定：停在完整句、完整段落或清晰可继续的局势节点，不能停在半句、半个动作、未闭合对白上。
8. 不要提前把下一章的大事件写出来；最多把本章推进到“可以进入收束”的位置。
9. 若【本章人物投放提示】写明 final_should_execute_planned_action=true，就在续写里把对应人物投放动作继续写实；若 final_do_not_force_action=true，就不要在续写阶段硬补新人或硬改旧角色作用位。
10. 若【文风继承摘要】提示对白偏高/偏低、句长偏短/偏长、动作密度偏高/偏低，就按那个方向贴着前文写，不要忽然换档。
11. 尽量避开这些安全句式或固定模板：
{blacklist}
12. 只输出新增正文，不要标题、不要“续写如下”。
""".strip()


def chapter_closing_user_prompt(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    last_chapter: dict[str, Any] | None = None,
    recent_summaries: list[dict[str, Any]] | None = None,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    closing_target_visible_chars_min: int,
    closing_target_visible_chars_max: int,
) -> str:
    existing = (existing_content or "").strip()
    plan_summary = _chapter_extension_plan_summary(chapter_plan)
    method_block = _chapter_tail_generation_method_block(chapter_plan)
    state_summary = _chapter_state_summary(chapter_plan, existing)
    style_summary = _style_inheritance_summary(existing)
    continuity_summary = _continuity_anchor_summary(None, None)
    head_anchor = _head_excerpt(existing, max_chars=240)
    tail_excerpt = _tail_excerpt(existing, max_chars=1000)
    tail_paragraphs = _tail_paragraphs(existing, count=2)
    last_complete_sentence = _last_complete_sentence(existing)
    dangling_fragment = _dangling_fragment(existing)
    landing_goal = _text(chapter_plan.get("payoff_or_pressure") or chapter_plan.get("ending_hook") or chapter_plan.get("closing_image"), "让当前场景自然落到本章应有的结果或压力上。")
    hook_style = _text(chapter_plan.get("hook_style"), "保持本章原定收束风格")
    blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST[:8])
    context_block = _soft_sorted_section_block(
        "chapter_closing",
        {"goal": chapter_plan.get("goal"), "hook_style": hook_style, "landing_goal": landing_goal},
        [
            {"title": "本章规划摘要", "body": _section_block("本章规划摘要", _compact_pretty(plan_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["计划", "流程", "本章"], "stages": ["chapter_closing"], "priority": "must"},
            {"title": "本章必须落到的结果/压力", "body": _section_block("本章必须落到的结果/压力", landing_goal), "tags": ["结果", "压力", "落点"], "stages": ["chapter_closing"], "priority": "must"},
            {"title": "章末风格", "body": _section_block("章末风格", hook_style), "tags": ["结尾", "风格"], "stages": ["chapter_closing"], "priority": "high"},
            {"title": "正文当前状态摘要", "body": _section_block("正文当前状态摘要", _compact_pretty(state_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["状态", "待落地"], "stages": ["chapter_closing"], "priority": "high"},
            {"title": "正文主生成方法", "body": method_block, "tags": ["方法", "收束"], "stages": ["chapter_closing"], "priority": "high"},
            {"title": "本章人物投放提示", "body": _section_block("本章人物投放提示", _compact_pretty(_chapter_stage_casting_prompt_payload(chapter_plan.get("planning_packet") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["投放", "新人", "换功能"], "stages": ["chapter_closing"], "priority": "high"},
            {"title": "正文主体长度", "body": _section_block("正文主体长度", f"""当前正文主体约 {len(existing)} 个可见字符；整章目标区间仍是 {target_visible_chars_min}-{target_visible_chars_max}。
本次只负责最后收束，建议新增约 {closing_target_visible_chars_min}-{closing_target_visible_chars_max} 个可见字符。"""), "tags": ["长度", "预算"], "stages": ["chapter_closing"], "priority": "medium"},
            {"title": "文风继承摘要", "body": _section_block("文风继承摘要", _compact_pretty(style_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["文风", "继承"], "stages": ["chapter_closing"], "priority": "medium"},
            {"title": "轻量连续性锚点", "body": _section_block("轻量连续性锚点", _compact_pretty(continuity_summary, max_depth=3, max_items=8, text_limit=100) if continuity_summary else '无'), "tags": ["连续性", "锚点"], "stages": ["chapter_closing"], "priority": "medium"},
            {"title": "正文开头风格锚点", "body": _section_block("正文开头风格锚点", head_anchor or '无'), "tags": ["风格锚点"], "stages": ["chapter_closing"], "priority": "low"},
            {"title": "最后一条完整句", "body": _section_block("最后一条完整句", last_complete_sentence or '无'), "tags": ["结尾", "句子"], "stages": ["chapter_closing"], "priority": "medium"},
            {"title": "若存在残缺片段", "body": _section_block("若存在残缺片段", dangling_fragment or '无'), "tags": ["残缺", "动作链"], "stages": ["chapter_closing"], "priority": "high"},
            {"title": "正文主体最后两段", "body": _section_block("正文主体最后两段", tail_paragraphs or tail_excerpt), "tags": ["尾部", "近文"], "stages": ["chapter_closing"], "priority": "high"},
            {"title": "正文主体尾部片段", "body": _section_block("正文主体尾部片段", tail_excerpt), "tags": ["尾部", "片段"], "stages": ["chapter_closing"], "priority": "medium"},
        ],
    )
    return f"""
请在已经写好的正文主体后面，补写这一章最后的收束段落。

{context_block}

输出要求：
1. 只输出紧接正文主体后面的新增文本，默认写 1-2 段，不要重写更前面的正文。
2. 先吃掉当前尾部尚未落地的动作、判断、对白或异常，再把本章应有的结果、压力、选择或钩子落下来；若提供了【轻量连续性锚点】，不能把上一章未完动作链写丢。
3. 延续正文主体已有的动作密度、对话节奏、句长呼吸和叙事视角，不要突然变成总结、解释或提纲腔。
4. 章末必须服从本章规划中的 payoff_or_pressure / ending_hook / hook_style，不要提前把下一章的大事件写出来。
5. 若主体已经很接近收束，只补 1-3 句即可；但必须自然闭合，不能停在半句、未闭合引号或悬空判断上。
6. 不要重复尾部已有句子，不要回头概括全章，不要为了收尾硬塞世界观解释。
7. 不要突然切新地点、新时间，也不要额外引入未铺垫的重要人物。
8. 若【本章人物投放提示】写明 final_should_execute_planned_action=true，就把对应人物投放动作在章末自然落稳；若 final_do_not_force_action=true，就不要为了收尾阶段硬塞新人或硬改旧角色作用位。
9. 若【文风继承摘要】提示对白偏高/偏低、句长偏短/偏长、动作密度偏高/偏低，就按那个方向收尾，不要突然换档。
10. 尽量避开这些安全句式或固定模板：
{blacklist}
11. 只输出新增正文，不要标题、不要注释、不要“续写如下”。
""".strip()


def chapter_draft_user_prompt(
    novel_context: dict[str, Any],
    chapter_plan: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
    target_words: int,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> str:
    workflow_runtime = ((novel_context or {}).get("story_memory") or {}).get("workflow_runtime") or {}
    runtime_feedback = dict(workflow_runtime.get("retry_feedback") or {})
    plan_retry_feedback = chapter_plan.get("retry_feedback") or {}
    if isinstance(plan_retry_feedback, dict):
        runtime_feedback.update({key: value for key, value in plan_retry_feedback.items() if value is not None})
    proactive_move = _text(chapter_plan.get("proactive_move"), "主角必须主动做出判断并推动局势前进。")
    agency_mode_block = _agency_mode_prompt_block(chapter_plan)
    progress_result_block = _progress_result_prompt_block(chapter_plan)
    agency_constraints = f"""
【主角主动性硬约束】
- 本章指定主动动作：{proactive_move}
- 前两段内必须让主角先做一个可见动作或判断；也可以是设问、验证或改条件，不能先站着听、站着看、压下念头。
- 本章至少出现一次完整链条：主角先手 -> 外界反应 -> 主角顺势调整或加码。
- 中段受阻后，主角必须再追一步：追问、换价、设局、藏证、试探、借规矩、抢先出手、换验证方法，至少落实一种。
- 主动不只有一种形状：可以是试探、设局、交易、验证、表态或逆势押注；关键是主角主动施加影响。
- 谨慎不等于被动；若主角需要隐藏，也要写成“先藏、先试、先换、先误导、先撤再回身”的主动谨慎。
- 禁止把“只是观察局势、没有立刻行动、暂时压下念头”写成整章的主导状态。
""".strip()
    runtime_feedback_block = ""
    if runtime_feedback:
        runtime_feedback_block = f"\n\n【本章重试纠偏】\n{_compact_pretty(runtime_feedback, max_depth=3, max_items=6, text_limit=100)}\n若上一次草稿被指出'主角被动'或'主动性不足'，这次必须优先修正，不得重复同类写法。"
    repetition_note = chapter_plan.get("writing_note")
    repetition_block = f"\n【额外写作提醒】\n{repetition_note}\n" if repetition_note else ""
    protagonist_name = _protagonist_name_from_context(novel_context)
    planning_packet = chapter_plan.get("planning_packet") or {}
    planning_packet_summary = _chapter_body_plan_packet_summary({"planning_packet": planning_packet}) if planning_packet else {}
    planning_packet_block = f"\n【本章规划包】\n{_compact_pretty(planning_packet_summary, max_depth=3, max_items=8, text_limit=100)}\n" if planning_packet_summary else ""
    blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST)
    retry_prompt_mode = _text(chapter_plan.get("retry_prompt_mode")).lower()
    compact_memory = _compact_pretty(compact_data({
        "project_card": ((novel_context or {}).get("story_memory") or {}).get("project_card"),
        "current_volume_card": ((novel_context or {}).get("story_memory") or {}).get("current_volume_card"),
        "execution_brief": ((novel_context or {}).get("story_memory") or {}).get("execution_brief"),
        "recent_retrospectives": ((novel_context or {}).get("story_memory") or {}).get("recent_retrospectives"),
        "hard_fact_guard": ((novel_context or {}).get("story_memory") or {}).get("hard_fact_guard"),
        "workflow_runtime": ((novel_context or {}).get("story_memory") or {}).get("workflow_runtime"),
    }, max_depth=3, max_items=8, text_limit=100), max_depth=3, max_items=8, text_limit=100)
    compact_plan_view = _compact_pretty(_chapter_plan_prompt_view(chapter_plan, include_packet=False), max_depth=3, max_items=8, text_limit=120)
    compact_last_view = _compact_pretty(_chapter_body_last_chapter_summary(last_chapter), max_depth=3, max_items=8, text_limit=100)
    compact_recent_view = _compact_pretty(_recent_summaries_prompt_view(recent_summaries, limit=2), max_depth=3, max_items=6, text_limit=100)
    prompt_context = {
        "goal": chapter_plan.get("goal"),
        "flow": chapter_plan.get("flow_template_name") or chapter_plan.get("flow_template_tag") or chapter_plan.get("flow_template_id"),
        "focus_character": ((chapter_plan.get("planning_packet") or {}).get("selected_elements") or {}).get("focus_character"),
        "event_type": chapter_plan.get("event_type"),
        "progress_kind": chapter_plan.get("progress_kind"),
    }
    if retry_prompt_mode in {"compact", "light"}:
        compact_block = _soft_sorted_section_block(
            "chapter_draft_retry",
            prompt_context,
            [
                {"title": "本章拍表", "body": _section_block("本章拍表", compact_plan_view), "tags": ["计划", "流程", "本章"], "stages": ["chapter_draft_retry"], "priority": "must"},
                {"title": "必要上下文", "body": _section_block("必要上下文", compact_memory), "tags": ["记忆", "硬事实"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "上一章信息", "body": _section_block("上一章信息", compact_last_view), "tags": ["上一章", "承接"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "最近摘要", "body": _section_block("最近摘要", compact_recent_view), "tags": ["最近摘要", "连续性"], "stages": ["chapter_draft_retry"], "priority": "medium"},
                {"title": "本章规划包", "body": planning_packet_block.strip(), "tags": ["规划包", "局部卡片"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "本章主动方式", "body": agency_mode_block, "tags": ["主动性", "模式"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "本章推进结果", "body": progress_result_block, "tags": ["推进", "结果"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "本章人物投放提示", "body": _section_block("本章人物投放提示", _compact_pretty(_chapter_stage_casting_prompt_payload(chapter_plan.get("planning_packet") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["投放", "新人", "换功能"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "主角主动性硬约束", "body": agency_constraints, "tags": ["主动性", "硬约束"], "stages": ["chapter_draft_retry"], "priority": "must"},
                {"title": "本章重试纠偏", "body": runtime_feedback_block.strip(), "tags": ["纠偏", "重试"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "额外写作提醒", "body": repetition_block.strip(), "tags": ["反重复", "提醒"], "stages": ["chapter_draft_retry"], "priority": "medium"},
            ],
        )
        return f"""
请直接重写这一章正文，并优先修正上一次草稿的问题。

{compact_block}

写作要求：
1. 只写完整章节正文，不要标题、JSON、markdown。
2. 前两段就让主角先手，形成“主角动作/判断 -> 外界反应 -> 主角调整”的链条。
3. 至少推进一项清晰结果：信息、关系、资源、风险或实力。
4. 必须有开场动作、中段受阻、一次发现和自然收束的结尾。
5. 严格服从硬事实与上一章衔接，别改人物状态、物件归属和时序。
6. 目标约 {target_words} 字，尽量控制在 {target_visible_chars_min}-{target_visible_chars_max} 个中文可见字符。
7. 这次优先修复：主动性、推进、篇幅、结尾，不要再回到模板句和空转气氛。
8. 若提供了【本章规划包】，正文只围绕其中 recent_continuity_plan / selected_elements / card_index / card_selection / relevant_cards / resource_plan / resource_capability_plan / continuity_window / opening_reveal_guidance / character_template_guidance 写，不要回看全书或擅自扩成全量卡池。
8.1 若 opening_reveal_guidance 提供了当前窗口该补的世界/势力/实力等级信息，就把它自然揉进动作、对话、试错和代价里，不要写成设定说明书，也别拖到前20章后还含糊。
9. 若【本章人物投放提示】写明 final_should_execute_planned_action=true，就把对应人物投放动作自然落进本章正文；若 final_do_not_force_action=true，就不要为了补新人或换功能硬塞多余动作。
10. recent_continuity_plan 负责最近几章的承接链：recent_progression / carry_in / current_chapter_bridge / lookahead_handoff 都要尽量兑现，别把上一章和下一章写断。
11. 若 relevant_cards.resources 或 resource_plan 提供了 quantity / unit / delta_hint，正文必须保持资源数量、消耗和剩余量前后一致，不能把三块灵石写成五块。
12. 若 resource_capability_plan 或资源卡里提供了 ability_summary / core_functions / activation_rules / usage_limits / costs / unlock_state，只能按这些边界写资源能力，不能临场把核心资源写成万能外挂。
13. 开头承接上一章末尾时，优先吃掉 continuity_window 里的 last_chapter_tail_excerpt / opening_anchor / unresolved_action_chain。
14. 禁止出现这些重复模板：
{blacklist}
""".strip()
    full_memory_view = _compact_pretty(_novel_context_prompt_view(novel_context), max_depth=3, max_items=8, text_limit=120)
    recent_view = _compact_pretty(_recent_summaries_prompt_view(recent_summaries, limit=4), max_depth=3, max_items=6, text_limit=100)
    interventions_view = _compact_pretty(_interventions_prompt_view(active_interventions, limit=4), max_depth=3, max_items=6, text_limit=100)
    full_block = _soft_sorted_section_block(
        "chapter_draft_full",
        prompt_context,
        [
            {"title": "本章拍表", "body": _section_block("本章拍表", compact_plan_view), "tags": ["计划", "流程", "本章"], "stages": ["chapter_draft_full"], "priority": "must"},
            {"title": "本章规划包", "body": planning_packet_block.strip(), "tags": ["规划包", "局部连续性", "卡片"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "上一章信息", "body": _section_block("上一章信息", compact_last_view) + "\n\n若【上一章信息】里包含 continuity_bridge / last_two_paragraphs / last_scene_card / unresolved_action_chain / onstage_characters，必须把它们视为开章硬承接依据。", "tags": ["上一章", "承接", "连续性"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "轻量小说记忆", "body": _section_block("轻量小说记忆", full_memory_view), "tags": ["记忆", "硬事实", "项目卡"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "最近章节摘要", "body": _section_block("最近章节摘要", recent_view), "tags": ["最近摘要", "连续性"], "stages": ["chapter_draft_full"], "priority": "medium"},
            {"title": "当前生效的读者干预", "body": _section_block("当前生效的读者干预", interventions_view), "tags": ["干预", "偏好"], "stages": ["chapter_draft_full"], "priority": "medium"},
            {"title": "本章主动方式", "body": agency_mode_block, "tags": ["主动性", "模式"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "本章推进结果", "body": progress_result_block, "tags": ["推进", "结果"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "本章人物投放提示", "body": _section_block("本章人物投放提示", _compact_pretty(_chapter_stage_casting_prompt_payload(chapter_plan.get("planning_packet") or {}), max_depth=4, max_items=8, text_limit=90)), "tags": ["投放", "新人", "换功能"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "主角主动性硬约束", "body": agency_constraints, "tags": ["主动性", "硬约束"], "stages": ["chapter_draft_full"], "priority": "must"},
            {"title": "本章重试纠偏", "body": runtime_feedback_block.strip(), "tags": ["纠偏", "重试"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "额外写作提醒", "body": repetition_block.strip(), "tags": ["反重复", "提醒"], "stages": ["chapter_draft_full"], "priority": "medium"},
            {"title": "连续性输入规则", "body": "若【本章规划包】里包含 recent_continuity_plan / continuity_window / selected_elements / relevant_cards / resource_capability_plan，也必须把它们当成本章正文的局部连续性输入：先承接，再推进，不要回顾全书。", "tags": ["连续性", "规则"], "stages": ["chapter_draft_full"], "priority": "high"},
        ],
    )
    return f"""
请根据以下信息写出下一章正文。

{full_block}

写作要求：
1. 用中文写完整下一章，目标约 {target_words} 字，建议控制在 {target_visible_chars_min}-{target_visible_chars_max} 个中文可见字符之间，允许自然波动，但必须写成完整一章而不是片段。
2. 把【轻量小说记忆】中的 project_card / current_volume_card / protagonist_state / near_7_chapter_outline / foreshadowing / daily_workbench / execution_brief / recent_retrospectives / character_roster / hard_fact_guard 当成硬约束，严格按“项目卡 -> 当前卷卡 -> 近7章近纲 -> 本章执行卡 -> 复盘纠偏 -> 正文”的顺序落实，不得跳步。
3. 本章只围绕 1 个核心场景与 1 个主要矛盾展开，节奏稳定、连贯。
4. 本章必须依次落到四个拍点：开场落点、一次中段受阻或转折、一次具体发现、一个来自当前场景的结尾钩子。
5. 本章不能重复最近两章的主事件类型；如果最近两章都在隐藏、盘问、怀疑，本章必须换挡，改成资源获取、关系推进、反制、外部任务或危机爆发中的一种有效推进。
6. 本章必须有明确推进，至少推进信息、关系、资源、实力、风险中的一项，并且正文里要让读者看得见这个推进结果。
7. 主角不能只被动应对，本章必须存在至少一个主动行为或主动决策，优先落实 chapter_execution_card 里的 proactive_move，并贴合本章的主动方式。
7.1 开头两段必须先给主角一个可见动作、试探、验证、表态或改条件，再给环境反应，不要先空转气氛。
7.2 中段受阻后，主角必须再追一步，不能只是心里一沉或暂时按下不动。
7.3 结尾的变化最好来自主角本章的先手动作，而不是纯粹等外界把事情送上门；但主动方式不必每章都一样。
8. 优先写具体的动作、观察、试探和对话，不要用旁白总结剧情，不要像提纲扩写。
6. 开头必须直接落在当前场景，不要用空泛天气句、危险句、任务句开场。
7. 轻量上下文只提供当前章真正需要的记忆点，不要机械复述设定，不要回顾整本书。
7.1 若提供了【本章规划包】，正文输入顺序固定为：本章拍表 -> 近章承接规划 -> 本章规划包 -> 最近几章摘要 -> 上一章末尾正文片段。不要脱离这个顺序乱扩写。
7.1.1 若本章规划包里附带 opening_reveal_guidance，就把当前窗口该补的世界/势力/实力等级信息自然埋进本章动作、试探、受挫或他人评价里；不要写成硬设定说明，也不要拖过前20章。
7.2 recent_continuity_plan 负责把最近两三章接成一条连续线：recent_progression 负责回看推进，carry_in / current_chapter_bridge 负责本章承接，lookahead_handoff 负责给后一两章留自然入口。
7.3 recent_chapter_summaries 负责承接最近几章的事件连续性，last_chapter_tail_excerpt / last_two_paragraphs 负责承接场面与语气连续性，两者都要吃进去。
7.4 selected_elements / relevant_cards 之外的角色、资源、势力，除非上下文明确要求，否则不要突然大量拉入本章；若 planning_packet 还带了 card_selection，也把它当成本章局部选卡参考。
7.5 若本章规划包里提供了 resource_plan，则把它视为资源数量与变化的硬参考：起始数量、单位、计划消耗/获得都要尽量保持一致。
7.6 若本章规划包里提供了 resource_capability_plan，则把它视为资源能力使用的硬参考：哪些资源该用、怎么用、付什么代价、有哪些限制，都要尽量兑现；核心资源只能小步显露，不得跳级成万能解题。
8. 结尾必须自然收束，不能停在半句上；是否留悬念，要服从本章 hook_style。若是“平稳过渡/余味收束”，可以只落在人物选择、结果落地、关系变化或下一步准备上，不必硬留悬念。
10. {_chapter_genre_guidance(novel_context)}
11. 配角不能只是抛信息的工具人。尤其是反复出现的人物，要给他一点职业习惯、说话方式、私心、忌讳或防备心理，让他先像人，再推动情节。
12. 若本章出现反派、帮众或威胁角色，至少给他们一处能被记住的细节：口头禅、手势、癖好、伤疤、做事逻辑或对上位者的惧怕。
13. 若本章涉及失去、离别、当掉旧物、被迫离开、冒险抉择等情节，要把{protagonist_name}的情绪再往下沉半层，但通过动作、停顿、视线、呼吸、手指和旧物处理落出来，不要一句带过，也不要直接抒情喊痛。
14. 若本章拍表给了 supporting_character_focus / supporting_character_note，至少在一个场面里落实出来；同一个配角不能永远只负责盘问或警告，要写出他的说话风格、利益诉求、受压反应、小动作或忌讳。
15. 若【本章规划包】里提供了 character_template_guidance，或轻量记忆里提供了 execution_brief.character_voice_pack / story_memory.character_roster，必须让对应人物说话和做事贴着这些差异化信息写，不能重新写回模板腔。
16. 若【本章人物投放提示】写明 final_should_execute_planned_action=true，就自然承担该动作；若 planned_action=new_core_entry，只落一个新人或新核心位；若 planned_action=role_refresh，只让对应旧角色换成更能带剧情的作用位。若 final_do_not_force_action=true，就不要为此硬塞额外人物投放。
17. 若轻量记忆里提供了 recent_retrospectives，优先避免里面指出的重复问题，尤其不要再写“同类桥段重复、主角被动、配角功能化、结尾发虚”。
18. 对话要分人：掌柜、摊主、帮众、散修、同门、师长，不要全都说成同一种冷硬叙述腔。
19. 句子可以克制，但不要一味求稳；少量关键句要更具体、更有辨识度，不要全靠“温凉/微弱/若有若无/看了片刻/没有再说什么”这种安全表达支撑氛围。
20. 本章结尾必须形成追更动力或结果落地，优先服从 chapter_execution_card 的 chapter_hook / hook_kind；禁止用“回去休息了/暂时压下念头/明日再看/夜色沉沉事情暂告一段落”这类平钩子收尾。
18. 只允许温和体现读者干预，不能破坏章节主目标。
19. 若轻量上下文与本章拍表有轻微冲突，以本章拍表和上一章衔接为准。
20. 若提供了上一章 continuity_bridge，开头两段必须优先承接它的 opening_anchor / last_two_paragraphs / unresolved_action_chain，除非本章拍表明确要求跳场，否则不要突然切镜头。
21. 若提供了上一章 last_scene_card，本章第一场必须与它的 main_scene、在场人物、未完成动作链或结尾局势保持连续；可以推进，但不能像换了一本书。
22. 保持核心机缘、线索物件或关键关系的状态稳定；如果上一章写的是一枚令牌、一株灵草、一段关系，这一章不能无说明改成别的东西。
23. 如果本章存在数日或半个月的时间跳跃，必须在前两段明确写出过渡，不要突然跳时间。
24. 只输出章节正文，不要输出标题、JSON、markdown、解释或自我分析。
25. 少于 {target_visible_chars_min} 个可见中文字符视为偏短，必须补足场景细节、互动过程和信息推进，不要匆忙收尾。
26. 若最近两三章都在调查同一条线索，本章至少要推进其中一种变化：线索状态变化、资源兑现、地图切换、对手介入、关系变化或能力验证。
27. 除非当前上下文已经明确建立，否则不要自行把剧情锁定成“药铺-掌柜-残页-坊市-夜探”这一固定组合。
28. 数量、伤势、旧物、地点和时序必须与上下文一致，不能把三块灵石写成五块，也不能把旧伤位置和人物经历写乱。
29. 若轻量记忆里提供了 hard_fact_guard，必须优先服从其中的境界、生死、伤势、身份暴露和关键物件归属；除非本章明确写出突破、疗伤、复生、遮掩或转移过程，否则不能直接改写这些状态。
30. 下面这些重复模板绝对不要出现：
{blacklist}
""".strip()





def _head_excerpt(text: str, max_chars: int = 260) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if len(raw) <= max_chars:
        return raw
    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    if not blocks:
        return raw[:max_chars].rstrip()
    chosen: list[str] = []
    current = 0
    for block in blocks:
        extra = len(block) + (2 if chosen else 0)
        if chosen and current + extra > max_chars:
            break
        chosen.append(block)
        current += extra
        if current >= max_chars:
            break
    return "\n\n".join(chosen).strip() or raw[:max_chars].rstrip()


def _keyword_chunks(value: Any) -> list[str]:
    raw = _text(value)
    if not raw:
        return []
    cleaned = raw
    for token in ["，", "。", "；", "：", ",", ".", ";", ":", "（", "）", "(", ")", "、", "\n", "\t", "-", "—", "|", "/"]:
        cleaned = cleaned.replace(token, " ")
    parts = [part.strip() for part in cleaned.split() if part.strip()]
    chunks: list[str] = []
    for part in parts:
        compact = part.strip()
        if len(compact) >= 2 and compact not in chunks:
            chunks.append(compact)
    if raw and raw not in chunks and len(raw) <= 18:
        chunks.insert(0, raw)
    return chunks[:6]


def _phrase_hits_text(text: str, phrase: Any) -> bool:
    haystack = (text or "").strip()
    if not haystack:
        return False
    for chunk in _keyword_chunks(phrase):
        if chunk in haystack:
            return True
    return False


def _style_inheritance_summary(existing_content: str) -> dict[str, Any]:
    raw = (existing_content or "").strip()
    if not raw:
        return {
            "叙事视角": "默认延续当前章既有视角""",
            "句长节奏": "均衡",
            "对白占比": "偏低",
            "动作密度": "中等",
            "风格提醒": ["延续当前章已有的叙事口径，不要突然改腔。"],
        }

    sentence_delims = "。！？!?；;…"
    sentence_count = sum(raw.count(ch) for ch in sentence_delims)
    sentence_count = max(sentence_count, 1)
    avg_sentence_len = max(len(raw) // sentence_count, 1)

    dialogue_marks = raw.count("“") + raw.count("”") + raw.count('"')
    dialogue_ratio = dialogue_marks / max(len(raw), 1)
    if dialogue_ratio >= 0.03:
        dialogue_level = "偏高"
    elif dialogue_ratio >= 0.012:
        dialogue_level = "均衡"
    else:
        dialogue_level = "偏低"

    action_tokens = ["抬", "按", "握", "看", "退", "进", "收", "换", "压", "拧", "踢", "摸", "试", "转", "盯", "听", "扫", "探", "撑", "推", "掐", "站", "蹲"]
    action_hits = sum(raw.count(token) for token in action_tokens)
    if action_hits >= max(len(raw) // 55, 10):
        action_level = "偏高"
    elif action_hits >= max(len(raw) // 95, 5):
        action_level = "中等"
    else:
        action_level = "偏低"

    if avg_sentence_len <= 18:
        sentence_rhythm = "短促"
    elif avg_sentence_len <= 30:
        sentence_rhythm = "均衡"
    else:
        sentence_rhythm = "稍长"

    first_person_hits = raw.count("我") + raw.count("我们")
    third_person_hits = raw.count("他") + raw.count("她") + raw.count("方尘")
    perspective = "第一人称倾向" if first_person_hits > third_person_hits else "第三人称倾向"

    reminders: list[str] = []
    if dialogue_level == "偏高":
        reminders.append("对白占比已经不低，续写时优先沿着现有对话链推进，不要突然改成大段旁白总结。")
    else:
        reminders.append("当前对白并不密，续写时优先维持动作、观察和短对话交替的节奏。")
    if action_level == "偏高":
        reminders.append("当前章动作密度较高，续写和收尾要继续用可见动作带出判断，不要忽然空转抒情。")
    else:
        reminders.append("当前章更偏稳，续写时仍要有可见动作支撑推进，但不要为了热闹强行提速。")
    if sentence_rhythm == "短促":
        reminders.append("保持句子偏利落，少用解释腔长句把节奏拖松。")
    elif sentence_rhythm == "稍长":
        reminders.append("已有句子偏长，续写时注意别再膨胀成解释段，要保住读感的紧绷度。")
    else:
        reminders.append("句长整体均衡，续写时尽量延续同样的呼吸节奏。")

    return {
        "叙事视角": perspective,
        "句长节奏": sentence_rhythm,
        "对白占比": dialogue_level,
        "动作密度": action_level,
        "风格提醒": reminders,
    }




def _continuity_anchor_summary(last_chapter: dict[str, Any] | None, recent_summaries: list[dict[str, Any]] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    chapter = last_chapter or {}
    bridge = chapter.get("continuity_bridge") or {}
    scene_card = chapter.get("last_scene_card") or {}
    opening_anchor = _text(bridge.get("opening_anchor") or bridge.get("last_chapter_tail_excerpt"))
    unresolved = _text(bridge.get("unresolved_action_chain") or scene_card.get("unresolved_action_chain"))
    onstage = bridge.get("onstage_characters") or scene_card.get("onstage_characters") or []
    if opening_anchor:
        payload["上一章开场锚点"] = opening_anchor
    if unresolved:
        payload["上一章未完动作链"] = unresolved
    if onstage:
        payload["上一章在场人物"] = onstage
    summary_items: list[str] = []
    for item in recent_summaries or []:
        if not isinstance(item, dict):
            continue
        event = _text(item.get("event_summary") or item.get("summary") or item.get("title"))
        if event:
            summary_items.append(event)
        if len(summary_items) >= 2:
            break
    if summary_items:
        payload["最近推进摘要"] = summary_items
    return payload

def _chapter_state_summary(chapter_plan: dict[str, Any], existing_content: str) -> dict[str, Any]:
    existing = (existing_content or "").strip()
    summary: dict[str, Any] = {
        "当前场景": _text(chapter_plan.get("main_scene") or chapter_plan.get("title") or "当前场景"),
    }
    completed: list[str] = []
    pending: list[str] = []
    beat_map = [
        ("开场动作", chapter_plan.get("opening_beat") or chapter_plan.get("proactive_move")),
        ("中段受阻/转折", chapter_plan.get("mid_turn") or chapter_plan.get("conflict")),
        ("具体发现/验证", chapter_plan.get("discovery") or chapter_plan.get("payoff_or_pressure")),
        ("章末落点", chapter_plan.get("closing_image") or chapter_plan.get("ending_hook") or chapter_plan.get("payoff_or_pressure")),
    ]
    for label, phrase in beat_map:
        phrase_text = _text(phrase)
        if not phrase_text:
            continue
        if _phrase_hits_text(existing, phrase_text):
            completed.append(f"{label}：{phrase_text}")
        else:
            pending.append(f"{label}：{phrase_text}")

    if completed:
        summary["已完成拍点"] = completed
    if pending:
        summary["仍待落地"] = pending

    last_sentence = _last_complete_sentence(existing)
    dangling = _dangling_fragment(existing)
    if last_sentence:
        summary["最后完整句"] = last_sentence
    if dangling and dangling != last_sentence:
        summary["当前未闭合动作/判断"] = dangling

    supporting_focus = _text(chapter_plan.get("supporting_character_focus") or chapter_plan.get("supporting_character_note"))
    if supporting_focus:
        summary["配角提醒"] = supporting_focus
    summary["本章目标"] = _text(chapter_plan.get("goal"), "继续朝本章既定目标推进")
    summary["本章应兑现"] = _text(chapter_plan.get("payoff_or_pressure") or chapter_plan.get("ending_hook"), "让本章结果或压力落地")
    return summary

def _tail_excerpt(text: str, max_chars: int = 900) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if len(raw) <= max_chars:
        return raw

    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    if len(blocks) > 1:
        chosen: list[str] = []
        current = 0
        for block in reversed(blocks):
            extra = len(block) + (2 if chosen else 0)
            if chosen and current + extra > max_chars:
                break
            if not chosen and len(block) > max_chars:
                return block[-max_chars:].lstrip()
            chosen.append(block)
            current += extra
        if chosen:
            return "\n\n".join(reversed(chosen)).lstrip()

    return raw[-max_chars:].lstrip()


def _tail_paragraphs(text: str, *, count: int = 2) -> str:
    blocks = [block.strip() for block in (text or "").split("\n") if block.strip()]
    if not blocks:
        return ""
    return "\n\n".join(blocks[-count:])


def _last_complete_sentence(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    for idx in range(len(raw) - 1, -1, -1):
        if raw[idx] in "。！？!?…』」》）)】":
            return raw[: idx + 1].split("\n")[-1].strip()
    return ""


def _dangling_fragment(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    last_complete = _last_complete_sentence(raw)
    if not last_complete:
        return raw[-120:]
    last_index = raw.rfind(last_complete)
    fragment = raw[last_index + len(last_complete):].strip()
    return fragment or raw[-120:]


def _chapter_extension_plan_summary(chapter_plan: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "chapter_no", "title", "goal", "conflict", "progress_kind", "event_type",
        "flow_template_id", "flow_template_tag", "flow_template_name", "proactive_move",
        "payoff_or_pressure", "ending_hook", "hook_style", "hook_kind", "closing_image", "writing_note",
    )
    payload: dict[str, Any] = {}
    for key in keys:
        value = chapter_plan.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    return payload


def _repair_mode_instruction(repair_mode: str) -> str:
    mapping = {
        "append_inline_tail": "你要直接续接最后一句或最后一个动作链，只输出紧接原文尾部的新增文本，不要另起解释。",
        "replace_last_paragraph": "你要重写最后一段。输出内容必须是一整段替换稿，不要把前文再复制一遍。",
        "replace_last_two_paragraphs": "你要重写最后两段。输出内容必须是尾部替换稿，保留前文事实，不要扩写成新场景。",
    }
    return mapping.get(repair_mode, mapping["append_inline_tail"])


def chapter_extension_system_prompt(repair_mode: str = "append_inline_tail") -> str:
    return (
        "你是一名中文连载小说尾部修复助手。"
        "你的任务不是重写整章，而是修好正文尾部，让本章在当前场景内闭合，并且服从本章原定规划。"
        "不能改写前文既成事实，不能提前解决下一章的问题，不能突然开新地点、新时间、新人物线。"
        "修尾时要尽量贴住前文已经形成的句长、对白节奏、动作密度和叙事视角，不要一修就像换了作者。"
        "先对齐本章规划中的结尾目标，再处理文本完整性。"
        + _repair_mode_instruction(repair_mode)
        + "只输出用于拼接或替换的正文结果，不要解释，不要标题，不要 JSON。"
    )


def chapter_extension_user_prompt(
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    *,
    repair_mode: str = "append_inline_tail",
    ending_issue: str | None = None,
    repair_attempt_no: int = 1,
    previous_repair_modes: list[str] | None = None,
) -> str:
    existing = (existing_content or "").strip()
    tail_excerpt = _tail_excerpt(existing, max_chars=1100)
    tail_paragraphs = _tail_paragraphs(existing, count=2)
    last_complete_sentence = _last_complete_sentence(existing)
    dangling_fragment = _dangling_fragment(existing)
    full_visible_chars = len(existing)
    plan_summary = _chapter_extension_plan_summary(chapter_plan)
    state_summary = _chapter_state_summary(chapter_plan, existing)
    style_summary = _style_inheritance_summary(existing)
    continuity_summary = _continuity_anchor_summary(None, None)
    head_anchor = ""
    generation_method = _chapter_tail_generation_method_block(chapter_plan)
    previous_modes_text = "、".join(previous_repair_modes or []) or "无"
    hook_style = _text(chapter_plan.get("hook_style"), "保持本章原定的落点风格")
    landing_goal = _text(chapter_plan.get("payoff_or_pressure") or chapter_plan.get("ending_hook") or chapter_plan.get("closing_image"), "让当前场景自然收束")
    tail_blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST[:8])
    output_shape = {
        "append_inline_tail": "只输出紧接原文尾部的新增文本，优先补完残句，再补 1-3 句自然收束。",
        "replace_last_paragraph": "只输出用于替换最后一段的完整段落，不要复制更前面的段落。",
        "replace_last_two_paragraphs": "只输出用于替换最后两段的完整尾部块，不要扩到新场景。",
    }.get(repair_mode, "只输出修复后的尾部正文。")
    context_block = _soft_sorted_section_block(
        "chapter_extension",
        {"repair_mode": repair_mode, "landing_goal": landing_goal, "hook_style": hook_style},
        [
            {"title": "修复模式", "body": _section_block("修复模式", repair_mode), "tags": ["修复模式"], "stages": ["chapter_extension"], "priority": "must"},
            {"title": "当前问题", "body": _section_block("当前问题", f"""- 补写原因：{reason}
- ending_issue：{ending_issue or 'unknown'}
- 当前是第 {repair_attempt_no} 次尾部修复
- 之前已经尝试过的修法：{previous_modes_text}"""), "tags": ["问题", "修复"], "stages": ["chapter_extension"], "priority": "must"},
            {"title": "本章规划摘要", "body": _section_block("本章规划摘要", _compact_pretty(plan_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["计划", "本章"], "stages": ["chapter_extension"], "priority": "high"},
            {"title": "本章必须落到的结果/压力", "body": _section_block("本章必须落到的结果/压力", landing_goal), "tags": ["结果", "压力"], "stages": ["chapter_extension"], "priority": "high"},
            {"title": "章末风格", "body": _section_block("章末风格", hook_style), "tags": ["结尾", "风格"], "stages": ["chapter_extension"], "priority": "high"},
            {"title": "正文当前状态摘要", "body": _section_block("正文当前状态摘要", _compact_pretty(state_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["状态", "待落地"], "stages": ["chapter_extension"], "priority": "high"},
            {"title": "正文主生成方法", "body": generation_method, "tags": ["方法", "修尾"], "stages": ["chapter_extension"], "priority": "medium"},
            {"title": "全文长度", "body": _section_block("全文长度", f"当前正文约 {full_visible_chars} 个可见字符，修完后整章仍应尽量落在 {target_visible_chars_min}-{target_visible_chars_max} 个可见字符范围内。以下只提供结尾片段，目的是让你只做“补尾”。"), "tags": ["长度", "预算"], "stages": ["chapter_extension"], "priority": "medium"},
            {"title": "文风继承摘要", "body": _section_block("文风继承摘要", _compact_pretty(style_summary, max_depth=3, max_items=8, text_limit=100)), "tags": ["文风", "继承"], "stages": ["chapter_extension"], "priority": "medium"},
            {"title": "轻量连续性锚点", "body": _section_block("轻量连续性锚点", _compact_pretty(continuity_summary, max_depth=3, max_items=8, text_limit=100) if continuity_summary else '无'), "tags": ["连续性", "锚点"], "stages": ["chapter_extension"], "priority": "medium"},
            {"title": "最后一条完整句", "body": _section_block("最后一条完整句", last_complete_sentence or '无'), "tags": ["结尾", "句子"], "stages": ["chapter_extension"], "priority": "medium"},
            {"title": "当前残缺片段", "body": _section_block("当前残缺片段", dangling_fragment or '无'), "tags": ["残缺", "动作链"], "stages": ["chapter_extension"], "priority": "high"},
            {"title": "尾部最近两段", "body": _section_block("尾部最近两段", tail_excerpt), "tags": ["尾部", "近文"], "stages": ["chapter_extension"], "priority": "high"},
            {"title": "已有正文结尾片段", "body": _section_block("已有正文结尾片段", tail_excerpt), "tags": ["尾部", "片段"], "stages": ["chapter_extension"], "priority": "medium"},
            {"title": "正文开头风格锚点", "body": _section_block("正文开头风格锚点", head_anchor or '无'), "tags": ["风格锚点"], "stages": ["chapter_extension"], "priority": "low"},
        ],
    )
    return f"""
请修复这一章的尾部，但只能做尾部修复，不能改动更前面的剧情事实。

{context_block}

输出要求：
1. {output_shape}
2. 先处理文本完整性：补闭合引号、补完残句、补完动作链，不要让结尾停在半句、悬空比喻或未完成判断上。
3. 若结尾停在对白、命令、动作或判断的半句上，先把这一半句补完整，再补 1-3 个自然收束句。
4. 再对齐章节规划：章末必须落在本章已经铺开的结果、压力、选择、异常或具体画面上，不能提前写出下一章的大事件；优先兑现【正文当前状态摘要】里仍待落地的拍点。
5. 不要重复已有句子，不要回头总结，不要为了补完整而解释世界观。
6. 不要突然切新地点、新时间，也不要额外引入未铺垫的重要人物。
7. 若已有正文已经接近完整，只需补 80-220 字；若是重写尾段，保持尾部更紧，不要把范围越写越大。
8. 若【文风继承摘要】提示对白偏高/偏低、句长偏短/偏长、动作密度偏高/偏低，就按那个方向收尾，不要突然换档。
9. 尽量避开这些安全句式或固定模板：
{tail_blacklist}
10. 只输出修复结果本身，不要标题、不要注释、不要“修复如下”。
""".strip()


def summary_system_prompt() -> str:
    return (
        "你是小说章节摘要提取器。"
        "只提取正文里已经出现的信息，不要编造。"
        "不要输出 JSON，不要输出 markdown，不要解释你的思考过程。"
        "严格按给定标签输出。"
    )



def summary_user_prompt(chapter_title: str, chapter_content: str) -> str:
    return f"""
请提取下面这个章节的结构化摘要。

【章节标题】
{chapter_title}

【章节正文】
{chapter_content}

输出格式必须严格如下，缺少内容时写“无”：
事件摘要：<80字以内，一句话概括本章发生了什么>
人物变化：<若无则写 无>
新线索：<用；分隔，若无则写 无>
未回收钩子：<用；分隔，若无则写 无>
已回收钩子：<用；分隔，若无则写 无>

要求：
1. 不要输出任何额外说明。
2. 不要复述提示词。
3. 只基于正文提取。
""".strip()



def chapter_title_refinement_system_prompt() -> str:
    return (
        "你是小说章节标题精修器。"
        "你的任务不是复述剧情，而是给这一章起更稳、更不重复、更贴近成稿结果的标题。"
        "你必须避开最近章节的高相似标题与高频套词。"
        "标题要短，尽量 4 到 10 个汉字；允许更短，但不要空泛。"
        "优先使用具体结果、具体新信息、具体关系变化、具体风险落点。"
        "不要输出解释性散文，不要输出 markdown，只输出合法 JSON。"
    )



def chapter_title_refinement_user_prompt(
    *,
    chapter_no: int,
    original_title: str,
    chapter_plan: dict[str, Any],
    content_digest: dict[str, Any],
    summary_payload: dict[str, Any],
    recent_titles: list[str],
    cooled_terms: list[str],
    candidate_count: int,
) -> str:
    return f"""
请为第 {chapter_no} 章做标题精修。

【当前工作标题】
{original_title}

【本章计划】
{_compact_pretty(_chapter_plan_prompt_view(chapter_plan, include_packet=False), max_depth=3, max_items=8, text_limit=120)}

【本章成稿摘录】
{_compact_pretty(compact_data(content_digest, max_depth=3, max_items=8, text_limit=100), max_depth=3, max_items=8, text_limit=100)}

【本章摘要】
{_compact_pretty(compact_data(summary_payload, max_depth=3, max_items=8, text_limit=100), max_depth=3, max_items=8, text_limit=100)}

【最近章节标题】
{_compact_pretty(compact_data(recent_titles, max_depth=2, max_items=12, text_limit=40), max_depth=2, max_items=12, text_limit=40)}

【近期冷却词】
{_compact_pretty(compact_data(cooled_terms, max_depth=2, max_items=12, text_limit=20), max_depth=2, max_items=12, text_limit=20)}

要求：
1. 输出 {candidate_count} 个候选标题，并给出 recommended_title。
2. 标题尽量 4 到 10 个汉字，不要超过 14 个汉字。
3. 不要再写成“夜半微光 / 旧纸页 / 坊市试探 / 暗流再起”这种空泛氛围标题。
4. 标题必须更贴本章最终成稿，优先落在：结果、后果、新信息、人物选择、关系变化、具体风险、具体物件。
5. 候选标题之间也要有区分，不要只是同义换词。
6. 不要直接剧透终极秘密，但可以点出本章已经落地的变化。
7. 若当前工作标题已经不错，可以保留或微调，但不要机械复用最近章节的结构模板。
8. title_type 可参考：结果型 / 风险型 / 关系型 / 悬念型 / 物件型 / 地点型 / 人物选择型。
9. angle 用一句短话说明这个标题抓住了哪种落点。
10. reason 用一句短话说明为什么它比空泛标题更好。
11. 只输出 JSON，对象 schema 如下：
{_pretty(TITLE_REFINEMENT_SCHEMA)}
""".strip()



def instruction_parse_system_prompt() -> str:
    return (
        "你是读者意见解析器。"
        "你要把自然语言读者意见提炼成结构化约束。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )



def instruction_parse_user_prompt(raw_instruction: str) -> str:
    return f"""
请把下面这条读者意见解析成结构化结果。

【读者意见】
{raw_instruction}

要求：
1. character_focus 用角色名到强度的映射表示。
2. tone 只允许 lighter / darker / warmer / tenser / null。
3. pace 只允许 faster / slower / null。
4. protected_characters 只保留明确提到需要保护的角色。
5. relationship_direction 只允许 slow_burn / stronger_romance / weaker_romance / null。

请只输出 JSON，对象 schema 如下：
{_pretty(INSTRUCTION_OUTPUT_SCHEMA)}
""".strip()
