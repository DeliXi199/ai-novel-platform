from __future__ import annotations

import json
from typing import Any, Iterable


def _tokenize_hint_text(value: Any, *, limit: int = 48) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_tokenize_hint_text(item, limit=limit))
            if len(chunks) >= limit:
                break
        return chunks[:limit]
    if isinstance(value, dict):
        chunks: list[str] = []
        for key, item in list(value.items())[:12]:
            chunks.extend(_tokenize_hint_text(key, limit=limit))
            chunks.extend(_tokenize_hint_text(item, limit=limit))
            if len(chunks) >= limit:
                break
        return chunks[:limit]
    text = str(value).strip()
    if not text:
        return []
    cleaned = text
    for token in ["，", "。", "；", "：", ",", ".", ";", ":", "（", "）", "(", ")", "、", "\n", "\t", "-", "—", "|", "/"]:
        cleaned = cleaned.replace(token, " ")
    tokens: list[str] = []
    seen: set[str] = set()
    for part in cleaned.split():
        piece = part.strip()
        if len(piece) < 2:
            continue
        if len(piece) > 18:
            piece = piece[:18]
        if piece in seen:
            continue
        seen.add(piece)
        tokens.append(piece)
        if len(tokens) >= limit:
            break
    if text and len(text) <= 18 and text not in seen:
        tokens.insert(0, text)
    return tokens[:limit]


def _priority_weight(label: Any) -> int:
    mapping = {"must": 60, "high": 32, "medium": 12, "low": 0}
    return mapping.get(str(label or "normal").strip().lower(), 8)


def soft_sort_prompt_sections(
    sections: list[dict[str, Any]] | None,
    *,
    stage: str = "",
    context: Any = None,
) -> list[dict[str, Any]]:
    payload = list(sections or [])
    if not payload:
        return []
    stage_tokens = set(_tokenize_hint_text(stage, limit=12))
    context_tokens = set(_tokenize_hint_text(context, limit=64))
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for idx, section in enumerate(payload):
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        tags = [str(item or "").strip() for item in (section.get("tags") or []) if str(item or "").strip()]
        keywords = [str(item or "").strip() for item in (section.get("keywords") or []) if str(item or "").strip()]
        stages = [str(item or "").strip() for item in (section.get("stages") or []) if str(item or "").strip()]
        body = str(section.get("body") or "").strip()
        score = float(_priority_weight(section.get("priority")))
        reasons: list[str] = []
        if stage and stage in stages:
            score += 24.0
            reasons.append("阶段匹配")
        search_text = " ".join([title, body[:120], *tags, *keywords, *stages])
        for token in stage_tokens:
            if token and token in search_text:
                score += 3.0
                if len(reasons) < 4 and "阶段词" not in reasons:
                    reasons.append("阶段词")
        hit_count = 0
        for token in context_tokens:
            if token and token in search_text:
                score += 4.0
                hit_count += 1
                if hit_count >= 4:
                    break
        if hit_count:
            reasons.append("上下文命中")
        if title.startswith("本章") or "上一章" in title:
            score += 2.0
        if section.get("priority") == "must":
            reasons.append("必带")
        ranked.append((score, idx, {**section, "soft_sort_score": round(score, 2), "soft_sort_reasons": reasons[:4]}))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]


def clip_text(value: Any, max_chars: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 12:
        return text[:max_chars]
    head = max_chars - 1
    return text[:head].rstrip() + "…"


def pick_nonempty(mapping: dict[str, Any] | None, keys: Iterable[str], *, text_limit: int = 160) -> dict[str, Any]:
    source = mapping or {}
    picked: dict[str, Any] = {}
    for key in keys:
        value = source.get(key)
        if value in (None, "", [], {}):
            continue
        picked[key] = compact_data(value, max_depth=2, max_items=6, text_limit=text_limit)
    return picked


def compact_data(value: Any, *, max_depth: int = 2, max_items: int = 6, text_limit: int = 160) -> Any:
    if value in (None, "", [], {}):
        return value
    if isinstance(value, str):
        return clip_text(value, text_limit)
    if isinstance(value, (int, float, bool)):
        return value
    if max_depth <= 0:
        if isinstance(value, dict):
            keys = [str(key) for key in list(value.keys())[:max_items]]
            return {"_keys": keys, "_count": len(value)}
        if isinstance(value, list):
            return [clip_text(item, text_limit) for item in value[:max_items]]
        return clip_text(value, text_limit)
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in list(value.items())[:max_items]:
            if item in (None, "", [], {}):
                continue
            compacted[str(key)] = compact_data(item, max_depth=max_depth - 1, max_items=max_items, text_limit=text_limit)
        if len(value) > max_items:
            compacted["_omitted_keys"] = len(value) - max_items
        return compacted
    if isinstance(value, list):
        compacted_items = [
            compact_data(item, max_depth=max_depth - 1, max_items=max_items, text_limit=text_limit)
            for item in value[:max_items]
            if item not in (None, "", [], {})
        ]
        if len(value) > max_items:
            compacted_items.append({"_omitted_items": len(value) - max_items})
        return compacted_items
    return clip_text(value, text_limit)


def compact_json(value: Any, *, max_depth: int = 2, max_items: int = 6, text_limit: int = 160) -> str:
    return json.dumps(
        compact_data(value, max_depth=max_depth, max_items=max_items, text_limit=text_limit),
        ensure_ascii=False,
        indent=2,
    )


def summarize_recent_summaries(items: list[dict[str, Any]] | None, *, limit: int = 3) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in (items or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        payload.append(
            pick_nonempty(
                item,
                [
                    "chapter_no",
                    "title",
                    "event_summary",
                    "character_shift",
                    "new_clues",
                    "open_hooks",
                    "resolved_hooks",
                    "continuity_bridge",
                ],
                text_limit=100,
            )
        )
    return payload


def summarize_story_bible(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    bible = story_bible or {}
    summary = pick_nonempty(
        bible,
        [
            "version",
            "story_engine_diagnosis",
            "story_strategy_card",
            "power_system",
            "opening_constraints",
            "planner_state",
            "retrospective_state",
            "flow_control",
            "project_card",
            "core_cast_state",
        ],
        text_limit=120,
    )
    template_library = bible.get("template_library") or {}
    if template_library:
        roadmap = template_library.get("roadmap") or {}
        summary["template_library"] = {
            "character_template_target_count": roadmap.get("character_template_target_count") or template_library.get("character_template_target_count"),
            "flow_template_target_count": roadmap.get("flow_template_target_count") or template_library.get("flow_template_target_count"),
            "payoff_card_target_count": roadmap.get("payoff_card_target_count") or template_library.get("payoff_card_target_count"),
            "scene_template_target_count": roadmap.get("scene_template_target_count") or template_library.get("scene_template_target_count"),
            "current_character_template_count": roadmap.get("current_character_template_count") or len(template_library.get("character_templates") or []),
            "current_flow_template_count": roadmap.get("current_flow_template_count") or len(template_library.get("flow_templates") or []),
            "current_payoff_card_count": roadmap.get("current_payoff_card_count") or len(template_library.get("payoff_cards") or []),
            "current_scene_template_count": roadmap.get("current_scene_template_count") or len(template_library.get("scene_templates") or []),
            "character_templates": compact_data(template_library.get("character_templates") or [], max_depth=2, max_items=8, text_limit=80),
            "flow_templates": compact_data(template_library.get("flow_templates") or [], max_depth=2, max_items=6, text_limit=80),
            "payoff_cards": compact_data(template_library.get("payoff_cards") or [], max_depth=2, max_items=5, text_limit=80),
            "scene_templates": compact_data(template_library.get("scene_templates") or [], max_depth=2, max_items=6, text_limit=80),
        }
    core_cast = bible.get("core_cast_state") or {}
    if core_cast:
        slots = []
        for item in (core_cast.get("slots") or [])[:4]:
            if not isinstance(item, dict):
                continue
            slots.append(pick_nonempty(item, ["slot_id", "entry_phase", "entry_chapter_window", "binding_pattern", "first_entry_mission", "appearance_frequency", "bound_character", "status"], text_limit=60))
        summary["core_cast_state"] = {
            "profile": core_cast.get("profile"),
            "target_count": core_cast.get("target_count"),
            "planning_basis": compact_data(core_cast.get("planning_basis"), max_depth=1, max_items=4, text_limit=60),
            "slots": slots,
        }
    latest_stage_review = (((bible.get("story_workspace") or {}).get("latest_stage_character_review")) or ((bible.get("retrospective_state") or {}).get("latest_stage_character_review")) or {})
    if latest_stage_review:
        summary["latest_stage_character_review"] = pick_nonempty(
            latest_stage_review,
            [
                "review_chapter",
                "stage_start_chapter",
                "stage_end_chapter",
                "next_window_start",
                "next_window_end",
                "focus_characters",
                "priority_relation_ids",
                "casting_strategy",
                "max_new_core_entries",
                "max_role_refreshes",
                "candidate_slot_ids",
                "should_refresh_role_functions",
                "role_refresh_targets",
                "role_refresh_suggestions",
                "next_window_tasks",
                "watchouts",
                "review_note",
            ],
            text_limit=80,
        )
    story_domains = bible.get("story_domains") or {}
    if story_domains:
        summary["story_domains"] = {
            "character_count": len((story_domains.get("characters") or {})),
            "resource_count": len((story_domains.get("resources") or {})),
            "faction_count": len((story_domains.get("factions") or {})),
            "relation_count": len((story_domains.get("relations") or [])),
        }
    return summary


def summarize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return pick_nonempty(
        payload or {},
        [
            "genre",
            "premise",
            "protagonist_name",
            "style_preferences",
            "world_setting",
            "core_conflict",
            "golden_finger",
            "opening_guidance",
        ],
        text_limit=140,
    )


def summarize_global_outline(global_outline: dict[str, Any] | None) -> dict[str, Any]:
    outline = global_outline or {}
    acts = []
    for item in (outline.get("acts") or [])[:6]:
        if not isinstance(item, dict):
            continue
        acts.append(pick_nonempty(item, ["act_no", "title", "purpose", "target_chapter_end", "summary"], text_limit=90))
    return {"story_positioning": compact_data(outline.get("story_positioning") or {}, max_depth=2, max_items=6, text_limit=100), "acts": acts}


def summarize_chapter_plan(plan: dict[str, Any] | None, *, include_packet: bool = False) -> dict[str, Any]:
    chapter = pick_nonempty(
        plan or {},
        [
            "chapter_no",
            "title",
            "chapter_type",
            "event_type",
            "progress_kind",
            "goal",
            "conflict",
            "main_scene",
            "proactive_move",
            "payoff_or_pressure",
            "payoff_mode",
            "payoff_level",
            "payoff_visibility",
            "reader_payoff",
            "new_pressure",
            "ending_hook",
            "hook_style",
            "hook_kind",
            "supporting_character_focus",
            "supporting_character_note",
            "flow_template_id",
            "flow_template_tag",
            "flow_template_name",
            "flow_turning_points",
            "flow_variation_note",
            "new_resources",
            "new_factions",
            "new_relations",
            "writing_note",
            "retry_feedback",
        ],
        text_limit=120,
    )
    if include_packet:
        packet = (plan or {}).get("planning_packet") or {}
        if packet:
            chapter["planning_packet"] = compact_data(packet, max_depth=2, max_items=8, text_limit=90)
    return chapter


def summarize_novel_context(novel_context: dict[str, Any] | None) -> dict[str, Any]:
    context = novel_context or {}
    summary = pick_nonempty(
        context,
        [
            "project_card",
            "current_volume_card",
            "protagonist_profile",
            "execution_brief",
            "hard_fact_guard",
            "workflow_runtime",
        ],
        text_limit=120,
    )
    story_memory = context.get("story_memory") or {}
    if story_memory:
        summary["story_memory"] = pick_nonempty(
            story_memory,
            [
                "project_card",
                "current_volume_card",
                "protagonist_profile",
                "execution_brief",
                "recent_retrospectives",
                "character_roster",
                "hard_fact_guard",
                "workflow_runtime",
            ],
            text_limit=100,
        )
    return summary


def summarize_interventions(active_interventions: list[dict[str, Any]] | None, *, limit: int = 4) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in (active_interventions or [])[:limit]:
        if not isinstance(item, dict):
            continue
        payload.append(pick_nonempty(item, ["instruction", "character_focus", "tone", "pace", "protected_characters", "relationship_direction"], text_limit=90))
    return payload


def summarize_candidates(candidates: list[dict[str, Any]] | None, *, limit: int = 6) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in (candidates or [])[:limit]:
        if not isinstance(item, dict):
            continue
        payload.append(compact_data(item, max_depth=2, max_items=6, text_limit=90))
    return payload


def middle_excerpt(text: str, *, max_chars: int = 1600) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    half = max_chars // 2
    return f"{raw[:half]}\n\n……（中间略）……\n\n{raw[-half:]}"


PROMPT_MODULE_LIBRARY: dict[str, dict[str, Any]] = {
    "json_only": {
        "title": "只输出 JSON",
        "summary": "只输出合法 JSON，不要 markdown 或解释。",
        "body": "只输出合法 JSON，不要输出 markdown、代码块、解释或多余前后缀。",
        "tags": ["json", "输出"]
    },
    "short_fields": {
        "title": "短字段",
        "summary": "字段尽量短，列表尽量短。",
        "body": "为了提速和省 token，请优先使用短字段、短句子、短列表；单条列表尽量控制在 2 到 4 项。",
        "tags": ["压缩", "短句"]
    },
    "continuity_bridge": {
        "title": "连续性承接",
        "summary": "优先承接上一章尾部和本章承接锚点。",
        "body": "若提供了 continuity_bridge / last_two_paragraphs / last_scene_card / unresolved_action_chain / onstage_characters，必须视为开章硬承接依据；开头两段必须优先承接它的 opening_anchor / last_two_paragraphs / unresolved_action_chain。",
        "tags": ["连续性", "承接"]
    },
    "resource_guard": {
        "title": "资源一致性",
        "summary": "资源数量、能力、代价前后一致。",
        "body": "若提供了 resource_plan / resource_capability_plan 或资源卡里的 quantity / delta_hint / ability_summary / activation_rules / usage_limits / costs，就把它们视为硬参考：资源数量、消耗、剩余量和能力边界必须前后一致。",
        "tags": ["资源", "一致性"]
    },
    "protagonist_agency": {
        "title": "主角先手",
        "summary": "主角不能只被动应对。",
        "body": "主角不能只被动应对；前两段内必须让主角先做一个可见动作或判断；本章至少出现一次完整链条：主角先手 -> 外界反应 -> 主角顺势调整或加码。",
        "tags": ["主动性", "推进"]
    },
    "visible_progress": {
        "title": "推进可感",
        "summary": "必须给出能复述的新增结果。",
        "body": "本章必须有明确推进；禁止只写气氛、顾虑、怀疑、压迫感或回忆，而不把结果落地；读完后读者应能一句话说清本章新增了什么。",
        "tags": ["推进", "结果"]
    },
    "anti_repetition": {
        "title": "反模板重复",
        "summary": "避开高频模板句和空泛钩子。",
        "body": "禁止复用上一章的开头句式、结尾句式、任务句、转折句和固定意象；不要自行把剧情锁定成“药铺-掌柜-残页-坊市-夜探”这一固定组合；禁止用“回去休息了/暂时压下念头/明日再看/夜色沉沉事情暂告一段落”这类平钩子收尾。",
        "tags": ["反重复", "避免套话"]
    },
    "character_humanization": {
        "title": "配角像人",
        "summary": "配角不是功能按钮。",
        "body": "配角不能只是抛信息的工具人；要给关键配角写出说话方式、私心、受压反应、小动作或忌讳，让他先像人，再推动情节。",
        "tags": ["人物", "配角"]
    },
    "ending_control": {
        "title": "结尾收束",
        "summary": "结尾自然闭合，不停在半句。",
        "body": "结尾必须自然收束，不能停在半句、未闭合对白或悬空判断上；是否留悬念，要服从本章 hook_style。",
        "tags": ["结尾", "闭合"]
    },
    "hard_fact_guard": {
        "title": "硬事实守卫",
        "summary": "境界、生死、伤势、身份暴露和关键物件归属要一致。",
        "body": "严格服从 hard_fact_guard；境界、生死、伤势、身份暴露和关键物件归属必须保持一致，不得擅自改写。",
        "tags": ["事实", "一致性"]
    },
}


def render_prompt_modules(
    module_ids: Iterable[str],
    *,
    include_index: bool = False,
    stage: str = "",
    context: Any = None,
) -> str:
    ids = [module_id for module_id in module_ids if module_id in PROMPT_MODULE_LIBRARY]
    if not ids:
        return ""
    ranked_sections = soft_sort_prompt_sections(
        [
            {
                **PROMPT_MODULE_LIBRARY[module_id],
                "module_id": module_id,
                "title": PROMPT_MODULE_LIBRARY[module_id]["title"],
                "body": PROMPT_MODULE_LIBRARY[module_id]["body"],
                "tags": PROMPT_MODULE_LIBRARY[module_id].get("tags") or [],
                "stages": PROMPT_MODULE_LIBRARY[module_id].get("stages") or [],
                "priority": PROMPT_MODULE_LIBRARY[module_id].get("priority") or "medium",
            }
            for module_id in ids
        ],
        stage=stage,
        context=context,
    )
    parts: list[str] = []
    if include_index:
        index = [
            {
                "module_id": item.get("module_id"),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "tags": item.get("tags") or [],
                "soft_sort_score": item.get("soft_sort_score"),
            }
            for item in ranked_sections
        ]
        parts.append("【本次生效模块索引】\n" + compact_json(index, max_depth=2, max_items=10, text_limit=80))
    body_lines = ["【本次生效模块】"]
    for item in ranked_sections:
        body_lines.append(f"- {item['title']}（{item['module_id']}）：{item['body']}")
    parts.append("\n".join(body_lines))
    return "\n\n".join(part for part in parts if part).strip()
