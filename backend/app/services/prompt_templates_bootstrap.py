from __future__ import annotations

from app.services.prompt_templates_shared import *

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



def _planning_payoff_compensation_prompt_payload(story_bible: dict[str, Any], *, start_chapter: int, end_chapter: int) -> dict[str, Any]:
    retrospective_state = (story_bible or {}).get("retrospective_state") or {}
    payload = retrospective_state.get("pending_payoff_compensation") or {}
    if not isinstance(payload, dict) or not payload or not bool(payload.get("enabled", True)):
        return {}
    chapter_biases = payload.get("chapter_biases") or []
    overlaps: list[dict[str, Any]] = []
    for item in chapter_biases:
        if not isinstance(item, dict):
            continue
        chapter_no = int(item.get("chapter_no", 0) or 0)
        if start_chapter <= chapter_no <= end_chapter:
            role = _text(item.get("bias") or item.get("window_role"))
            priority = _text(item.get("priority") or payload.get("priority"), "medium")
            bias_payload = payoff_window_event_bias(role, priority=priority)
            overlaps.append({
                "chapter_no": chapter_no,
                "bias": role,
                "priority": priority,
                "note": _text(item.get("note") or payload.get("note") or payload.get("reason")),
                "preferred_event_types": list(bias_payload.get("preferred_event_types") or []),
                "limited_event_types": list(bias_payload.get("limited_event_types") or []),
                "preferred_progress_kinds": list(bias_payload.get("preferred_progress_kinds") or []),
                "event_bias_note": _text(bias_payload.get("event_bias_note")),
            })
    if not overlaps:
        return {}
    base_note = _text(payload.get("note") or payload.get("reason"), "上一章兑现偏虚，接下来 1-2 章要追回一次明确回报。")
    source_chapter_no = int(payload.get("source_chapter_no", 0) or 0)
    priority = _text(payload.get("priority"), "medium")
    hint_lines = [
        f"这次追账来自第{source_chapter_no}章，当前窗口里至少有一章要把回报写实。" if source_chapter_no else "当前窗口里至少有一章要把回报写实。",
        "覆盖到的章节里，第一顺位优先补明确落袋，别继续两章都只抬压力。",
    ]
    if len(overlaps) >= 2:
        hint_lines.append("若窗口里有两章都受影响，前一章负责追回，后一章负责稳住兑现余波，别写成同款围观反应。")
    if bool(payload.get("should_reduce_pressure", True)):
        hint_lines.append("在补偿窗口里适度降低继续纯蓄压的比例，让资源、关系或信息至少回收一次。")
    event_guidance = []
    for item in overlaps[:2]:
        preferred = " / ".join([_text(name) for name in (item.get("preferred_event_types") or [])[:3] if _text(name)])
        limited = " / ".join([_text(name) for name in (item.get("limited_event_types") or [])[:2] if _text(name)])
        label = f"第{int(item.get('chapter_no', 0) or 0)}章"
        if preferred:
            line = f"{label}优先安排{preferred}"
            if limited:
                line += f"，少用{limited}"
            event_guidance.append(line)
    return {
        "source_chapter_no": source_chapter_no,
        "priority": priority,
        "note": base_note,
        "target_chapter_no": int(payload.get("target_chapter_no", 0) or 0),
        "window_end_chapter_no": int(payload.get("window_end_chapter_no", 0) or 0),
        "overlapping_chapters": overlaps,
        "hint_lines": hint_lines[:4],
        "event_guidance": event_guidance[:2],
    }


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

【待处理爽点追账（若有）】
{_compact_pretty(_planning_payoff_compensation_prompt_payload(story_bible, start_chapter=start_chapter, end_chapter=end_chapter), max_depth=3, max_items=8, text_limit=90)}

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
19. 如果【待处理爽点追账】覆盖当前窗口，就把它视为短周期节奏纠偏：优先让重叠到的前 1-2 章里至少一章给出明确落袋回报，降低连续两章都只蓄压的概率；若两章都受影响，前一章负责追回，后一章负责稳住兑现余波并换一种显影方式。对【待处理爽点追账】里给出的 preferred_event_types / limited_event_types / preferred_progress_kinds 要尽量落到对应章节，不要嘴上说追回，章法还在继续纯试探或纯发现。
20. 如果 story_bible 里有 story_strategy_card，且当前章节落在 1-30 章内，要优先贴合对应阶段（1-10 / 11-20 / 21-30）的 stage_mission、reader_hook、relationship_tasks 与 anti_homogenization_rules。
21. {_variety_guidance(payload)}
22. title 不要与最近十几章常见标题重复，避免再次出现“夜半微光/旧纸页/坊市试探”这类高相似标题。
23. 除非开书信息明确要求，否则不要把场景反复锁在药铺、后院、坊市、夜半试探这种固定组合。
24. 不要大场面堆砌，不要一口气揭露终极秘密。
25. 配角不是功能按钮；若某章有关键配角，supporting_character_note 要写出他的说话方式、私心、顾虑、受压反应或做事风格。
26. 不要输出任何解释、前缀、后缀、代码块或注释，只输出 JSON。
27. 对象 schema 如下：
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




__all__ = [name for name in globals() if not name.startswith("__")]
