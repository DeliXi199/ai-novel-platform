from __future__ import annotations

from typing import Any

from app.services import openai_story_engine_selection as selection_engine


def chapter_preparation_shortlist_schema() -> dict[str, Any]:
    return selection_engine.ChapterPreparationShortlistPayload.model_json_schema()


def chapter_preparation_plan_snapshot(chapter_plan: dict[str, Any], planning_packet: dict[str, Any], *, compact_mode: bool) -> dict[str, Any]:
    packet = planning_packet or {}
    plan = chapter_plan or {}
    max_items = 4 if compact_mode else 7
    return {
        'chapter_info': selection_engine._compact_for_prompt({
            key: plan.get(key)
            for key in [
                'chapter_no', 'title', 'goal', 'conflict', 'main_scene', 'event_type',
                'progress_kind', 'flow_template_name', 'flow_template_tag', 'ending_hook',
                'supporting_character_focus', 'supporting_character_note',
            ]
            if plan.get(key) not in (None, '', [], {})
        }, max_depth=3, max_items=max_items, text_limit=96 if not compact_mode else 72),
        'hard_requirements': selection_engine._compact_for_prompt({
            'focus_character': ((packet.get('selected_elements') or {}).get('focus_character')),
            'new_resources': plan.get('new_resources') or [],
            'new_factions': plan.get('new_factions') or [],
            'new_relations': plan.get('new_relations') or [],
        }, max_depth=3, max_items=max_items, text_limit=72),
        'selected_elements': selection_engine._compact_for_prompt(packet.get('selected_elements') or {}, max_depth=3, max_items=max_items, text_limit=72),
        'book_execution_profile': selection_engine._compact_for_prompt(selection_engine._book_bias_brief(packet), max_depth=3, max_items=max_items, text_limit=72),
        'schedule_candidate_index': selection_engine._compact_for_prompt(packet.get('schedule_candidate_index') or {}, max_depth=4 if not compact_mode else 3, max_items=max_items, text_limit=72),
        'selection_runtime': selection_engine._compact_for_prompt(packet.get('selection_runtime') or {}, max_depth=3, max_items=max_items, text_limit=72),
    }


def chapter_preparation_selector_input(
    selector_name: str,
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    compact_mode: bool,
    shortlist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = planning_packet or {}
    base = chapter_preparation_plan_snapshot(chapter_plan, packet, compact_mode=compact_mode)
    if shortlist:
        base['preselection_shortlist'] = selection_engine._compact_for_prompt(shortlist, max_depth=3, max_items=6, text_limit=64)
    if selector_name == 'schedule':
        base['task_focus'] = '只根据角色/关系调度压缩索引，复核本章该重点写谁、推进哪条关系、哪些人别抢戏。'
        base['focused_schedule_candidate_index'] = selection_engine._compact_for_prompt(selection_engine._focused_schedule_candidate_index(packet, shortlist), max_depth=4 if not compact_mode else 3, max_items=8 if not compact_mode else 6, text_limit=72)
        return base
    if selector_name == 'cards':
        base['task_focus'] = '从全量压缩卡片索引里选出正文真正会动用的卡。'
        base['focused_card_index'] = selection_engine._compact_for_prompt(selection_engine._focused_card_index(packet, shortlist), max_depth=3 if not compact_mode else 2, max_items=8 if not compact_mode else 6, text_limit=72)
        return base
    if selector_name == 'payoff':
        base['task_focus'] = '从爽点候选压缩索引里选出本章真正执行的一张 payoff card，并参考本书长期爽点偏置。'
        base['focused_payoff_candidate_index'] = selection_engine._compact_for_prompt(selection_engine._focused_payoff_candidate_index(packet, shortlist), max_depth=3 if not compact_mode else 2, max_items=7 if not compact_mode else 5, text_limit=72)
        return base
    if selector_name == 'foreshadowing':
        base['task_focus'] = '从伏笔母卡/子卡与章节级候选压缩索引里决定本章埋哪条、碰哪条、回哪条，并服从本书长期伏笔偏置。'
        base['focused_foreshadowing_candidate_index'] = selection_engine._compact_for_prompt(selection_engine._focused_foreshadowing_candidate_index(packet, shortlist), max_depth=3 if not compact_mode else 2, max_items=7 if not compact_mode else 5, text_limit=72)
        return base
    if selector_name == 'prompt':
        base['task_focus'] = '从流程母卡/子卡与写法母卡/子卡压缩索引里选出本章真正要强调的写法结构，并参考本书运行画像。'
        base['focused_prompt_bundle_index'] = selection_engine._compact_for_prompt(selection_engine._focused_prompt_bundle_index(packet, shortlist), max_depth=3 if not compact_mode else 2, max_items=8 if not compact_mode else 5, text_limit=72)
        return base
    return base


def selector_output_schema(selector_name: str) -> dict[str, Any]:
    if selector_name == 'schedule':
        return selection_engine.CharacterRelationScheduleReviewPayload.model_json_schema()
    if selector_name == 'cards':
        return selection_engine.ChapterCardSelectionPayload.model_json_schema()
    if selector_name == 'payoff':
        return selection_engine.PayoffSelectionPayload.model_json_schema()
    if selector_name == 'foreshadowing':
        return selection_engine.ForeshadowingSelectionPayload.model_json_schema()
    if selector_name == 'prompt':
        return selection_engine.PromptStrategySelectionPayload.model_json_schema()
    return selection_engine.ChapterFrontloadDecisionPayload.model_json_schema()


def selector_system_prompt(selector_name: str) -> str:
    prompts = {
        'schedule': '你是“章节准备阶段·角色关系选择器”。只负责判断本章该重点写谁、推进哪些关系、谁应轻触、谁应暂缓。输出必须是 JSON。',
        'cards': '你是“章节准备阶段·卡片选择器”。只负责从全量压缩卡片索引里挑出正文真正要动用的少量卡片编号。不要为了看起来全而乱选。输出必须是 JSON。',
        'payoff': '你是“章节准备阶段·爽点选择器”。只负责从爽点候选压缩索引里选出本章真正执行的一张 payoff card。要优先尊重本书 book_execution_profile 的长期偏置，但不能违背本章实际计划。输出必须是 JSON。',
        'foreshadowing': '你是“章节准备阶段·伏笔选择器”。只负责从伏笔母卡/子卡与章节级候选压缩索引里决定本章埋哪条、碰哪条、回哪条。要参考本书的伏笔主次偏置和 hold_back 规则。输出必须是 JSON。',
        'prompt': '你是“章节准备阶段·写法卡选择器”。只负责从流程母卡/子卡与写法母卡/子卡压缩索引里选出本章真正该强调的写法结构。要把本书 book_execution_profile 的长期运行画像当成稳定偏置，而不是每章从零开始。输出必须是 JSON。',
    }
    return prompts.get(selector_name, '你是章节准备阶段选择器，只输出 JSON。')


def selector_user_prompt(
    selector_name: str,
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    compact_mode: bool,
    shortlist: dict[str, Any] | None = None,
) -> str:
    selector_input = chapter_preparation_selector_input(
        selector_name,
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        compact_mode=compact_mode,
        shortlist=shortlist,
    )
    extra_rules = {
        'schedule': [
            'focus_characters 只放本章最该正面推进的人。',
            'main_relation_ids 只放本章真该正面推进的关系。',
            '若人物投放提示和本章章法冲突，可以 defer_to_next 或 hold_steady，不要硬塞。',
        ],
        'cards': [
            'selected_card_ids 里只放编号，不放名字。',
            '优先少而准，不要把全部候选都选上。',
            '若 book_execution_profile 对某些流程/爽点/伏笔有长期偏置，可在不违背本章目标的前提下顺着偏置选。',
            '若某张卡只是背景板、本章不会真正动它，就不要选。',
        ],
        'payoff': [
            'selected_card_id 只放一个编号，优先直接填写候选里的真实 card_id。',
            '不要自造 payoff_001 / payoff_023 这类序号占位符；若你参考候选里的 selector_key，也必须映射回真实 card_id 后再输出。',
            '要和本章人物关系推进方向一致，不要单独唱戏。',
            '同等合理时，优先贴近本书 payoff_priority 的高优先项，回避 demotion_rules。',
        ],
        'foreshadowing': [
            'selected_primary_candidate_id 必须填写聚焦伏笔压缩索引里已出现的稳定 candidate_id（如 fcand_001）或 selector_key（如 foreshadow_001），不能为空。',
            '如果聚焦伏笔候选只有 1 条，直接填写那 1 条的 candidate_id，不要留空，不要改写，不要概括。',
            '同等合理时，优先遵循本书 foreshadowing_priority 的主次顺序。',
            'selected_supporting_candidate_ids 最多放 2 个，而且必须来自同一份聚焦伏笔压缩索引。',
            '不要把 source_hook、display_label、selector_label、fit_reason、child_card_name 当成 candidate_id 填写。',
            '优先明确本章主动作是新埋、轻碰、加深、验证还是部分/完整回收，不要什么都想做。',
        ],
        'prompt': [
            'selected_flow_template_id 只放一个流程母卡编号。',
            '同等合理时，优先遵循本书 flow_family_priority 与 writing_strategy_priority。',
            'selected_flow_child_card_id 只放一个流程子卡编号，而且必须属于所选流程母卡。',
            'selected_strategy_ids 选 2-4 个最重要的写法母卡，不要铺满。',
            'selected_writing_child_card_ids 选 1-4 个写法子卡，优先让每张母卡至少有一个真正会改变正文写法的子卡。',
        ],
    }
    compact_rule = '当前为紧凑重试模式：只抓主冲突、主关系和真正会动用的候选。\n' if compact_mode else ''
    rules = '\n'.join(f'- {item}' for item in extra_rules.get(selector_name, []))
    return f"""
请完成当前子选择任务。
{compact_rule}
上下文：
{selection_engine._pretty_json(selector_input)}

输出 JSON schema：
{selection_engine._pretty_json(selector_output_schema(selector_name))}

补充规则：
{rules}
""".strip()


def merge_selection_system_prompt() -> str:
    return '你是“章节准备阶段·全局仲裁器”。你的任务是整合多个并行 AI 选择结果，统一成人物/关系、卡片、爽点、伏笔动作、流程母卡/子卡、写法母卡/子卡一致的一套最终选择。场景连续性不由你决定，后续会由独立 AI 评审直接给出完整续场/切场与场景顺序方案，本地不再提供替代规划。只输出 JSON。'


def merge_selection_user_prompt(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    selector_outputs: dict[str, Any],
    compact_mode: bool,
    shortlist: dict[str, Any] | None = None,
) -> str:
    payload = {
        'chapter_context': chapter_preparation_plan_snapshot(chapter_plan, planning_packet, compact_mode=compact_mode),
        'parallel_selector_outputs': selection_engine._compact_for_prompt(selector_outputs, max_depth=4 if not compact_mode else 3, max_items=7 if not compact_mode else 5, text_limit=88 if not compact_mode else 72),
        'preselection_shortlist': selection_engine._compact_for_prompt(shortlist or {}, max_depth=3, max_items=6, text_limit=64),
        'focused_indexes': selection_engine._compact_for_prompt({
            'schedule_candidate_index': selection_engine._focused_schedule_candidate_index(planning_packet or {}, shortlist),
            'card_index': selection_engine._focused_card_index(planning_packet or {}, shortlist),
            'payoff_candidate_index': selection_engine._focused_payoff_candidate_index(planning_packet or {}, shortlist),
            'foreshadowing_candidate_index': selection_engine._focused_foreshadowing_candidate_index(planning_packet or {}, shortlist),
            'prompt_bundle_index': selection_engine._focused_prompt_bundle_index(planning_packet or {}, shortlist),
        }, max_depth=3 if not compact_mode else 2, max_items=7 if not compact_mode else 5, text_limit=72),
    }
    compact_rule = '当前为紧凑重试模式：优先保证主线一致和选择可执行，不必展开次要解释。\n' if compact_mode else ''
    return f"""
请把并行筛选结果整合成一套最终可执行的章节准备选择。
{compact_rule}
上下文：
{selection_engine._pretty_json(payload)}

输出 JSON schema：
{selection_engine._pretty_json(selection_engine.ChapterFrontloadDecisionPayload.model_json_schema())}

补充规则：
- 所有编号必须来自已给候选索引或并行结果；流程子卡必须属于所选流程母卡，写法子卡必须属于所选写法母卡。
- 最终结果优先保证人物/关系、用卡、爽点、伏笔动作、流程母卡/子卡、写法母卡/子卡彼此一致，并尽量贴合 book_execution_profile 的长期偏置。
- 每章伏笔动作以 1 条主动作 + 0-2 条辅助动作为宜，不要同时新埋、轻碰、回收太多条。
- 不要为了全面而增加正文不会真正执行的选择。
""".strip()


def preselection_system_prompt() -> str:
    return '你是“章节准备阶段·压缩索引预筛器”。你只能阅读压缩索引，先做粗粒度 shortlist，给后续并行选择器缩小注意力，但不能替代最终选择。只输出 JSON。'


def preselection_user_prompt(*, chapter_plan: dict[str, Any], planning_packet: dict[str, Any], compact_mode: bool) -> str:
    payload = {
        'chapter_context': chapter_preparation_plan_snapshot(chapter_plan, planning_packet, compact_mode=compact_mode),
        'schedule_candidate_index': selection_engine._compact_for_prompt((planning_packet or {}).get('schedule_candidate_index') or {}, max_depth=4 if not compact_mode else 3, max_items=8 if not compact_mode else 6, text_limit=72),
        'card_index': selection_engine._compact_for_prompt((planning_packet or {}).get('card_index') or {}, max_depth=3 if not compact_mode else 2, max_items=8 if not compact_mode else 6, text_limit=72),
        'payoff_candidate_index': selection_engine._compact_for_prompt((planning_packet or {}).get('payoff_candidate_index') or {}, max_depth=3 if not compact_mode else 2, max_items=7 if not compact_mode else 5, text_limit=72),
        'foreshadowing_candidate_index': selection_engine._compact_for_prompt((planning_packet or {}).get('foreshadowing_candidate_index') or {}, max_depth=3 if not compact_mode else 2, max_items=7 if not compact_mode else 5, text_limit=72),
        'scene_continuity_index': selection_engine._compact_for_prompt((planning_packet or {}).get('scene_continuity_index') or {}, max_depth=3 if not compact_mode else 2, max_items=7 if not compact_mode else 5, text_limit=72),
        'prompt_bundle_index': selection_engine._compact_for_prompt((planning_packet or {}).get('prompt_bundle_index') or {}, max_depth=3 if not compact_mode else 2, max_items=8 if not compact_mode else 5, text_limit=72),
    }
    compact_rule = '当前为紧凑重试模式：shortlist 只抓主冲突、主关系和真正会动用的候选。\n' if compact_mode else ''
    return f"""
请先对章节准备阶段做粗粒度预筛。
{compact_rule}
上下文：
{selection_engine._pretty_json(payload)}

输出 JSON schema：
{selection_engine._pretty_json(chapter_preparation_shortlist_schema())}

补充规则：
- 这一步只产出 shortlist，不做最终拍板。
- 可参考 book_execution_profile 作为长期偏置，但不能把它当硬性名单。
- 所有编号都必须来自给定压缩索引。
- 宁可少而准，也不要为了看起来全而乱塞。
""".strip()


__all__ = [
    'chapter_preparation_shortlist_schema',
    'chapter_preparation_plan_snapshot',
    'chapter_preparation_selector_input',
    'selector_output_schema',
    'selector_system_prompt',
    'selector_user_prompt',
    'merge_selection_system_prompt',
    'merge_selection_user_prompt',
    'preselection_system_prompt',
    'preselection_user_prompt',
]
