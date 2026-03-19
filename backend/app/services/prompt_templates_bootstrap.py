from __future__ import annotations

from app.services.prompt_templates_shared import *

def bootstrap_intent_parse_system_prompt() -> str:
    return (
        "你是一名中文网文立项编辑。"
        "你的任务是先把用户输入还原成可执行的创作意图。"
        "你不写正文，不做散文分析，只输出紧凑立项卡。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_intent_parse_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请先把这本小说的创建输入，整理成后续所有初始化步骤都能共用的“立项意图卡”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这一步只做意图拆解，不写剧情正文。
2. 重点回答：这本书持续追更的承诺是什么、主角最硬的驱动力是什么、前10章必须建立什么、最容易写崩的点是什么。
3. expected_payoffs / first_ten_chapter_tasks / major_risks 都尽量控制在 2 到 4 项。
4. 所有字段要短、狠、可执行。
5. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_INTENT_PACKET_SCHEMA)}
""".strip()

def bootstrap_intent_strategy_bundle_system_prompt() -> str:
    return (
        "你是一名擅长中文网文立项与开局规划的总编。"
        "你的任务是一次性完成立项意图拆解、题材拆解、书级长期方向和首个五章开局策略。"
        "输出要像编辑部的紧凑指挥卡，不要写正文，不要散文分析。"
        "为了提速和稳定，请优先使用短字段、短句子、短列表。"
        "你只能输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_intent_strategy_bundle_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请一次性生成这本小说的“立项意图卡 + 题材画像 + 书级长期方向 + 首个五章开局策略”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这是初始化快照，不写正文，不写散文式分析，只给后续规划可直接使用的结构卡。
2. 输出必须只包含三个顶层键：bootstrap_intent_packet、story_engine_diagnosis、story_strategy_card。
3. bootstrap_intent_packet 负责回答：这本书持续追更的承诺是什么、主角最硬的驱动力是什么、前10章必须建立什么、最容易写崩的点是什么。
4. story_engine_diagnosis 负责回答：这本书属于什么更细子类型、前期真正该靠什么推进、最该避开什么老套路。
5. story_strategy_card 负责回答：整本书长期怎么跑、开局五章先怎么抓人、滚动五章规划时哪些元素常用、哪些必须少用。
6. 所有字段尽量短，单条列表尽量控制在 2 到 4 项，避免长篇解释。
7. 除非开书信息明确要求，否则不要默认写成“药铺 / 坊市 / 残页 / 掌柜起疑 / 夜探试探”这一类固定开局组合。
8. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_INTENT_STRATEGY_BUNDLE_SCHEMA)}
""".strip()


def bootstrap_strategy_candidates_system_prompt() -> str:
    return (
        "你是一名中文网文立项总编。"
        "你的任务是围绕同一个立项意图，给出多套真正有差异的书级方向与开局五章策略方案。"
        "不是同义改写，而是推进重心、抓人方式、节奏结构都要有差别。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_strategy_candidates_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any], intent_packet: dict[str, Any], candidate_count: int = 3) -> str:
    return f"""
请基于下面的立项信息，为这本小说并行设计 {candidate_count} 套不同的“题材画像 + 书级方向 + 开局五章策略”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

【立项意图卡】
{_compact_pretty(intent_packet, max_depth=3, max_items=8, text_limit=100)}

要求：
1. 一共输出 {candidate_count} 个 candidate，candidate_id 用 A/B/C 这种短标识。
2. 每个 candidate 都必须包含 design_focus、story_engine_diagnosis、story_strategy_card。
3. 候选方案之间必须真有差别，例如：更偏求生压迫、更偏资源升级、更偏关系入局、更偏异常暗线。
4. 候选方案都必须遵守同一立项意图卡，但抓人方式不能只是换词。
5. 不要默认落回固定套路组合。
6. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_STRATEGY_CANDIDATES_SCHEMA)}
""".strip()


def bootstrap_strategy_arbitration_system_prompt() -> str:
    return (
        "你是一名负责最终拍板的中文网文总编。"
        "你的任务不是重复候选方案，而是选出最适合长篇连载的版本，并吸收其它候选的优点。"
        "这一步只负责拍板题材画像、书级方向与开局五章策略，不要再发明平行模板系统。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_strategy_arbitration_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any], intent_packet: dict[str, Any], candidates: dict[str, Any]) -> str:
    return f"""
请在下面这些初始化候选方案中，选出最适合这本小说长期连载的一套，并做必要融合。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

【立项意图卡】
{_compact_pretty(intent_packet, max_depth=3, max_items=8, text_limit=100)}

【候选方案】
{_compact_pretty(candidates, max_depth=4, max_items=10, text_limit=100)}

要求：
1. 先选出 selected_candidate_id，再写 selection_reason 和 merge_notes。
2. 最终输出的 story_engine_diagnosis / story_strategy_card 必须是可直接落库的正式版，可以吸收多个候选的优点，但不能含糊。
3. 这里只负责拍板故事引擎、书级方向与开局五章策略，不要输出额外母卡系统；后续会基于整套修仙模板池单独生成书级运行画像。
4. 所有字段保持短句和短列表，方便后续压缩与筛选。
5. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_STRATEGY_ARBITRATION_SCHEMA)}
""".strip()


def bootstrap_execution_profile_system_prompt() -> str:
    return (
        "你是一名中文网文项目总编。"
        "你的任务是在不筛掉修仙模板池的前提下，为这本书定义长期稳定的模板使用画像。"
        "所有模板都保留，后续每章都会重筛；你现在只负责给整本书定长期偏置与降权规则。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_execution_profile_user_prompt(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    intent_packet: dict[str, Any],
    template_pool_profile: dict[str, Any],
    story_engine_diagnosis: dict[str, Any],
    story_strategy_card: dict[str, Any],
) -> str:
    return f"""
请基于下面信息，为这本小说生成“书级运行画像”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

【立项意图卡】
{_compact_pretty(intent_packet, max_depth=3, max_items=8, text_limit=100)}

【拍板后的题材画像】
{_compact_pretty(story_engine_diagnosis, max_depth=3, max_items=8, text_limit=100)}

【拍板后的长期方向与开局五章策略】
{_compact_pretty(story_strategy_card, max_depth=3, max_items=8, text_limit=100)}

【基础模板池画像】
{_compact_pretty(template_pool_profile, max_depth=3, max_items=8, text_limit=100)}

要求：
1. 所有修仙模板都默认保留在候选池里，不要筛掉模板，也不要输出“禁用整个模板库”的结论。
2. 你要回答的是：这本书默认更偏向怎么使用这整套模板池。
3. flow_family_priority、scene_template_priority、payoff_priority、foreshadowing_priority、writing_strategy_priority、character_template_priority 都只做高/中/低或主/次排序，不做硬排除。
4. 尽量优先使用模板池里已经出现过的 family、template_id、scene_id、card_id、strategy_id 或名称，避免自造名字。
5. rhythm_bias 要回答：前期开局节奏、世界观揭示密度、关系线权重、章尾拉力、爽点间隔和压力曲线。
6. demotion_rules 要写清楚这本书前期最该降权的写法倾向，不少于 2 条。
7. 所有字段尽量短，方便后续每章选择时直接消费。
8. 只输出 JSON，对象 schema 如下：
{_pretty(BOOK_EXECUTION_PROFILE_SCHEMA)}
""".strip()


def bootstrap_story_review_system_prompt() -> str:
    return (
        "你是一名中文网文立项复核编辑。"
        "你的任务是检查初始化方案是否真的能写，而不是表面完整。"
        "发现问题时，只给最少但关键的修补建议，尤其允许直接改首段 arc 的少数字段。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_story_review_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any], global_outline: dict[str, Any], first_arc: dict[str, Any], arc_digest: dict[str, Any] | None = None) -> str:
    return f"""
请复核这本小说当前的初始化结果，判断它是否已经足够稳定，可以直接进入第一章生成。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【故事圣经】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

【全书粗纲】
{_compact_pretty(_global_outline_prompt_view(global_outline), max_depth=3, max_items=8, text_limit=100)}

【首段剧情弧摘要包】
{_compact_pretty(arc_digest or first_arc, max_depth=4, max_items=10, text_limit=96)}

【首段剧情弧原始版】
{_compact_pretty(first_arc, max_depth=3, max_items=8, text_limit=88)}

要求：
1. 重点检查：主线是否清楚、前10章抓力是否够、策略卡和首段 arc 是否一致、有没有看似完整但实际难写的问题。
2. 若整体可用，status=keep；若需要轻修，status=repair。
3. arc_adjustments 只允许改首段 arc 的少数字段：goal、conflict、ending_hook、payoff_or_pressure、writing_note。
4. 不要大改结构，不要重写整段 arc，只修关键偏差。
5. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_STORY_REVIEW_SCHEMA)}
""".strip()


def bootstrap_outline_title_system_prompt() -> str:
    return (
        "你是一名擅长中文长篇网文立项与包装的策划编辑。"
        "你的任务是在同一次调用里，同时完成全书粗纲和正式书名。"
        "你要保证标题、包装抓点和全书总纲属于同一套作品定位。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_outline_title_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any], total_acts: int) -> str:
    return f"""
请在同一次输出里，完成这本小说的“全书粗纲 + 正式书名”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【故事圣经】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. global_outline 只做高层规划，共 {total_acts} 个 act；story_bible 里的 story_engine_diagnosis / story_strategy_card 是高优先级约束。
2. 每个 act 只写 title、purpose、target_chapter_end、summary。
3. title 要适合中文网文连载，不要太长，尽量控制在 12 个汉字以内。
4. packaging_line 可选，用一句短话说明包装抓点；reason 用一句话解释标题为什么贴合作品定位。
5. 标题、包装抓点、总纲 tone 必须互相一致，不能像三本不同的书。
6. 开局导向请遵守：{_opening_guidance(payload)}
7. 不要落回空泛标题，比如“问仙录”“命运序章”这种完全通用的壳子，除非输入明确要求。
8. 除非开书信息明确要求，否则不要默认开局是“药铺捡残页/夜探坊市/掌柜起疑”这一类固定套路。
9. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_OUTLINE_AND_TITLE_SCHEMA)}
""".strip()


def bootstrap_title_system_prompt() -> str:
    return (
        "你是一名中文网文包装编辑。"
        "你的任务是根据题材、主角与推进引擎，给这本书拟一个适合连载平台的正式书名。"
        "标题要有辨识度，不要太泛，也不要写成长句。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def bootstrap_title_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请为这本小说生成正式书名。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【故事底盘】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. title 要适合中文网文连载，不要太长，尽量控制在 12 个汉字以内，可带书名号外展示时使用的短副标感，但不要变成长句简介。
2. packaging_line 可选，用一句短话说明包装抓点。
3. reason 用一句话说明为什么贴合主角、题材与推进引擎。
4. 不要落回空泛标题，比如“问仙录”“命运序章”这种完全通用的壳子，除非输入明确要求。
5. 只输出 JSON，对象 schema 如下：
{_pretty(BOOTSTRAP_TITLE_SCHEMA)}
""".strip()


def story_engine_strategy_bundle_system_prompt() -> str:
    return (
        "你是一名擅长中文网文立项与开局规划的总编。"
        "你的任务是一次性完成题材拆解、书级长期方向和首个五章开局策略。"
        "输出要像编辑部的紧凑指挥卡，不要写正文，不要解释。"
        "为了提速和稳定，请优先使用短字段、短句子、短列表。"
        "你只能输出一个合法 JSON 对象，不要输出 markdown。"
    )


def story_engine_strategy_bundle_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请一次性生成这本小说的“题材画像 + 书级长期方向 + 首个五章开局策略”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这是初始化快照，不写正文，不写散文式分析，只给后续规划可直接使用的结构卡。
2. 输出必须只包含两个顶层键：story_engine_diagnosis、story_strategy_card。
3. story_engine_diagnosis 负责回答：这本书属于什么更细子类型、前期真正该靠什么推进、最该避开什么老套路。
4. story_strategy_card 负责回答：整本书长期怎么跑、开局五章先怎么抓人、滚动五章规划时哪些元素常用、哪些必须少用。
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
        "你的任务是把全书方向和开局五章策略设计清楚。"
        "你要输出的是创作指挥卡，不是正文，不是散文式解释。"
        "为了提速和稳定，请优先输出短字段、短句子、短列表。"
        "只输出一个合法 JSON 对象，不要输出 markdown。"
    )


def story_strategy_card_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any]) -> str:
    return f"""
请基于下面信息，生成“全书战略图 + 开局五章策略卡”。

【开书信息】
{_compact_pretty(_payload_prompt_view(payload), max_depth=3, max_items=8, text_limit=140)}

【当前故事底稿】
{_compact_pretty(_story_bible_prompt_view(story_bible), max_depth=3, max_items=8, text_limit=120)}

要求：
1. 这一步的重点是：让系统知道这本书长期怎么跑，以及开局五章应该怎么抓读者，而不是每章临时想。
2. story_promise 要写清楚读者持续追更能得到什么核心体验。
3. strategic_premise 要写清楚整本书长期怎么推进。
4. long_term_direction 要写清整本书长期方向；opening_five_summary 要写成一句可执行的开局主线描述。
5. opening_window 要写出开局五章的阶段任务、读者钩子、常用元素、少用元素、关系任务和阶段结果；rolling_replan_rule 要明确后续按五章滚动重规划。
6. frequent_event_types / limited_event_types 既可以是事件类别，也可以是推进方式，但必须能指导后续近纲。
7. anti_homogenization_rules 要明确指出如何避免写成常见模板。
8. 除非开书信息明确要求，否则不要默认开局五章都围绕药铺、坊市、残页、掌柜起疑、夜半试探这种固定组合。
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


def _planning_window_execution_bias_prompt_payload(story_bible: dict[str, Any], *, start_chapter: int, end_chapter: int) -> dict[str, Any]:
    payload = (((story_bible or {}).get("story_workspace") or {}).get("window_execution_bias") or {})
    if not isinstance(payload, dict) or not payload:
        return {}
    return {
        "window_mode": _text(payload.get("window_mode")),
        "directive": _text(payload.get("directive")),
        "boosted_flow_families": list(payload.get("boosted_flow_families") or [])[:4],
        "boosted_payoffs": list(payload.get("boosted_payoffs") or [])[:4],
        "boosted_foreshadowing": list(payload.get("boosted_foreshadowing") or [])[:4],
        "boosted_writing_strategies": list(payload.get("boosted_writing_strategies") or [])[:4],
        "rhythm_adjustments": payload.get("rhythm_adjustments") or {},
        "recent_corrections": list(payload.get("recent_corrections") or [])[:3],
    }


def _planning_book_execution_profile_prompt_payload(story_bible: dict[str, Any], *, start_chapter: int, end_chapter: int) -> dict[str, Any]:
    profile = (story_bible or {}).get("book_execution_profile") or {}
    if not isinstance(profile, dict) or not profile:
        return {}
    rhythm = profile.get("rhythm_bias") or {}
    return {
        "positioning_summary": _text(profile.get("positioning_summary")),
        "template_pool_policy": _text(profile.get("template_pool_policy")),
        "flow_family_priority": {
            "high": list(((profile.get("flow_family_priority") or {}).get("high") or []))[:4],
            "medium": list(((profile.get("flow_family_priority") or {}).get("medium") or []))[:3],
            "low": list(((profile.get("flow_family_priority") or {}).get("low") or []))[:3],
        },
        "scene_template_priority": {
            "high": list(((profile.get("scene_template_priority") or {}).get("high") or []))[:4],
            "medium": list(((profile.get("scene_template_priority") or {}).get("medium") or []))[:3],
            "low": list(((profile.get("scene_template_priority") or {}).get("low") or []))[:3],
        },
        "payoff_priority": {
            "high": list(((profile.get("payoff_priority") or {}).get("high") or []))[:4],
            "medium": list(((profile.get("payoff_priority") or {}).get("medium") or []))[:3],
            "low": list(((profile.get("payoff_priority") or {}).get("low") or []))[:3],
        },
        "foreshadowing_priority": {
            "primary": list(((profile.get("foreshadowing_priority") or {}).get("primary") or []))[:4],
            "secondary": list(((profile.get("foreshadowing_priority") or {}).get("secondary") or []))[:3],
            "hold_back": list(((profile.get("foreshadowing_priority") or {}).get("hold_back") or []))[:3],
        },
        "writing_strategy_priority": {
            "high": list(((profile.get("writing_strategy_priority") or {}).get("high") or []))[:4],
            "medium": list(((profile.get("writing_strategy_priority") or {}).get("medium") or []))[:3],
            "low": list(((profile.get("writing_strategy_priority") or {}).get("low") or []))[:3],
        },
        "rhythm_bias": {
            "opening_pace": _text(rhythm.get("opening_pace")),
            "world_reveal_density": _text(rhythm.get("world_reveal_density")),
            "relationship_weight": _text(rhythm.get("relationship_weight")),
            "hook_strength": _text(rhythm.get("hook_strength")),
            "payoff_interval": _text(rhythm.get("payoff_interval")),
            "pressure_curve": _text(rhythm.get("pressure_curve")),
        },
        "demotion_rules": list(profile.get("demotion_rules") or [])[:4],
        "planning_window": {"start_chapter": int(start_chapter or 0), "end_chapter": int(end_chapter or 0)},
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

【本书长期运行画像（本窗口必须遵守）】
{_compact_pretty(_planning_book_execution_profile_prompt_payload(story_bible, start_chapter=start_chapter, end_chapter=end_chapter), max_depth=3, max_items=8, text_limit=90)}

【当前窗口执行偏置（若有）】
{_compact_pretty(_planning_window_execution_bias_prompt_payload(story_bible, start_chapter=start_chapter, end_chapter=end_chapter), max_depth=3, max_items=8, text_limit=90)}

【可选章节流程卡】
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
2. 每章尽量只输出这些键：chapter_no、title、chapter_type、event_type、progress_kind、proactive_move、payoff_or_pressure、goal、conflict、ending_hook、hook_style、hook_kind、main_scene、supporting_character_focus、supporting_character_note、new_resources、new_factions、new_relations、flow_template_id、flow_template_tag、flow_template_name，以及仅在需要时才输出的 opening_beat、mid_turn、discovery、closing_image、flow_variation_note、writing_note、stage_casting_action、stage_casting_target、stage_casting_note。
3. title、goal、conflict、ending_hook、main_scene 都尽量简短，单项最好不超过 28 个汉字。
4. chapter_type 只允许 probe / progress / turning_point。
5. event_type 必须从这些里选最贴切的一种：发现类 / 试探类 / 交易类 / 冲突类 / 潜入类 / 逃避类 / 资源获取类 / 反制类 / 身份伪装类 / 关系推进类 / 外部任务类 / 危机爆发。
6. progress_kind 必须从这些里选最贴切的一种：信息推进 / 关系推进 / 资源推进 / 实力推进 / 风险升级 / 地点推进。
7. proactive_move 要明确写出主角本章主动做什么，不能只是“谨慎应对”。
8. payoff_or_pressure 要明确写出本章给读者的兑现或压力升级，不能空泛。
9. hook_style 只允许：异象 / 人物选择 / 危险逼近 / 信息反转 / 平稳过渡 / 余味收束。
10. hook_kind 至少贴近以下之一：新发现 / 新威胁 / 新任务 / 身份暴露风险 / 古镜异常反应 / 更大谜团 / 关键人物动作 / 意外收获隐患。
11. 每章都必须从【可选章节流程卡】里选一个最贴切的 flow_template_id，并同步写出对应的 flow_template_tag、flow_template_name。
12. 若【最近已使用流程】里刚出现过某个 flow_template_id，下一章默认不要继续用它；除非剧情性质明显变了，否则禁止连续多章重复同一流程。
13. 若同一 arc 里已经连续两章用了同一主事件类型，下一章必须换 event_type，禁止出现连续三章都在“被怀疑—应付—隐藏”或“发现异常—隐藏秘密—再被盘问”的重复结构。
14. opening_beat、mid_turn、discovery、closing_image、flow_variation_note、writing_note 都是可选短字段：只有当它们能明显帮助后续“这一章该怎么写”时才输出；若输出，必须短、狠、可执行，单项最好不超过 24 个汉字。
14.1 book_execution_profile 是这段近纲的长期写法约束，不只是选卡偏置：它必须实际体现在每章的 goal / conflict / proactive_move / payoff_or_pressure / hook_style / writing_note 里，决定这一章是稳推、渐压、轻揭示、补兑现还是强挂钩。
14.2 若 rhythm_bias 指向低世界揭示密度，就不要在近纲里安排百科式说明；若 relationship_weight 偏低，就不要每章都硬塞关系戏；若 hook_strength 偏高，章尾要更有牵引；若 payoff_interval 偏短，窗口前半段至少要更早给出一次明确回报。
14.3 demotion_rules 视为长期禁忌，近纲不要主动掉回这些写法。
14.3.1 若【当前窗口执行偏置】存在，就把它视为多章规划刷新后的阶段偏置：在不违背 book_execution_profile 的前提下，优先让当前五章顺着窗口模式去排。
14.4 只有当本章会首次引入新资源、新势力或新关系时，才额外输出 new_resources / new_factions / new_relations；不用时就省略。
14.5 new_resources 与 new_factions 只写名字，不要写解释；new_relations 最多 3 条，每条只写 subject、target、relation_type、status、recent_trigger 这些短字段。
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
20. 如果 story_bible 里有 story_strategy_card，且当前仍处于开局五章窗口内，要优先贴合 opening_window 的 stage_mission、reader_hook、relationship_tasks 与 anti_homogenization_rules；若已离开开局窗口，就继续遵守 long_term_direction、rolling_replan_rule 与 anti_homogenization_rules。
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
