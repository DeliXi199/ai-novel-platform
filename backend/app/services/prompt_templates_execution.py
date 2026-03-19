from __future__ import annotations

import json
from typing import Any


def _trim_text(value: Any, limit: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_value(value: Any, *, depth: int = 0, max_depth: int = 3, max_items: int = 5, text_limit: int = 88) -> Any:
    if depth >= max_depth:
        return _trim_text(value, text_limit)
    if isinstance(value, str):
        return _trim_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1, max_depth=max_depth, max_items=max_items, text_limit=text_limit) for item in value[:max_items]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                break
            compact[str(key)] = _compact_value(item, depth=depth + 1, max_depth=max_depth, max_items=max_items, text_limit=text_limit)
        return compact
    return _trim_text(value, text_limit)


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


EXECUTION_STRUCTURE_SCHEMA = {
    "chapter_function": "一句话说明本章真正功能，必须贴合本章而不是模板口号",
    "chapter_change": "一句话说明本章会发生的核心变化",
    "opening": "开场怎么落地，要写到具体动作/异常/场面，不要空话",
    "middle": "中段真正的受阻、误判、试探、换招或遮掩",
    "ending": "结尾落到什么具体结果、代价、关系变化或新问题",
    "chapter_hook": "章末拉力，用一句话说明后续最该追的东西",
    "reason": "你为什么这样安排，简短说明即可"
}


def chapter_execution_structure_system_prompt() -> str:
    return """
你是“章节执行结构规划器”。
你的任务不是写正文，而是把这一章真正该怎么写，压缩成 3 个贴章、可执行、非模板化的结构指令。

输出要求：
1. 只输出 JSON，对齐给定 schema。
2. opening / middle / ending 必须贴着当前章目标、当前场景、上一章尾巴、人物关系，以及 scene_execution_card 里的续场/切场约束来写。
3. 不要输出空泛章法口号，不要写“开场先落在一个具体动作上”“中段加入一次受阻”“结尾收在一个画面上”这种模板句。
4. 不要照抄 agency mode 的固定句库；可以吸收其思路，但必须改写成当前章节自己的具体写法。
5. 如果当前章明显应继续上一章的动作链，就把 opening 写成“承接什么具体动作/局势”。
6. middle 要说明真正的阻力或换招，不要只写“推进剧情”。
7. ending 要说明本章落到什么结果、代价、关系变化或新悬念，必须可感。
8. 全部字段都尽量短、准、具体，避免抽象总结。
""".strip()


def chapter_execution_structure_user_prompt(*, payload: dict[str, Any]) -> str:
    compact_payload = _compact_value(payload, max_depth=4, max_items=6, text_limit=96)
    return f"""
请基于下面的信息，生成这一章真正该执行的结构卡。

【输入信息】
{_pretty(compact_payload)}

请输出 JSON schema：
{_pretty(EXECUTION_STRUCTURE_SCHEMA)}

额外规则：
- opening / middle / ending 三段必须彼此衔接，像同一章，而不是三个孤立建议。
- 可以比原计划更具体，但不要改掉章节核心目标。
- 若原计划里的 opening_beat / mid_turn / closing_image 已经具体，你可以吸收、细化；若它们空泛或模板化，你必须重写。
- 若 scene_outline 明确给了场景推进顺序，结构卡应与之对齐。
- 若 supporting_character_focus 存在，要让该人物在本章里有真实功能，而不是只挂名。
""".strip()
