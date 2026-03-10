import json
from typing import Any


def _pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


GLOBAL_OUTLINE_SCHEMA = {
    "story_positioning": {
        "tone": "慢热、克制、偏凡人流",
        "core_promise": "前期先写生存与试探，中期再扩大世界与冲突。",
    },
    "acts": [
        {
            "act_no": 1,
            "title": "凡人求生",
            "purpose": "建立主角处境、资源压力与异常线索",
            "target_chapter_end": 12,
            "summary": "主角从日常困境进入更大的局势边缘。",
        }
    ],
}


ARC_OUTLINE_SCHEMA = {
    "arc_no": 1,
    "start_chapter": 1,
    "end_chapter": 3,
    "focus": "确认线索、避免暴露、获取小资源",
    "bridge_note": "这一小段先稳住衔接，再把风险轻轻抬高。",
    "chapters": [
        {
            "chapter_no": 1,
            "title": "药铺后的旧纸页",
            "chapter_type": "probe",
            "goal": "让主角在具体日常里发现异常线索",
            "conflict": "主角想试探残页，却担心被掌柜发现",
            "ending_hook": "纸页在夜里自行发热",
            "hook_style": "异象",
            "main_scene": "边陲小城药铺后院",
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
        "你必须给出稳定、可执行、慢热的全书粗纲。"
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
4. 如果是凡人流修仙，前期先写资源、风险、试探、低调求生。
5. 目标是让后续小弧线有稳定方向，而不是一开始就爆大场面。
6. 只输出 JSON，对象 schema 如下：
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
7. 节奏要慢热，每章只推进一个主冲突，不要重复同一意象和同一动作模板。
8. 核心线索物件的形态要稳定，例如“残页/残卷/几页”不能随意漂移，除非本章明确揭示它发生变化。
9. 不要大场面堆砌，不要一口气揭露终极秘密。
10. 不要输出任何解释、前缀、后缀、代码块或注释，只输出 JSON。
11. 对象 schema 如下：
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
        "你是一名擅长中文网文连载的主笔，尤其擅长凡人流修仙和慢热升级流。"
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
2. 把【轻量小说记忆】中的 project_card / current_volume_card / protagonist_state / near_7_chapter_outline / foreshadowing / daily_workbench / execution_brief 当成硬约束，严格按“项目卡 → 当前卷卡 → 近7章近纲 → 本章执行卡 → 正文”的顺序落实，不得跳步。
3. 本章只围绕 1 个核心场景与 1 个主要矛盾展开，节奏慢热、连贯。
4. 本章必须依次落到四个拍点：开场落点、一次中段受阻或转折、一次具体发现、一个来自当前场景的结尾钩子。
5. 优先写具体的动作、观察、试探和对话，不要用旁白总结剧情，不要像提纲扩写。
6. 开头必须直接落在当前场景，不要用空泛天气句、危险句、任务句开场。
7. 轻量上下文只提供当前章真正需要的记忆点，不要机械复述设定，不要回顾整本书。
8. 结尾必须自然收束，不能停在半句上；是否留悬念，要服从本章 hook_style。若是“平稳过渡/余味收束”，可以只落在人物选择、结果落地、关系变化或下一步准备上，不必硬留悬念。
9. 如果题材是凡人流修仙，要强调资源、风险、谨慎和代价，而不是宏大奇观。
10. 配角不能只是抛信息的工具人。尤其是反复出现的人物，要给他一点职业习惯、说话方式、私心、忌讳或防备心理，让他先像人，再推动情节。
11. 若本章出现反派、帮众或威胁角色，至少给他们一处能被记住的细节：口头禅、手势、癖好、伤疤、做事逻辑或对上位者的惧怕。
12. 若本章涉及失去、离别、当掉旧物、被迫离开、冒险抉择等情节，要把林玄的情绪再往下沉半层，但通过动作、停顿、视线、呼吸、手指和旧物处理落出来，不要一句带过，也不要直接抒情喊痛。
13. 若本章拍表给了 supporting_character_focus / supporting_character_note，至少在一个场面里落实出来，但不要用大段说明直说。
14. 对话要分人：掌柜、摊主、帮众、散修，不要全都说成同一种冷硬叙述腔。
15. 句子可以克制，但不要一味求稳；少量关键句要更具体、更有辨识度，不要全靠“温凉/微弱/若有若无/看了片刻/没有再说什么”这种安全表达支撑氛围。
16. 只允许温和体现读者干预，不能破坏章节主目标。
17. 若轻量上下文与本章拍表有轻微冲突，以本章拍表和上一章衔接为准。
18. 保持核心线索物件形态稳定；如果上一章写的是一张残页，这一章不能无说明变成一卷古卷。
19. 如果本章存在数日或半个月的时间跳跃，必须在前两段明确写出过渡，不要突然跳时间。
20. 只输出章节正文，不要输出标题、JSON、markdown、解释或自我分析。
21. 少于 {target_visible_chars_min} 个可见中文字符视为偏短，必须补足场景细节、互动过程和信息推进，不要匆忙收尾。
22. 下面这些重复模板绝对不要出现：
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
