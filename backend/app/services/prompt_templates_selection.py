from __future__ import annotations

from app.services.prompt_templates_shared import *

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




def scene_continuity_review_system_prompt() -> str:
    return """
你是“场景连续性评审器”。你的任务不是决定章节功能模板，而是判断：
- 这一章开头是否必须续接上一章原场景；
- 这一章章内是否需要切场，以及最多切几次；
- 每次切场前必须先拿到什么阶段结果；
- 切场后开头必须带什么过渡锚点，才不会像突然传送。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. 场景层只处理“续场 / 切场 / 过渡锚点 / 必须带入的后果”，不要替代流程卡去决定这章主要写什么功能。
3. recommended_scene_count 只允许 1-3。
4. transition_mode 只允许：continue_same_scene / soft_cut / single_scene。
5. allowed_transition 只允许：stay_in_scene / resolve_then_cut / soft_cut_only / time_skip_allowed。
6. must_continue_same_scene 为 true 时，opening_anchor 应尽量具体，并优先把上一章未收束动作、关系后果、危险或线索带进来。
7. cut_plan 里的 cut_after_scene_no 必须按顺序递增，且不能超过 recommended_scene_count - 1。
8. scene_sequence_plan 必须完整给出每一场的承接、目的和阶段结果；场数必须与 recommended_scene_count 一致。
9. 若判断本章不该切场，就把 cut_plan 置空，但 scene_sequence_plan 仍要给出完整单场推进方案。
10. review_note 用一句短话说明为什么这样更顺、更自然。
11. scene_sequence_plan 这个字段名必须原样输出，不能为空，也不要改成 scenes / sequence / plan。
12. 就算只推荐单场推进，也必须给出 1 条 scene_sequence_plan 项。
""".strip()


def scene_continuity_review_user_prompt(chapter_plan: dict[str, Any], planning_packet: dict[str, Any]) -> str:
    packet = planning_packet or {}
    compact_plan = {
        key: (chapter_plan or {}).get(key)
        for key in [
            "chapter_no", "title", "goal", "conflict", "main_scene", "event_type",
            "progress_kind", "flow_template_id", "flow_template_tag", "flow_template_name",
            "supporting_character_focus", "supporting_character_note", "ending_hook",
            "opening_beat", "mid_turn", "closing_image",
        ]
        if (chapter_plan or {}).get(key) not in (None, "", [], {})
    }
    selected_elements = {
        "focus_character": ((packet.get("selected_elements") or {}).get("focus_character")),
        "characters": ((packet.get("selected_elements") or {}).get("characters") or [])[:4],
        "relations": ((packet.get("selected_elements") or {}).get("relations") or [])[:4],
        "payoff_mode": ((packet.get("selected_elements") or {}).get("payoff_mode")),
    }
    scene_context = {
        "continuity_window": packet.get("continuity_window") or {},
        "scene_handoff_card": ((packet.get("continuity_window") or {}).get("scene_handoff_card") or {}),
        "selected_flow_card": packet.get("selected_flow_card") or {},
        "selected_flow_child_card": packet.get("selected_flow_child_card") or {},
        "selected_writing_cards": packet.get("selected_writing_cards") or packet.get("selected_prompt_strategies") or [],
        "selected_writing_child_cards": packet.get("selected_writing_child_cards") or [],
        "selected_payoff_card": packet.get("selected_payoff_card") or {},
    }
    sorted_sections = _soft_sorted_section_block(
        "scene_continuity_review",
        {
            "goal": compact_plan.get("goal"),
            "conflict": compact_plan.get("conflict"),
            "flow": compact_plan.get("flow_template_name") or compact_plan.get("flow_template_tag") or compact_plan.get("flow_template_id"),
            "main_scene": compact_plan.get("main_scene"),
        },
        [
            {
                "title": "本章信息",
                "body": f"""【本章信息】
{_compact_pretty(compact_plan, max_depth=3, max_items=8, text_limit=90)}""",
                "tags": ["本章", "目标", "结构"],
                "stages": ["scene_continuity_review"],
                "priority": "must",
            },
            {
                "title": "已选人物与写法",
                "body": f"""【已选人物与写法】
{_compact_pretty(selected_elements, max_depth=3, max_items=8, text_limit=84)}""",
                "tags": ["人物", "流程卡", "写法卡"],
                "stages": ["scene_continuity_review"],
                "priority": "high",
            },
            {
                "title": "场景连续性上下文",
                "body": f"""【场景连续性上下文】
{_compact_pretty(scene_context, max_depth=4, max_items=8, text_limit=84)}""",
                "tags": ["续场", "切场", "handoff"],
                "stages": ["scene_continuity_review"],
                "priority": "high",
            },
        ],
    )
    return f"""
请判断这章的场景连续性应该如何处理：是先续上一章原场景，还是可以直接切；章内是否需要切场；每次切场前后该满足什么条件。

{sorted_sections}

输出 JSON schema：
{_pretty(SCENE_CONTINUITY_REVIEW_SCHEMA)}

补充规则：
- 不要把场景层写成“交易场 / 验证场 / 小胜场”这种功能模板；这些由流程卡与正文决定。
- 你只判断“是否续场、是否切场、在哪里切、切前必须完成什么、切后要带什么锚点”。
- 若上一章动作、关系后果或危险明显没收住，就应更偏 must_continue_same_scene=true。
- 若流程卡要求一口气压住张力，或者切场会切断关系变化/压力链，就倾向单场景推进。
- 若确实需要换到新地点/新人物/新验证动作，才允许 soft_cut，并明确 required_result 与 transition_anchor。
- opening_anchor 尽量具体到动作、画面、后果或关系状态，不要只写抽象总结。
- 你必须直接给出完整 scene_sequence_plan；不要把场景拆解工作留给本地规则。
- scene_sequence_plan 里的每一项都必须带 scene_no / scene_name / scene_role / purpose / transition_in / target_result。
- 不要把 scene_sequence_plan 改写成 scenes、scene_plan、scene_steps 或其它字段名。
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
                "tags": ["回场", "关系", "调度"],
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


def chapter_frontload_decision_system_prompt() -> str:
    return """
你是“章节准备阶段选择器”。你的任务是在一次决策里完成筛选阶段，然后才进入后续拼装阶段。
你要同时完成五件事：
1. 复核本章人物/关系推进重心；
2. 从全量轻量卡片索引里挑出本章真正要展开的少量卡片编号；
3. 从爽点候选压缩索引里选出本章要执行的 payoff card；
4. 从 写法卡压缩索引里选出本章真正要强调的写法。

注意：场景不再走功能模板筛选；场景连续性会由独立 AI 评审直接给出续场/切场与场景顺序方案，本地不再提供替代规划。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. schedule_review 要解决“这章该重点写谁、推进哪条关系、哪些人别抢戏”。
3. card_selection 要解决“正文真正需要带哪些卡，不要为了看起来全而乱选”。
4. payoff_selection / prompt_strategy_selection 也必须和人物关系选择一致，不能各唱各的戏。
5. 宁可少而准，也不要把所有候选都选上。
6. 输入里的 card_index / payoff_candidate_index / prompt_strategy_index 都是压缩候选全集；后续本地只做校验和拼装，不再替你做本地排序终选；场景连续性由独立 AI 评审直接给出完整方案，本地不再提供任何替代规划。
""".strip()


def chapter_frontload_decision_user_prompt(
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    *,
    compact_mode: bool = False,
) -> str:
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
    schedule = packet.get("character_relation_schedule") or {}
    priority_snapshot = {
        "due_characters": ((schedule.get("appearance_schedule") or {}).get("due_characters") or []),
        "resting_characters": ((schedule.get("appearance_schedule") or {}).get("resting_characters") or []),
        "priority_characters": ((schedule.get("appearance_schedule") or {}).get("priority_characters") or [])[: (4 if compact_mode else 6)],
        "due_relations": ((schedule.get("relationship_schedule") or {}).get("due_relations") or []),
        "priority_relations": ((schedule.get("relationship_schedule") or {}).get("priority_relations") or [])[: (4 if compact_mode else 6)],
    }
    max_items = 5 if compact_mode else 8
    text_limit = 64 if compact_mode else 80
    plan_text_limit = 84 if compact_mode else 100
    card_index_items = 6 if compact_mode else 8
    sections = [
        {
            "title": "本章信息",
            "body": f"""【本章信息】
{_compact_pretty(compact_plan, max_depth=3, max_items=max_items, text_limit=plan_text_limit)}""",
            "tags": ["计划", "流程", "目标"],
            "stages": ["chapter_frontload_decision"],
            "priority": "must",
        },
        {
            "title": "核心配角分批规则",
            "body": f"""【核心配角分批规则】
{_compact_pretty(packet.get('core_cast_guidance') or {}, max_depth=3, max_items=max_items, text_limit=text_limit)}""",
            "tags": ["核心配角", "阶段", "分批"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "角色回场与关系推进",
            "body": f"""【角色回场与关系推进】
{_compact_pretty(schedule, max_depth=3 if compact_mode else 4, max_items=max_items, text_limit=text_limit)}""",
            "tags": ["回场", "关系", "软调度"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "人物关系调度快照",
            "body": f"""【人物关系调度快照】
{_compact_pretty(priority_snapshot, max_depth=3 if compact_mode else 4, max_items=max_items, text_limit=text_limit)}""",
            "tags": ["调度", "角色", "关系"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "本章人物投放提示",
            "body": f"""【本章人物投放提示】
{_compact_pretty(_chapter_stage_casting_prompt_payload(packet), max_depth=3 if compact_mode else 4, max_items=max_items, text_limit=text_limit)}""",
            "tags": ["投放", "新人", "换功能"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "必须优先考虑",
            "body": f"""【必须优先考虑】
{_compact_pretty(hard_requirements, max_depth=3, max_items=4 if compact_mode else 6, text_limit=text_limit)}""",
            "tags": ["焦点人物", "新引入", "硬要求"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "候选卡片轻量索引",
            "body": f"""【候选卡片轻量索引】
{_compact_pretty(packet.get('card_index') or {}, max_depth=2 if compact_mode else 3, max_items=card_index_items, text_limit=text_limit)}""",
            "tags": ["候选卡", "索引", "全集"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "爽点候选压缩索引",
            "body": f"""【爽点候选压缩索引】
{_compact_pretty((packet.get('payoff_candidate_index') or {}), max_depth=2 if compact_mode else 3, max_items=max_items, text_limit=text_limit)}""",
            "tags": ["爽点", "候选", "全集"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
        {
            "title": "写法卡压缩索引",
            "body": f"""【写法卡压缩索引】
{_compact_pretty((packet.get('prompt_strategy_index') or []), max_depth=2 if compact_mode else 3, max_items=max_items, text_limit=text_limit)}""",
            "tags": ["prompt", "策略", "全集"],
            "stages": ["chapter_frontload_decision"],
            "priority": "high",
        },
    ]
    if not compact_mode and packet.get('selection_runtime'):
        sections.append(
            {
                "title": "准备阶段说明",
                "body": f"""【准备阶段说明】
{_compact_pretty(packet.get('selection_runtime') or {}, max_depth=3, max_items=8, text_limit=80)}""",
                "tags": ["阶段", "筛选", "拼装"],
                "stages": ["chapter_frontload_decision"],
                "priority": "medium",
            }
        )
    sorted_sections = _soft_sorted_section_block(
        "chapter_frontload_decision",
        {"chapter_plan": compact_plan, "hard_requirements": hard_requirements, "compact_mode": compact_mode},
        sections,
    )
    compact_rule = "\n- 当前为紧凑重试模式：优先抓主线人物、主关系和真正会动用的卡，不必展开次要背景。" if compact_mode else ""
    return f"""
请在一次决策里，同时完成“本章人物关系推进复核”和“本章用卡选择”。

{sorted_sections}

输出 JSON schema：
{_pretty(CHAPTER_FRONTLOAD_DECISION_SCHEMA)}

补充规则：
- focus_characters 是本章最该正面写到、推进到的人，不等于所有该回场的人。
- main_relation_ids 只放本章真该正面推进的关系；light_touch_relation_ids 放适合顺手推一格的关系。
- 候选索引展示的是压缩全集，不代表已经通过本地筛选；你需要自己做真正的筛选。
- 若【本章人物投放提示】里的 planned_action 与当前章法不自然，就把 stage_casting_verdict 写成 defer_to_next 或 hold_steady，不要硬执行。
- selected_card_ids 里只放编号，不要放名字。
- 优先少而准，不要把全部候选都选上。
- 若 schedule_review 点名了 focus_characters / main_relation_ids，card_selection 应优先围绕它们选卡；supporting/light_touch 可辅助，defer_* 尽量别抢戏。
- selected_strategy_ids 只保留 2-4 个真正该强调的 写法卡，不要全选。
- selected_card_ids / selected_strategy_ids 都必须来自给定索引。{compact_rule}
""".strip()


def payoff_card_selector_system_prompt() -> str:
    return """
你是“爽点终选仲裁器”。你会看到已经压缩好的爽点候选索引。
你的任务不是重排本地首选，而是直接从压缩候选里选出最适合当前章节的那一张。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. selected_card_id 必须从候选卡里选；backup_card_id 也必须来自候选卡或留空。
3. 优先考虑：本章目标、当前场景公开度、最近几章欠账、重复风险、以及是否需要下一章追账补偿。
4. 不要为了“更炸”而无视本章流程；若本章更适合中强度兑现，就不要硬上过度炫技的卡。
5. execution_hint 要具体到正文怎么落：回报怎么落袋，谁来显影，后患怎么接上。
6. 不要假设存在本地兜底；若候选不合适，也必须在候选内选出当前最优的一张。
""".strip()



def payoff_card_selector_user_prompt(
    *,
    chapter_plan: dict[str, Any],
    payoff_candidate_index: dict[str, Any],
    payoff_compensation: dict[str, Any] | None = None,
) -> str:
    compact_plan = {
        key: chapter_plan.get(key)
        for key in [
            "chapter_no", "title", "goal", "conflict", "main_scene", "event_type",
            "progress_kind", "flow_template_id", "flow_template_name", "supporting_character_focus",
            "payoff_or_pressure", "payoff_level", "payoff_visibility", "reader_payoff", "new_pressure",
        ]
        if chapter_plan.get(key) not in (None, "", [], {})
    }
    diagnostics = (payoff_candidate_index or {}).get("diagnostics") or {}
    candidates = (payoff_candidate_index or {}).get("candidates") or []
    return f"""
请直接从以下“压缩爽点候选索引”里完成一次 AI 终选，并给出正文执行提示。

【本章信息】
{_compact_pretty(compact_plan, max_depth=3, max_items=8, text_limit=100)}

【爽点候选诊断】
{_compact_pretty(diagnostics, max_depth=3, max_items=8, text_limit=90)}

【待补偿的爽点欠账】
{_compact_pretty(payoff_compensation or {}, max_depth=3, max_items=8, text_limit=90)}

【压缩爽点候选索引】
{_compact_pretty({
    "candidate_count": len(candidates),
    "compression_mode": (payoff_candidate_index or {}).get("compression_mode") or "compact_payoff_index",
    "candidates": candidates,
}, max_depth=3, max_items=10, text_limit=90)}

输出 JSON schema：
{_pretty(PAYOFF_CARD_SELECTOR_SCHEMA)}

补充规则：
- 只能从候选卡里挑，不能自造 card_id。
- 若上一章兑现偏虚且本章需要追账，就更偏向“明确回报可感、外部显影更清楚”的卡。
- 若候选里重复风险高，就优先换 family / payoff_mode / visibility 的组合，不要再写成同一套围观反应。
- reason 解释为什么这张最适合当前章，不要引用任何“本地首选”概念。
- execution_hint 要直接告诉正文：先让主角拿到什么，再让谁看见，最后留下什么新压力。
""".strip()



def payoff_delivery_review_system_prompt() -> str:
    return """
你是“爽点兑现复核器”。你会看到本地对正文的爽点兑现软评分。
你的任务不是改写正文，而是判断这章到底有没有把计划里的爽点真正写出来，并决定下一章是否需要追账补偿。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. delivery_level 只能是 low / medium / high。
3. 若这章已经兑现扎实，不要为了显得严厉而硬判低分。
4. 若这章只有主角心里爽、没有落袋结果、没有外部显影或没有后患，就应明确指出。
5. should_compensate_next_chapter 只在本章兑现确实偏弱，或本章承诺强兑现却没有落到位时再置 true。
""".strip()



def payoff_delivery_review_user_prompt(
    *,
    title: str,
    content: str,
    chapter_plan: dict[str, Any],
    local_review: dict[str, Any],
) -> str:
    compact_plan = {
        key: chapter_plan.get(key)
        for key in [
            "chapter_no", "title", "goal", "event_type", "progress_kind", "flow_template_id",
            "payoff_or_pressure", "payoff_level", "payoff_visibility", "reader_payoff", "new_pressure",
        ]
        if chapter_plan.get(key) not in (None, "", [], {})
    }
    excerpt = _text(content)[:2200]
    return f"""
请复核这章正文的爽点兑现情况。

【章节标题】
{title}

【本章计划】
{_compact_pretty(compact_plan, max_depth=3, max_items=8, text_limit=100)}

【本地软评分】
{_compact_pretty(local_review, max_depth=3, max_items=8, text_limit=90)}

【正文节选】
{excerpt}

输出 JSON schema：
{_pretty(PAYOFF_DELIVERY_REVIEW_SCHEMA)}

补充规则：
- 回报落袋要看主角到底拿到了什么、坐实了什么、压回了什么，不要只看情绪。
- public / semi_public 的爽点，要看外部反应是不是写出来了；private 爽点，也要看主角的路线、计划或判断有没有立刻变化。
- 若这章主要问题是“有回报但显影太弱”或“有显影但没落袋”，missed_targets 要说清楚。
- compensation_note 要具体说明下一章该如何补，不要只说“加强爽点”。
""".strip()





__all__ = [name for name in globals() if not name.startswith("__")]
