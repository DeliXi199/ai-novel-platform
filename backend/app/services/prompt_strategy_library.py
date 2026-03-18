from __future__ import annotations

from typing import Any

from app.services.story_blueprint_builders import build_flow_templates


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truncate(value: Any, limit: int) -> str:
    text = _text(value)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def build_prompt_strategy_library() -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": "continuity_guard",
            "name": "连续性优先",
            "summary": "优先吃掉上一章尾巴、本章承接点和最近未回收链条，先接上再推进。",
            "use_when": ["上一章尾钩很强", "本章必须同场景续接", "最近两章动作链不能断"],
            "avoid_when": ["本章本来就是全新独立任务开场"],
            "writing_directive": "开头两段先兑现 opening_anchor / unresolved_action_chain，再转入本章推进。",
        },
        {
            "strategy_id": "proactive_drive",
            "name": "主角先手",
            "summary": "把主角先手、再追一步、再逼出反应写得更硬，防止正文空转。",
            "use_when": ["本章容易写成观察与犹豫", "目标和冲突都清楚"],
            "avoid_when": ["只需要温和过渡的短收束章"],
            "writing_directive": "前两段就给主角可见动作/判断，中段受阻后必须再追一步。",
        },
        {
            "strategy_id": "relationship_pressure",
            "name": "关系推进显性化",
            "summary": "把人物来回、态度变化、试探和微妙让步写得更可感。",
            "use_when": ["本章主推进在人物关系", "需要让配角不再像工具人"],
            "avoid_when": ["纯资源任务或纯战斗爆发章"],
            "writing_directive": "重点关系至少出现一次具体来回：试探、让步、误判、互惠、戒备或撕裂。",
        },
        {
            "strategy_id": "resource_precision",
            "name": "资源与能力精确化",
            "summary": "把资源数量、代价、能力边界写实，避免万能外挂味。",
            "use_when": ["本章会动用关键资源或能力", "资源变化本身是推进结果"],
            "avoid_when": ["资源只是背景陪衬"],
            "writing_directive": "资源的获得、消耗、限制、冷却和代价都要在正文里交代清楚。",
        },
        {
            "strategy_id": "payoff_delivery",
            "name": "爽点落袋",
            "summary": "把回报、显影和后患写成完整链条，不只做情绪预热。",
            "use_when": ["本章有明确 payoff card", "最近两章欠账偏多"],
            "avoid_when": ["本章就是刻意压低输出的蓄压章"],
            "writing_directive": "至少兑现一次 reader_payoff -> external_reaction -> new_pressure/aftershock 的完整链条。",
        },
        {
            "strategy_id": "mystery_probe",
            "name": "谜团试探",
            "summary": "用验证、试错、旁人反应和异常细节自然补设定与线索。",
            "use_when": ["本章要补世界/势力/等级信息", "发现线索比硬说明更重要"],
            "avoid_when": ["这章主要是正面冲突和爆发"],
            "writing_directive": "通过试探、交易、受挫或旁人评价自然补信息，不写成说明书。",
        },
        {
            "strategy_id": "danger_pressure",
            "name": "压力逼近",
            "summary": "让风险、盯梢、代价和暴露感逐步压近，结尾留下可追的后患。",
            "use_when": ["hook_style 偏危险逼近/反转下压", "本章需要收强钩"],
            "avoid_when": ["本章应以清晰收束和小胜落袋为主"],
            "writing_directive": "结尾要把压力写成具体变化，而不是空泛不安。",
        },
        {
            "strategy_id": "scene_compactness",
            "name": "场景紧凑",
            "summary": "减少无效切场，把一两个场景写扎实，让结果更集中。",
            "use_when": ["本章目标单一", "最近容易写散"],
            "avoid_when": ["本章必须跨两三段场景推进"],
            "writing_directive": "每次切场前先给阶段结果或明确的时间/地点/动作过渡。",
        },
    ]


def build_prompt_strategy_index() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in build_prompt_strategy_library():
        summary = _truncate(item.get("summary"), 72)
        use_when = [_truncate(value, 24) for value in (item.get("use_when") or [])[:3]]
        avoid_when = [_truncate(value, 24) for value in (item.get("avoid_when") or [])[:2]]
        payload.append(
            {
                "strategy_id": _text(item.get("strategy_id")),
                "type": "prompt_strategy",
                "title": _text(item.get("name")),
                "name": _text(item.get("name")),
                "summary": summary,
                "chapter_use": "；".join(use_when[:2]) if use_when else summary,
                "constraint": "；".join(avoid_when[:2]),
                "priority_hint": "medium",
                "use_when": use_when,
                "avoid_when": avoid_when,
                "writing_directive": _truncate(item.get("writing_directive"), 88),
            }
        )
    return payload


def build_flow_template_index(story_bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    template_library = (story_bible or {}).get("template_library") or {}
    flow_templates = template_library.get("flow_templates") or []
    source = [item for item in flow_templates if isinstance(item, dict) and _text(item.get("flow_id"))] or build_flow_templates()
    payload: list[dict[str, Any]] = []
    for item in source:
        when_to_use = _truncate(item.get("when_to_use"), 56)
        variation = _truncate(item.get("variation_notes"), 72)
        payload.append(
            {
                "flow_id": _text(item.get("flow_id")),
                "type": "flow_template",
                "title": _truncate(item.get("name"), 20),
                "quick_tag": _truncate(item.get("quick_tag"), 12),
                "name": _truncate(item.get("name"), 20),
                "family": _truncate(item.get("family"), 12),
                "summary": when_to_use,
                "chapter_use": when_to_use,
                "constraint": variation,
                "priority_hint": "medium",
                "when_to_use": when_to_use,
                "preferred_event_types": [_truncate(value, 12) for value in (item.get("preferred_event_types") or [])[:3]],
                "preferred_progress_kinds": [_truncate(value, 12) for value in (item.get("preferred_progress_kinds") or [])[:3]],
                "preferred_hook_styles": [_truncate(value, 12) for value in (item.get("preferred_hook_styles") or [])[:2]],
                "turning_points": [_truncate(value, 22) for value in (item.get("turning_points") or [])[:3]],
                "variation_notes": variation,
            }
        )
    return payload


def build_prompt_bundle_index(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "flow_templates": build_flow_template_index(story_bible),
        "prompt_strategies": build_prompt_strategy_index(),
    }


def apply_prompt_strategy_selection_to_packet(
    packet: dict[str, Any],
    selected_strategy_ids: list[str] | None,
    *,
    selected_flow_template_id: str | None = None,
    selection_note: str | None = None,
) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return packet
    ordered_ids = [str(item or "").strip() for item in (selected_strategy_ids or []) if str(item or "").strip()]
    clean_flow_id = _text(selected_flow_template_id)
    if not ordered_ids and not clean_flow_id:
        packet["prompt_selection"] = {
            "selected_flow_template_id": None,
            "selected_strategy_ids": [],
            "selection_note": _truncate(selection_note, 96),
        }
        packet["selected_prompt_strategies"] = []
        return packet

    library = {item["strategy_id"]: item for item in build_prompt_strategy_library() if _text(item.get("strategy_id"))}
    selected = [library[item] for item in ordered_ids if item in library]
    packet["prompt_selection"] = {
        "selected_flow_template_id": clean_flow_id or None,
        "selected_strategy_ids": ordered_ids,
        "selection_note": _truncate(selection_note, 96),
    }
    packet["selected_prompt_strategies"] = selected[:4]

    flow_index = {item["flow_id"]: item for item in (packet.get("flow_template_index") or []) if _text(item.get("flow_id"))}
    selected_flow = flow_index.get(clean_flow_id) if clean_flow_id else None
    if selected_flow:
        packet["selected_flow_template"] = selected_flow
        chapter_identity = packet.setdefault("chapter_identity", {})
        flow_plan = packet.setdefault("flow_plan", {})
        chapter_identity["flow_template_id"] = _text(selected_flow.get("flow_id"))
        chapter_identity["flow_template_tag"] = _text(selected_flow.get("quick_tag"))
        chapter_identity["flow_template_name"] = _text(selected_flow.get("name"))
        flow_plan["flow_template_id"] = _text(selected_flow.get("flow_id"))
        flow_plan["flow_template_tag"] = _text(selected_flow.get("quick_tag"))
        flow_plan["flow_template_name"] = _text(selected_flow.get("name"))
        flow_plan["turning_points"] = list(selected_flow.get("turning_points") or [])[:3]
        flow_plan["variation_note"] = _truncate(selected_flow.get("variation_notes"), 72)

    input_policy = packet.setdefault("input_policy", {})
    input_policy["prompt_selection_rule"] = "AI 先从 prompt_bundle_index 里选定本章流程模板和 prompt 策略，再把这些写法插入正文生成提示。"
    return packet
