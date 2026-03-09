import json
from typing import Any


def _pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


CHAPTER_OUTPUT_SCHEMA = {
    "title": "章节标题字符串",
    "content": "完整章节正文，必须是自然中文小说，不要解释，不要提及提示词",
    "event_summary": "100字以内，概括本章发生的关键事件",
    "character_updates": {
        "角色名": {
            "relationship_change": "关系变化描述，可选",
            "emotion": "当前情绪，可选",
            "goal": "本章后的目标，可选",
        }
    },
    "new_clues": ["本章新增线索1"],
    "open_hooks": ["本章留下的悬念1"],
    "closed_hooks": ["本章回收的伏笔1"],
}


def bootstrap_system_prompt() -> str:
    return (
        "你是一名擅长中文连载小说的主笔编辑。"
        "你的任务是为读者生成可持续追更的章节。"
        "必须严格保持自然中文小说风格，禁止输出说明、注释、提示词复述。"
        "输出必须是单个 JSON 对象，且字段严格遵守用户提供的 schema。"
    )


def bootstrap_user_prompt(payload: dict[str, Any], story_bible: dict[str, Any], target_words: int) -> str:
    return f"""
请根据以下开书信息，生成这本书的第1章。

【开书信息】
{_pretty(payload)}

【故事圣经】
{_pretty(story_bible)}

要求：
1. 语言必须是中文。
2. 这一章必须像真正网文/连载小说的开篇，不要写成简介，不要写成设定说明。
3. 需要有场景、有动作、有情绪、有悬念。
4. 保持读者可追更感，结尾必须留下明确钩子。
5. 目标长度约 {target_words} 字。
6. 主角名必须自然出现在正文中。
7. 不要输出 markdown，不要使用代码块。

请只输出 JSON，对象 schema 如下：
{_pretty(CHAPTER_OUTPUT_SCHEMA)}
""".strip()


def next_chapter_system_prompt() -> str:
    return (
        "你是一名负责长篇连载续写的中文小说主笔。"
        "你必须同时遵守故事圣经、最近章节摘要、角色连续性和读者干预。"
        "输出必须是单个 JSON 对象，且字段严格遵守用户提供的 schema。"
        "正文必须是自然小说，而不是提纲或解释。"
    )


def next_chapter_user_prompt(
    novel_context: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
    target_words: int,
) -> str:
    return f"""
请续写这本连载小说的下一章。

【小说上下文】
{_pretty(novel_context)}

【上一章信息】
{_pretty(last_chapter)}

【最近章节摘要】
{_pretty(recent_summaries)}

【当前生效的读者干预】
{_pretty(active_interventions)}

写作要求：
1. 用中文写出完整下一章，目标长度约 {target_words} 字。
2. 必须承接上一章的因果，不得突然跳脱。
3. 优先推进主线，同时在可能时体现读者干预，但不能破坏基本逻辑。
4. 结尾保留新的追更钩子。
5. 禁止出现“系统检测到”“读者要求”“本章任务”等元叙事表达。
6. 不要输出 markdown，不要使用代码块。

请只输出 JSON，对象 schema 如下：
{_pretty(CHAPTER_OUTPUT_SCHEMA)}
""".strip()


def instruction_parse_system_prompt() -> str:
    return (
        "你是一个读者偏好解析器。"
        "你的任务是把一句中文自然语言偏好，转换成稳定的 JSON 控制参数。"
        "不要解释，只输出 JSON。"
    )


INSTRUCTION_OUTPUT_SCHEMA = {
    "character_focus": {"角色名": 1.5},
    "tone": "lighter | darker | warmer | tenser | null",
    "pace": "faster | slower | null",
    "protected_characters": ["角色名"],
    "relationship_direction": "slow_burn | stronger_romance | weaker_romance | null",
}


def instruction_parse_user_prompt(raw_instruction: str) -> str:
    return f"""
请解析这句读者要求：
{raw_instruction}

输出 JSON schema：
{_pretty(INSTRUCTION_OUTPUT_SCHEMA)}

要求：
1. 如果没有提到角色名，character_focus 返回空对象。
2. 只能输出一个 JSON 对象。
3. 不要添加 schema 以外的字段。
""".strip()
