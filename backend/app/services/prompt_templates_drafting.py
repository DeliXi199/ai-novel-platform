from __future__ import annotations

from app.services.prompt_templates_shared import *

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
    for key in ["project_card", "current_volume_card", "protagonist_profile", "execution_brief", "hard_fact_guard"]:
        value = story_memory.get(key) or (novel_context or {}).get(key)
        if value:
            payload[key] = value
    recent_retrospectives = story_memory.get("recent_retrospectives") or []
    if recent_retrospectives:
        payload["recent_retrospectives"] = recent_retrospectives[:2]
    if not payload and novel_context:
        for key in ["project_card", "current_volume_card", "protagonist_profile", "execution_brief", "hard_fact_guard"]:
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
    if packet.get("payoff_runtime"):
        summary["payoff_runtime"] = packet.get("payoff_runtime")
    if packet.get("selected_payoff_card"):
        summary["selected_payoff_card"] = packet.get("selected_payoff_card")
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
            for key in ["opening_anchor", "last_two_paragraphs", "last_chapter_tail_excerpt", "unresolved_action_chain", "onstage_characters", "scene_handoff_card"]
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




def _selected_prompt_strategies_block(planning_packet: dict[str, Any] | None) -> str:
    packet = planning_packet or {}
    strategies = packet.get("selected_prompt_strategies") or []
    selection = packet.get("prompt_selection") or {}
    if not strategies and not selection:
        return ""
    payload = {
        "selection_note": selection.get("selection_note"),
        "selected_strategy_ids": selection.get("selected_strategy_ids") or [],
        "selected_prompt_strategies": [
            {
                "strategy_id": item.get("strategy_id"),
                "name": item.get("name"),
                "summary": item.get("summary"),
                "writing_directive": item.get("writing_directive"),
            }
            for item in strategies[:4] if isinstance(item, dict)
        ],
    }
    return _section_block("本章选中的 prompt 策略", _compact_pretty(payload, max_depth=3, max_items=8, text_limit=90))


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
            {"title": "本章选中的 prompt 策略", "body": _selected_prompt_strategies_block(chapter_plan.get("planning_packet") or {}), "tags": ["prompt", "策略", "写法"], "stages": ["chapter_body_draft"], "priority": "high"},
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
    selected_payoff_card = (planning_packet.get("selected_payoff_card") or {}) if isinstance(planning_packet, dict) else {}
    payoff_block = f"\n【本章爽点执行卡】\n{_compact_pretty(selected_payoff_card, max_depth=3, max_items=8, text_limit=90)}\n" if selected_payoff_card else ""
    payoff_compensation = chapter_plan.get("payoff_compensation") or {}
    payoff_compensation_block = f"\n【爽点追账补偿】\n{_compact_pretty(payoff_compensation, max_depth=3, max_items=8, text_limit=90)}\n" if payoff_compensation else ""
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
                {"title": "本章选中的 prompt 策略", "body": _selected_prompt_strategies_block(chapter_plan.get("planning_packet") or {}), "tags": ["prompt", "策略", "写法"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "本章主动方式", "body": agency_mode_block, "tags": ["主动性", "模式"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "本章推进结果", "body": progress_result_block, "tags": ["推进", "结果"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "本章爽点执行卡", "body": payoff_block.strip(), "tags": ["爽点", "兑现", "回报"], "stages": ["chapter_draft_retry"], "priority": "high"},
                {"title": "爽点追账补偿", "body": payoff_compensation_block.strip(), "tags": ["追账", "补偿", "爽点"], "stages": ["chapter_draft_retry"], "priority": "high"},
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
8. 若提供了【本章规划包】，正文只围绕其中 recent_continuity_plan / selected_elements / card_index / card_selection / relevant_cards / selected_payoff_card / resource_plan / resource_capability_plan / continuity_window / opening_reveal_guidance / character_template_guidance 写，不要回看全书或擅自扩成全量卡池。
8.0 若提供了【本章爽点执行卡】，至少兑现一次“reader_payoff -> external_reaction -> new_pressure/aftershock”的完整链条；public/semi_public 爽点必须让旁人看见，private 爽点也要让主角的下一步动作立刻改变。
8.0.1 若同时提供了【爽点追账补偿】，优先把这一章写成“追回一次明确回报”的章，不要继续只蓄压、只埋钩、只让主角心里有数。
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
            {"title": "本章选中的 prompt 策略", "body": _selected_prompt_strategies_block(chapter_plan.get("planning_packet") or {}), "tags": ["prompt", "策略", "写法"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "上一章信息", "body": _section_block("上一章信息", compact_last_view) + "\n\n若【上一章信息】里包含 continuity_bridge / scene_handoff_card / last_two_paragraphs / last_scene_card / unresolved_action_chain / onstage_characters，必须把它们视为开章硬承接依据。", "tags": ["上一章", "承接", "连续性"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "轻量小说记忆", "body": _section_block("轻量小说记忆", full_memory_view), "tags": ["记忆", "硬事实", "项目卡"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "最近章节摘要", "body": _section_block("最近章节摘要", recent_view), "tags": ["最近摘要", "连续性"], "stages": ["chapter_draft_full"], "priority": "medium"},
            {"title": "当前生效的读者干预", "body": _section_block("当前生效的读者干预", interventions_view), "tags": ["干预", "偏好"], "stages": ["chapter_draft_full"], "priority": "medium"},
            {"title": "本章主动方式", "body": agency_mode_block, "tags": ["主动性", "模式"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "本章推进结果", "body": progress_result_block, "tags": ["推进", "结果"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "本章爽点执行卡", "body": payoff_block.strip(), "tags": ["爽点", "兑现", "回报"], "stages": ["chapter_draft_full"], "priority": "high"},
            {"title": "爽点追账补偿", "body": payoff_compensation_block.strip(), "tags": ["追账", "补偿", "爽点"], "stages": ["chapter_draft_full"], "priority": "high"},
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
2. 把【轻量小说记忆】中的 project_card / current_volume_card / protagonist_profile / near_7_chapter_outline / foreshadowing / daily_workbench / execution_brief / recent_retrospectives / character_roster / hard_fact_guard 当成硬约束，严格按“项目卡 -> 当前卷卡 -> 近7章近纲 -> 本章执行卡 -> 复盘纠偏 -> 正文”的顺序落实，不得跳步。
3. 本章默认围绕 1 个主场景推进；若 execution_brief.scene_outline / scene_execution_card 明确给了场景链，允许自然切到 1~2 个副场景，但每次切场都必须先给出阶段结果或明确的时间/地点/动作过渡。
4. 本章必须依次落到拍点链：开场承接 -> 中段受阻或转折 -> 至少一次具体发现或兑现 -> 结尾结果/钩子；若提供了 scene_outline，就按它的场景顺序推进，不要乱跳。
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
7.7 若本章规划包里提供了 selected_payoff_card，就把它视为本章爽点执行卡：至少兑现一次“reader_payoff -> external_reaction -> new_pressure/aftershock”的完整链条。reader_payoff 是本章读者要拿到的实在回报，external_reaction 决定这次爽点如何显影，new_pressure / aftershock 负责把爽完后的后患接上。public/semi_public 爽点必须让旁人看见，private 爽点也要让主角的路线、计划或判断立刻发生变化。
7.7.1 若 chapter_plan 或 execution_brief 里提供了 payoff_compensation / payoff_compensation_note，就把它视为“追账补偿指令”：这一章必须优先补一次明确兑现，降低继续只蓄压不回收的比例。
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
20. 若提供了上一章 continuity_bridge，开头两段必须优先承接它的 opening_anchor / last_two_paragraphs / unresolved_action_chain；其中 continuity_bridge / last_two_paragraphs / last_scene_card 是开章承接的最高优先级输入。若 continuity_bridge.scene_handoff_card 明示 scene_status_at_end=open/interrupted 或 must_continue_same_scene=true，则第一场必须先续接旧场景，再决定是否切场；若 allowed_transition=time_skip，前两段必须写明时间锚点。
21. 若提供了上一章 last_scene_card / scene_handoff_card 或本章 scene_outline，本章第一场必须与上一场景局势保持连续；若中途切场，也要把切场写成可见过渡，不能像被传送。
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




__all__ = [name for name in globals() if not name.startswith("__")]
