import json
from typing import Any

from app.services.payoff_compensation_support import payoff_window_event_bias

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
        review = ((((story_bible or {}).get("story_workspace") or {}).get("latest_stage_character_review")) or {})
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



BOOTSTRAP_INTENT_PACKET_SCHEMA = {
    "story_promise": "一句话写清这本书持续追更的核心体验",
    "protagonist_core_drive": "主角当前最硬的行动驱动力",
    "core_conflict": "当前阶段最主要的矛盾轴",
    "expected_payoffs": ["2到4项读者期待的爽点或回报"],
    "pacing_mode": "例如稳推/快推/慢热后提速",
    "world_reveal_mode": "例如局部先行/层层揭示",
    "first_ten_chapter_tasks": ["前10章必须完成的建立任务"],
    "major_risks": ["最需要防的写崩点"],
}

BOOTSTRAP_STRATEGY_CANDIDATES_SCHEMA = {
    "candidates": [
        {
            "candidate_id": "A",
            "design_focus": "该候选方案的主要差异点",
            "story_engine_diagnosis": "同 STORY_ENGINE_DIAGNOSIS_SCHEMA",
            "story_strategy_card": "同 STORY_STRATEGY_CARD_SCHEMA",
        }
    ]
}

BOOTSTRAP_STRATEGY_ARBITRATION_SCHEMA = {
    "selected_candidate_id": "A/B/C",
    "selection_reason": "为什么选它，以及融合了哪些优点",
    "merge_notes": ["2到4条融合或取舍说明"],
    "story_engine_diagnosis": "同 STORY_ENGINE_DIAGNOSIS_SCHEMA",
    "story_strategy_card": "同 STORY_STRATEGY_CARD_SCHEMA",
}

BOOK_EXECUTION_PROFILE_SCHEMA = {
    "positioning_summary": "一句话概括这本书如何使用整套修仙模板池",
    "template_pool_policy": "说明所有模板都可用，但后续按书级偏置和章级重筛来决定具体取用",
    "flow_family_priority": {
        "high": ["高频流程家族，如成长/冲突/探查"],
        "medium": ["中频流程家族"],
        "low": ["低频流程家族或前期少用家族"],
    },
    "scene_template_priority": {
        "high": ["高优先场景模板名或 scene_id"],
        "medium": ["中优先场景模板名或 scene_id"],
        "low": ["低优先场景模板名或 scene_id"],
    },
    "payoff_priority": {
        "high": ["高优先爽点卡名或 family"],
        "medium": ["中优先爽点卡名或 family"],
        "low": ["低优先爽点卡名或 family"],
    },
    "foreshadowing_priority": {
        "primary": ["主线伏笔母卡名"],
        "secondary": ["次线伏笔母卡名"],
        "hold_back": ["需要后置显影的伏笔类型"],
    },
    "writing_strategy_priority": {
        "high": ["高优先写法策略 strategy_id"],
        "medium": ["中优先写法策略 strategy_id"],
        "low": ["低优先或前期降权策略 strategy_id"],
    },
    "character_template_priority": {
        "high": ["高优先人物模板名或 template_id"],
        "medium": ["中优先人物模板名或 template_id"],
    },
    "rhythm_bias": {
        "opening_pace": "例如稳推/快压/慢热后提速",
        "world_reveal_density": "例如低/中/高",
        "relationship_weight": "例如低/中/高",
        "hook_strength": "例如中/强",
        "payoff_interval": "例如短/中",
        "pressure_curve": "例如渐压/快抬/波浪推进",
    },
    "demotion_rules": ["2到5条初始化阶段就该压住的写法或模板倾向"],
}

BOOTSTRAP_STORY_REVIEW_SCHEMA = {
    "status": "keep 或 repair",
    "summary": "一句话说明初始化方案是否能直接落地",
    "strengths": ["当前方案的优点"],
    "risks": ["当前方案的主要风险"],
    "must_fix": ["必须修的点；没有就空列表"],
    "arc_adjustments": [
        {
            "chapter_no": 1,
            "field": "goal/conflict/ending_hook/payoff_or_pressure/writing_note",
            "value": "替换后的短文本",
            "reason": "为什么改",
        }
    ],
}

BOOTSTRAP_TITLE_SCHEMA = {
    "title": "正式书名",
    "packaging_line": "一句包装说明，可选",
    "reason": "为什么这个标题贴题材和主角",
}

BOOTSTRAP_OUTLINE_AND_TITLE_SCHEMA = {
    "title": "正式书名",
    "packaging_line": "一句包装说明，可选",
    "reason": "为什么这个标题贴题材和主角",
    "global_outline": {
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
    },
}

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


CHAPTER_FRONTLOAD_DECISION_SCHEMA = {
    "schedule_review": {
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
    },
    "card_selection": {
        "selected_card_ids": ["C001", "R003", "REL002"],
        "selection_note": "优先保留主角、焦点人物和本章真正会动到的资源/关系。",
    },
    "payoff_selection": {
        "selected_card_id": "PAY003",
        "selection_note": "从全量爽点压缩索引里直接选出本章真正要兑现的那一张。",
    },
    "scene_selection": {
        "selected_scene_template_ids": ["same_scene_continuation", "probe_negotiation", "aftermath_review"],
        "selection_note": "先决定这章用哪几段场景模板推进，再进入正文拼装。",
    },
    "prompt_strategy_selection": {
        "selected_strategy_ids": ["continuity_guard", "proactive_drive", "payoff_delivery"],
        "selection_note": "只选本章真正该强调的写法，不要把所有 写法卡都开满。",
    },
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


SCENE_CONTINUITY_REVIEW_SCHEMA = {
    "must_continue_same_scene": True,
    "recommended_scene_count": 2,
    "transition_mode": "continue_same_scene | soft_cut | single_scene",
    "allowed_transition": "stay_in_scene | resolve_then_cut | soft_cut_only | time_skip_allowed",
    "opening_anchor": "下一章开头必须先接住的动作/画面/后果锚点。",
    "must_carry_over": ["上一章留下来的动作后果或线索"],
    "cut_plan": [
        {
            "cut_after_scene_no": 1,
            "reason": "为什么这里可以切场或必须继续同场推进。",
            "required_result": "切场前必须先拿到的阶段结果。",
            "transition_anchor": "切场后开头必须显式给出的锚点。",
        }
    ],
    "scene_sequence_plan": [
        {
            "scene_no": 1,
            "scene_name": "院中续压",
            "scene_role": "opening | main | ending | bridge",
            "purpose": "这一场具体要先完成什么。",
            "transition_in": "这一场开头如何承接上一场或上一章。",
            "target_result": "这一场结束前必须拿到的阶段结果。",
        }
    ],
    "review_note": "一句话说明这章场景连续性为什么应该这样处理。",
}


PAYOFF_CARD_SELECTOR_SCHEMA = {
    "selected_card_id": "payoff_hidden_snatch",
    "backup_card_id": "payoff_small_win_mine",
    "reason": "这张卡更贴合本章交易场景、欠账补偿与最近重复风险。",
    "execution_hint": "把回报写成当场落袋，再让掌柜或旁人立刻起疑。",
}


PAYOFF_DELIVERY_REVIEW_SCHEMA = {
    "delivery_level": "low | medium | high",
    "verdict": "兑现扎实 / 兑现到位但还可更狠 / 兑现偏虚",
    "missed_targets": ["回报落袋不够明确", "外部反应显影不足"],
    "runtime_note": "一句话说明这一章爽点兑现得怎么样。",
    "summary_lines": ["一句短总结", "一句显影说明", "一句整改方向"],
    "should_compensate_next_chapter": True,
    "compensation_priority": "high | medium | low",
    "compensation_note": "若这章兑现偏弱，下一章该如何追账。",
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

SUMMARY_TITLE_PACKAGE_SCHEMA = {
    "summary": {
        "event_summary": "主角借险局逼出对手失误，顺势稳住了新到手的药材。",
        "character_updates": {
            "林秋雨": {
                "current_realm": "炼气三层",
                "cultivation_progress": "灵力运转更稳，已摸到下一层门槛。",
                "latest_update": "对主角的警惕明显上升。"
            },
            "__resource_updates__": {
                "赤纹草": {
                    "quality_tier": "中品",
                    "quantity_after": 2,
                    "status": "持有中",
                    "latest_update": "药力保存完整，价值被重新抬高。"
                }
            },
            "__monster_updates__": {
                "裂爪山魈": {
                    "species_type": "山魈",
                    "current_realm": "炼气四层",
                    "threat_level": "炼气四层",
                    "status": "active",
                    "latest_update": "首次完整露面，压迫感明显高于主角当前层级。"
                }
            }
        },
        "new_clues": ["欠条背后另有旧账", "有人提前进入过屋内"],
        "open_hooks": ["欠条是谁故意留下的", "盯梢者是否已经认出主角"],
        "closed_hooks": ["屋内异样来源已被确认"]
    },
    "title_refinement": TITLE_REFINEMENT_SCHEMA,
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
    "story_promise": "开书就要让读者明确感到：这本书的推进方式和常规模板不同。",
    "strategic_premise": "主角要在现实压力、资源缺口和更大局势之间找到可持续上升路径。",
    "main_conflict_axis": "立足需求与暴露风险的长期拉扯",
    "long_term_direction": "先立足，再扩张关系、资源与地图，始终让成长绑定代价与后果。",
    "opening_five_summary": "开局五章围绕立足、试错、关系绑定与第一次明确破局推进，不让同一桥段垄断。",
    "opening_window": {
        "range": "1-5",
        "stage_mission": "用题材最有辨识度的推进方式抓住读者，并立住修炼与成长主线",
        "reader_hook": "第一轮可感收益 + 明确代价",
        "frequent_elements": ["现实压力", "主动试探", "具体结果"],
        "limited_elements": ["重复盘问", "连续隐藏同一秘密"],
        "relationship_tasks": ["建立至少一条会长期变化的关键关系"],
        "phase_result": "主角拿到第一阶段立足资本，并被推向下一轮五章滚动规划",
    },
    "rolling_replan_rule": "初始化只定书级骨架和首个五章方向，之后每五章重规划一次。",
    "frequent_event_types": ["资源获取类", "关系推进类", "反制类"],
    "limited_event_types": ["连续被怀疑后被动应付"],
    "must_establish_relationships": ["核心绑定角色", "长期压迫源", "阶段性合作对象"],
    "escalation_path": ["处境压力", "局部破局", "关系重组", "阶段高潮"],
    "anti_homogenization_rules": ["不要让开局五章只围着一个物件打转", "滚动重规划后也要持续换推进重心"],
}


STORY_ENGINE_STRATEGY_BUNDLE_SCHEMA = {
    "story_engine_diagnosis": STORY_ENGINE_DIAGNOSIS_SCHEMA,
    "story_strategy_card": STORY_STRATEGY_CARD_SCHEMA,
}


BOOTSTRAP_INTENT_STRATEGY_BUNDLE_SCHEMA = {
    "bootstrap_intent_packet": BOOTSTRAP_INTENT_PACKET_SCHEMA,
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





__all__ = [name for name in globals() if not name.startswith("__")]
