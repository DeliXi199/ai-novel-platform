import json
from typing import Any


def _pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


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
            "goal": "让主角面对第一轮具体问题或机会",
            "conflict": "目标出现，但获取它需要付出可感知的代价",
            "ending_hook": "新的方向、风险或人物介入被确认",
            "hook_style": "信息反转",
            "main_scene": "当前阶段最能承载冲突的核心场景",
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
2. 每章尽量只输出这些键：chapter_no、title、chapter_type、goal、conflict、ending_hook、hook_style、main_scene。
3. title、goal、conflict、ending_hook、main_scene 都尽量简短，单项最好不超过 28 个汉字。
4. chapter_type 只允许 probe / progress / turning_point。
5. hook_style 只允许：异象 / 人物选择 / 危险逼近 / 信息反转 / 平稳过渡 / 余味收束。
6. 这一步只做紧凑近纲，不要输出 opening_beat、mid_turn、discovery、closing_image、supporting_character_note、writing_note 这类长字段；后续章节执行卡阶段会再补全。
7. 节奏要贴合题材定位，每章只推进一个主冲突，不要重复同一意象和同一动作模板。
8. 核心机缘、线索、目标物或关键关系的状态要稳定，但不要默认它一定是残页、古卷、地图、碎片或石头。
9. {_variety_guidance(payload)}
10. title 不要与最近十几章常见标题重复，避免再次出现“夜半微光/旧纸页/坊市试探”这类高相似标题。
11. 除非开书信息明确要求，否则不要把场景反复锁在药铺、后院、坊市、夜半试探这种固定组合。
12. 不要大场面堆砌，不要一口气揭露终极秘密。
13. 不要输出任何解释、前缀、后缀、代码块或注释，只输出 JSON。
14. 对象 schema 如下：
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
    repetition_note = chapter_plan.get("writing_note")
    repetition_block = f"\n【额外写作提醒】\n{repetition_note}\n" if repetition_note else ""
    protagonist_name = _protagonist_name_from_context(novel_context)
    blacklist = "\n".join(f"- {item}" for item in REPETITION_BLACKLIST)
    return f"""
请根据以下信息写出下一章正文。

【轻量小说记忆】
{_pretty(novel_context)}

【本章拍表】
{_pretty(chapter_plan)}

【上一章信息】
{_pretty(last_chapter)}

【最近章节摘要】
{_pretty(recent_summaries)}

【当前生效的读者干预】
{_pretty(active_interventions)}
{repetition_block}
写作要求：
1. 用中文写完整下一章，目标约 {target_words} 字，建议控制在 {target_visible_chars_min}-{target_visible_chars_max} 个中文可见字符之间，允许自然波动，但必须写成完整一章而不是片段。
2. 把【轻量小说记忆】中的 project_card / current_volume_card / protagonist_state / near_7_chapter_outline / foreshadowing / daily_workbench / execution_brief 当成硬约束，严格按“项目卡 -> 当前卷卡 -> 近7章近纲 -> 本章执行卡 -> 正文”的顺序落实，不得跳步。
3. 本章只围绕 1 个核心场景与 1 个主要矛盾展开，节奏稳定、连贯。
4. 本章必须依次落到四个拍点：开场落点、一次中段受阻或转折、一次具体发现、一个来自当前场景的结尾钩子。
5. 优先写具体的动作、观察、试探和对话，不要用旁白总结剧情，不要像提纲扩写。
6. 开头必须直接落在当前场景，不要用空泛天气句、危险句、任务句开场。
7. 轻量上下文只提供当前章真正需要的记忆点，不要机械复述设定，不要回顾整本书。
8. 结尾必须自然收束，不能停在半句上；是否留悬念，要服从本章 hook_style。若是“平稳过渡/余味收束”，可以只落在人物选择、结果落地、关系变化或下一步准备上，不必硬留悬念。
9. {_chapter_genre_guidance(novel_context)}
10. 配角不能只是抛信息的工具人。尤其是反复出现的人物，要给他一点职业习惯、说话方式、私心、忌讳或防备心理，让他先像人，再推动情节。
11. 若本章出现反派、帮众或威胁角色，至少给他们一处能被记住的细节：口头禅、手势、癖好、伤疤、做事逻辑或对上位者的惧怕。
12. 若本章涉及失去、离别、当掉旧物、被迫离开、冒险抉择等情节，要把{protagonist_name}的情绪再往下沉半层，但通过动作、停顿、视线、呼吸、手指和旧物处理落出来，不要一句带过，也不要直接抒情喊痛。
13. 若本章拍表给了 supporting_character_focus / supporting_character_note，至少在一个场面里落实出来，但不要用大段说明直说。
14. 对话要分人：掌柜、摊主、帮众、散修、同门、师长，不要全都说成同一种冷硬叙述腔。
15. 句子可以克制，但不要一味求稳；少量关键句要更具体、更有辨识度，不要全靠“温凉/微弱/若有若无/看了片刻/没有再说什么”这种安全表达支撑氛围。
16. 只允许温和体现读者干预，不能破坏章节主目标。
17. 若轻量上下文与本章拍表有轻微冲突，以本章拍表和上一章衔接为准。
18. 保持核心机缘、线索物件或关键关系的状态稳定；如果上一章写的是一枚令牌、一株灵草、一段关系，这一章不能无说明改成别的东西。
19. 如果本章存在数日或半个月的时间跳跃，必须在前两段明确写出过渡，不要突然跳时间。
20. 只输出章节正文，不要输出标题、JSON、markdown、解释或自我分析。
21. 少于 {target_visible_chars_min} 个可见中文字符视为偏短，必须补足场景细节、互动过程和信息推进，不要匆忙收尾。
22. 若最近两三章都在调查同一条线索，本章至少要推进其中一种变化：线索状态变化、资源兑现、地图切换、对手介入、关系变化或能力验证。
23. 除非当前上下文已经明确建立，否则不要自行把剧情锁定成“药铺-掌柜-残页-坊市-夜探”这一固定组合。
24. 数量、伤势、旧物、地点和时序必须与上下文一致，不能把三块灵石写成五块，也不能把旧伤位置和人物经历写乱。
25. 下面这些重复模板绝对不要出现：
{blacklist}
""".strip()



def chapter_extension_system_prompt() -> str:
    return (
        "你是一名中文连载小说修稿助手。"
        "你的任务不是重写整章，而是顺着已有正文继续补写同一场景，使它完整、自然收束。"
        "不能重复前文，不能改写已发生的事实，不能突然开新场景。"
        "只输出补写的新增正文，不要解释，不要标题。"
    )



def chapter_extension_user_prompt(
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> str:
    return f"""
请顺着下面这章正文的结尾继续补写。

【本章拍表】
{_pretty(chapter_plan)}

【已有正文】
{existing_content}

补写原因：{reason}

要求：
1. 只补写新增的后续正文，不要重复已有句子，不要回头重讲前文。
2. 补写后整章应尽量落在 {target_visible_chars_min}-{target_visible_chars_max} 个可见字符范围内。
3. 若已有正文已经接近完整，只需补 150-350 字，把当前小场景自然收住。
4. 若已有正文明显偏短，可补 300-700 字，把中段动作、对话和信息推进补全。
5. 结尾必须完整闭合，并服从本章 hook_style：可以停在具体画面、人物选择、危险逼近、信息反转，或正常过渡的余味上，但不要停在半句。
6. 只输出新增补写的正文，不要标题、不要 JSON、不要解释。
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
