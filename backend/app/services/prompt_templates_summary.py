from __future__ import annotations

from app.services.prompt_templates_shared import *

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
人物变化：<若无则写 无；若正文明确出现境界/实力/修炼进度/突破结果，也要写进去>
新线索：<用；分隔，若无则写 无>
未回收钩子：<用；分隔，若无则写 无>
已回收钩子：<用；分隔，若无则写 无>

要求：
1. 不要输出任何额外说明。
2. 不要复述提示词。
3. 只基于正文提取。
4. 关键资源若正文明确写到品质、数量变化或炼化结果，人物变化里要顺手提到。
5. 怪兽/妖兽/异类若正文明确出现并给出强弱层位或状态变化，人物变化里也要顺手提到。
""".strip()



def summary_title_package_system_prompt() -> str:
    return (
        "你是小说章节后处理器。"
        "你要在一次输出中同时完成结构化摘要和标题精修候选生成。"
        "摘要只能提取正文里已经发生的内容，不准编造。"
        "标题必须贴合本章成稿结果，避开空泛氛围词、最近重复标题与高频冷却词。"
        "不要输出 markdown，不要解释过程，只输出合法 JSON。"
    )



def summary_title_package_user_prompt(
    *,
    chapter_no: int,
    chapter_title: str,
    chapter_plan: dict[str, Any],
    chapter_content: str,
    recent_titles: list[str],
    cooled_terms: list[str],
    candidate_count: int,
) -> str:
    return f"""
请为第 {chapter_no} 章生成联合后处理结果，一次完成“结构化摘要 + 标题精修候选”。

【当前工作标题】
{chapter_title}

【本章计划】
{_compact_pretty(_chapter_plan_prompt_view(chapter_plan, include_packet=False), max_depth=3, max_items=8, text_limit=120)}

【章节正文】
{chapter_content}

【最近章节标题】
{_compact_pretty(compact_data(recent_titles, max_depth=2, max_items=12, text_limit=40), max_depth=2, max_items=12, text_limit=40)}

【近期冷却词】
{_compact_pretty(compact_data(cooled_terms, max_depth=2, max_items=12, text_limit=20), max_depth=2, max_items=12, text_limit=20)}

要求：
1. 只输出一个 JSON 对象，严格对齐给定 schema。
2. summary.event_summary 必须是 80 字以内的一句话，只概括本章已经发生的事。
3. summary.character_updates 只写正文里明确可见的变化；普通角色直接写角色名键值即可。
4. 若正文明确出现了资源品质/数量变化，可把它们写进 character_updates.__resource_updates__；若正文明确出现了怪兽/妖兽/异类的出场、强弱层位或状态变化，可写进 character_updates.__monster_updates__。
5. 角色、怪兽、资源若正文里明确提到了境界/实力/品质变化，优先用结构化字段表达，例如 current_realm / current_strength / cultivation_progress / breakthrough / quality_tier / quantity_after / threat_level / status / latest_update。
6. summary.new_clues / open_hooks / closed_hooks 只保留正文里已经落地的信息，每项尽量短，最多 6 项。
5. title_refinement.recommended_title 必须是你最推荐的标题。
6. 一共输出 {candidate_count} 个标题候选，标题尽量 4 到 10 个汉字，不要超过 14 个汉字。
7. 标题优先落在：结果、后果、新信息、人物选择、关系变化、具体风险、具体物件。
8. 不要写成“夜半微光 / 旧纸页 / 坊市试探 / 暗流再起”这种空泛氛围标题。
9. 候选标题彼此要有区分，不要只是同义替换。
10. 不要剧透正文尚未落地的终极秘密，但可以点出本章已经形成的变化或风险。
11. title_type 可参考：结果型 / 风险型 / 关系型 / 悬念型 / 物件型 / 地点型 / 人物选择型。
12. angle 用一句短话说明标题抓住了哪种落点；reason 用一句短话说明为什么它比空泛标题更好。
13. 只输出 JSON，对象 schema 如下：
{_pretty(SUMMARY_TITLE_PACKAGE_SCHEMA)}
""".strip()



def chapter_title_refinement_system_prompt() -> str:
    return (
        "你是小说章节标题精修器。"
        "你的任务不是复述剧情，而是给这一章起更稳、更不重复、更贴近成稿结果的标题。"
        "你必须避开最近章节的高相似标题与高频套词。"
        "标题要短，尽量 4 到 10 个汉字；允许更短，但不要空泛。"
        "优先使用具体结果、具体新信息、具体关系变化、具体风险落点。"
        "不要输出解释性散文，不要输出 markdown，只输出合法 JSON。"
    )



def chapter_title_refinement_user_prompt(
    *,
    chapter_no: int,
    original_title: str,
    chapter_plan: dict[str, Any],
    content_digest: dict[str, Any],
    summary_payload: dict[str, Any],
    recent_titles: list[str],
    cooled_terms: list[str],
    candidate_count: int,
) -> str:
    return f"""
请为第 {chapter_no} 章做标题精修。

【当前工作标题】
{original_title}

【本章计划】
{_compact_pretty(_chapter_plan_prompt_view(chapter_plan, include_packet=False), max_depth=3, max_items=8, text_limit=120)}

【本章成稿摘录】
{_compact_pretty(compact_data(content_digest, max_depth=3, max_items=8, text_limit=100), max_depth=3, max_items=8, text_limit=100)}

【本章摘要】
{_compact_pretty(compact_data(summary_payload, max_depth=3, max_items=8, text_limit=100), max_depth=3, max_items=8, text_limit=100)}

【最近章节标题】
{_compact_pretty(compact_data(recent_titles, max_depth=2, max_items=12, text_limit=40), max_depth=2, max_items=12, text_limit=40)}

【近期冷却词】
{_compact_pretty(compact_data(cooled_terms, max_depth=2, max_items=12, text_limit=20), max_depth=2, max_items=12, text_limit=20)}

要求：
1. 输出 {candidate_count} 个候选标题，并给出 recommended_title。
2. 标题尽量 4 到 10 个汉字，不要超过 14 个汉字。
3. 不要再写成“夜半微光 / 旧纸页 / 坊市试探 / 暗流再起”这种空泛氛围标题。
4. 标题必须更贴本章最终成稿，优先落在：结果、后果、新信息、人物选择、关系变化、具体风险、具体物件。
5. 候选标题之间也要有区分，不要只是同义换词。
6. 不要直接剧透终极秘密，但可以点出本章已经落地的变化。
7. 若当前工作标题已经不错，可以保留或微调，但不要机械复用最近章节的结构模板。
8. title_type 可参考：结果型 / 风险型 / 关系型 / 悬念型 / 物件型 / 地点型 / 人物选择型。
9. angle 用一句短话说明这个标题抓住了哪种落点。
10. reason 用一句短话说明为什么它比空泛标题更好。
11. 只输出 JSON，对象 schema 如下：
{_pretty(TITLE_REFINEMENT_SCHEMA)}
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


__all__ = [name for name in globals() if not name.startswith("__")]
