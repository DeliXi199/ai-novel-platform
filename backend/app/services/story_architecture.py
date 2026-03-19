from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.character import Character
from app.models.monster import Monster
from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.generation_exceptions import GenerationError
from app.services.hard_fact_guard import (
    compact_hard_fact_guard,
    ensure_hard_fact_guard,
)
from app.services.importance_evaluator import evaluate_story_elements_importance
from app.services.llm_runtime import call_json_response
from app.services.payoff_compensation_support import payoff_window_event_bias
from app.services.prompt_templates_execution import (
    chapter_execution_structure_system_prompt,
    chapter_execution_structure_user_prompt,
)
from app.services.story_blueprint_builders import (
    _default_cultivation_system,
    _default_world_bible,
    _endgame_direction,
    _golden_finger,
    _mid_term_direction,
    _one_line_intro,
    _sell_line,
    _target_end,
    build_arc_digest,
    build_story_workspace,
    build_core_cast_state_payload,
    build_entity_registry,
    build_flow_control,
    build_opening_constraints,
    build_planner_state,
    build_power_system,
    build_project_card,
    build_retrospective_state,
    build_story_domains,
    build_template_library,
    build_volume_cards,
)
from app.services.resource_card_support import apply_resource_capability_plan, apply_resource_plan, build_resource_card, ensure_resource_card_structure, infer_resource_quality, normalize_resource_refs
from app.services.monster_card_support import build_monster_card, ensure_monster_card_structure
from app.services.story_character_support import (
    _build_chapter_retrospective,
    _character_voice_pack,
    _recent_retrospective_feedback,
    _safe_list,
    _supporting_voice_template,
    _text,
    apply_character_template_defaults,
    pick_character_template,
)
from app.services.story_fact_ledger import (
    _compact_fact_text,
    _now_iso,
    promote_stock_fact_entries,
    record_chapter_fact_entries,
)
from app.services.core_cast_support import (
    bind_character_to_core_slot,
    core_cast_guidance_for_chapter,
    materialize_anchored_core_cast,
    update_core_cast_after_chapter,
)
from app.services.character_schedule_support import update_character_relation_schedule_after_chapter
from app.services.stage_review_support import (
    apply_role_refresh_execution,
    build_chapter_casting_runtime_summary,
    record_stage_casting_resolution,
    stage_character_review_for_window,
    summarize_arc_casting_layout_review,
)
from app.services.story_runtime_support import (
    DEFAULT_SERIAL_DELIVERY_MODE,
    _build_initialization_packet,
    _current_volume_card,
    ensure_story_bible_v2_structure,
    build_serial_rules,
    set_delivery_mode,
    sync_long_term_state,
)
from app.services.story_state import (
    ensure_story_workspace,
    ensure_planning_layers,
    ensure_serial_runtime,
    ensure_story_state_domains,
    ensure_workflow_state,
    update_story_state_bucket,
)

DEFAULT_CONTINUITY_RULES = [
    "主角每章都要有行动、判断、试探、隐藏或反击，不能整章只被剧情推着走。",
    "每章都要有新变化：得到信息、失去退路、关系变化、暴露风险或世界认知升级。",
    "最近两章若已经用了同类桥段，下一章必须换事件类型，不能连续三章都在同一结构里打转。",
    "如果时间跨度超过一天，开头两段必须写明过渡。",
    "章末要么留下拉力，要么自然收在结果落地与人物选择上，不能停在半句。",
]


KNOWN_GENERIC_EXECUTION_LINES = {
    "开场先落在一个具体动作或眼前小异常上。",
    "中段加入一次受阻、遮掩或判断失误，让场面真正动起来。",
    "给出一个具体而可感的发现，推动本章信息增量。",
    "结尾收在一个可见可感的画面上，而不是抽象总结。",
}


def _book_execution_profile_payload(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    payload = (story_bible or {}).get("book_execution_profile") or {}
    return payload if isinstance(payload, dict) else {}


def _card_system_profile(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    payload = (story_bible or {}).get("card_system_profile") or {}
    if isinstance(payload, dict) and payload:
        return payload
    return {
        "version": "card_layers_v1",
        "template_cards": [
            "character_templates",
            "flow_templates",
            "scene_templates",
            "payoff_cards",
            "foreshadowing_parent_cards",
            "foreshadowing_child_cards",
            "writing_strategy_cards",
        ],
        "book_level_cards": [
            "project_card",
            "volume_cards",
            "active_arc",
            "pending_arc",
            "chapter_card_queue",
            "book_execution_profile",
            "window_execution_bias",
        ],
        "chapter_execution_cards": [
            "chapter_plan",
            "planning_packet",
            "chapter_execution_card",
            "selected_payoff_card",
            "selected_foreshadowing_instance_cards",
            "selected_writing_cards",
            "scene_execution_card",
        ],
        "runtime_state_cards": [
            "cast_cards",
            "monster_cards",
            "relationship_journal",
            "foreshadowing",
            "recent_progress",
            "chapter_retrospectives",
            "daily_workbench",
            "execution_packet_history",
            "power_progress_journal",
        ],
        "governance": {
            "template_cards_are_library_only": True,
            "book_level_cards_are_bootstrap_and_window_planning_outputs": True,
            "chapter_execution_cards_are_per_chapter_outputs": True,
            "runtime_state_cards_are_post_chapter_updates": True,
        },
    }


def _match_priority_terms(choices: list[str], source_text: str) -> list[str]:
    lowered = source_text.lower()
    hits: list[str] = []
    for item in choices:
        token = _text(item)
        if token and token.lower() in lowered and token not in hits:
            hits.append(token)
    return hits


def _derive_window_execution_bias(story_bible: dict[str, Any], current_chapter_no: int = 0) -> dict[str, Any]:
    workspace_state = ensure_story_workspace(story_bible)
    queue = [item for item in (workspace_state.get("chapter_card_queue") or []) if isinstance(item, dict)]
    next_items = queue[:3]
    profile = _book_execution_profile_payload(story_bible)
    recent_retrospectives = [item for item in (workspace_state.get("chapter_retrospectives") or [])[-2:] if isinstance(item, dict)]
    pending = ((story_bible.get("retrospective_state") or {}).get("pending_payoff_compensation") or {})
    active_arc = story_bible.get("active_arc") or {}

    text_blob = " ".join(
        _text(item.get("goal")) + " " + _text(item.get("conflict")) + " " + _text(item.get("ending_hook")) + " " + _text(item.get("event_type"))
        for item in next_items
    )
    next_no = int((next_items[0].get("chapter_no", 0) if next_items else current_chapter_no + 1) or (current_chapter_no + 1))
    has_compensation = bool(pending) and int(pending.get("target_chapter_no", 0) or 0) == next_no
    near_arc_end = bool(active_arc) and int(active_arc.get("end_chapter", 0) or 0) <= next_no + 1
    if has_compensation:
        window_mode = "repay"
    elif near_arc_end or any(token in text_blob for token in ["回收", "收束", "翻面", "真相", "揭开"]):
        window_mode = "reveal"
    else:
        window_mode = "probe"

    flow_priority = profile.get("flow_family_priority") or {}
    payoff_priority = profile.get("payoff_priority") or {}
    foreshadow_priority = profile.get("foreshadowing_priority") or {}
    writing_priority = profile.get("writing_strategy_priority") or {}
    rhythm = dict(profile.get("rhythm_bias") or {})

    flow_high = list((flow_priority.get("high") or []))[:4]
    payoff_high = list((payoff_priority.get("high") or []))[:4]
    foreshadow_primary = list((foreshadow_priority.get("primary") or []))[:4]
    writing_high = list((writing_priority.get("high") or []))[:4]

    corrections = [_text(item.get("next_chapter_correction")) for item in recent_retrospectives if _text(item.get("next_chapter_correction"))]
    if has_compensation:
        corrections.insert(0, _text(pending.get("note") or pending.get("reason"), "这一章优先补一次明确兑现。"))

    if window_mode == "repay":
        boosted_flows = _match_priority_terms(flow_high, text_blob) or flow_high[:2]
        boosted_payoffs = payoff_high[:3]
        boosted_foreshadowing = []
        boosted_writing = _match_priority_terms(writing_high, "aftermath_binding goal_chain_clarity payoff_delivery") or writing_high[:2]
        rhythm["payoff_interval"] = "短"
        rhythm["hook_strength"] = _text(rhythm.get("hook_strength"), "中强")
        directive = "本窗口优先追回一次明确回报，并把余波与后患写出来。"
    elif window_mode == "reveal":
        boosted_flows = _match_priority_terms(flow_high, text_blob) or flow_high[:2]
        boosted_payoffs = payoff_high[:2]
        boosted_foreshadowing = foreshadow_primary[:3]
        boosted_writing = _match_priority_terms(writing_high, "danger_pressure evidence_density mystery_probe") or writing_high[:2]
        rhythm["hook_strength"] = "强"
        directive = "本窗口更适合抬升发现、验证、显影或回收，不要把章法写平。"
    else:
        boosted_flows = _match_priority_terms(flow_high, text_blob) or flow_high[:3]
        boosted_payoffs = payoff_high[:2]
        boosted_foreshadowing = foreshadow_primary[:2]
        boosted_writing = _match_priority_terms(writing_high, "proactive_drive danger_pressure goal_chain_clarity") or writing_high[:2]
        directive = "本窗口优先试探、验证、压强渐增，保持主角先手。"

    return {
        "source": "arc_window_refresh",
        "window_mode": window_mode,
        "current_arc_no": int(active_arc.get("arc_no", 0) or 0),
        "current_arc_focus": _text(active_arc.get("focus")),
        "directive": directive,
        "boosted_flow_families": boosted_flows[:4],
        "boosted_payoffs": boosted_payoffs[:4],
        "boosted_foreshadowing": boosted_foreshadowing[:4],
        "boosted_writing_strategies": boosted_writing[:4],
        "rhythm_adjustments": {
            "opening_pace": _text(rhythm.get("opening_pace")),
            "hook_strength": _text(rhythm.get("hook_strength")),
            "payoff_interval": _text(rhythm.get("payoff_interval")),
            "pressure_curve": _text(rhythm.get("pressure_curve")),
        },
        "recent_corrections": corrections[:3],
        "target_chapters": [int(item.get("chapter_no", 0) or 0) for item in next_items[:3]],
        "summary_lines": [
            f"窗口模式：{window_mode}",
            f"流程倾向：{' / '.join(boosted_flows[:3]) or '沿用书级高优先流程'}",
            f"兑现/伏笔：{' / '.join((boosted_payoffs[:2] or boosted_foreshadowing[:2])) or '按当前主线推进'}",
            directive,
        ],
    }


def _normalize_match_text(value: Any) -> str:
    return str(value or "").strip().replace("\r", "").replace("\n", "")


def _is_generic_execution_text(value: Any) -> bool:
    text = _normalize_match_text(value)
    if not text:
        return True
    return any(snippet and snippet in text for snippet in KNOWN_GENERIC_EXECUTION_LINES)


def _pick_specific_text(*candidates: Any) -> str:
    for item in candidates:
        text = _text(item)
        if text and not _is_generic_execution_text(text):
            return text
    for item in candidates:
        text = _text(item)
        if text:
            return text
    return ""


def _contextual_execution_fallback(*, plan: dict[str, Any], scene_execution_card: dict[str, Any], scene_outline: list[dict[str, Any]], last_chapter_tail: str, today_function: str, change_line: str) -> dict[str, str]:
    first_scene = scene_outline[0] if scene_outline else {}
    middle_scene = scene_outline[1] if len(scene_outline) > 1 else {}
    last_scene = scene_outline[-1] if scene_outline else {}
    return {
        "chapter_function": _pick_specific_text(plan.get("goal"), today_function),
        "chapter_change": _pick_specific_text(plan.get("discovery"), plan.get("conflict"), change_line),
        "opening": _pick_specific_text(
            plan.get("opening_beat"),
            scene_execution_card.get("opening_anchor"),
            first_scene.get("transition_in"),
            first_scene.get("purpose"),
            plan.get("main_scene"),
            plan.get("goal"),
            last_chapter_tail,
        ),
        "middle": _pick_specific_text(
            plan.get("mid_turn"),
            middle_scene.get("purpose"),
            middle_scene.get("target_result"),
            plan.get("conflict"),
            plan.get("payoff_or_pressure"),
            plan.get("discovery"),
        ),
        "ending": _pick_specific_text(
            plan.get("closing_image"),
            last_scene.get("target_result"),
            last_scene.get("purpose"),
            plan.get("ending_hook"),
            plan.get("payoff_or_pressure"),
            change_line,
        ),
        "chapter_hook": _pick_specific_text(plan.get("ending_hook"), plan.get("closing_image"), change_line),
        "reason": "fallback",
        "structure_source": "contextual_fallback",
    }


def _resolve_execution_structure(*, story_bible: dict[str, Any], next_chapter_no: int, plan: dict[str, Any], last_chapter_tail: str, scene_execution_card: dict[str, Any], scene_outline: list[dict[str, Any]], today_function: str, change_line: str) -> dict[str, str]:
    fallback = _contextual_execution_fallback(
        plan=plan,
        scene_execution_card=scene_execution_card,
        scene_outline=scene_outline,
        last_chapter_tail=last_chapter_tail,
        today_function=today_function,
        change_line=change_line,
    )
    cached = (plan.get("execution_structure_card") or {}) if isinstance(plan, dict) else {}
    if isinstance(cached, dict) and any(_text(cached.get(key)) for key in ["opening", "middle", "ending"]):
        resolved = {**fallback, **{key: _text(cached.get(key)) for key in ["chapter_function", "chapter_change", "opening", "middle", "ending", "chapter_hook", "reason", "structure_source"] if _text(cached.get(key))}}
        return resolved

    if not bool(getattr(settings, "execution_card_ai_enabled", True)):
        if isinstance(plan, dict):
            plan["execution_structure_card"] = dict(fallback)
        return fallback

    payload = {
        "chapter_no": int(next_chapter_no or 0),
        "project_card": _compact_value(story_bible.get("project_card") or {}, text_limit=88),
        "current_volume_card": _compact_value(_current_volume_card(story_bible, next_chapter_no), text_limit=88),
        "chapter_plan": _compact_value({
            key: plan.get(key)
            for key in [
                "chapter_no", "title", "goal", "conflict", "main_scene", "event_type", "progress_kind",
                "supporting_character_focus", "supporting_character_note", "opening_beat", "mid_turn",
                "discovery", "closing_image", "ending_hook", "proactive_move", "payoff_or_pressure",
            ]
            if plan.get(key) not in (None, "", [], {})
        }, text_limit=96),
        "scene_execution_card": _compact_value(scene_execution_card or {}, text_limit=88),
        "scene_outline": _compact_value(scene_outline or [], text_limit=88),
        "last_chapter_tail": _truncate_text(last_chapter_tail, 220),
        "base_function": today_function,
        "base_change": change_line,
    }
    try:
        data = call_json_response(
            stage="chapter_execution_structure",
            system_prompt=chapter_execution_structure_system_prompt(),
            user_prompt=chapter_execution_structure_user_prompt(payload=payload),
            max_output_tokens=max(int(getattr(settings, "execution_card_ai_max_output_tokens", 520) or 520), 260),
            timeout_seconds=max(int(getattr(settings, "execution_card_ai_timeout_seconds", 24) or 24), 12),
        )
    except GenerationError as exc:
        if bool(getattr(settings, "execution_card_ai_soft_fail_enabled", True)) and bool(getattr(exc, "retryable", False)):
            fallback["structure_source"] = "contextual_fallback_after_ai_soft_fail"
            if isinstance(plan, dict):
                plan["execution_structure_card"] = dict(fallback)
                details = dict(getattr(exc, "details", {}) or {})
                plan["execution_structure_runtime"] = {
                    "status": "soft_failed",
                    "stage": str(getattr(exc, "stage", "chapter_execution_structure") or "chapter_execution_structure"),
                    "code": str(getattr(exc, "code", "") or ""),
                    "retryable": bool(getattr(exc, "retryable", False)),
                    "trace_id": _text(details.get("trace_id")),
                    "message": _truncate_text(str(getattr(exc, "message", "") or str(exc)), 180),
                }
            return fallback
        raise

    resolved = {
        "chapter_function": _pick_specific_text(data.get("chapter_function"), fallback.get("chapter_function")),
        "chapter_change": _pick_specific_text(data.get("chapter_change"), fallback.get("chapter_change")),
        "opening": _pick_specific_text(data.get("opening"), fallback.get("opening")),
        "middle": _pick_specific_text(data.get("middle"), fallback.get("middle")),
        "ending": _pick_specific_text(data.get("ending"), fallback.get("ending")),
        "chapter_hook": _pick_specific_text(data.get("chapter_hook"), fallback.get("chapter_hook")),
        "reason": _text(data.get("reason")),
        "structure_source": "ai",
    }
    if isinstance(plan, dict):
        plan["execution_structure_card"] = dict(resolved)
        plan["execution_structure_runtime"] = {
            "status": "success",
            "source": "ai",
            "reason": _text(data.get("reason")),
        }
    return resolved



def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


def _compact_value(value: Any, *, text_limit: int = 60) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, text_limit=text_limit) for item in value[:6]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 8:
                break
            compact[str(key)] = _compact_value(item, text_limit=text_limit)
        return compact
    return _truncate_text(value, text_limit)



def _clone_execution_packet(
    execution_brief: dict[str, Any] | None,
    *,
    chapter_no: int,
    packet_phase: str,
) -> dict[str, Any]:
    packet = deepcopy(execution_brief or {})
    packet["for_chapter_no"] = int(chapter_no or 0)
    packet["packet_phase"] = _text(packet.get("packet_phase"), packet_phase)
    packet["packet_label"] = _text(packet.get("packet_label"), f"第{int(chapter_no or 0)}章执行意图卡")
    chapter_card = packet.setdefault("chapter_execution_card", {})
    if isinstance(chapter_card, dict):
        chapter_card.setdefault("for_chapter_no", int(chapter_no or 0))
        chapter_card.setdefault("packet_phase", _text(packet.get("packet_phase"), packet_phase))
    daily = packet.setdefault("daily_workbench", {})
    if isinstance(daily, dict):
        daily["for_chapter_no"] = int(chapter_no or 0)
        daily["packet_phase"] = _text(packet.get("packet_phase"), packet_phase)
    return packet


def _paragraphs(text: Any) -> list[str]:
    raw = str(text or "")
    lines = [part.strip() for part in raw.replace("\r", "").split("\n")]
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                blocks.append("".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("".join(current).strip())
    return [item for item in blocks if item]


def build_realized_scene_report(
    *,
    chapter_no: int,
    chapter_title: str,
    plan: dict[str, Any] | None,
    summary: Any,
    content: str,
    execution_packet: dict[str, Any] | None = None,
    scene_handoff_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = execution_packet if isinstance(execution_packet, dict) else {}
    planned_outline = [
        {
            "scene_no": int(item.get("scene_no", index + 1) or (index + 1)),
            "scene_name": _text(item.get("scene_name"), "未命名场景"),
            "scene_role": _text(item.get("scene_role")),
            "purpose": _text(item.get("purpose")),
        }
        for index, item in enumerate((packet.get("scene_outline") or [])[:3])
        if isinstance(item, dict)
    ]
    paragraphs = _paragraphs(content)
    first_para = _truncate_text(paragraphs[0] if paragraphs else content, 120)
    last_para = _truncate_text(paragraphs[-1] if paragraphs else content, 120)
    event_summary = _text(getattr(summary, "event_summary", None), _text((plan or {}).get("goal"), "本章完成一次推进。"))
    new_clues = [_text(item) for item in (getattr(summary, "new_clues", None) or []) if _text(item)][:3]
    open_hooks = [_text(item) for item in (getattr(summary, "open_hooks", None) or []) if _text(item)][:3]
    closed_hooks = [_text(item) for item in (getattr(summary, "closed_hooks", None) or []) if _text(item)][:3]
    actual_slots = [
        {
            "slot": "opening",
            "planned": _text((plan or {}).get("opening_beat"), _text((planned_outline[0] if planned_outline else {}).get("purpose"))),
            "actual": first_para,
        },
        {
            "slot": "middle",
            "planned": _text((plan or {}).get("mid_turn"), _text((planned_outline[1] if len(planned_outline) >= 2 else {}).get("purpose"))),
            "actual": _truncate_text(event_summary, 120),
        },
        {
            "slot": "ending",
            "planned": _text((plan or {}).get("closing_image") or (plan or {}).get("ending_hook"), _text((planned_outline[2] if len(planned_outline) >= 3 else {}).get("purpose"))),
            "actual": last_para,
        },
    ]
    preview_lines = [
        f"第{int(chapter_no or 0)}章《{_text(chapter_title, '未命名章节')}》",
        f"实绩摘要：{event_summary}",
    ]
    if first_para:
        preview_lines.append(f"正文开场：{first_para}")
    if last_para:
        preview_lines.append(f"正文收束：{last_para}")
    if new_clues:
        preview_lines.append(f"新增线索：{'、'.join(new_clues)}")
    if open_hooks:
        preview_lines.append(f"未回收点：{'、'.join(open_hooks)}")
    if closed_hooks:
        preview_lines.append(f"已回收点：{'、'.join(closed_hooks)}")
    handoff = scene_handoff_card if isinstance(scene_handoff_card, dict) else {}
    return {
        "chapter_no": int(chapter_no or 0),
        "chapter_title": _text(chapter_title),
        "report_phase": "realized",
        "event_summary": event_summary,
        "planned_scene_outline": planned_outline,
        "actual_scene_slots": actual_slots,
        "new_clues": new_clues,
        "open_hooks": open_hooks,
        "closed_hooks": closed_hooks,
        "handoff_hint": {
            "scene_status_at_end": _text(handoff.get("scene_status_at_end")),
            "must_continue_same_scene": bool(handoff.get("must_continue_same_scene")),
            "next_opening_anchor": _text(handoff.get("next_opening_anchor")),
        },
        "preview_lines": preview_lines[:6],
    }


def prepare_story_workspace_for_chapter_entry(
    story_bible: dict[str, Any],
    *,
    next_chapter_no: int,
) -> dict[str, Any]:
    story_bible = ensure_story_state_domains(story_bible)
    workspace_state = ensure_story_workspace(story_bible)
    current_packet = workspace_state.get("current_execution_packet") if isinstance(workspace_state.get("current_execution_packet"), dict) else {}
    current_target = int(current_packet.get("for_chapter_no", 0) or 0)
    if current_packet and current_target and current_target != int(next_chapter_no or 0):
        stale_packet = deepcopy(current_packet)
        stale_packet["packet_phase"] = "stale_cleared"
        stale_packet["resolved_for_chapter_no"] = int(next_chapter_no or 0)
        workspace_state["last_completed_execution_packet"] = stale_packet
        history = workspace_state.setdefault("execution_packet_history", [])
        history.append({
            "chapter_no": current_target,
            "packet_phase": "stale_cleared",
            "chapter_function": _text(((stale_packet.get("chapter_execution_card") or {}).get("chapter_function"))),
        })
        workspace_state["execution_packet_history"] = history[-8:]
        workspace_state.pop("current_execution_packet", None)
    workspace_state["entry_target_chapter_no"] = int(next_chapter_no or 0)
    story_bible["story_workspace"] = workspace_state
    return story_bible

DEFAULT_STRICT_PIPELINE = [
    "定位",
    "读状态",
    "章纲",
    "场景",
    "正文",
    "检查",
    "摘要",
    "状态更新",
    "发布状态标记",
    "下一章入口",
]



def _chapter_cards_from_arc(arc: dict[str, Any] | None) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if not arc:
        return queue
    for chapter in _safe_list(arc.get("chapters")):
        queue.append(
            {
                "chapter_no": int(chapter.get("chapter_no", 0) or 0),
                "title": _text(chapter.get("title"), ""),
                "goal": _text(chapter.get("goal"), "推进当前主线"),
                "chapter_type": _text(chapter.get("chapter_type"), "progress"),
                "progress_kind": _text(chapter.get("progress_kind"), ""),
                "payoff_or_pressure": _text(chapter.get("payoff_or_pressure"), ""),
                "payoff_mode": _text(chapter.get("payoff_mode"), ""),
                "hook_style": _text(chapter.get("hook_style"), ""),
                "opening": _text(chapter.get("opening_beat"), ""),
                "middle": _text(chapter.get("mid_turn"), ""),
                "ending": _text(chapter.get("closing_image") or chapter.get("ending_hook"), ""),
                "hook": _text(chapter.get("ending_hook"), ""),
                "stage_casting_action": _text(chapter.get("stage_casting_action"), ""),
                "stage_casting_target": _text(chapter.get("stage_casting_target"), ""),
                "stage_casting_note": _text(chapter.get("stage_casting_note") or chapter.get("stage_casting_review_note"), ""),
                "stage_casting_review_note": _text(chapter.get("stage_casting_review_note"), ""),
            }
        )
    return queue


def _workflow_state_from_arc(first_arc: dict[str, Any] | None) -> dict[str, Any]:
    planned_until = int((first_arc or {}).get("end_chapter", 0) or 0)
    return {
        "mode": "document_first_strict_pipeline",
        "init_generates_chapters": False,
        "strict_pipeline": list(DEFAULT_STRICT_PIPELINE),
        "strict_pipeline_internal": [
            "project_card",
            "current_volume_card",
            "near_outline",
            "chapter_execution_card",
            "chapter_scene_outline",
            "chapter_draft",
            "quality_check",
            "summary_and_review",
            "publish_mark",
            "next_entry",
        ],
        "bootstrap_documents_ready": True,
        "bootstrap_generated_chapter_cards_until": planned_until,
        "current_pipeline": {
            "target_chapter_no": 1,
            "project_card_ready": True,
            "current_volume_ready": True,
            "near_outline_ready": planned_until > 0,
            "chapter_card_ready": planned_until > 0,
            "draft_ready": False,
            "summary_review_ready": False,
            "last_completed_stage": "bootstrap_documents",
            "last_completed_chapter_no": 0,
        },
    }




def _deep_fill_missing(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        existing = target.get(key)
        if key not in target or existing is None or existing == "" or existing == []:
            target[key] = deepcopy(value)
            continue
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_fill_missing(existing, value)
    return target



def _merge_character_template_library(existing: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_fill_missing(existing or {}, built or {})
    built_templates = (built.get("character_templates") or []) if isinstance(built, dict) else []
    current_templates = (merged.get("character_templates") or []) if isinstance(merged, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in built_templates:
        if isinstance(item, dict):
            template_id = _text(item.get("template_id"))
            if template_id:
                by_id[template_id] = deepcopy(item)
    for item in current_templates:
        if isinstance(item, dict):
            template_id = _text(item.get("template_id"))
            if template_id:
                base = by_id.get(template_id, {})
                merged_item = deepcopy(item)
                if isinstance(base, dict):
                    _deep_fill_missing(merged_item, base)
                by_id[template_id] = merged_item
    merged["character_templates"] = list(by_id.values()) or built_templates
    roadmap = merged.setdefault("roadmap", {})
    built_roadmap = (built.get("roadmap") or {}) if isinstance(built, dict) else {}
    _deep_fill_missing(roadmap, built_roadmap)
    roadmap["current_character_template_count"] = len(merged.get("character_templates") or [])
    roadmap["current_flow_template_count"] = len(merged.get("flow_templates") or [])
    roadmap["current_payoff_card_count"] = len(merged.get("payoff_cards") or [])
    roadmap["current_scene_template_count"] = len(merged.get("scene_templates") or [])
    return merged



def _upgrade_opening_constraints(existing: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    payload = _deep_fill_missing(existing or {}, built or {})
    payload["opening_phase_chapter_range"] = [1, 20]
    background_delivery = payload.setdefault("background_delivery", {})
    built_background = (built.get("background_delivery") or {}) if isinstance(built, dict) else {}
    for key, value in built_background.items():
        current = _text(background_delivery.get(key))
        if not current or current.startswith("前15章内") or current.startswith("前15章以内"):
            background_delivery[key] = value
    pace_rules = payload.setdefault("pace_rules", {})
    built_pace = (built.get("pace_rules") or {}) if isinstance(built, dict) else {}
    if not _text(pace_rules.get("first_three_chapters")):
        pace_rules["first_three_chapters"] = built_pace.get("first_three_chapters")
    if not _text(pace_rules.get("first_fifteen_chapters")):
        pace_rules["first_fifteen_chapters"] = built_pace.get("first_fifteen_chapters")
    if not _text(pace_rules.get("first_twenty_chapters")) or _text(pace_rules.get("first_twenty_chapters")).startswith("前15章"):
        pace_rules["first_twenty_chapters"] = built_pace.get("first_twenty_chapters")
    if not payload.get("foundation_reveal_schedule"):
        payload["foundation_reveal_schedule"] = deepcopy((built.get("foundation_reveal_schedule") or []) if isinstance(built, dict) else [])
    if not payload.get("power_system_reveal_plan"):
        payload["power_system_reveal_plan"] = deepcopy((built.get("power_system_reveal_plan") or []) if isinstance(built, dict) else [])
    return payload


def _rebuild_entity_registry(story_bible: dict[str, Any]) -> None:
    domains = story_bible.setdefault("story_domains", {})
    registry = story_bible.setdefault("entity_registry", build_entity_registry())
    by_type = registry.setdefault("by_type", {})
    by_type["character"] = list((domains.get("characters") or {}).keys())
    by_type["resource"] = list((domains.get("resources") or {}).keys())
    by_type["relation"] = list((domains.get("relations") or {}).keys())
    by_type["faction"] = list((domains.get("factions") or {}).keys())



def _upsert_story_domain_character(domains: dict[str, Any], *, protagonist_name: str, name: str, source: dict[str, Any]) -> None:
    if not name:
        return
    characters = domains.setdefault("characters", {})
    current = characters.get(name, {}) if isinstance(characters, dict) else {}
    role_type = _text(source.get("role_type"), "protagonist" if name == protagonist_name else "supporting")
    camp = _text(source.get("camp"), "主角阵营" if name == protagonist_name else "待观察")
    defaults = {
        "name": name,
        "entity_type": "character",
        "role_type": role_type,
        "importance_tier": "核心主角" if name == protagonist_name else _text(source.get("importance_tier"), "重要配角" if role_type in {"supporting", "partner"} else "功能配角"),
        "protagonist_relation_level": "self" if name == protagonist_name else _text(source.get("relationship_to_protagonist") or source.get("attitude_to_protagonist"), "待观察"),
        "narrative_priority": 100 if name == protagonist_name else (80 if role_type in {"supporting", "partner"} else 40),
        "current_strength": _text(source.get("current_strength"), "待补充"),
        "current_goal": _text(source.get("current_desire") or source.get("current_plot_function"), "待补充"),
        "core_desire": _text(source.get("core_desire"), "待补充"),
        "core_fear": _text(source.get("core_fear"), "待补充"),
        "behavior_template_id": _text(source.get("behavior_template_id"), "starter_cautious_observer" if name == protagonist_name else ""),
        "speech_style": _text(source.get("speech_style"), "待补充"),
        "work_style": _text(source.get("work_style") or source.get("behavior_logic"), "待补充"),
        "behavior_mode": _text(source.get("behavior_mode") or source.get("work_style") or source.get("behavior_logic"), "待补充"),
        "core_value": _text(source.get("core_value"), "待补充"),
        "decision_logic": _text(source.get("decision_logic"), "待补充"),
        "pressure_response": _text(source.get("pressure_response"), "待补充"),
        "small_tell": _text(source.get("small_tell"), "待补充"),
        "taboo": _text(source.get("taboo"), "待补充"),
        "relationship_index": deepcopy(source.get("relationship_index") or {}),
        "resource_refs": normalize_resource_refs(source.get("resource_refs") or []),
        "faction_refs": [camp] if camp else [],
        "status": _text(source.get("status"), "active"),
    }
    merged = deepcopy(defaults)
    if isinstance(current, dict):
        merged.update({k: deepcopy(v) for k, v in current.items() if v not in (None, "", [], {})})
    characters[name] = merged



def _normalize_story_domain_resources(domains: dict[str, Any], *, default_owner: str) -> None:
    resources = domains.setdefault("resources", {})
    normalized: dict[str, dict[str, Any]] = {}
    for key, card in list(resources.items()):
        raw_name = _text((card or {}).get("display_name") or (card or {}).get("name") or key)
        normalized_name = _text((card or {}).get("name") or key)
        if not normalized_name and raw_name:
            normalized_name, seeded = build_resource_card(
                raw_name,
                owner=default_owner,
                resource_type="待细化资源",
                status="持有中",
                rarity="普通/待判定",
                exposure_risk="待观察",
                narrative_role="资源状态待后续章节细化。",
                recent_change="结构补齐。",
                source="normalize_story_domains",
            )
            card = seeded
        normalized_card = ensure_resource_card_structure(card if isinstance(card, dict) else {}, fallback_name=raw_name or normalized_name, owner=default_owner)
        target_name = _text(normalized_card.get("name") or normalized_name or raw_name)
        if not target_name:
            continue
        existing = normalized.get(target_name)
        if existing and isinstance(existing, dict):
            existing_quantity = int(existing.get("quantity") or 0)
            new_quantity = int(normalized_card.get("quantity") or 0)
            if new_quantity > existing_quantity:
                existing["quantity"] = new_quantity
                existing["display_name"] = _text(normalized_card.get("display_name"), existing.get("display_name", target_name))
            continue
        normalized[target_name] = normalized_card
    domains["resources"] = normalized





def _ensure_story_bible_foundation(
    story_bible: dict[str, Any],
    *,
    payload: NovelCreate,
    global_outline: dict[str, Any] | None = None,
    active_arc: dict[str, Any] | None = None,
    foundation_assets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assets = foundation_assets or {}
    story_bible = ensure_story_bible_v2_structure(story_bible)
    world_bible = story_bible.setdefault("world_bible", deepcopy(assets.get("world_bible") or _default_world_bible(payload)))
    cultivation_system = story_bible.setdefault("cultivation_system", deepcopy(assets.get("cultivation_system") or _default_cultivation_system(payload)))
    if not story_bible.get("story_domains"):
        story_bible["story_domains"] = deepcopy(assets.get("story_domains") or build_story_domains(payload, first_arc=active_arc, world_bible=world_bible, cultivation_system=cultivation_system))
    if not story_bible.get("power_system"):
        story_bible["power_system"] = deepcopy(assets.get("power_system") or build_power_system(payload, cultivation_system))
    built_opening_constraints = assets.get("opening_constraints") or build_opening_constraints(payload, global_outline or {})
    story_bible["opening_constraints"] = _upgrade_opening_constraints(story_bible.get("opening_constraints") or {}, built_opening_constraints)
    if not story_bible.get("template_library"):
        story_bible["template_library"] = deepcopy(assets.get("template_library") or build_template_library(payload))
    elif assets.get("template_library"):
        story_bible["template_library"] = _merge_character_template_library(
            story_bible.get("template_library") or {},
            assets.get("template_library") or {},
        )
    existing_core_cast = story_bible.get("core_cast_state") or {}
    built_core_cast = assets.get("core_cast_state") or build_core_cast_state_payload(payload)
    story_bible["core_cast_state"] = _deep_fill_missing(existing_core_cast, built_core_cast)
    if not (story_bible["core_cast_state"].get("slots") and int(story_bible["core_cast_state"].get("target_count") or 0) > 0):
        story_bible["core_cast_state"] = built_core_cast
    active_arc_digest = assets.get("active_arc_digest") or story_bible.get("active_arc_digest") or build_arc_digest(active_arc)
    story_bible["active_arc_digest"] = deepcopy(active_arc_digest)
    materialize_anchored_core_cast(story_bible, protagonist_name=payload.protagonist_name)
    story_bible["planner_state"] = _deep_fill_missing(story_bible.get("planner_state") or {}, build_planner_state())
    story_bible["retrospective_state"] = _deep_fill_missing(
        story_bible.get("retrospective_state") or {},
        build_retrospective_state(),
    )
    story_bible["flow_control"] = _deep_fill_missing(story_bible.get("flow_control") or {}, build_flow_control())
    story_bible["entity_registry"] = _deep_fill_missing(story_bible.get("entity_registry") or {}, build_entity_registry())
    importance_state = story_bible.get("importance_state") or {}
    entity_index = (importance_state.get("entity_index") or {}) if isinstance(importance_state, dict) else {}
    if not any((entity_index.get(key) or {}) for key in ["character", "resource", "relation", "faction"]):
        evaluate_story_elements_importance(
            story_bible=story_bible,
            protagonist_name=payload.protagonist_name,
            scope="foundation",
            chapter_no=0,
            plan=None,
            recent_summaries=None,
            touched_entities=None,
            allow_ai=False,
        )
    return story_bible


def refresh_planning_views(story_bible: dict[str, Any], current_chapter_no: int = 0) -> dict[str, Any]:
    story_bible = ensure_story_state_domains(story_bible, workflow_factory=_workflow_state_from_arc)
    workspace_state = ensure_story_workspace(story_bible)
    workflow_state = ensure_workflow_state(story_bible, workflow_factory=_workflow_state_from_arc)

    retrospective_state = story_bible.get("retrospective_state") or {}
    active_arc = story_bible.get("active_arc") or {}
    pending_arc = story_bible.get("pending_arc") or {}
    queue = [item for item in _chapter_cards_from_arc(active_arc) if int(item.get("chapter_no", 0) or 0) > current_chapter_no]
    if len(queue) < 7 and pending_arc:
        remaining = 7 - len(queue)
        queue.extend(_chapter_cards_from_arc(pending_arc)[:remaining])

    pending_payoff_compensation = (retrospective_state.get("pending_payoff_compensation") or {}) if isinstance(retrospective_state, dict) else {}
    bias_map = {
        int(item.get("chapter_no", 0) or 0): item
        for item in (pending_payoff_compensation.get("chapter_biases") or [])
        if isinstance(item, dict)
    }
    queue_with_payoff_bias: list[dict[str, Any]] = []
    for item in queue[:7]:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        bias = bias_map.get(int(copied.get("chapter_no", 0) or 0))
        if bias:
            note = _text(bias.get("note") or pending_payoff_compensation.get("note") or pending_payoff_compensation.get("reason"))
            copied["payoff_compensation"] = {
                "enabled": True,
                "source_chapter_no": int(pending_payoff_compensation.get("source_chapter_no", 0) or 0),
                "target_chapter_no": int(copied.get("chapter_no", 0) or 0),
                "priority": _text(bias.get("priority") or pending_payoff_compensation.get("priority"), "medium"),
                "note": note,
                "window_role": _text(bias.get("bias") or bias.get("window_role"), "primary_repay"),
                "window_end_chapter_no": int(pending_payoff_compensation.get("window_end_chapter_no", 0) or 0),
            }
            role = _text(bias.get("bias") or bias.get("window_role"), "primary_repay")
            copied["payoff_window_bias"] = role
            copied["payoff_window_event_bias"] = payoff_window_event_bias(role, priority=_text(bias.get("priority") or pending_payoff_compensation.get("priority"), "medium"))
        queue_with_payoff_bias.append(copied)
    workspace_state["chapter_card_queue"] = queue_with_payoff_bias
    outline_state = story_bible.get("outline_state") or {}
    current_stage_review = stage_character_review_for_window(story_bible, current_chapter_no=current_chapter_no)
    review_interval = max(int(retrospective_state.get("scheduled_review_interval", 5) or 5), 1)
    stage_review_due = bool(current_chapter_no > 0 and current_chapter_no % review_interval == 0 and int(retrospective_state.get("last_stage_review_chapter", 0) or 0) < current_chapter_no)

    active_arc_layout_review = summarize_arc_casting_layout_review(active_arc)
    pending_arc_layout_review = summarize_arc_casting_layout_review(pending_arc) if pending_arc else {}
    active_arc_digest = deepcopy(story_bible.get("active_arc_digest") or build_arc_digest(active_arc))
    pending_arc_digest = deepcopy(story_bible.get("pending_arc_digest") or (build_arc_digest(pending_arc) if pending_arc else {}))
    story_bible["active_arc_digest"] = deepcopy(active_arc_digest)
    story_bible["pending_arc_digest"] = deepcopy(pending_arc_digest) if pending_arc_digest else {}
    workspace_state["active_arc_digest"] = deepcopy(active_arc_digest)
    workspace_state["pending_arc_digest"] = deepcopy(pending_arc_digest) if pending_arc_digest else {}
    card_system_profile = story_bible.setdefault("card_system_profile", _card_system_profile(story_bible))
    window_execution_bias = _derive_window_execution_bias(story_bible, current_chapter_no=current_chapter_no)
    workspace_state["window_execution_bias"] = deepcopy(window_execution_bias)

    workspace_state["planning_status"] = {
        "documents_only_bootstrap": True,
        "auto_planning_enabled": True,
        "planned_until": int(outline_state.get("planned_until", 0) or 0),
        "next_arc_no": int(outline_state.get("next_arc_no", 0) or 0),
        "stage_review_due": stage_review_due,
        "stage_review_interval": review_interval,
        "current_stage_review": current_stage_review or {},
        "active_arc": {
            "arc_no": int(active_arc.get("arc_no", 0) or 0),
            "start_chapter": int(active_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(active_arc.get("end_chapter", 0) or 0),
            "focus": _text(active_arc.get("focus"), ""),
            "bridge_note": _text(active_arc.get("bridge_note"), ""),
            "casting_layout_review_summary": active_arc_layout_review,
            "arc_digest": deepcopy(active_arc_digest),
        },
        "pending_arc": {
            "arc_no": int(pending_arc.get("arc_no", 0) or 0),
            "start_chapter": int(pending_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(pending_arc.get("end_chapter", 0) or 0),
            "focus": _text(pending_arc.get("focus"), ""),
            "bridge_note": _text(pending_arc.get("bridge_note"), ""),
            "casting_layout_review_summary": pending_arc_layout_review,
            "arc_digest": deepcopy(pending_arc_digest),
        } if pending_arc else None,
        "active_arc_casting_layout_review": active_arc_layout_review,
        "pending_arc_casting_layout_review": pending_arc_layout_review,
        "ready_chapter_cards": [int(item.get("chapter_no", 0) or 0) for item in queue[:7]],
        "window_execution_bias": deepcopy(window_execution_bias),
        "card_system_profile": deepcopy(card_system_profile),
        "core_cast_brief": core_cast_guidance_for_chapter(story_bible, chapter_no=current_chapter_no + 1),
        "pending_payoff_compensation": {
            "enabled": bool(((retrospective_state.get("pending_payoff_compensation") or {}).get("enabled", False))),
            "source_chapter_no": int((((retrospective_state.get("pending_payoff_compensation") or {}).get("source_chapter_no")) or 0)),
            "target_chapter_no": int((((retrospective_state.get("pending_payoff_compensation") or {}).get("target_chapter_no")) or 0)),
            "window_end_chapter_no": int((((retrospective_state.get("pending_payoff_compensation") or {}).get("window_end_chapter_no")) or 0)),
            "priority": _text(((retrospective_state.get("pending_payoff_compensation") or {}).get("priority")), ""),
            "note": _text((((retrospective_state.get("pending_payoff_compensation") or {}).get("note")) or ((retrospective_state.get("pending_payoff_compensation") or {}).get("reason"))), ""),
            "chapter_biases": [
                {
                    "chapter_no": int(item.get("chapter_no", 0) or 0),
                    "bias": _text(item.get("bias") or item.get("window_role")),
                    "priority": _text(item.get("priority"), ""),
                    "note": _text(item.get("note"), ""),
                    "event_bias": payoff_window_event_bias(
                        _text(item.get("bias") or item.get("window_role")),
                        priority=_text(item.get("priority") or ((retrospective_state.get("pending_payoff_compensation") or {}).get("priority")), "medium"),
                    ),
                }
                for item in (((retrospective_state.get("pending_payoff_compensation") or {}).get("chapter_biases")) or [])[:3]
                if isinstance(item, dict)
            ],
        },
    }

    if queue:
        workspace_state["near_7_chapter_outline"] = [
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "title": _text(item.get("title"), f"第{item.get('chapter_no', '')}章"),
                "goal": _text(item.get("goal"), "推进当前主线"),
                "hook": _text(item.get("hook"), "新问题浮出"),
            }
            for item in queue[:7]
        ]

    workflow_state["bootstrap_generated_chapter_cards_until"] = max(
        int(workflow_state.get("bootstrap_generated_chapter_cards_until", 0) or 0),
        int((active_arc or {}).get("end_chapter", 0) or 0),
        int((pending_arc or {}).get("end_chapter", 0) or 0),
    )
    current_pipeline = workflow_state.setdefault("current_pipeline", {})
    current_pipeline.setdefault("target_chapter_no", current_chapter_no + 1)
    current_pipeline["project_card_ready"] = bool(story_bible.get("project_card"))
    current_pipeline["current_volume_ready"] = bool(story_bible.get("volume_cards"))
    current_pipeline["near_outline_ready"] = bool(queue)
    current_pipeline["chapter_card_ready"] = bool(queue and int(queue[0].get("chapter_no", 0) or 0) == current_chapter_no + 1)
    runtime = ensure_serial_runtime(story_bible)
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers["serial_rules_ready"] = bool(story_bible.get("serial_rules"))
    planning_layers["long_term_state_ready"] = True
    planning_layers["initialization_packet_ready"] = True
    story_bible["workflow_state"] = workflow_state
    story_bible["story_workspace"] = workspace_state
    story_bible["serial_runtime"] = runtime
    story_bible["initialization_packet"] = _build_initialization_packet(story_bible, current_chapter_no)
    update_story_state_bucket(
        story_bible,
        planning_window={
            "current_chapter_no": current_chapter_no,
            "planned_until": int(outline_state.get("planned_until", 0) or 0),
            "queue_size": len(queue[:7]),
            "active_arc_no": int(active_arc.get("arc_no", 0) or 0),
            "pending_arc_no": int((pending_arc or {}).get("arc_no", 0) or 0) if pending_arc else None,
        },
    )
    return story_bible


def set_pipeline_target(
    story_bible: dict[str, Any],
    *,
    next_chapter_no: int,
    execution_brief: dict[str, Any] | None = None,
    stage: str = "chapter_execution_card",
    last_completed_chapter_no: int | None = None,
) -> dict[str, Any]:
    story_bible = refresh_planning_views(story_bible, max(next_chapter_no - 1, 0))
    workflow_state = ensure_workflow_state(story_bible, workflow_factory=_workflow_state_from_arc)
    pipeline = workflow_state.setdefault("current_pipeline", {})
    pipeline.update(
        {
            "target_chapter_no": next_chapter_no,
            "project_card_ready": bool(story_bible.get("project_card")),
            "current_volume_ready": bool(story_bible.get("volume_cards")),
            "near_outline_ready": bool((story_bible.get("story_workspace") or {}).get("chapter_card_queue")),
            "chapter_card_ready": execution_brief is not None,
            "draft_ready": False,
            "summary_review_ready": False,
            "last_completed_stage": stage,
        }
    )
    if last_completed_chapter_no is not None:
        pipeline["last_completed_chapter_no"] = last_completed_chapter_no
    if execution_brief is not None:
        workspace_state = ensure_story_workspace(story_bible)
        packet = _clone_execution_packet(
            execution_brief,
            chapter_no=next_chapter_no,
            packet_phase="planning",
        )
        workspace_state["current_execution_packet"] = packet
        workspace_state["daily_workbench"] = deepcopy(packet.get("daily_workbench", {}))
    story_bible["workflow_state"] = workflow_state
    return story_bible


def compose_story_bible(
    payload: NovelCreate,
    title: str,
    base_story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    first_arc: dict[str, Any],
    story_engine_diagnosis: dict[str, Any] | None = None,
    story_strategy_card: dict[str, Any] | None = None,
    bootstrap_review: dict[str, Any] | None = None,
    foundation_assets: dict[str, Any] | None = None,
    arc_digest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assets = foundation_assets or {}
    resolved_arc_digest = deepcopy(arc_digest or assets.get("active_arc_digest") or build_arc_digest(first_arc))
    story_bible = ensure_story_state_domains(deepcopy(base_story_bible), workflow_factory=_workflow_state_from_arc, active_arc=first_arc)
    diagnosis = story_engine_diagnosis or story_bible.get("story_engine_diagnosis") or {}
    strategy = story_strategy_card or story_bible.get("story_strategy_card") or {}
    story_bible["story_engine_diagnosis"] = deepcopy(diagnosis)
    story_bible["story_strategy_card"] = deepcopy(strategy)
    if bootstrap_review:
        story_bible["bootstrap_review"] = deepcopy(bootstrap_review)
    story_bible["project_card"] = build_project_card(payload, title, global_outline, diagnosis, strategy)
    story_bible["world_bible"] = deepcopy(assets.get("world_bible") or _default_world_bible(payload))
    story_bible["cultivation_system"] = deepcopy(assets.get("cultivation_system") or _default_cultivation_system(payload))
    story_bible["volume_cards"] = build_volume_cards(global_outline, first_arc)
    story_bible["active_arc_digest"] = deepcopy(resolved_arc_digest)
    story_bible["story_workspace"] = deepcopy(assets.get("story_workspace") or build_story_workspace(payload, first_arc, arc_digest=resolved_arc_digest))
    story_bible = _ensure_story_bible_foundation(
        story_bible,
        payload=payload,
        global_outline=global_outline,
        active_arc=first_arc,
        foundation_assets={**assets, "active_arc_digest": resolved_arc_digest},
    )
    story_bible["serial_rules"] = build_serial_rules()
    story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    story_bible["daily_workflow"] = {
        "steps": [
            "回看昨天结尾",
            "确定今天这章的功能",
            "写三行章纲",
            "写正文时盯住主角行动、事件推进、新变化和章末拉力",
            "收工时留下明天提示",
        ],
        "quality_floor": [
            "主角有没有行动",
            "事件有没有推进",
            "有没有新变化",
            "节奏有没有拖",
            "结尾有没有拉力",
        ],
    }
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers.clear()
    planning_layers.update({
        "global_outline_ready": bool(global_outline),
        "volume_cards_ready": True,
        "first_near_outline_ready": bool(first_arc),
        "first_chapter_cards_ready": bool((first_arc or {}).get("chapters")),
        "serial_rules_ready": True,
        "long_term_state_ready": True,
        "initialization_packet_ready": True,
    })
    story_bible["planning_layers"] = planning_layers
    story_bible["workflow_state"] = _workflow_state_from_arc(first_arc)
    story_bible = set_delivery_mode(story_bible, DEFAULT_SERIAL_DELIVERY_MODE)
    story_bible = refresh_planning_views(story_bible, 0)
    stub_novel = Novel(
        title=title,
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences or {},
        current_chapter_no=0,
    )
    return sync_long_term_state(story_bible, stub_novel, chapters=[])


def update_volume_card_statuses(story_bible: dict[str, Any], current_chapter_no: int) -> None:
    for card in _safe_list(story_bible.get("volume_cards")):
        start = int(card.get("start_chapter", 0) or 0)
        end = int(card.get("end_chapter", 0) or 0)
        if current_chapter_no >= end > 0:
            card["status"] = "completed"
        elif start <= current_chapter_no + 1 <= max(end, start):
            card["status"] = "current"
        else:
            card["status"] = "planned"


def ensure_story_architecture(story_bible: dict[str, Any], novel: Novel) -> dict[str, Any]:
    story_bible = ensure_story_state_domains(deepcopy(story_bible or {}), workflow_factory=_workflow_state_from_arc, active_arc=(story_bible or {}).get("active_arc") if isinstance(story_bible, dict) else None)
    payload = NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )
    global_outline = story_bible.get("global_outline") or {}
    active_arc = story_bible.get("active_arc") or {}
    diagnosis = story_bible.get("story_engine_diagnosis") or {}
    strategy = story_bible.get("story_strategy_card") or {}
    active_arc_digest = story_bible.get("active_arc_digest") or build_arc_digest(active_arc)
    story_bible["active_arc_digest"] = deepcopy(active_arc_digest)
    workspace_state = story_bible.get("story_workspace") or {}
    if isinstance(workspace_state, dict):
        workspace_state.setdefault("active_arc_digest", deepcopy(active_arc_digest))
    story_bible.setdefault("story_engine_diagnosis", deepcopy(diagnosis))
    story_bible.setdefault("story_strategy_card", deepcopy(strategy))
    if "project_card" not in story_bible:
        story_bible["project_card"] = build_project_card(payload, novel.title, global_outline, diagnosis, strategy)
    if "world_bible" not in story_bible:
        story_bible["world_bible"] = _default_world_bible(payload)
    if "cultivation_system" not in story_bible:
        story_bible["cultivation_system"] = _default_cultivation_system(payload)
    if "volume_cards" not in story_bible:
        story_bible["volume_cards"] = build_volume_cards(global_outline, active_arc)
    if "story_workspace" not in story_bible:
        story_bible["story_workspace"] = build_story_workspace(payload, active_arc, arc_digest=active_arc_digest)
    if "serial_rules" not in story_bible:
        story_bible["serial_rules"] = build_serial_rules()
    if "continuity_rules" not in story_bible:
        story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    if "daily_workflow" not in story_bible:
        story_bible["daily_workflow"] = {
            "steps": ["回看昨天结尾", "确定今天这章的功能", "写三行章纲", "写正文", "留明天提示"],
            "quality_floor": ["主角有没有行动", "事件有没有推进", "有没有新变化", "节奏有没有拖", "结尾有没有拉力"],
        }
    story_bible = _ensure_story_bible_foundation(
        story_bible,
        payload=payload,
        global_outline=global_outline,
        active_arc=active_arc,
        foundation_assets={"active_arc_digest": active_arc_digest},
    )
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers.setdefault("global_outline_ready", bool(global_outline))
    planning_layers.setdefault("volume_cards_ready", bool(story_bible.get("volume_cards")))
    planning_layers.setdefault("first_near_outline_ready", bool(active_arc))
    planning_layers.setdefault("first_chapter_cards_ready", bool((active_arc or {}).get("chapters")))
    planning_layers.setdefault("serial_rules_ready", True)
    planning_layers.setdefault("long_term_state_ready", True)
    planning_layers.setdefault("initialization_packet_ready", True)
    story_bible["planning_layers"] = planning_layers
    if "workflow_state" not in story_bible:
        story_bible["workflow_state"] = _workflow_state_from_arc(active_arc)
    story_bible = set_delivery_mode(story_bible, (story_bible.get("serial_runtime") or {}).get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE))
    ensure_hard_fact_guard(story_bible)
    update_volume_card_statuses(story_bible, novel.current_chapter_no)
    story_bible = refresh_planning_views(story_bible, novel.current_chapter_no)
    return sync_long_term_state(story_bible, novel)


def build_execution_brief(
    *,
    story_bible: dict[str, Any],
    next_chapter_no: int,
    plan: dict[str, Any],
    last_chapter_tail: str,
) -> dict[str, Any]:
    workspace_state = ensure_story_workspace(story_bible)
    current_volume = _current_volume_card(story_bible, next_chapter_no)
    today_function = _text(plan.get("goal"), "推进剧情")
    if plan.get("supporting_character_focus"):
        today_function += f" + 让{_text(plan.get('supporting_character_focus'))}在场面里立住"
    change_line = _text(plan.get("discovery") or plan.get("conflict"), _text(plan.get("goal")))
    focus_name = _text(plan.get("supporting_character_focus"))
    character_focus_card = {}
    if focus_name:
        character_focus_card = ((workspace_state.get("cast_cards") or {}).get(focus_name) or {}) if isinstance(workspace_state.get("cast_cards"), dict) else {}
    character_voice_pack = _character_voice_pack(character_focus_card) if character_focus_card else {}
    retrospective_feedback = _recent_retrospective_feedback(workspace_state)
    planning_packet = (plan.get("planning_packet") or {}) if isinstance(plan, dict) else {}
    selected_payoff_card = (planning_packet.get("selected_payoff_card") or {}) if isinstance(planning_packet, dict) else {}
    payoff_runtime = (planning_packet.get("payoff_runtime") or {}) if isinstance(planning_packet, dict) else {}
    payoff_diagnostics = (payoff_runtime.get("payoff_diagnostics") or {}) if isinstance(payoff_runtime, dict) else {}
    preparation_diagnostics = (((planning_packet.get("preparation_selection") or {}).get("diagnostics")) or {}) if isinstance(planning_packet, dict) else {}
    preparation_summary_lines = list(preparation_diagnostics.get("readable_lines") or [])[:5] if isinstance(preparation_diagnostics, dict) else []
    pending_payoff_compensation = (((story_bible.get("retrospective_state") or {}).get("pending_payoff_compensation")) or {})
    if isinstance(pending_payoff_compensation, dict) and pending_payoff_compensation:
        matched_bias = _pending_payoff_compensation_bias_for_chapter(pending_payoff_compensation, next_chapter_no)
        if matched_bias:
            pending_payoff_compensation = {
                **pending_payoff_compensation,
                "target_chapter_no": int(matched_bias.get("chapter_no", 0) or next_chapter_no),
                "priority": _text(matched_bias.get("priority") or pending_payoff_compensation.get("priority"), "medium"),
                "note": _text(matched_bias.get("note") or pending_payoff_compensation.get("note") or pending_payoff_compensation.get("reason")),
                "window_role": _text(matched_bias.get("bias") or matched_bias.get("window_role"), "primary_repay"),
            }
        elif int(pending_payoff_compensation.get("target_chapter_no", 0) or 0) != int(next_chapter_no or 0):
            pending_payoff_compensation = {}
    else:
        pending_payoff_compensation = {}
    plan_payoff_compensation = (plan.get("payoff_compensation") or {}) if isinstance(plan, dict) else {}
    effective_payoff_compensation = plan_payoff_compensation or pending_payoff_compensation
    rolling_continuity = (planning_packet.get("recent_continuity_plan") or {}) if isinstance(planning_packet, dict) else {}
    book_execution_profile = _book_execution_profile_payload(story_bible)
    window_execution_bias = deepcopy((workspace_state.get("window_execution_bias") or _derive_window_execution_bias(story_bible, current_chapter_no=max(next_chapter_no - 1, 0))) if isinstance(workspace_state, dict) else _derive_window_execution_bias(story_bible, current_chapter_no=max(next_chapter_no - 1, 0)))
    card_system_profile = story_bible.get("card_system_profile") or _card_system_profile(story_bible)
    chapter_stage_casting_hint = (planning_packet.get("chapter_stage_casting_hint") or {}) if isinstance(planning_packet, dict) else {}
    chapter_stage_casting_runtime = build_chapter_casting_runtime_summary(
        story_bible,
        chapter_no=next_chapter_no,
        plan=plan,
        stage_hint=chapter_stage_casting_hint,
    )
    scene_runtime = (planning_packet.get("scene_runtime") or {}) if isinstance(planning_packet, dict) else {}
    scene_execution_card = (scene_runtime.get("scene_execution_card") or {}) if isinstance(scene_runtime, dict) else {}
    scene_sequence_plan = (scene_runtime.get("scene_sequence_plan") or []) if isinstance(scene_runtime, dict) else []
    resolved_scene_outline = [
        {
            "scene_no": int(item.get("scene_no", index + 1) or (index + 1)),
            "scene_name": _text(item.get("scene_name")),
            "scene_role": _text(item.get("scene_role")),
            "purpose": _text(item.get("purpose"), "推进当前场景"),
            "transition_in": _text(item.get("transition_in")),
            "target_result": _text(item.get("target_result")),
            "must_carry_over": _safe_list(item.get("must_carry_over"))[:3],
        }
        for index, item in enumerate(scene_sequence_plan)
        if isinstance(item, dict)
    ]
    if not resolved_scene_outline:
        resolved_scene_outline = [
            {"scene_no": 1, "purpose": _text(plan.get("opening_beat"), "承接上一章结尾并定位本章场景")},
            {"scene_no": 2, "purpose": _text(plan.get("mid_turn"), "中段制造受阻、试探或发现")},
            {"scene_no": 3, "purpose": _text(plan.get("closing_image") or plan.get("ending_hook"), "结尾落到结果、钩子或下一章入口")},
        ]
    execution_structure = _resolve_execution_structure(
        story_bible=story_bible,
        next_chapter_no=next_chapter_no,
        plan=plan,
        last_chapter_tail=last_chapter_tail,
        scene_execution_card=scene_execution_card,
        scene_outline=resolved_scene_outline,
        today_function=today_function,
        change_line=change_line,
    )
    opening_line = _text(execution_structure.get("opening"))
    middle_line = _text(execution_structure.get("middle"))
    ending_line = _text(execution_structure.get("ending"))
    today_function = _text(execution_structure.get("chapter_function"), today_function)
    change_line = _text(execution_structure.get("chapter_change"), change_line)
    chapter_hook_line = _text(execution_structure.get("chapter_hook"), _text(plan.get("ending_hook")))

    tomorrow_hints = [
        f"明天从第{next_chapter_no}章结尾的后续局势接上。",
        f"明天最大冲突：{_text(plan.get('conflict') or plan.get('goal'), _text(plan.get('goal')) or '继续推进当前矛盾')}",
        f"明天章末可往‘{chapter_hook_line or _text(plan.get('ending_hook'), '新问题浮出')}’方向留钩子。",
    ]
    long_term_state = story_bible.get("long_term_state") or {}
    release_state = (long_term_state.get("chapter_release_state") or {})
    return {
        "project_card": story_bible.get("project_card", {}),
        "current_volume_card": current_volume,
        "book_execution_profile": deepcopy(book_execution_profile),
        "window_execution_bias": deepcopy(window_execution_bias),
        "card_system_profile": deepcopy(card_system_profile),
        "chapter_execution_card": {
            "chapter_function": today_function,
            "event_type": _text(plan.get("event_type"), "试探类"),
            "progress_kind": _text(plan.get("progress_kind"), "信息推进"),
            "flow_card": _text(plan.get("flow_template_name") or plan.get("flow_template_tag") or plan.get("flow_template_id"), "当前流程卡"),
            "flow_child_card": _text(plan.get("flow_child_card_name") or ((plan.get("planning_packet") or {}).get("selected_flow_child_card") or {}).get("name")),
            "proactive_move": _text(plan.get("proactive_move"), _text(plan.get("goal"))),
            "payoff_or_pressure": _text(plan.get("payoff_or_pressure"), _text(plan.get("goal"))),
            "payoff_mode": _text(plan.get("payoff_mode") or selected_payoff_card.get("payoff_mode"), "明确兑现"),
            "payoff_level": _text(plan.get("payoff_level") or selected_payoff_card.get("payoff_level"), "medium"),
            "payoff_visibility": _text(plan.get("payoff_visibility") or selected_payoff_card.get("payoff_visibility"), "semi_public"),
            "payoff_card_id": _text(selected_payoff_card.get("card_id")),
            "reader_payoff": _text(plan.get("reader_payoff") or selected_payoff_card.get("reader_payoff"), _text(plan.get("payoff_or_pressure"), "本章必须给出明确回报或压力升级。")),
            "new_pressure": _text(plan.get("new_pressure") or selected_payoff_card.get("new_pressure")),
            "aftershock": _text(selected_payoff_card.get("aftershock")),
            "payoff_external_reaction": _text(selected_payoff_card.get("external_reaction")),
            "payoff_compensation_note": _text((effective_payoff_compensation or {}).get("note") or (effective_payoff_compensation or {}).get("reason")),
            "payoff_compensation_priority": _text((effective_payoff_compensation or {}).get("priority")),
            "payoff_diagnostics": _compact_value(payoff_diagnostics, text_limit=72),
            "foreshadowing_primary_action": _text((plan.get("planning_packet") or {}).get("selected_foreshadowing_primary", {}).get("action_type")),
            "foreshadowing_primary_hook": _text((plan.get("planning_packet") or {}).get("selected_foreshadowing_primary", {}).get("source_hook")),
            "foreshadowing_summary": _text(((plan.get("planning_packet") or {}).get("selected_foreshadowing_instance_cards") or [{}])[0].get("execution_hint")),
            "hook_kind": _text(plan.get("hook_kind"), _text(plan.get("ending_hook"))),
            "opening": opening_line,
            "middle": middle_line,
            "ending": ending_line,
            "structure_source": _text(execution_structure.get("structure_source"), "contextual_fallback"),
            "structure_reason": _text(execution_structure.get("reason")),
            "writing_card_summary": _text((plan.get("planning_packet") or {}).get("writing_card_selection", {}).get("selection_note") or (plan.get("planning_packet") or {}).get("prompt_selection", {}).get("selection_note")),
            "writing_child_card_summary": _text(((plan.get("planning_packet") or {}).get("selected_writing_child_cards") or [{}])[0].get("summary")),
            "chapter_change": change_line,
            "chapter_hook": chapter_hook_line,
            "stage_casting_hint": _compact_value(chapter_stage_casting_hint, text_limit=72),
            "stage_casting_runtime": chapter_stage_casting_runtime,
            "scene_count": int(scene_execution_card.get("scene_count", len(resolved_scene_outline)) or len(resolved_scene_outline)),
            "scene_transition_mode": _text(scene_execution_card.get("transition_mode"), "single_scene"),
            "must_continue_same_scene": bool(scene_execution_card.get("must_continue_same_scene")),
            "scene_opening_anchor": _text(scene_execution_card.get("opening_anchor")),
            "scene_first_focus": _text(scene_execution_card.get("first_scene_focus")),
            "scene_must_carry_over": _safe_list(scene_execution_card.get("must_carry_over"))[:4],
            "scene_sequence_note": _text(scene_execution_card.get("sequence_note")),
            "preparation_summary": preparation_summary_lines,
            "book_execution_note": _text(book_execution_profile.get("positioning_summary")),
            "window_execution_note": _text(window_execution_bias.get("directive")),
        },
        "scene_execution_card": scene_execution_card,
        "scene_outline": resolved_scene_outline,
        "serial_context": {
            "delivery_mode": release_state.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE),
            "published_through": int(release_state.get("published_through", 0) or 0),
            "latest_available_chapter": int(release_state.get("latest_available_chapter", 0) or 0),
            "fact_priority": (story_bible.get("serial_rules") or {}).get("fact_priority", []),
        },
        "character_focus_card": character_focus_card,
        "character_voice_pack": character_voice_pack,
        "chapter_retrospective_feedback": retrospective_feedback,
        "daily_workbench": {
            "yesterday_ending": _text(last_chapter_tail),
            "today_function": today_function,
            "three_line_outline": {
                "opening": opening_line,
                "middle": middle_line,
                "ending": ending_line or chapter_hook_line,
            },
            "rolling_continuity": {
                "must_continue": _safe_list((((rolling_continuity.get("current_chapter_bridge") or {}).get("must_continue")) or []))[:3],
                "carry_in": _safe_list((((rolling_continuity.get("carry_in") or {}).get("carry_over_points")) or []))[:3],
                "preserve_for_next": _safe_list((((rolling_continuity.get("lookahead_handoff") or {}).get("preserve_for_next")) or []))[:3],
            },
            "payoff_diagnostics": _compact_value(payoff_diagnostics, text_limit=72),
            "payoff_runtime_note": _text(((payoff_diagnostics.get("summary_lines") or ["", "", ""])[2])),
            "payoff_compensation": _compact_value(effective_payoff_compensation, text_limit=72),
            "payoff_compensation_note": _text((effective_payoff_compensation or {}).get("note") or (effective_payoff_compensation or {}).get("reason")),
            "chapter_stage_casting_hint": _compact_value(chapter_stage_casting_hint, text_limit=72),
            "chapter_stage_casting_runtime": chapter_stage_casting_runtime,
            "chapter_stage_casting_runtime_note": _text(chapter_stage_casting_runtime.get("runtime_note")),
            "preparation_diagnostics": _compact_value(preparation_diagnostics, text_limit=72),
            "preparation_runtime_note": _text((preparation_summary_lines or ["", "", "", ""])[2]),
            "preparation_layer_note": _text((preparation_summary_lines or ["", "", "", ""])[3]),
            "scene_execution_card": _compact_value(scene_execution_card, text_limit=72),
            "scene_sequence_plan": _compact_value(resolved_scene_outline, text_limit=72),
            "book_execution_profile": _compact_value(book_execution_profile, text_limit=72),
            "window_execution_bias": _compact_value(window_execution_bias, text_limit=72),
            "card_system_profile": _compact_value(card_system_profile, text_limit=72),
            "tomorrow_hints": tomorrow_hints,
        },
        "quality_floor": [
            "主角必须在本章主动做出至少一次观察、判断、试探、设局、争资源、验证、表态或反击。",
            "本章不能重复最近两章的主事件类型。",
            "本章必须出现事件推进，而不是只补设定。",
            "本章必须产生新变化：信息、关系、风险、资源、退路至少改变其一。",
            "节奏不能拖成长段说明书。",
            "章末必须有拉力或结果落地。",
        ],
        "continuity_rules": _safe_list(story_bible.get("continuity_rules")) or list(DEFAULT_CONTINUITY_RULES),
    }


def _merge_character_card(workspace_state: dict[str, Any], name: str, defaults: dict[str, Any]) -> None:
    cards = workspace_state.setdefault("cast_cards", {})
    existing = cards.get(name, {}) if isinstance(cards, dict) else {}
    merged = dict(defaults)
    merged.update({k: v for k, v in existing.items() if v not in (None, "", [], {})})
    cards[name] = merged


_SUMMARY_RESERVED_UPDATE_KEYS = {"notes", "__resource_updates__", "__monster_updates__", "__power_progress__"}



def _summary_character_items(summary: Any) -> list[tuple[str, Any]]:
    updates = getattr(summary, "character_updates", None) or {}
    if not isinstance(updates, dict):
        return []
    items: list[tuple[str, Any]] = []
    for key, value in updates.items():
        name = _text(key)
        if not name or name in _SUMMARY_RESERVED_UPDATE_KEYS or name.startswith("__"):
            continue
        items.append((name, value))
    return items



def _summary_resource_updates(summary: Any) -> dict[str, Any]:
    updates = getattr(summary, "character_updates", None) or {}
    if not isinstance(updates, dict):
        return {}
    payload = updates.get("__resource_updates__") or {}
    return payload if isinstance(payload, dict) else {}



def _summary_monster_updates(summary: Any) -> dict[str, Any]:
    updates = getattr(summary, "character_updates", None) or {}
    if not isinstance(updates, dict):
        return {}
    payload = updates.get("__monster_updates__") or {}
    return payload if isinstance(payload, dict) else {}



def _maybe_merge_text(target: dict[str, Any], key: str, value: Any) -> None:
    text = _text(value)
    if text:
        target[key] = text



def _apply_character_summary_update(*, workspace_state: dict[str, Any], story_bible: dict[str, Any], novel: Novel, name: str, state: Any, chapter_no: int) -> None:
    payload = state if isinstance(state, dict) else {"latest_update": state}
    protagonist_name = novel.protagonist_name
    cast_cards = workspace_state.setdefault("cast_cards", {})
    story_domains = story_bible.setdefault("story_domains", {})
    characters = story_domains.setdefault("characters", {})
    current_card = deepcopy((cast_cards.get(name) or characters.get(name) or {"name": name}))
    current_card.setdefault("name", name)
    current_card.setdefault("role_type", "protagonist" if name == protagonist_name else "supporting")
    current_card.setdefault("status", "active")
    realm = _text(payload.get("current_realm") or payload.get("realm") or payload.get("current_strength") or current_card.get("current_realm") or current_card.get("current_strength"))
    if realm:
        current_card["current_realm"] = realm
        current_card["current_strength"] = realm
        current_card["strength_label"] = realm
    for field in ["status", "latest_update", "relationship_to_protagonist", "attitude_to_protagonist", "current_plot_function", "recent_impact", "speech_style", "work_style", "behavior_logic"]:
        _maybe_merge_text(current_card, field, payload.get(field))
    if _text(payload.get("cultivation_progress")):
        current_card["cultivation_progress"] = _text(payload.get("cultivation_progress"))
    if _text(payload.get("breakthrough")):
        current_card["latest_breakthrough"] = _text(payload.get("breakthrough"))
    current_card["last_seen_chapter"] = chapter_no
    current_card.setdefault("first_appearance_rule", "角色第一次完整登场时，尽量让读者知道其大致境界或强弱层位。")
    cast_cards[name] = current_card
    characters[name] = {**(characters.get(name) or {}), **current_card, "entity_type": "character"}

    if name == protagonist_name:
        protagonist_profile = workspace_state.setdefault("protagonist_profile", {})
        if realm:
            protagonist_profile["current_realm"] = realm
            protagonist_profile["visible_strength_label"] = realm
        _maybe_merge_text(protagonist_profile, "current_status", payload.get("latest_update") or payload.get("status"))
        _maybe_merge_text(protagonist_profile, "recent_cultivation_focus", payload.get("cultivation_progress"))
        if _text(payload.get("breakthrough")):
            protagonist_profile["latest_breakthrough"] = _text(payload.get("breakthrough"))
            journal = workspace_state.setdefault("power_progress_journal", [])
            journal.append({
                "chapter_no": chapter_no,
                "realm": realm,
                "breakthrough": _text(payload.get("breakthrough")),
                "cultivation_progress": _text(payload.get("cultivation_progress")),
            })
            workspace_state["power_progress_journal"] = journal[-12:]



def _apply_resource_summary_updates(*, story_bible: dict[str, Any], updates: dict[str, Any], chapter_no: int) -> None:
    resources = (((story_bible.get("story_domains") or {}).get("resources")) or {})
    for raw_name, state in updates.items():
        name = _text(raw_name)
        if not name:
            continue
        payload = state if isinstance(state, dict) else {"latest_update": state}
        card = ensure_resource_card_structure(resources.get(name) or {}, fallback_name=name, owner=_text((resources.get(name) or {}).get("owner")))
        quality = _text(payload.get("quality_tier") or payload.get("quality") or payload.get("quality_rank"))
        if quality:
            normalized = infer_resource_quality(quality, rarity=_text(card.get("rarity")), resource_type=_text(card.get("resource_type")))
            card["quality_tier"] = normalized
            card["quality_rank"] = normalized
            try:
                from app.services.resource_card_support import resource_quality_index
                card["quality_index"] = resource_quality_index(normalized)
            except Exception:
                pass
            card["quality_note"] = f"{normalized}资源，正文出现时尽量顺手点明品质与价值。"
        for field in ["status", "latest_update", "narrative_role", "recent_change"]:
            _maybe_merge_text(card, field, payload.get(field))
        for field in ["owner", "resource_type"]:
            _maybe_merge_text(card, field, payload.get(field))
        quantity_after = payload.get("quantity_after")
        if quantity_after not in (None, ""):
            try:
                card["quantity"] = max(int(quantity_after), 0)
            except Exception:
                pass
        card["last_seen_chapter"] = chapter_no
        resources[name] = card



def _apply_monster_summary_updates(*, workspace_state: dict[str, Any], story_bible: dict[str, Any], updates: dict[str, Any], chapter_no: int, default_realm: str = "待判定") -> None:
    monster_cards = workspace_state.setdefault("monster_cards", {})
    story_domains = story_bible.setdefault("story_domains", {})
    monsters = story_domains.setdefault("monsters", {})
    for raw_name, state in updates.items():
        name = _text(raw_name)
        if not name:
            continue
        payload = state if isinstance(state, dict) else {"latest_update": state}
        card = ensure_monster_card_structure(monster_cards.get(name) or monsters.get(name) or {}, fallback_name=name, default_realm=default_realm)
        realm = _text(payload.get("current_realm") or payload.get("realm") or payload.get("power_level") or payload.get("threat_level") or card.get("current_realm") or default_realm)
        if realm:
            card["current_realm"] = realm
            card["current_strength"] = realm
            card["threat_level"] = realm
        for field in ["species_type", "hostility", "status", "intelligence_level", "narrative_role", "threat_note", "latest_update"]:
            _maybe_merge_text(card, field, payload.get(field))
        traits = payload.get("signature_traits")
        if isinstance(traits, list) and traits:
            card["signature_traits"] = [_text(item) for item in traits if _text(item)][:4]
        if int(card.get("first_seen_chapter") or 0) <= 0:
            card["first_seen_chapter"] = chapter_no
        card["last_seen_chapter"] = chapter_no
        monster_cards[name] = card
        monsters[name] = {**(monsters.get(name) or {}), **card, "entity_type": "monster"}



def _apply_summary_structured_updates(*, workspace_state: dict[str, Any], story_bible: dict[str, Any], novel: Novel, summary: Any, chapter_no: int) -> None:
    for name, state in _summary_character_items(summary):
        _apply_character_summary_update(workspace_state=workspace_state, story_bible=story_bible, novel=novel, name=name, state=state, chapter_no=chapter_no)
    resource_updates = _summary_resource_updates(summary)
    if resource_updates:
        _apply_resource_summary_updates(story_bible=story_bible, updates=resource_updates, chapter_no=chapter_no)
    monster_updates = _summary_monster_updates(summary)
    if monster_updates:
        default_realm = _text((((story_bible.get("power_system") or {}).get("realm_system") or {}).get("current_reference_realm")), "待判定")
        _apply_monster_summary_updates(workspace_state=workspace_state, story_bible=story_bible, updates=monster_updates, chapter_no=chapter_no, default_realm=default_realm)


def sync_character_registry(
    db: Session,
    novel: Novel,
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    summary: Any,
) -> None:
    workspace_state = story_bible.get("story_workspace") or {}
    protagonist_profile = workspace_state.get("protagonist_profile") or {}
    cards = workspace_state.get("cast_cards") or {}

    def upsert(name: str, role_type: str, core_profile: dict[str, Any], dynamic_state: dict[str, Any]) -> None:
        if not name:
            return
        row = (
            db.query(Character)
            .filter(Character.novel_id == novel.id, Character.name == name)
            .first()
        )
        if not row:
            row = Character(novel_id=novel.id, name=name, role_type=role_type)
        row.core_profile = core_profile
        row.dynamic_state = dynamic_state
        db.add(row)

    protagonist_name = novel.protagonist_name
    protagonist_card = cards.get(protagonist_name, {}) if isinstance(cards, dict) else {}
    upsert(
        protagonist_name,
        "protagonist",
        protagonist_card or {"name": protagonist_name, "role_type": "protagonist"},
        protagonist_profile,
    )

    focus_name = _text(plan.get("supporting_character_focus"))
    if focus_name:
        note = _text(plan.get("supporting_character_note"), "本卷的重要配角，需要持续保持辨识度。")
        current = cards.get(focus_name, {}) if isinstance(cards, dict) else {}
        palette = _supporting_voice_template(focus_name, note)
        template = pick_character_template(
            story_bible,
            name=focus_name,
            note=note,
            role_hint="supporting",
            relation_hint=_text((current or {}).get("attitude_to_protagonist"), "待观察"),
            fallback_id="starter_hard_shell_soft_core",
        )
        profile = apply_character_template_defaults(
            current
            or {
                "name": focus_name,
                "role_type": "supporting",
                "current_plot_function": "本阶段重要配角",
                "current_desire": _text(palette.get("private_goal"), "先保住自己的利益，再决定是否靠近主角。"),
                "attitude_to_protagonist": "待观察",
                "recent_impact": "刚在当前剧情中留下存在感。",
                "do_not_break": ["不能只会盘问和警告", "要保留角色自己的利益与语气"],
                "behavior_logic": _text(palette.get("work_style"), note),
            },
            template,
        )
        if note and len(note) >= 8:
            profile["speech_style"] = _text(note, _text(profile.get("speech_style")))
        dynamic_state = {
            "last_seen_chapter": int(plan.get("chapter_no", 0) or 0),
            "latest_note": note,
        }
        upsert(focus_name, "supporting", profile, dynamic_state)

    for char_name, state in _summary_character_items(summary):
        current = cards.get(char_name, {}) if isinstance(cards, dict) else {}
        role_type = _text(current.get("role_type"), "supporting")
        profile = current or {"name": char_name, "role_type": role_type}
        dynamic_state = state if isinstance(state, dict) else {"latest_update": state}
        upsert(char_name, role_type, profile, dynamic_state)


def sync_monster_registry(
    db: Session,
    novel: Novel,
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    summary: Any,
) -> None:
    workspace_state = story_bible.get("story_workspace") or {}
    monster_cards = workspace_state.get("monster_cards") or {}
    story_domains = story_bible.get("story_domains") or {}
    monsters_domain = story_domains.get("monsters") or {}
    default_realm = _text((((story_bible.get("power_system") or {}).get("realm_system") or {}).get("current_reference_realm")), "待判定")

    def upsert(name: str, species_type: str, threat_level: str, core_profile: dict[str, Any], dynamic_state: dict[str, Any]) -> None:
        if not name:
            return
        row = (
            db.query(Monster)
            .filter(Monster.novel_id == novel.id, Monster.name == name)
            .first()
        )
        if not row:
            row = Monster(novel_id=novel.id, name=name, species_type=species_type or "monster", threat_level=threat_level or default_realm)
        row.species_type = species_type or row.species_type or "monster"
        row.threat_level = threat_level or row.threat_level or default_realm
        row.core_profile = core_profile
        row.dynamic_state = dynamic_state
        db.add(row)

    seeded_name = _text(plan.get("monster_focus"))
    if seeded_name:
        current = monster_cards.get(seeded_name, {}) if isinstance(monster_cards, dict) else {}
        seeded = ensure_monster_card_structure(
            current or monsters_domain.get(seeded_name) or {},
            fallback_name=seeded_name,
            default_realm=default_realm,
        )
        upsert(
            seeded_name,
            _text(seeded.get("species_type"), "monster"),
            _text(seeded.get("threat_level") or seeded.get("current_realm"), default_realm),
            seeded,
            {
                "last_seen_chapter": int(plan.get("chapter_no", 0) or 0),
                "latest_update": _text(seeded.get("latest_update") or seeded.get("threat_note") or "怪兽卡已进入当前故事运行状态。"),
            },
        )

    for raw_name, state in _summary_monster_updates(summary).items():
        monster_name = _text(raw_name)
        if not monster_name:
            continue
        payload = state if isinstance(state, dict) else {"latest_update": state}
        current = monster_cards.get(monster_name, {}) if isinstance(monster_cards, dict) else {}
        profile = ensure_monster_card_structure(
            current or monsters_domain.get(monster_name) or payload,
            fallback_name=monster_name,
            default_realm=default_realm,
        )
        threat_level = _text(payload.get("current_realm") or payload.get("realm") or payload.get("power_level") or payload.get("threat_level") or profile.get("threat_level"), default_realm)
        dynamic_state = {
            "last_seen_chapter": int(plan.get("chapter_no", 0) or 0),
            "status": _text(payload.get("status") or profile.get("status"), "active"),
            "latest_update": _text(payload.get("latest_update") or payload.get("threat_note") or profile.get("latest_update") or profile.get("threat_note")),
            "current_realm": threat_level,
            "threat_level": threat_level,
        }
        if _text(payload.get("hostility") or profile.get("hostility")):
            dynamic_state["hostility"] = _text(payload.get("hostility") or profile.get("hostility"))
        upsert(
            monster_name,
            _text(payload.get("species_type") or profile.get("species_type"), "monster"),
            threat_level,
            profile,
            dynamic_state,
        )


def _build_pending_payoff_compensation_payload(*, source_chapter_no: int, priority: str, note: str) -> dict[str, Any]:
    clean_priority = _text(priority, "medium").lower()
    if clean_priority not in {"high", "medium", "low"}:
        clean_priority = "medium"
    chapter_biases: list[dict[str, Any]] = [
        {
            "chapter_no": source_chapter_no + 1,
            "bias": "primary_repay",
            "priority": clean_priority,
            "note": note,
        }
    ]
    if clean_priority == "high":
        chapter_biases.append(
            {
                "chapter_no": source_chapter_no + 2,
                "bias": "stabilize_after_repay",
                "priority": "medium",
                "note": "若上一章只追回一半，这一章继续补一次可感兑现，并换一种显影方式。",
            }
        )
    window_end = max(int(item.get("chapter_no", 0) or 0) for item in chapter_biases) if chapter_biases else source_chapter_no + 1
    return {
        "enabled": True,
        "source_chapter_no": source_chapter_no,
        "target_chapter_no": source_chapter_no + 1,
        "window_end_chapter_no": window_end,
        "priority": clean_priority,
        "reason": note,
        "note": note,
        "chapter_biases": chapter_biases,
        "should_reduce_pressure": True,
    }


def _pending_payoff_compensation_bias_for_chapter(payload: dict[str, Any] | None, chapter_no: int) -> dict[str, Any]:
    source = payload or {}
    for item in (source.get("chapter_biases") or []):
        if not isinstance(item, dict):
            continue
        if int(item.get("chapter_no", 0) or 0) == int(chapter_no or 0):
            return item
    if int(source.get("target_chapter_no", 0) or 0) == int(chapter_no or 0):
        return {
            "chapter_no": chapter_no,
            "bias": _text(source.get("window_role"), "primary_repay"),
            "priority": _text(source.get("priority"), "medium"),
            "note": _text(source.get("note") or source.get("reason")),
        }
    return {}


def _roll_pending_payoff_compensation(payload: dict[str, Any] | None, *, chapter_no: int, payoff_delivery: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {})
    if not source:
        return {}
    current_bias = _pending_payoff_compensation_bias_for_chapter(source, chapter_no)
    if not current_bias:
        future = [item for item in (source.get("chapter_biases") or []) if isinstance(item, dict) and int(item.get("chapter_no", 0) or 0) > int(chapter_no or 0)]
        if future:
            return source
        if int(source.get("target_chapter_no", 0) or 0) > int(chapter_no or 0):
            return source
        return {}
    future_biases = [item for item in (source.get("chapter_biases") or []) if isinstance(item, dict) and int(item.get("chapter_no", 0) or 0) > int(chapter_no or 0)]
    delivery_level = _text((payoff_delivery or {}).get("delivery_level"), "").lower()
    role = _text(current_bias.get("bias"), "primary_repay")
    if role == "primary_repay" and delivery_level == "high":
        return {}
    if future_biases:
        next_bias = future_biases[0]
        source["target_chapter_no"] = int(next_bias.get("chapter_no", 0) or 0)
        source["window_end_chapter_no"] = max(int(item.get("chapter_no", 0) or 0) for item in future_biases)
        source["chapter_biases"] = future_biases
        source["priority"] = _text(next_bias.get("priority") or source.get("priority"), "medium")
        source["note"] = _text(next_bias.get("note") or source.get("note") or source.get("reason"))
        source["reason"] = _text(source.get("reason") or source.get("note"))
        return source
    return {}


def update_story_architecture_after_chapter(
    *,
    story_bible: dict[str, Any],
    novel: Novel,
    chapter_no: int,
    chapter_title: str,
    plan: dict[str, Any],
    summary: Any,
    last_chapter_tail: str,
    chapter_content: str = "",
    payoff_delivery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    story_bible = ensure_story_architecture(story_bible, novel)
    workspace_state = ensure_story_workspace(story_bible)
    retrospective_state = story_bible.setdefault("retrospective_state", {})
    pending_compensation = retrospective_state.get("pending_payoff_compensation") or {}
    protagonist_profile = workspace_state.setdefault("protagonist_profile", {})
    protagonist_profile["current_goal"] = _text(plan.get("ending_hook") or plan.get("goal"), protagonist_profile.get("current_goal", ""))
    protagonist_profile["current_status"] = _text(getattr(summary, "event_summary", None), protagonist_profile.get("current_status", ""))
    _apply_summary_structured_updates(
        workspace_state=workspace_state,
        story_bible=story_bible,
        novel=novel,
        summary=summary,
        chapter_no=chapter_no,
    )

    volume_card = _current_volume_card(story_bible, chapter_no)
    update_volume_card_statuses(story_bible, chapter_no)

    progress = workspace_state.setdefault("recent_progress", [])
    progress.append(
        {
            "chapter_no": chapter_no,
            "title": chapter_title,
            "event_summary": _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), "推进当前主线")),
            "new_change": _text(plan.get("discovery") or plan.get("conflict"), "局势发生了新的偏移。"),
            "chapter_hook": _text(plan.get("ending_hook"), "新的问题浮出。"),
        }
    )
    workspace_state["recent_progress"] = progress[-12:]

    retrospective = _build_chapter_retrospective(
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        plan=plan,
        summary=summary,
        workspace_state=workspace_state,
        story_bible=story_bible,
        payoff_delivery=payoff_delivery,
    )
    retrospectives = workspace_state.setdefault("chapter_retrospectives", [])
    retrospectives.append(retrospective)
    workspace_state["chapter_retrospectives"] = retrospectives[-12:]
    rolled_pending_compensation = _roll_pending_payoff_compensation(
        pending_compensation if isinstance(pending_compensation, dict) else {},
        chapter_no=chapter_no,
        payoff_delivery=payoff_delivery,
    )
    if bool((payoff_delivery or {}).get("should_compensate_next_chapter")):
        retrospective_state["pending_payoff_compensation"] = _build_pending_payoff_compensation_payload(
            source_chapter_no=chapter_no,
            priority=_text((payoff_delivery or {}).get("compensation_priority"), "medium"),
            note=_text((payoff_delivery or {}).get("compensation_note"), retrospective.get("next_chapter_correction")),
        )
    else:
        retrospective_state["pending_payoff_compensation"] = rolled_pending_compensation

    current_execution_packet = workspace_state.get("current_execution_packet") if isinstance(workspace_state.get("current_execution_packet"), dict) else {}
    if current_execution_packet:
        completed_packet = deepcopy(current_execution_packet)
        completed_packet["packet_phase"] = "completed_plan_reference"
        completed_packet["completed_at_chapter_no"] = int(chapter_no or 0)
        workspace_state["last_completed_execution_packet"] = completed_packet
        history = workspace_state.setdefault("execution_packet_history", [])
        history.append(
            {
                "chapter_no": int(completed_packet.get("for_chapter_no", chapter_no) or chapter_no),
                "packet_phase": "completed_plan_reference",
                "chapter_function": _text((((completed_packet.get("chapter_execution_card") or {}).get("chapter_function"))), ""),
            }
        )
        workspace_state["execution_packet_history"] = history[-8:]
    workspace_state["last_generated_scene_report"] = build_realized_scene_report(
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        plan=plan,
        summary=summary,
        content=chapter_content or last_chapter_tail,
        execution_packet=current_execution_packet,
    )
    workspace_state.pop("current_execution_packet", None)

    daily = build_execution_brief(
        story_bible=story_bible,
        next_chapter_no=chapter_no + 1,
        plan=plan,
        last_chapter_tail=last_chapter_tail,
    )
    next_preview = _clone_execution_packet(daily, chapter_no=chapter_no + 1, packet_phase="next_chapter_preview")
    workspace_state["next_chapter_preview_packet"] = next_preview
    workspace_state["daily_workbench"] = deepcopy(next_preview.get("daily_workbench", {}))

    near_progress = workspace_state.setdefault("near_window_progress", workspace_state.get("near_30_progress") or {})
    near_progress["current_position"] = f"已写到第{chapter_no}章"
    near_progress["current_volume_gap"] = _text(volume_card.get("main_conflict"), near_progress.get("current_volume_gap", ""))
    near_progress["next_big_payoff"] = _text(volume_card.get("cool_point"), near_progress.get("next_big_payoff", ""))
    near_progress["next_twist"] = _text(plan.get("ending_hook"), near_progress.get("next_twist", ""))
    workspace_state["near_30_progress"] = deepcopy(near_progress)

    timeline = workspace_state.setdefault("timeline", [])
    timeline.append(
        {
            "chapter_no": chapter_no,
            "event": _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), "推进当前主线")),
        }
    )
    workspace_state["timeline"] = timeline[-30:]

    foreshadowing = workspace_state.setdefault("foreshadowing", [])
    existing_open = {str(item.get("surface_info", "")): item for item in foreshadowing if isinstance(item, dict)}
    for hook in getattr(summary, "open_hooks", []) or []:
        hook_text = _text(hook)
        if not hook_text:
            continue
        existing_open.setdefault(
            hook_text,
            {
                "name": hook_text[:24],
                "introduced_in_chapter": chapter_no,
                "surface_info": hook_text,
                "real_info": "待后续揭示",
                "known_by": [novel.protagonist_name],
                "expected_resolution": "待后续回收",
                "status": "open",
            },
        )
    foreshadowing = list(existing_open.values())
    closed = {_text(item) for item in (getattr(summary, "closed_hooks", []) or []) if _text(item)}
    for item in foreshadowing:
        if _text(item.get("surface_info")) in closed:
            item["status"] = "closed"
            item["expected_resolution"] = f"已在第{chapter_no}章阶段性回收"
    workspace_state["foreshadowing"] = foreshadowing[-30:]

    protagonist_name = novel.protagonist_name
    _merge_character_card(
        workspace_state,
        protagonist_name,
        {
            "name": protagonist_name,
            "role_type": "protagonist",
            "current_strength": _text(protagonist_profile.get("current_realm"), "低阶求生阶段"),
            "current_plot_function": "推动视角、承接风险、做出选择。",
            "behavior_logic": "先观察和试探，再决定是否行动。",
            "relationship_to_protagonist": "self",
        },
    )
    focus_name = _text(plan.get("supporting_character_focus"))
    if focus_name:
        note = _text(plan.get("supporting_character_note"))
        palette = _supporting_voice_template(focus_name, note)
        template = pick_character_template(
            story_bible,
            name=focus_name,
            note=note,
            role_hint="supporting",
            relation_hint="试探中",
            fallback_id="starter_hard_shell_soft_core",
        )
        _merge_character_card(
            workspace_state,
            focus_name,
            apply_character_template_defaults(
                {
                    "name": focus_name,
                    "role_type": "supporting",
                    "temperament": _text(note, "本阶段的重要配角。"),
                    "speech_style": _text(note, _text(palette.get("speech_style"), "说话方式需要有辨识度。")),
                    "work_style": _text(palette.get("work_style"), _text(plan.get("conflict") or plan.get("goal"), "做事有自己的算盘与顾虑。")),
                    "current_desire": _text(plan.get("goal"), _text(palette.get("private_goal"), "在当前局势中争取自己的利益。")),
                    "attitude_to_protagonist": "试探中",
                    "recent_impact": _text(plan.get("ending_hook") or plan.get("conflict"), "给主角带来新的局势变化。"),
                    "current_plot_function": "作为本章关键配角参与推进。",
                    "relationship_to_protagonist": "待剧情更新",
                    "possible_change": "关系可能由试探转向合作或对立。",
                    "do_not_break": ["不能所有配角都说同一种话", "不能只剩功能没有人格"],
                },
                template,
            ),
        )
        relations = workspace_state.setdefault("relationship_journal", [])
        relations.append(
            {
                "subject": protagonist_name,
                "target": focus_name,
                "chapter_no": chapter_no,
                "change": _text(plan.get("conflict") or plan.get("goal"), "关系发生新的试探或位移。"),
            }
        )
        workspace_state["relationship_journal"] = relations[-20:]

    if focus_name:
        bind_character_to_core_slot(
            story_bible,
            character_name=focus_name,
            chapter_no=chapter_no,
            note=_text(plan.get("supporting_character_note") or plan.get("goal")),
            protagonist_name=protagonist_name,
        )
    summary_character_names = [name for name, _ in _summary_character_items(summary)]
    onstage_character_names = [
        protagonist_name,
        focus_name,
        *summary_character_names,
    ]
    update_core_cast_after_chapter(
        story_bible,
        chapter_no=chapter_no,
        onstage_characters=onstage_character_names,
    )
    apply_role_refresh_execution(
        story_bible,
        chapter_no=chapter_no,
        plan=plan,
    )
    record_stage_casting_resolution(
        story_bible,
        chapter_no=chapter_no,
        plan=plan,
    )
    update_character_relation_schedule_after_chapter(
        story_bible,
        chapter_no=chapter_no,
        onstage_characters=onstage_character_names,
        focus_name=focus_name,
        plan=plan,
    )

    current_volume_end = int(volume_card.get("end_chapter", 0) or 0)
    if current_volume_end and chapter_no >= current_volume_end:
        reviews = workspace_state.setdefault("volume_reviews", [])
        reviews.append(
            {
                "volume_no": int(volume_card.get("volume_no", 0) or 0),
                "volume_name": _text(volume_card.get("volume_name"), f"第{volume_card.get('volume_no', '')}卷"),
                "mainline_advanced": True,
                "protagonist_growth": _text(protagonist_profile.get("current_status"), "主角完成了一次阶段性成长与位置变化。"),
                "best_cool_point": _text(volume_card.get("cool_point"), "阶段性破局。"),
                "drag_point": "留待人工复盘微调。",
                "recovered_foreshadowing": [_text(x) for x in (getattr(summary, "closed_hooks", []) or []) if _text(x)],
                "unresolved_foreshadowing": [_text(item.get("surface_info")) for item in workspace_state.get("foreshadowing", []) if item.get("status") != "closed"][:6],
                "next_volume_newness": _text(volume_card.get("next_hook"), "下一卷会抬高地图、规则与代价。"),
            }
        )
        workspace_state["volume_reviews"] = reviews[-8:]

    next_outline = workspace_state.setdefault("near_7_chapter_outline", [])
    if next_outline and next_outline[0].get("chapter_no") == chapter_no:
        next_outline = next_outline[1:]
    workspace_state["near_7_chapter_outline"] = next_outline
    delivery_mode = ((story_bible.get("serial_runtime") or {}).get("delivery_mode") or DEFAULT_SERIAL_DELIVERY_MODE)
    serial_stage = "published" if delivery_mode == "live_publish" else "stock"
    story_bible = record_chapter_fact_entries(
        story_bible,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        summary=summary,
        plan=plan,
        serial_stage=serial_stage,
        fallback_content=_text(getattr(summary, "event_summary", None), _text(plan.get("goal"), chapter_title)),
    )
    payload = NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )
    story_bible["planner_state"].setdefault("chapter_element_selection", {})[str(chapter_no)] = {
        "focus_character": focus_name,
        "event_type": _text(plan.get("event_type"), ""),
        "progress_kind": _text(plan.get("progress_kind"), ""),
    }
    story_bible["planner_state"]["last_planned_chapter"] = chapter_no + 1
    story_bible["retrospective_state"]["last_review_chapter"] = chapter_no
    story_bible["retrospective_state"]["last_review_notes"] = [
        {
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "core_problem": retrospective.get("core_problem"),
            "next_correction": retrospective.get("next_chapter_correction"),
        }
    ]
    planning_packet = (plan.get("planning_packet") or {}) if isinstance(plan, dict) else {}
    resource_plan = (planning_packet.get("resource_plan") or {}) if isinstance(planning_packet, dict) else {}
    resource_capability_plan = (planning_packet.get("resource_capability_plan") or {}) if isinstance(planning_packet, dict) else {}
    resources_domain = (((story_bible.get("story_domains") or {}).get("resources")) or {})
    apply_resource_plan(resources_domain, resource_plan, chapter_no=chapter_no)
    apply_resource_capability_plan(resources_domain, resource_capability_plan, chapter_no=chapter_no)
    planner_state = story_bible.setdefault("planner_state", build_planner_state())
    if resource_plan:
        planner_state.setdefault("resource_plan_cache", {})[str(chapter_no)] = resource_plan
        history = planner_state.setdefault("resource_plan_history", [])
        history.append({"chapter_no": chapter_no, "resource_names": list(resource_plan.keys())[:6]})
        planner_state["resource_plan_history"] = history[-12:]
    if resource_capability_plan:
        planner_state.setdefault("resource_capability_plan_cache", {})[str(chapter_no)] = resource_capability_plan
        capability_history = planner_state.setdefault("resource_capability_history", [])
        capability_history.append({
            "chapter_no": chapter_no,
            "resource_names": [name for name in list(resource_capability_plan.keys())[:6] if name != "__meta__"],
            "used_ai": bool(((resource_capability_plan.get("__meta__") or {}).get("used_ai"))) if isinstance(resource_capability_plan, dict) else False,
            "cache_status": _text((((resource_capability_plan.get("__meta__") or {}).get("cache_status")))) if isinstance(resource_capability_plan, dict) else "",
        })
        planner_state["resource_capability_history"] = capability_history[-12:]
    continuity_plan = (planning_packet.get("recent_continuity_plan") or {}) if isinstance(planning_packet, dict) else {}
    if continuity_plan:
        planner_state.setdefault("continuity_packet_cache", {})[str(chapter_no)] = continuity_plan
        continuity_history = planner_state.setdefault("rolling_continuity_history", [])
        continuity_history.append(
            {
                "chapter_no": chapter_no,
                "must_continue": _safe_list((((continuity_plan.get("current_chapter_bridge") or {}).get("must_continue")) or []))[:3],
                "preserve_for_next": _safe_list((((continuity_plan.get("lookahead_handoff") or {}).get("preserve_for_next")) or []))[:3],
            }
        )
        planner_state["rolling_continuity_history"] = continuity_history[-12:]
        planner_state["last_continuity_review_chapter"] = chapter_no
    flow_control = story_bible.setdefault("flow_control", build_flow_control())
    recent_event_types = flow_control.setdefault("recent_event_types", [])
    event_type = _text(plan.get("event_type"))
    if event_type:
        recent_event_types.append(event_type)
        flow_control["recent_event_types"] = recent_event_types[-int(flow_control.get("anti_repeat_window", 5) or 5):]
    flow_id = _text(plan.get("flow_template_id"))
    if flow_id:
        recent_flow_ids = flow_control.setdefault("recent_flow_ids", [])
        recent_flow_ids.append(flow_id)
        flow_control["recent_flow_ids"] = recent_flow_ids[-int(flow_control.get("anti_repeat_window", 5) or 5):]
    summary_character_updates = getattr(summary, "character_updates", None) or {}
    summary_resource_updates = _summary_resource_updates(summary)
    summary_monster_updates = _summary_monster_updates(summary)
    touched_entities = {
        "character": [
            name
            for name in [
                protagonist_name,
                focus_name,
                *summary_character_names,
            ]
            if name
        ],
        "resource": [
            name
            for name in _safe_list(
                list((resource_plan or {}).keys())
                + list((resource_capability_plan or {}).keys())
                + list(summary_resource_updates.keys())
            )
            if name and name != "__meta__"
        ],
        "monster": [name for name in _safe_list(list(summary_monster_updates.keys())) if name],
        "relation": [f"{protagonist_name}::{focus_name}"] if focus_name else [],
        "faction": list((((planning_packet.get("selected_elements") or {}).get("factions")) or [])),
    }
    evaluate_story_elements_importance(
        story_bible=story_bible,
        protagonist_name=protagonist_name,
        scope="post_chapter",
        chapter_no=chapter_no,
        plan=plan,
        recent_summaries=[
            {
                "chapter_no": chapter_no,
                "event_summary": _text(getattr(summary, "event_summary", None), chapter_title),
                "open_hooks": list(getattr(summary, "open_hooks", []) or []),
            }
        ],
        touched_entities=touched_entities,
        allow_ai=True,
    )
    story_bible["story_workspace"] = workspace_state
    story_bible = _ensure_story_bible_foundation(
        story_bible,
        payload=payload,
        global_outline=story_bible.get("global_outline") or {},
        active_arc=story_bible.get("active_arc") or {},
    )
    runtime = ensure_serial_runtime(story_bible)
    runtime["last_chapter_review"] = retrospective
    story_bible["serial_runtime"] = runtime
    story_bible = refresh_planning_views(story_bible, chapter_no)
    story_bible = set_pipeline_target(story_bible, next_chapter_no=chapter_no + 1, stage="summary_and_review", last_completed_chapter_no=chapter_no)
    update_story_state_bucket(
        story_bible,
        last_chapter_update={
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "delivery_mode": delivery_mode,
            "recent_progress_count": len(workspace_state.get("recent_progress", [])),
        },
    )
    return sync_long_term_state(story_bible, novel)


def build_story_workspace_snapshot(novel: Novel) -> dict[str, Any]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    workspace_state = ensure_story_workspace(story_bible)
    return {
        "novel_id": novel.id,
        "title": novel.title,
        "story_bible_meta": story_bible.get("story_bible_meta", {}),
        "project_card": story_bible.get("project_card", {}),
        "world_bible": story_bible.get("world_bible", {}),
        "cultivation_system": story_bible.get("cultivation_system", {}),
        "power_system": story_bible.get("power_system", {}),
        "opening_constraints": story_bible.get("opening_constraints", {}),
        "story_domains": story_bible.get("story_domains", {}),
        "template_library": story_bible.get("template_library", {}),
        "planner_state": story_bible.get("planner_state", {}),
        "retrospective_state": story_bible.get("retrospective_state", {}),
        "flow_control": story_bible.get("flow_control", {}),
        "serial_rules": story_bible.get("serial_rules", {}),
        "serial_runtime": story_bible.get("serial_runtime", {}),
        "fact_ledger": story_bible.get("fact_ledger", {}),
        "hard_fact_guard": compact_hard_fact_guard(story_bible.get("hard_fact_guard", {})),
        "long_term_state": story_bible.get("long_term_state", {}),
        "initialization_packet": story_bible.get("initialization_packet", {}),
        "current_volume_card": _current_volume_card(story_bible, novel.current_chapter_no + 1),
        "story_workspace": workspace_state,
        "planning_layers": story_bible.get("planning_layers", {}),
        "planning_state": story_bible.get("workflow_state", {}),
        "continuity_rules": story_bible.get("continuity_rules", list(DEFAULT_CONTINUITY_RULES)),
        "daily_workflow": story_bible.get("daily_workflow", {}),
        "story_state": story_bible.get("story_state", {}),
    }
