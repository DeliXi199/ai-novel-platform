import json
from typing import Any


def _pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


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
        "前15章要在以下功能之间轮换：立足、获得资源、验证能力、关系推进、训练/试错、地图推进、势力接触、小冲突或局部破局。"
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
{_pretty(payload)}

【故事圣经】
{_pretty(story_bible)}

要求：
1. 只做高层规划，共 {total_acts} 个 act。
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
{_pretty(payload)}

【故事圣经】
{_pretty(story_bible)}

【全书粗纲】
{_pretty(global_outline)}

【最近章节摘要】
{_pretty(recent_summaries)}

要求：
1. 这是第 {arc_no} 个 arc，只覆盖第 {start_chapter}-{end_chapter} 章。
2. 每章尽量只输出这些键：chapter_no、title、chapter_type、event_type、progress_kind、proactive_move、payoff_or_pressure、goal、conflict、ending_hook、hook_style、hook_kind、main_scene、supporting_character_focus、supporting_character_note。
3. title、goal、conflict、ending_hook、main_scene 都尽量简短，单项最好不超过 28 个汉字。
4. chapter_type 只允许 probe / progress / turning_point。
5. event_type 必须从这些里选最贴切的一种：发现类 / 试探类 / 交易类 / 冲突类 / 潜入类 / 逃避类 / 资源获取类 / 反制类 / 身份伪装类 / 关系推进类 / 外部任务类 / 危机爆发。
6. progress_kind 必须从这些里选最贴切的一种：信息推进 / 关系推进 / 资源推进 / 实力推进 / 风险升级 / 地点推进。
7. proactive_move 要明确写出主角本章主动做什么，不能只是“谨慎应对”。
8. payoff_or_pressure 要明确写出本章给读者的兑现或压力升级，不能空泛。
9. hook_style 只允许：异象 / 人物选择 / 危险逼近 / 信息反转 / 平稳过渡 / 余味收束。
10. hook_kind 至少贴近以下之一：新发现 / 新威胁 / 新任务 / 身份暴露风险 / 古镜异常反应 / 更大谜团 / 关键人物动作 / 意外收获隐患。
11. 若同一 arc 里已经连续两章用了同一主事件类型，下一章必须换 event_type，禁止出现连续三章都在“被怀疑—应付—隐藏”或“发现异常—隐藏秘密—再被盘问”的重复结构。
12. 这一步只做紧凑近纲，不要输出 opening_beat、mid_turn、discovery、closing_image、writing_note 这类长字段；后续章节执行卡阶段会再补全。
13. 节奏要贴合题材定位，每章只推进一个主冲突，但必须明确本章新增了什么，不要重复同一意象和同一动作模板。
14. 核心机缘、线索、目标物或关键关系的状态要稳定，但不要默认它一定是残页、古卷、地图、碎片或石头。
15. supporting_character_note 不能只写“有辨识度”，要具体到说话风格、私心、受压反应、小动作或忌讳中的至少两项。
16. 若最近章节已经出现“配角只负责盘问/警告/发任务”的倾向，下一章要把关键配角改成更像人：先有立场和算盘，再推动剧情。
17. {_variety_guidance(payload)}
18. title 不要与最近十几章常见标题重复，避免再次出现“夜半微光/旧纸页/坊市试探”这类高相似标题。
19. 除非开书信息明确要求，否则不要把场景反复锁在药铺、后院、坊市、夜半试探这种固定组合。
20. 不要大场面堆砌，不要一口气揭露终极秘密。
21. 配角不是功能按钮；若某章有关键配角，supporting_character_note 要写出他的说话方式、私心、顾虑、受压反应或做事风格。
22. 不要输出任何解释、前缀、后缀、代码块或注释，只输出 JSON。
23. 对象 schema 如下：
{_pretty(ARC_OUTLINE_SCHEMA)}
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
    runtime_feedback = workflow_runtime.get("retry_feedback") or {}
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
        runtime_feedback_block = f"\n\n【本章重试纠偏】\n{_pretty(runtime_feedback)}\n若上一次草稿被指出'主角被动'或'主动性不足'，这次必须优先修正，不得重复同类写法。"
    repetition_note = chapter_plan.get("writing_note")
    repetition_block = f"\n【额外写作提醒】\n{repetition_note}\n" if repetition_note else ""
    protagonist_name = _protagonist_name_from_context(novel_context)
    blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST)
    retry_prompt_mode = _text(chapter_plan.get("retry_prompt_mode")).lower()
    if retry_prompt_mode in {"compact", "light"}:
        return f"""
请直接重写这一章正文，并优先修正上一次草稿的问题。

【必要上下文】
{_pretty({
    "project_card": ((novel_context or {}).get("story_memory") or {}).get("project_card"),
    "current_volume_card": ((novel_context or {}).get("story_memory") or {}).get("current_volume_card"),
    "execution_brief": ((novel_context or {}).get("story_memory") or {}).get("execution_brief"),
    "recent_retrospectives": ((novel_context or {}).get("story_memory") or {}).get("recent_retrospectives"),
    "hard_fact_guard": ((novel_context or {}).get("story_memory") or {}).get("hard_fact_guard"),
    "workflow_runtime": ((novel_context or {}).get("story_memory") or {}).get("workflow_runtime"),
})}

【本章拍表】
{_pretty(chapter_plan)}

【上一章信息】
{_pretty(last_chapter)}

【最近摘要】
{_pretty(recent_summaries[:1])}

{agency_mode_block}
{progress_result_block}
{agency_constraints}
{runtime_feedback_block}
{repetition_block}
写作要求：
1. 只写完整章节正文，不要标题、JSON、markdown。
2. 前两段就让主角先手，形成“主角动作/判断 -> 外界反应 -> 主角调整”的链条。
3. 至少推进一项清晰结果：信息、关系、资源、风险或实力。
4. 必须有开场动作、中段受阻、一次发现和自然收束的结尾。
5. 严格服从硬事实与上一章衔接，别改人物状态、物件归属和时序。
6. 目标约 {target_words} 字，尽量控制在 {target_visible_chars_min}-{target_visible_chars_max} 个中文可见字符。
7. 这次优先修复：主动性、推进、篇幅、结尾，不要再回到模板句和空转气氛。
8. 禁止出现这些重复模板：
{blacklist}
""".strip()
    return f"""
请根据以下信息写出下一章正文。

【轻量小说记忆】
{_pretty(novel_context)}

【本章拍表】
{_pretty(chapter_plan)}

【上一章信息】
{_pretty(last_chapter)}

若【上一章信息】里包含 continuity_bridge / last_two_paragraphs / last_scene_card / unresolved_action_chain / onstage_characters，必须把它们视为开章硬承接依据。

【最近章节摘要】
{_pretty(recent_summaries)}

【当前生效的读者干预】
{_pretty(active_interventions)}

{agency_mode_block}
{progress_result_block}
{agency_constraints}
{runtime_feedback_block}
{repetition_block}
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
8. 结尾必须自然收束，不能停在半句上；是否留悬念，要服从本章 hook_style。若是“平稳过渡/余味收束”，可以只落在人物选择、结果落地、关系变化或下一步准备上，不必硬留悬念。
10. {_chapter_genre_guidance(novel_context)}
11. 配角不能只是抛信息的工具人。尤其是反复出现的人物，要给他一点职业习惯、说话方式、私心、忌讳或防备心理，让他先像人，再推动情节。
12. 若本章出现反派、帮众或威胁角色，至少给他们一处能被记住的细节：口头禅、手势、癖好、伤疤、做事逻辑或对上位者的惧怕。
13. 若本章涉及失去、离别、当掉旧物、被迫离开、冒险抉择等情节，要把{protagonist_name}的情绪再往下沉半层，但通过动作、停顿、视线、呼吸、手指和旧物处理落出来，不要一句带过，也不要直接抒情喊痛。
14. 若本章拍表给了 supporting_character_focus / supporting_character_note，至少在一个场面里落实出来；同一个配角不能永远只负责盘问或警告，要写出他的说话风格、利益诉求、受压反应、小动作或忌讳。
15. 若轻量记忆里提供了 execution_brief.character_voice_pack 或 story_memory.character_roster，必须让对应人物说话和做事贴着这些差异化信息写，不能重新写回模板腔。
16. 若轻量记忆里提供了 recent_retrospectives，优先避免里面指出的重复问题，尤其不要再写“同类桥段重复、主角被动、配角功能化、结尾发虚”。
17. 对话要分人：掌柜、摊主、帮众、散修、同门、师长，不要全都说成同一种冷硬叙述腔。
18. 句子可以克制，但不要一味求稳；少量关键句要更具体、更有辨识度，不要全靠“温凉/微弱/若有若无/看了片刻/没有再说什么”这种安全表达支撑氛围。
17. 本章结尾必须形成追更动力或结果落地，优先服从 chapter_execution_card 的 chapter_hook / hook_kind；禁止用“回去休息了/暂时压下念头/明日再看/夜色沉沉事情暂告一段落”这类平钩子收尾。
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


def chapter_extension_system_prompt() -> str:
    return (
        "你是一名中文连载小说修稿助手。"
        "你的任务不是重写整章，而是根据已有正文的最后片段，只补齐截断的尾巴，让这一场景完整闭合并自然收束。"
        "不能重复前文，不能改写已发生的事实，不能突然开新场景，也不能另起一章。"
        "如果结尾停在对白、动作或命令半句上，就顺着那半句补完，并把引号、句意、动作链闭合。"
        "只输出新增补写的正文，不要解释，不要标题。"
    )



def chapter_extension_user_prompt(
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> str:
    existing = (existing_content or "").strip()
    tail_excerpt = _tail_excerpt(existing, max_chars=900)
    full_visible_chars = len(existing)
    return f"""
请顺着下面这章正文的结尾继续补写，只做“补尾”，不要重写前文。

【本章拍表】
{_pretty(chapter_plan)}

【全文长度】
当前正文约 {full_visible_chars} 个可见字符。以下只提供结尾片段，目的是让你顺着最后一个场景继续，把尾巴补齐。

【已有正文结尾片段】
{tail_excerpt}

补写原因：{reason}

要求：
1. 只补写新增的后续正文，不要重复已有句子，不要回头重讲前文，不要重写整章。
2. 你只能顺着上面这个结尾片段继续同一场景，不能突然跳到新地点、新时间，也不要补写未出现的大段回忆。
3. 若结尾停在对白、命令、动作或判断的半句上，先把这一半句补完整，再补 1-3 个自然收束句。
4. 你补的是“尾巴”，不是“续一大段新剧情”。若已有正文已经接近完整，只需补 80-220 字；除非上下文明显还差一个短收束，否则不要超过 300 字。
5. 优先完成这几件事：补闭合引号、补全残句、补完当前动作链、给当前小场景一个自然落点。
6. 不要为了凑字数新增无关描写，不要重复上一句的意思换个说法再说一遍。
7. 补写后整章应尽量仍落在 {target_visible_chars_min}-{target_visible_chars_max} 个可见字符范围内。
8. 结尾必须完整闭合，并服从本章 hook_style：可以停在具体画面、人物选择、危险逼近、信息反转，或正常过渡的余味上，但不要停在半句。
9. 只输出新增补写的正文，不要标题、不要 JSON、不要解释。
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
