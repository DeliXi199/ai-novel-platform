from __future__ import annotations

from copy import deepcopy
from typing import Any


ROLE_REFRESH_FUNCTIONS = {
    "先帮后反帮": "行动搭档",
    "共患难绑定": "行动搭档",
    "团队锚点": "行动搭档",
    "交易成线": "交易接口",
    "远端盟友": "资源线索源",
    "长期压迫源": "压力放大器",
    "先敌后友": "压力放大器",
    "镜像对照": "镜像对照位",
    "关键反转位": "背刺风险位",
    "旧账回潮": "秘密知情人",
}


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dedupe_texts(values: list[Any] | None, *, limit: int = 6) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values or []:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def _casting_action_label(action: str) -> str:
    mapping = {
        "new_core_entry": "补新人",
        "role_refresh": "旧人换功能",
    }
    return mapping.get(_text(action), _text(action) or "人物投放")



def _find_matching_moved_action(summary: dict[str, Any] | None, *, chapter_no: int, action: str = "", target: str = "") -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    moved_actions = [item for item in (summary.get("moved_actions") or []) if isinstance(item, dict)]
    wanted_action = _text(action)
    wanted_target = _text(target)
    fallback: dict[str, Any] | None = None
    for item in moved_actions:
        to_chapter = int(item.get("to_chapter", 0) or 0)
        if to_chapter != int(chapter_no or 0):
            continue
        item_action = _text(item.get("action"))
        item_target = _text(item.get("target"))
        if wanted_action and item_action != wanted_action:
            continue
        if wanted_target and item_target and item_target != wanted_target:
            continue
        if wanted_target and not item_target:
            continue
        return item
    if wanted_action or wanted_target:
        return None
    for item in moved_actions:
        if int(item.get("to_chapter", 0) or 0) == int(chapter_no or 0):
            fallback = item
            break
    return fallback


def build_chapter_casting_runtime_summary(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    plan: dict[str, Any] | None = None,
    stage_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chapter_no = int(chapter_no or 0)
    plan = plan or {}
    stage_hint = stage_hint or {}
    action = _text(plan.get("stage_casting_action"), _text(stage_hint.get("planned_action")))
    target = _text(plan.get("stage_casting_target"), _text(stage_hint.get("planned_target")))
    planned_note = _text(plan.get("stage_casting_note"), _text(stage_hint.get("planned_note")))
    review_note = _text(plan.get("stage_casting_review_note"))
    action_label = _casting_action_label(action)
    active_summary = summarize_arc_casting_layout_review((story_bible or {}).get("active_arc") or {}, limit=6)
    pending_summary = summarize_arc_casting_layout_review((story_bible or {}).get("pending_arc") or {}, limit=6)
    moved = _find_matching_moved_action(active_summary, chapter_no=chapter_no, action=action, target=target)
    source_arc = "active"
    if moved is None:
        moved = _find_matching_moved_action(pending_summary, chapter_no=chapter_no, action=action, target=target)
        source_arc = "pending"

    final_should_execute = bool(stage_hint.get("final_should_execute_planned_action", stage_hint.get("should_execute_planned_action")))
    final_do_not_force = bool(stage_hint.get("final_do_not_force_action", stage_hint.get("do_not_force_action")))
    final_recommended_action = _text(stage_hint.get("final_recommended_action"), _text(stage_hint.get("recommended_action")))
    ai_reason = _text(stage_hint.get("ai_stage_casting_reason"))
    chapter_hint = _text(stage_hint.get("chapter_hint"))
    watchouts = _dedupe_texts(stage_hint.get("watchouts"), limit=4)

    runtime_note = "本章人物投放默认稳住现有人物线。"
    display_lines: list[str] = []
    if moved:
        action_label = _text(moved.get("action_label"), action_label or "人物投放")
        if not action:
            action = _text(moved.get("action"))
        if not target:
            target = _text(moved.get("target"))
        from_chapter = int(moved.get("from_chapter", 0) or 0)
        move_span = f"第{from_chapter}章→第{chapter_no}章" if from_chapter > 0 else f"落到第{chapter_no}章"
        reason = _text(moved.get("reason"), review_note or ai_reason or chapter_hint)
        runtime_note = f"本章承接被挪来的{action_label}{(' · ' + target) if target else ''}，{move_span}。"
        display_lines.append(runtime_note)
        if reason:
            display_lines.append(f"改动原因：{reason[:72]}")
    elif action:
        if final_should_execute:
            runtime_note = f"本章承担{action_label}{(' · ' + target) if target else ''}，宜自然落地，别分心双塞。"
        elif final_do_not_force:
            runtime_note = f"本章原本挂了{action_label}{(' · ' + target) if target else ''}，但这章别硬塞。"
        else:
            runtime_note = f"本章可轻量考虑{action_label}{(' · ' + target) if target else ''}，但以正文顺滑为先。"
        display_lines.append(runtime_note)
        if review_note:
            display_lines.append(f"排法复核：{review_note[:72]}")
    elif chapter_hint:
        runtime_note = chapter_hint[:96]
        display_lines.append(runtime_note)

    if planned_note and planned_note not in " ".join(display_lines):
        display_lines.append(f"原计划：{planned_note[:72]}")
    if ai_reason and ai_reason not in " ".join(display_lines):
        display_lines.append(f"AI复核：{ai_reason[:72]}")
    if final_recommended_action:
        display_lines.append(f"最终建议：{final_recommended_action}")
    for item in watchouts[:2]:
        display_lines.append(f"注意：{item[:60]}")

    return {
        "chapter_no": chapter_no,
        "action": action or None,
        "action_label": action_label or None,
        "target": target or None,
        "planned_note": planned_note[:72] or None,
        "review_note": review_note[:72] or None,
        "carried_from_layout_review": bool(moved),
        "layout_review_source": source_arc if moved else None,
        "moved_from_chapter": int(moved.get("from_chapter", 0) or 0) if moved else None,
        "moved_to_chapter": int(moved.get("to_chapter", 0) or 0) if moved else None,
        "layout_review_reason": _text((moved or {}).get("reason"))[:96] or None,
        "final_should_execute": final_should_execute,
        "final_do_not_force": final_do_not_force,
        "final_recommended_action": final_recommended_action or None,
        "runtime_note": runtime_note[:120],
        "display_lines": display_lines[:5],
    }


def summarize_arc_casting_layout_review(arc: dict[str, Any] | None, *, limit: int = 4) -> dict[str, Any]:
    review = (arc or {}).get("casting_layout_review") or {}
    if not isinstance(review, dict):
        return {}
    raw_adjustments = [item for item in (review.get("chapter_adjustments") or []) if isinstance(item, dict)]
    if not review and not raw_adjustments:
        return {}

    adjustments = []
    for item in raw_adjustments:
        chapter_no = int(item.get("chapter_no", 0) or 0)
        decision = _text(item.get("decision"))
        action = _text(item.get("stage_casting_action"))
        target = _text(item.get("stage_casting_target"))
        note = _text(item.get("note"))[:96]
        if chapter_no <= 0 or not decision:
            continue
        adjustments.append({
            "chapter_no": chapter_no,
            "decision": decision,
            "action": action,
            "target": target,
            "note": note,
            "action_label": _casting_action_label(action),
        })

    unused_drop_indexes: set[int] = {idx for idx, item in enumerate(adjustments) if item["decision"] == "drop"}
    moved_actions: list[dict[str, Any]] = []
    kept_actions: list[dict[str, Any]] = []
    soft_actions: list[dict[str, Any]] = []
    dropped_actions: list[dict[str, Any]] = []

    for item in adjustments:
        decision = item["decision"]
        if decision == "move_here":
            source_idx = None
            for idx in list(unused_drop_indexes):
                candidate = adjustments[idx]
                if candidate.get("action") == item.get("action") and candidate.get("target") == item.get("target"):
                    source_idx = idx
                    break
            from_chapter = None
            if source_idx is not None:
                from_chapter = int(adjustments[source_idx]["chapter_no"] or 0)
                unused_drop_indexes.discard(source_idx)
            moved_actions.append({
                "action": item.get("action"),
                "action_label": item.get("action_label"),
                "target": item.get("target"),
                "from_chapter": from_chapter,
                "to_chapter": int(item.get("chapter_no") or 0),
                "reason": item.get("note") or "AI 复核后认为换章承接更顺。",
            })
        elif decision == "keep":
            kept_actions.append({
                "action": item.get("action"),
                "action_label": item.get("action_label"),
                "target": item.get("target"),
                "chapter_no": int(item.get("chapter_no") or 0),
                "reason": item.get("note") or "AI 复核后认为这一章可以继续承担该动作。",
            })
        elif decision == "soft_consider":
            soft_actions.append({
                "action": item.get("action"),
                "action_label": item.get("action_label"),
                "target": item.get("target"),
                "chapter_no": int(item.get("chapter_no") or 0),
                "reason": item.get("note") or "这章只适合轻量考虑，别硬塞。",
            })

    for idx in sorted(unused_drop_indexes):
        item = adjustments[idx]
        dropped_actions.append({
            "action": item.get("action"),
            "action_label": item.get("action_label"),
            "target": item.get("target"),
            "chapter_no": int(item.get("chapter_no") or 0),
            "reason": item.get("note") or "AI 复核后建议这章先不承担该动作。",
        })

    display_lines: list[str] = []
    for item in moved_actions[:limit]:
        target = f" {item['target']}" if item.get("target") else ""
        move_span = f"第{item['from_chapter']}章→第{item['to_chapter']}章" if item.get("from_chapter") else f"落到第{item['to_chapter']}章"
        display_lines.append(f"{item['action_label']}{target}：{move_span}｜{_text(item.get('reason'))[:48]}")
    for item in dropped_actions[: max(0, limit - len(display_lines))]:
        target = f" {item['target']}" if item.get("target") else ""
        display_lines.append(f"{item['action_label']}{target}：第{item['chapter_no']}章先稳住｜{_text(item.get('reason'))[:48]}")
    for item in kept_actions[: max(0, limit - len(display_lines))]:
        target = f" {item['target']}" if item.get("target") else ""
        display_lines.append(f"{item['action_label']}{target}：保留在第{item['chapter_no']}章｜{_text(item.get('reason'))[:48]}")

    return {
        "window_verdict": _text(review.get("window_verdict")),
        "review_note": _text(review.get("review_note"))[:120],
        "moved_actions": moved_actions[:limit],
        "dropped_actions": dropped_actions[:limit],
        "kept_actions": kept_actions[:limit],
        "soft_consider_actions": soft_actions[:limit],
        "display_lines": display_lines[:limit],
    }


def _latest_stage_review(story_bible: dict[str, Any]) -> dict[str, Any] | None:
    console = (story_bible or {}).get("control_console") or {}
    reviews = console.get("stage_character_reviews") or []
    for item in reversed(reviews):
        if isinstance(item, dict):
            return item
    return None


def _window_chapters(story_bible: dict[str, Any], *, start_chapter: int, end_chapter: int) -> list[dict[str, Any]]:
    if start_chapter <= 0 or end_chapter <= 0 or end_chapter < start_chapter:
        return []
    chapters: dict[int, dict[str, Any]] = {}
    for arc_key in ["active_arc", "pending_arc"]:
        arc = (story_bible or {}).get(arc_key) or {}
        for item in arc.get("chapters") or []:
            if not isinstance(item, dict):
                continue
            chapter_no = int(item.get("chapter_no", 0) or 0)
            if start_chapter <= chapter_no <= end_chapter and chapter_no not in chapters:
                chapters[chapter_no] = item
    return [chapters[key] for key in sorted(chapters)]


def _budget_status(*, limit: int, committed: int) -> str:
    limit = max(int(limit or 0), 0)
    committed = max(int(committed or 0), 0)
    if limit <= 0:
        return "closed" if committed <= 0 else "exceeded"
    if committed > limit:
        return "exceeded"
    if committed == limit:
        return "full"
    if limit > 1 and committed >= limit - 1:
        return "near_limit"
    return "open"


def _classify_casting_defer_cause(item: dict[str, Any]) -> str:
    action = _text(item.get("planned_action"))
    reason = _text(item.get("ai_stage_casting_reason")).lower()
    verdict = _text(item.get("ai_stage_casting_verdict")).lower()
    local_recommended = _text(item.get("local_recommended_action")).lower()
    limit_status = _text(
        item.get("new_core_limit_status") if action == "new_core_entry" else item.get("role_refresh_limit_status")
    ).lower()
    if limit_status in {"full", "near_limit", "exceeded", "closed"}:
        return "budget_pressure"
    if any(token in reason for token in ["上限", "名额", "已满", "太满", "别挤", "窗口太满", "额度"]):
        return "budget_pressure"
    if any(token in reason for token in ["错开", "同章", "重复", "后章", "后一章", "留给下一章", "别连着", "别机械重复"]):
        return "pacing_mismatch"
    if verdict in {"hold_steady", "soft_consider"}:
        return "chapter_fit"
    if verdict == "defer_to_next" and local_recommended in {"consider_new_core_entry", "consider_role_refresh", "balanced_light"}:
        return "chapter_fit"
    return "chapter_fit"


def _build_casting_defer_diagnostics(
    story_bible: dict[str, Any],
    *,
    stage_start_chapter: int,
    stage_end_chapter: int,
) -> dict[str, Any]:
    console = (story_bible or {}).get("control_console") or {}
    history = [
        item
        for item in (console.get("stage_casting_resolution_history") or [])
        if isinstance(item, dict) and stage_start_chapter <= int(item.get("chapter_no", 0) or 0) <= stage_end_chapter
    ]
    history.sort(key=lambda item: int(item.get("chapter_no", 0) or 0))
    compact_recent = []
    deferred_entries = []
    deferred_by_action = {"new_core_entry": 0, "role_refresh": 0}
    deferred_by_target: dict[str, int] = {}
    cause_counts = {"budget_pressure": 0, "chapter_fit": 0, "pacing_mismatch": 0}
    for item in history[-8:]:
        compact_recent.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "planned_action": _text(item.get("planned_action")) or None,
                "planned_target": _text(item.get("planned_target")) or None,
                "ai_verdict": _text(item.get("ai_stage_casting_verdict")) or None,
                "execution_status": _text(item.get("execution_status")) or None,
                "ai_reason": _text(item.get("ai_stage_casting_reason"))[:72] or None,
            }
        )
        status = _text(item.get("execution_status"))
        if status not in {"deferred_after_review", "planned_but_not_landed", "not_executed"}:
            continue
        action = _text(item.get("planned_action"))
        target = _text(item.get("planned_target"))
        cause = _classify_casting_defer_cause(item)
        cause_counts[cause] = cause_counts.get(cause, 0) + 1
        if action:
            deferred_by_action[action] = deferred_by_action.get(action, 0) + 1
        if target:
            deferred_by_target[target] = deferred_by_target.get(target, 0) + 1
        deferred_entries.append(item)

    dominant_cause = ""
    if deferred_entries:
        dominant_cause = max(cause_counts.items(), key=lambda pair: (pair[1], pair[0]))[0]
        if cause_counts.get(dominant_cause, 0) <= 0:
            dominant_cause = ""
    dominant_action = ""
    if deferred_entries:
        dominant_action = max(deferred_by_action.items(), key=lambda pair: (pair[1], pair[0]))[0]
        if deferred_by_action.get(dominant_action, 0) <= 0:
            dominant_action = ""
    repeated_targets = sorted(
        [name for name, count in deferred_by_target.items() if count >= 2],
        key=lambda name: (-deferred_by_target[name], name),
    )

    if not deferred_entries:
        summary = "最近几章人物投放没有明显被 AI 连续打回，下一窗口可按正常节奏安排。"
        bias = "steady"
    elif dominant_cause == "budget_pressure":
        summary = "最近几章人物投放多次被 AI 以名额/拥挤问题延后，说明窗口偏满，下一窗口先消化已有承诺更稳。"
        bias = "shrink_casting"
    elif dominant_cause == "pacing_mismatch":
        summary = "最近几章人物投放更像是节奏不顺或同类动作挤在一起，不是纯名额问题；下一窗口要错章、换对象或降频。"
        bias = "restage_actions"
    else:
        summary = "最近几章人物投放常被 AI 判断为本章不合适，说明章法承接偏弱；下一窗口先让人物线和冲突线更顺，再落动作。"
        bias = "tighten_chapter_fit"

    return {
        "recent_resolution_history": compact_recent,
        "recent_deferred_count": len(deferred_entries),
        "budget_pressure_count": cause_counts.get("budget_pressure", 0),
        "chapter_fit_count": cause_counts.get("chapter_fit", 0),
        "pacing_mismatch_count": cause_counts.get("pacing_mismatch", 0),
        "dominant_defer_cause": dominant_cause or None,
        "dominant_action_blocked": dominant_action or None,
        "repeatedly_deferred_targets": repeated_targets[:3],
        "summary": summary[:96],
        "next_window_bias": bias,
    }


def build_stage_review_window_progress(story_bible: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any]:
    review = review if isinstance(review, dict) else {}
    start_chapter = int(review.get("next_window_start", 0) or 0)
    end_chapter = int(review.get("next_window_end", 0) or 0)
    if start_chapter <= 0 or end_chapter <= 0 or end_chapter < start_chapter:
        return {}

    planned_new_targets: set[str] = set()
    planned_role_targets: set[str] = set()
    for chapter in _window_chapters(story_bible, start_chapter=start_chapter, end_chapter=end_chapter):
        action = _text(chapter.get("stage_casting_action"))
        target = _text(chapter.get("stage_casting_target"))
        if action == "new_core_entry" and target:
            planned_new_targets.add(target)
        elif action == "role_refresh" and target:
            planned_role_targets.add(target)

    core_cast_state = (story_bible or {}).get("core_cast_state") or {}
    binding_history = core_cast_state.get("chapter_binding_history") or []
    executed_new_targets = {
        _text(item.get("slot_id")) or _text(item.get("character"))
        for item in binding_history
        if isinstance(item, dict) and start_chapter <= int(item.get("chapter_no", 0) or 0) <= end_chapter and (_text(item.get("slot_id")) or _text(item.get("character")))
    }

    console = (story_bible or {}).get("control_console") or {}
    role_refresh_history = console.get("role_refresh_history") or []
    executed_role_targets = {
        _text(item.get("character"))
        for item in role_refresh_history
        if isinstance(item, dict) and start_chapter <= int(item.get("chapter_no", 0) or 0) <= end_chapter and _text(item.get("character"))
    }

    resolution_history = [
        item
        for item in (console.get("stage_casting_resolution_history") or [])
        if isinstance(item, dict) and start_chapter <= int(item.get("chapter_no", 0) or 0) <= end_chapter
    ]
    reviewed_new_execute_targets = {
        _text(item.get("planned_target"))
        for item in resolution_history
        if _text(item.get("planned_action")) == "new_core_entry" and bool(item.get("final_should_execute")) and _text(item.get("planned_target"))
    }
    reviewed_new_defer_targets = {
        _text(item.get("planned_target"))
        for item in resolution_history
        if _text(item.get("planned_action")) == "new_core_entry" and not bool(item.get("final_should_execute")) and _text(item.get("planned_target"))
    }
    reviewed_role_execute_targets = {
        _text(item.get("planned_target"))
        for item in resolution_history
        if _text(item.get("planned_action")) == "role_refresh" and bool(item.get("final_should_execute")) and _text(item.get("planned_target"))
    }
    reviewed_role_defer_targets = {
        _text(item.get("planned_target"))
        for item in resolution_history
        if _text(item.get("planned_action")) == "role_refresh" and not bool(item.get("final_should_execute")) and _text(item.get("planned_target"))
    }

    committed_new_targets = planned_new_targets | executed_new_targets
    committed_role_targets = planned_role_targets | executed_role_targets
    max_new_core_entries = max(int(review.get("max_new_core_entries", 0) or 0), 0)
    max_role_refreshes = max(int(review.get("max_role_refreshes", 0) or 0), 0)

    new_core_status = _budget_status(limit=max_new_core_entries, committed=len(committed_new_targets))
    role_refresh_status = _budget_status(limit=max_role_refreshes, committed=len(committed_role_targets))
    compact_resolution_history = []
    for item in sorted(resolution_history, key=lambda payload: int(payload.get("chapter_no", 0) or 0))[-8:]:
        compact_resolution_history.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "planned_action": _text(item.get("planned_action")) or None,
                "planned_target": _text(item.get("planned_target")) or None,
                "ai_verdict": _text(item.get("ai_stage_casting_verdict")) or None,
                "final_should_execute": bool(item.get("final_should_execute")),
                "execution_status": _text(item.get("execution_status")) or None,
                "executed_action": _text(item.get("executed_action")) or None,
                "executed_target": _text(item.get("executed_target")) or None,
            }
        )
    return {
        "planned_new_core_entries": len(planned_new_targets),
        "reviewed_new_core_execute_now": len(reviewed_new_execute_targets),
        "reviewed_new_core_deferred": len(reviewed_new_defer_targets),
        "executed_new_core_entries": len(executed_new_targets),
        "committed_new_core_entries": len(committed_new_targets),
        "planned_new_core_targets": sorted(planned_new_targets),
        "reviewed_new_core_execute_targets": sorted(reviewed_new_execute_targets),
        "reviewed_new_core_defer_targets": sorted(reviewed_new_defer_targets),
        "executed_new_core_targets": sorted(executed_new_targets),
        "new_core_remaining": max(max_new_core_entries - len(committed_new_targets), 0),
        "new_core_limit_status": new_core_status,
        "new_core_limit_reached": new_core_status in {"full", "near_limit", "exceeded"},
        "planned_role_refreshes": len(planned_role_targets),
        "reviewed_role_refresh_execute_now": len(reviewed_role_execute_targets),
        "reviewed_role_refresh_deferred": len(reviewed_role_defer_targets),
        "executed_role_refreshes": len(executed_role_targets),
        "committed_role_refreshes": len(committed_role_targets),
        "planned_role_refresh_targets": sorted(planned_role_targets),
        "reviewed_role_refresh_execute_targets": sorted(reviewed_role_execute_targets),
        "reviewed_role_refresh_defer_targets": sorted(reviewed_role_defer_targets),
        "executed_role_refresh_targets": sorted(executed_role_targets),
        "role_refresh_remaining": max(max_role_refreshes - len(committed_role_targets), 0),
        "role_refresh_limit_status": role_refresh_status,
        "role_refresh_limit_reached": role_refresh_status in {"full", "near_limit", "exceeded"},
        "casting_resolution_history": compact_resolution_history,
    }


def build_chapter_stage_casting_hint(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chapter_no = int(chapter_no or 0)
    if chapter_no <= 0:
        return {}
    review = stage_character_review_for_window(story_bible, current_chapter_no=max(chapter_no - 1, 0))
    if not isinstance(review, dict) or not review:
        return {}
    progress = review.get("window_progress") or build_stage_review_window_progress(story_bible, review)
    action = _text((plan or {}).get("stage_casting_action"))
    target = _text((plan or {}).get("stage_casting_target"))
    note = _text((plan or {}).get("stage_casting_note"))
    strategy = _text(review.get("casting_strategy"), "hold_steady")
    start_chapter = int(review.get("next_window_start", 0) or 0)
    end_chapter = int(review.get("next_window_end", 0) or 0)
    in_window = bool(start_chapter and end_chapter and start_chapter <= chapter_no <= end_chapter)

    candidate_slot_ids = _dedupe_texts(review.get("candidate_slot_ids"), limit=2)
    role_refresh_targets = _dedupe_texts(review.get("role_refresh_targets"), limit=2)
    new_core_status = _text(progress.get("new_core_limit_status"), "open")
    role_refresh_status = _text(progress.get("role_refresh_limit_status"), "open")
    new_core_remaining = max(int(progress.get("new_core_remaining", 0) or 0), 0)
    role_refresh_remaining = max(int(progress.get("role_refresh_remaining", 0) or 0), 0)
    new_core_open = new_core_status not in {"full", "exceeded", "closed"}
    role_refresh_open = role_refresh_status not in {"full", "exceeded", "closed"}

    should_execute = False
    do_not_force_action = False
    recommended_action = "hold_steady"
    action_priority = "hold"
    chapter_hint = "本章人物投放以稳住现有人物线为主。"
    watchouts: list[str] = []

    if not in_window:
        do_not_force_action = True
        chapter_hint = "当前章节不在本轮五章窗口内，不要硬塞补新人或旧人换功能。"
        watchouts.append("不在当前五章窗口")
    elif action == "new_core_entry":
        if target and target in candidate_slot_ids and new_core_open:
            should_execute = True
            recommended_action = "execute_new_core_entry"
            action_priority = "must_execute"
            chapter_hint = f"本章承担落新核心位任务，优先让 {target} 自然落地，但只做这一件。"
            watchouts.append("本章承担落新核心位")
        else:
            do_not_force_action = True
            action_priority = "avoid"
            chapter_hint = "本章原本想落新核心位，但当前窗口名额或目标不匹配，不要硬塞。"
            watchouts.append("新核心位名额受限")
    elif action == "role_refresh":
        if target and target in role_refresh_targets and role_refresh_open:
            should_execute = True
            recommended_action = "execute_role_refresh"
            action_priority = "must_execute"
            chapter_hint = f"本章承担旧角色换功能任务，优先让 {target} 换成更能带剧情的作用位。"
            watchouts.append("本章承担旧角色换功能")
        else:
            do_not_force_action = True
            action_priority = "avoid"
            chapter_hint = "本章原本想给旧角色换功能，但当前窗口名额或目标不匹配，不要硬推。"
            watchouts.append("旧角色换功能名额受限")
    else:
        do_not_force_action = True
        if strategy == "introduce_one_new" and candidate_slot_ids and new_core_open:
            recommended_action = "consider_new_core_entry"
            action_priority = "soft_consider"
            chapter_hint = "这轮允许补一个新人接线，但若本章没有明确承担动作，就不要硬塞。"
            watchouts.append("补新人最多 1 次")
        elif strategy == "prefer_refresh_existing" and role_refresh_targets and role_refresh_open:
            recommended_action = "consider_role_refresh"
            action_priority = "soft_consider"
            chapter_hint = "这轮更适合抬旧人顶功能；若本章没明确承担动作，也别强行改。"
            watchouts.append("优先抬旧人")
        elif strategy == "balanced_light":
            recommended_action = "balanced_light"
            action_priority = "soft_consider"
            chapter_hint = "这轮可以轻推补新人或旧人换功能，但尽量错开章节，不要本章双塞。"
            watchouts.append("同章别双塞")
        else:
            chapter_hint = "这轮先稳住现有人物线，本章默认不承担额外人物投放动作。"

    if strategy == "balanced_light":
        watchouts.append("新人落地与旧人换功能要错章")
    if new_core_status in {"full", "exceeded"}:
        watchouts.append("新核心位名额已满")
    if role_refresh_status in {"full", "exceeded"}:
        watchouts.append("旧角色换功能名额已满")

    result = {
        "active_window": in_window,
        "window": [start_chapter, end_chapter],
        "casting_strategy": strategy,
        "planned_action": action or None,
        "planned_target": target or None,
        "planned_note": note or None,
        "candidate_slot_ids": candidate_slot_ids,
        "role_refresh_targets": role_refresh_targets,
        "max_new_core_entries": max(int(review.get("max_new_core_entries", 0) or 0), 0),
        "max_role_refreshes": max(int(review.get("max_role_refreshes", 0) or 0), 0),
        "new_core_remaining": new_core_remaining,
        "role_refresh_remaining": role_refresh_remaining,
        "new_core_limit_status": new_core_status,
        "role_refresh_limit_status": role_refresh_status,
        "should_execute_planned_action": should_execute,
        "do_not_force_action": do_not_force_action,
        "recommended_action": recommended_action,
        "action_priority": action_priority,
        "chapter_hint": chapter_hint[:96],
        "watchouts": _dedupe_texts(watchouts, limit=5),
    }
    return result


def record_stage_casting_resolution(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    plan: dict[str, Any],
) -> dict[str, Any]:
    packet = (plan or {}).get("planning_packet") or {}
    stage_hint = (packet.get("chapter_stage_casting_hint") or {}) if isinstance(packet, dict) else {}
    planned_action = _text(stage_hint.get("planned_action"), _text((plan or {}).get("stage_casting_action")))
    planned_target = _text(stage_hint.get("planned_target"), _text((plan or {}).get("stage_casting_target")))
    planned_note = _text(stage_hint.get("planned_note"), _text((plan or {}).get("stage_casting_note")))
    local_should_execute = bool(stage_hint.get("should_execute_planned_action"))
    local_do_not_force = bool(stage_hint.get("do_not_force_action"))
    local_recommended_action = _text(stage_hint.get("recommended_action"))
    ai_verdict = _text(stage_hint.get("ai_stage_casting_verdict"))
    ai_reason = _text(stage_hint.get("ai_stage_casting_reason"))
    ai_should_execute = bool(stage_hint.get("ai_should_execute_planned_action")) if "ai_should_execute_planned_action" in stage_hint else None
    ai_do_not_force = bool(stage_hint.get("ai_do_not_force_action")) if "ai_do_not_force_action" in stage_hint else None
    final_should_execute = bool(stage_hint.get("final_should_execute_planned_action", stage_hint.get("should_execute_planned_action")))
    final_do_not_force = bool(stage_hint.get("final_do_not_force_action", stage_hint.get("do_not_force_action")))
    final_recommended_action = _text(stage_hint.get("final_recommended_action"), local_recommended_action)
    final_action_priority = _text(stage_hint.get("final_action_priority"), _text(stage_hint.get("action_priority")))

    executed_action = ""
    executed_target = ""
    execution_status = "no_planned_action"

    if planned_action == "new_core_entry":
        binding_history = (((story_bible or {}).get("core_cast_state") or {}).get("chapter_binding_history") or [])
        executed_binding = next(
            (
                item
                for item in reversed(binding_history)
                if isinstance(item, dict)
                and int(item.get("chapter_no", 0) or 0) == int(chapter_no or 0)
                and _text(item.get("slot_id")) == planned_target
            ),
            None,
        )
        if executed_binding:
            executed_action = "new_core_entry"
            executed_target = _text(executed_binding.get("slot_id")) or planned_target
            execution_status = "executed"
        elif final_should_execute:
            execution_status = "planned_but_not_landed"
        elif planned_action:
            execution_status = "deferred_after_review" if ai_verdict in {"defer_to_next", "hold_steady", "soft_consider"} or final_do_not_force else "not_executed"
    elif planned_action == "role_refresh":
        role_refresh_history = (((story_bible or {}).get("control_console") or {}).get("role_refresh_history") or [])
        executed_refresh = next(
            (
                item
                for item in reversed(role_refresh_history)
                if isinstance(item, dict)
                and int(item.get("chapter_no", 0) or 0) == int(chapter_no or 0)
                and _text(item.get("character")) == planned_target
            ),
            None,
        )
        if executed_refresh:
            executed_action = "role_refresh"
            executed_target = _text(executed_refresh.get("character")) or planned_target
            execution_status = "executed"
        elif final_should_execute:
            execution_status = "planned_but_not_landed"
        elif planned_action:
            execution_status = "deferred_after_review" if ai_verdict in {"defer_to_next", "hold_steady", "soft_consider"} or final_do_not_force else "not_executed"

    resolution_status = "no_action"
    if planned_action:
        if local_should_execute and final_should_execute:
            resolution_status = "confirmed_execute"
        elif local_should_execute and not final_should_execute:
            resolution_status = "deferred_by_ai_review"
        elif not local_should_execute and final_should_execute:
            resolution_status = "promoted_after_review"
        elif final_do_not_force:
            resolution_status = "held_after_review"
        else:
            resolution_status = "planned_without_execution"
    if execution_status == "executed":
        resolution_status = "executed"

    entry = {
        "chapter_no": int(chapter_no or 0),
        "planned_action": planned_action or None,
        "planned_target": planned_target or None,
        "planned_note": planned_note[:64] or None,
        "local_should_execute": local_should_execute,
        "local_do_not_force": local_do_not_force,
        "local_recommended_action": local_recommended_action or None,
        "new_core_limit_status": _text(stage_hint.get("new_core_limit_status")) or None,
        "role_refresh_limit_status": _text(stage_hint.get("role_refresh_limit_status")) or None,
        "chapter_stage_casting_hint": _text(stage_hint.get("chapter_hint"))[:96] or None,
        "ai_stage_casting_verdict": ai_verdict or None,
        "ai_stage_casting_reason": ai_reason[:96] or None,
        "ai_should_execute": ai_should_execute,
        "ai_do_not_force": ai_do_not_force,
        "final_should_execute": final_should_execute,
        "final_do_not_force": final_do_not_force,
        "final_recommended_action": final_recommended_action or None,
        "final_action_priority": final_action_priority or None,
        "executed_action": executed_action or None,
        "executed_target": executed_target or None,
        "execution_status": execution_status,
        "resolution_status": resolution_status,
    }
    console = (story_bible or {}).setdefault("control_console", {})
    history = [item for item in (console.get("stage_casting_resolution_history") or []) if isinstance(item, dict) and int(item.get("chapter_no", 0) or 0) != int(chapter_no or 0)]
    history.append(entry)
    console["stage_casting_resolution_history"] = history[-40:]
    return entry


def apply_role_refresh_execution(story_bible: dict[str, Any], *, chapter_no: int, plan: dict[str, Any]) -> dict[str, Any] | None:
    action = _text((plan or {}).get("stage_casting_action"))
    if action != "role_refresh":
        return None
    character = _text((plan or {}).get("stage_casting_target"))
    if not character:
        return None

    latest_review = _latest_stage_review(story_bible) or {}
    suggestion = {}
    for item in _safe_list(latest_review.get("role_refresh_suggestions")):
        if isinstance(item, dict) and _text(item.get("character")) == character:
            suggestion = item
            break
    suggested_function = _text(suggestion.get("suggested_function"), _text((plan or {}).get("stage_casting_note"), "作用位调整"))
    reason = _text(suggestion.get("reason"), _text((plan or {}).get("stage_casting_note"), "本章开始给旧角色换作用位。"))

    domains = (story_bible or {}).setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    card = characters.get(character) if isinstance(characters, dict) else None
    if isinstance(card, dict):
        card["current_plot_function"] = suggested_function
        card["function_refresh_note"] = reason[:48]
        card["last_role_refresh_chapter"] = int(chapter_no or 0)

    console = (story_bible or {}).setdefault("control_console", {})
    legacy = (console.setdefault("character_cards", {}) or {}).get(character)
    if isinstance(legacy, dict):
        legacy["current_plot_function"] = suggested_function
        legacy["possible_change"] = reason[:48]
    history = console.setdefault("role_refresh_history", [])
    entry = {
        "chapter_no": int(chapter_no or 0),
        "character": character,
        "suggested_function": suggested_function,
        "reason": reason[:48],
    }
    if not any(int(item.get("chapter_no", 0) or 0) == entry["chapter_no"] and _text(item.get("character")) == character for item in history if isinstance(item, dict)):
        history.append(entry)
    console["role_refresh_history"] = history[-20:]
    return entry


def _character_index(story_bible: dict[str, Any]) -> dict[str, dict[str, Any]]:
    characters = (((story_bible or {}).get("story_domains") or {}).get("characters") or [])
    index: dict[str, dict[str, Any]] = {}
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if name:
            index[name] = item
    return index


def _pick_role_refresh_function(*, binding_pattern: str, current_role_hint: str, trigger: str) -> str:
    for key, value in ROLE_REFRESH_FUNCTIONS.items():
        if key and key in binding_pattern:
            return value
    if "partner" in current_role_hint or "support" in current_role_hint:
        return "行动搭档"
    if "faction" in current_role_hint or "agent" in current_role_hint:
        return "势力代理人"
    if "resource" in current_role_hint:
        return "资源线索源"
    if "工具" in trigger or "传话" in trigger:
        return "行动搭档"
    return "关系调停位"


def should_run_stage_character_review(story_bible: dict[str, Any], *, current_chapter_no: int) -> bool:
    if int(current_chapter_no or 0) <= 0:
        return False
    retrospective_state = (story_bible or {}).get("retrospective_state") or {}
    interval = max(int(retrospective_state.get("scheduled_review_interval", 5) or 5), 1)
    if current_chapter_no % interval != 0:
        return False
    last_review_chapter = int(retrospective_state.get("last_stage_review_chapter", 0) or 0)
    return last_review_chapter < current_chapter_no



def build_stage_character_review_snapshot(
    story_bible: dict[str, Any],
    *,
    current_chapter_no: int,
    recent_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    console = (story_bible or {}).get("control_console") or {}
    core_cast = (story_bible or {}).get("core_cast_state") or {}
    schedule = console.get("character_relation_schedule") or {}
    review_interval = max(int(((story_bible or {}).get("retrospective_state") or {}).get("scheduled_review_interval", 5) or 5), 1)
    stage_start = max(1, current_chapter_no - review_interval + 1)
    stage_end = current_chapter_no
    next_window_start = current_chapter_no + 1
    next_window_end = current_chapter_no + review_interval

    active_core = []
    due_slots = []
    for slot in core_cast.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        bound = _text(slot.get("bound_character"))
        window = slot.get("entry_chapter_window") or [0, 0]
        start = int(window[0] or 0) if isinstance(window, list) and window else 0
        end = int(window[1] or 0) if isinstance(window, list) and len(window) > 1 else start
        if bound:
            active_core.append(
                {
                    "slot_id": _text(slot.get("slot_id")),
                    "character": bound,
                    "appearance_frequency": _text(slot.get("appearance_frequency"), "中频"),
                    "long_term_relation_line": _text(slot.get("long_term_relation_line"))[:48],
                    "last_appeared_chapter": int(slot.get("last_appeared_chapter") or 0),
                }
            )
        elif next_window_start <= max(end, start) + 1:
            due_slots.append(
                {
                    "slot_id": _text(slot.get("slot_id")),
                    "entry_phase": _text(slot.get("entry_phase")),
                    "entry_window": [start, end],
                    "binding_pattern": _text(slot.get("binding_pattern"))[:36],
                    "first_entry_mission": _text(slot.get("first_entry_mission"))[:36],
                    "appearance_frequency": _text(slot.get("appearance_frequency"), "中频"),
                }
            )
    active_core.sort(key=lambda item: int(item.get("last_appeared_chapter") or 0))
    due_slots.sort(key=lambda item: (int((item.get("entry_window") or [999])[0] or 999), _text(item.get("slot_id"))))

    recent_retrospectives = []
    for item in (console.get("chapter_retrospectives") or [])[-review_interval:]:
        if not isinstance(item, dict):
            continue
        recent_retrospectives.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "title": _text(item.get("title")),
                "core_problem": _text(item.get("core_problem"))[:52],
                "next_correction": _text(item.get("next_chapter_correction"))[:72],
                "character_flatness_risk": _text(item.get("character_flatness_risk")),
                "repetition_risk": _text(item.get("repetition_risk")),
            }
        )

    summaries = []
    for item in (recent_summaries or [])[-review_interval:]:
        if not isinstance(item, dict):
            continue
        summaries.append(
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "title": _text(item.get("title")),
                "event_summary": _text(item.get("event_summary"))[:72],
            }
        )

    appearance_schedule = (schedule.get("appearance_schedule") or {}) if isinstance(schedule, dict) else {}
    relationship_schedule = (schedule.get("relationship_schedule") or {}) if isinstance(schedule, dict) else {}
    priority_characters = []
    for item in (appearance_schedule.get("priority_characters") or [])[:6]:
        if not isinstance(item, dict):
            continue
        priority_characters.append(
            {
                "name": _text(item.get("name")),
                "due_status": _text(item.get("due_status")),
                "schedule_score": int(item.get("schedule_score") or 0),
                "appearance_frequency": _text(item.get("appearance_frequency"), "中频"),
                "core_cast_slot_id": _text(item.get("core_cast_slot_id")),
            }
        )
    priority_relations = []
    for item in (relationship_schedule.get("priority_relations") or [])[:6]:
        if not isinstance(item, dict):
            continue
        priority_relations.append(
            {
                "relation_id": _text(item.get("relation_id")),
                "due_status": _text(item.get("due_status")),
                "schedule_score": int(item.get("schedule_score") or 0),
                "interaction_depth": _text(item.get("interaction_depth")),
                "push_direction": _text(item.get("push_direction")),
            }
        )

    character_index = _character_index(story_bible)
    slot_by_character = {item.get("character"): item for item in active_core if _text(item.get("character"))}
    retrospective_text = "\n".join(
        filter(
            None,
            [
                _text(item.get("core_problem"))
                + " "
                + _text(item.get("character_flatness_risk"))
                + " "
                + _text(item.get("next_correction"))
                for item in recent_retrospectives
            ],
        )
    )
    role_refresh_candidates = []
    candidate_names = _dedupe_texts(
        [
            *(item.get("character") for item in active_core),
            *(item.get("name") for item in priority_characters if _text(item.get("core_cast_slot_id")) or _text(item.get("name")) in slot_by_character),
        ],
        limit=6,
    )
    for name in candidate_names:
        slot = slot_by_character.get(name) or {}
        card = character_index.get(name) or {}
        trigger_tags: list[str] = []
        if name and name in retrospective_text and ("工具人" in retrospective_text or "扁平" in retrospective_text or "戏份偏薄" in retrospective_text):
            trigger_tags.append("工具人风险")
        last_appeared = int(slot.get("last_appeared_chapter") or card.get("last_appeared_chapter") or 0)
        if last_appeared and last_appeared <= current_chapter_no - 3:
            trigger_tags.append("回场后可换作用")
        due_status = ""
        for item in priority_characters:
            if _text(item.get("name")) == name:
                due_status = _text(item.get("due_status"))
                break
        if due_status in {"该回场", "可推进"}:
            trigger_tags.append(due_status)
        if not trigger_tags:
            trigger_tags.append("人物线可扩")
        role_refresh_candidates.append(
            {
                "name": name,
                "current_role_hint": _text(card.get("role_type") or card.get("role_archetype") or slot.get("long_term_relation_line") or card.get("importance_tier"))[:20],
                "binding_pattern": _text(card.get("binding_pattern") or slot.get("long_term_relation_line") or "")[:24],
                "appearance_frequency": _text(card.get("appearance_frequency") or slot.get("appearance_frequency"), "中频"),
                "last_appeared_chapter": last_appeared,
                "trigger": " / ".join(_dedupe_texts(trigger_tags, limit=3))[:40],
            }
        )
    role_refresh_candidates.sort(key=lambda item: (0 if "工具人风险" in _text(item.get("trigger")) else 1, int(item.get("last_appeared_chapter") or 0), _text(item.get("name"))))
    casting_defer_diagnostics = _build_casting_defer_diagnostics(
        story_bible,
        stage_start_chapter=stage_start,
        stage_end_chapter=stage_end,
    )

    return {
        "stage_start_chapter": stage_start,
        "stage_end_chapter": stage_end,
        "next_window_start": next_window_start,
        "next_window_end": next_window_end,
        "active_core_characters": active_core[:5],
        "due_unbound_slots": due_slots[:3],
        "recent_retrospectives": recent_retrospectives,
        "recent_summaries": summaries,
        "priority_characters": priority_characters,
        "priority_relations": priority_relations,
        "role_refresh_candidates": role_refresh_candidates[:4],
        "casting_defer_diagnostics": casting_defer_diagnostics,
    }



def heuristic_stage_character_review(snapshot: dict[str, Any]) -> dict[str, Any]:
    active_core = _safe_list(snapshot.get("active_core_characters"))
    priority_characters = _safe_list(snapshot.get("priority_characters"))
    priority_relations = _safe_list(snapshot.get("priority_relations"))
    due_slots = _safe_list(snapshot.get("due_unbound_slots"))
    role_refresh_candidates = _safe_list(snapshot.get("role_refresh_candidates"))
    casting_defer_diagnostics = (snapshot.get("casting_defer_diagnostics") or {}) if isinstance(snapshot, dict) else {}

    focus_characters = _dedupe_texts([
        *(item.get("name") for item in priority_characters[:3]),
        *(item.get("character") for item in active_core[:2]),
    ], limit=4)
    supporting_characters = _dedupe_texts([
        *(item.get("character") for item in active_core[-2:]),
        *(item.get("name") for item in priority_characters[3:5]),
    ], limit=3)
    defer_characters = _dedupe_texts([
        item.get("name")
        for item in priority_characters
        if _text(item.get("due_status")) in {"刚出场过", "暂缓", "可缓一缓"}
    ], limit=3)
    priority_relation_ids = _dedupe_texts([item.get("relation_id") for item in priority_relations[:2]], limit=2)
    light_touch_relation_ids = _dedupe_texts([item.get("relation_id") for item in priority_relations[2:4]], limit=3)
    defer_relation_ids = _dedupe_texts([
        item.get("relation_id")
        for item in priority_relations
        if _text(item.get("due_status")) in {"轻触或略过", "暂缓"}
    ], limit=3)
    candidate_slot_ids = _dedupe_texts([item.get("slot_id") for item in due_slots[:2]], limit=2)

    role_refresh_targets = _dedupe_texts(
        [item.get("name") for item in role_refresh_candidates if "工具人风险" in _text(item.get("trigger"))][:2]
        or [item.get("name") for item in role_refresh_candidates[:1]],
        limit=2,
    )
    role_refresh_suggestions = []
    for item in role_refresh_candidates[:2]:
        name = _text(item.get("name"))
        if not name or name not in role_refresh_targets:
            continue
        new_function = _pick_role_refresh_function(
            binding_pattern=_text(item.get("binding_pattern")),
            current_role_hint=_text(item.get("current_role_hint")),
            trigger=_text(item.get("trigger")),
        )
        role_refresh_suggestions.append(
            {
                "character": name,
                "suggested_function": new_function,
                "reason": f"{_text(item.get('trigger'), '人物线可扩')}，别再只做工具位。"[:40],
            }
        )

    intro_pressure = len(candidate_slot_ids) + (1 if len(focus_characters) <= 2 and due_slots else 0)
    refresh_pressure = len(role_refresh_targets) + sum(1 for item in role_refresh_candidates if "工具人风险" in _text(item.get("trigger")))
    if due_slots and not active_core:
        intro_pressure += 2

    defer_count = int(casting_defer_diagnostics.get("recent_deferred_count", 0) or 0)
    dominant_defer_cause = _text(casting_defer_diagnostics.get("dominant_defer_cause"))
    dominant_action_blocked = _text(casting_defer_diagnostics.get("dominant_action_blocked"))
    if dominant_defer_cause == "budget_pressure":
        intro_pressure = max(intro_pressure - 2, 0)
        refresh_pressure = max(refresh_pressure - 2, 0)
    elif dominant_defer_cause == "pacing_mismatch":
        if dominant_action_blocked == "new_core_entry":
            intro_pressure = max(intro_pressure - 3, 0)
        elif dominant_action_blocked == "role_refresh":
            refresh_pressure = max(refresh_pressure - 3, 0)
    elif dominant_defer_cause == "chapter_fit":
        if dominant_action_blocked == "new_core_entry":
            intro_pressure = max(intro_pressure - 1, 0)
        elif dominant_action_blocked == "role_refresh":
            refresh_pressure = max(refresh_pressure - 1, 0)

    if defer_count >= 2 and dominant_defer_cause == "budget_pressure":
        if dominant_action_blocked == "new_core_entry" and role_refresh_targets:
            casting_strategy = "prefer_refresh_existing"
        else:
            casting_strategy = "hold_steady"
    elif defer_count >= 2 and dominant_defer_cause == "pacing_mismatch":
        if dominant_action_blocked == "new_core_entry" and role_refresh_targets:
            casting_strategy = "prefer_refresh_existing"
        elif dominant_action_blocked == "role_refresh" and candidate_slot_ids and not role_refresh_targets:
            casting_strategy = "introduce_one_new"
        else:
            casting_strategy = "hold_steady"
    elif defer_count >= 2 and dominant_defer_cause == "chapter_fit":
        casting_strategy = "hold_steady"
    elif refresh_pressure >= intro_pressure + 2:
        casting_strategy = "prefer_refresh_existing"
    elif intro_pressure >= refresh_pressure + 2 and candidate_slot_ids:
        casting_strategy = "introduce_one_new"
    elif candidate_slot_ids and role_refresh_targets:
        casting_strategy = "balanced_light"
    else:
        casting_strategy = "hold_steady"

    if casting_strategy == "prefer_refresh_existing":
        should_intro = False
        should_refresh_roles = bool(role_refresh_targets)
        max_new_core_entries = 0
        max_role_refreshes = 1 if should_refresh_roles else 0
        candidate_slot_ids = []
        role_refresh_targets = role_refresh_targets[:1]
        role_refresh_suggestions = [item for item in role_refresh_suggestions if _text(item.get("character")) in role_refresh_targets][:1]
        strategy_note = "下一规划窗口先抬旧人顶功能，暂时不要再挤新人进来。"
    elif casting_strategy == "introduce_one_new":
        should_intro = bool(candidate_slot_ids)
        should_refresh_roles = False
        max_new_core_entries = 1 if should_intro else 0
        max_role_refreshes = 0
        candidate_slot_ids = candidate_slot_ids[:1]
        role_refresh_targets = []
        role_refresh_suggestions = []
        strategy_note = "下一规划窗口更适合补一个新人接线，但一次只落一个核心位。"
    elif casting_strategy == "balanced_light":
        should_intro = bool(candidate_slot_ids)
        should_refresh_roles = bool(role_refresh_targets)
        max_new_core_entries = 1 if should_intro else 0
        max_role_refreshes = 1 if should_refresh_roles else 0
        candidate_slot_ids = candidate_slot_ids[:1]
        role_refresh_targets = role_refresh_targets[:1]
        role_refresh_suggestions = [item for item in role_refresh_suggestions if _text(item.get("character")) in role_refresh_targets][:1]
        strategy_note = "下一规划窗口可轻推双线，但别同章同时塞新人和旧人换挡。"
    else:
        should_intro = False
        should_refresh_roles = False
        max_new_core_entries = 0
        max_role_refreshes = 0
        candidate_slot_ids = []
        role_refresh_targets = []
        role_refresh_suggestions = []
        strategy_note = "下一规划窗口先稳住现有人物线，不急着补新人，也不硬改作用位。"

    diagnostics_summary = _text(casting_defer_diagnostics.get("summary"))
    tasks = []
    if focus_characters:
        tasks.append(f"下一规划窗口优先围绕{focus_characters[0]}这条人物线发力。")
    if len(focus_characters) >= 2:
        tasks.append(f"把{focus_characters[0]}与{focus_characters[1]}的互相牵制或互助写得更具体。")
    if priority_relation_ids:
        tasks.append(f"关系线优先推进{priority_relation_ids[0]}，不要只让配角做功能按钮。")
    if should_intro and candidate_slot_ids:
        tasks.append(f"本轮最多落地 {max_new_core_entries} 个新核心位，优先考虑：{candidate_slot_ids[0]}。")
    if should_refresh_roles and role_refresh_suggestions:
        tasks.append(f"本轮最多改 {max_role_refreshes} 个旧角色作用位，先处理{role_refresh_targets[0]}：{role_refresh_suggestions[0]['suggested_function']}。")
    tasks.append(strategy_note)
    if diagnostics_summary:
        tasks.append(diagnostics_summary)
    if not tasks:
        tasks.append("下一规划窗口继续稳住现有人物线，避免角色长时间失踪。")
    watchouts = []
    if diagnostics_summary:
        watchouts.append(diagnostics_summary)
    for item in _safe_list(snapshot.get("recent_retrospectives"))[-2:]:
        problem = _text(item.get("core_problem"))
        if problem:
            watchouts.append(problem[:56])
    if not watchouts:
        watchouts.append("避免让关键配角只剩传话、盘问或发任务功能。")
    note = (
        f"本轮人物策略：{strategy_note} {diagnostics_summary} 先抓{focus_characters[0]}，关系线优先看{priority_relation_ids[0] if priority_relation_ids else '当前焦点人物'}。"
        if focus_characters
        else f"本轮人物策略：{strategy_note} {diagnostics_summary}"
    )
    return {
        "stage_start_chapter": int(snapshot.get("stage_start_chapter", 0) or 0),
        "stage_end_chapter": int(snapshot.get("stage_end_chapter", 0) or 0),
        "next_window_start": int(snapshot.get("next_window_start", 0) or 0),
        "next_window_end": int(snapshot.get("next_window_end", 0) or 0),
        "focus_characters": focus_characters,
        "supporting_characters": supporting_characters,
        "defer_characters": defer_characters,
        "priority_relation_ids": priority_relation_ids,
        "light_touch_relation_ids": light_touch_relation_ids,
        "defer_relation_ids": defer_relation_ids,
        "casting_strategy": casting_strategy,
        "casting_strategy_note": strategy_note[:72],
        "max_new_core_entries": max_new_core_entries,
        "max_role_refreshes": max_role_refreshes,
        "should_introduce_character": should_intro,
        "candidate_slot_ids": candidate_slot_ids,
        "should_refresh_role_functions": should_refresh_roles,
        "role_refresh_targets": role_refresh_targets,
        "role_refresh_suggestions": role_refresh_suggestions[:2],
        "next_window_tasks": _dedupe_texts(tasks, limit=5),
        "watchouts": _dedupe_texts(watchouts, limit=4),
        "review_note": note[:96],
        "source": "heuristic",
    }



def normalize_stage_character_review(review: dict[str, Any] | None, snapshot: dict[str, Any]) -> dict[str, Any]:
    fallback = heuristic_stage_character_review(snapshot)
    payload = deepcopy(review or {})
    candidate_characters = _dedupe_texts([
        *(item.get("name") for item in _safe_list(snapshot.get("priority_characters"))),
        *(item.get("character") for item in _safe_list(snapshot.get("active_core_characters"))),
    ], limit=20)
    candidate_relations = _dedupe_texts([item.get("relation_id") for item in _safe_list(snapshot.get("priority_relations"))], limit=20)
    candidate_slots = _dedupe_texts([item.get("slot_id") for item in _safe_list(snapshot.get("due_unbound_slots"))], limit=10)
    candidate_role_refresh = _dedupe_texts([item.get("name") for item in _safe_list(snapshot.get("role_refresh_candidates"))], limit=10)

    def keep_texts(values: Any, candidates: list[str], limit: int) -> list[str]:
        items = []
        seen = set()
        for value in _safe_list(values):
            text = _text(value)
            if not text or text not in candidates or text in seen:
                continue
            seen.add(text)
            items.append(text)
            if len(items) >= limit:
                break
        return items

    role_refresh_targets = keep_texts(payload.get("role_refresh_targets"), candidate_role_refresh, 3) or fallback.get("role_refresh_targets", [])
    role_refresh_suggestions = []
    for item in _safe_list(payload.get("role_refresh_suggestions"))[:3]:
        if not isinstance(item, dict):
            continue
        character = _text(item.get("character"))
        if character not in candidate_role_refresh:
            continue
        suggested_function = _text(item.get("suggested_function"))[:14]
        reason = _text(item.get("reason"))[:48]
        if not suggested_function:
            continue
        role_refresh_suggestions.append({
            "character": character,
            "suggested_function": suggested_function,
            "reason": reason,
        })
    casting_strategy = _text(payload.get("casting_strategy"), _text(fallback.get("casting_strategy"), "hold_steady"))
    if casting_strategy not in {"prefer_refresh_existing", "introduce_one_new", "balanced_light", "hold_steady"}:
        casting_strategy = _text(fallback.get("casting_strategy"), "hold_steady")
    candidate_slot_ids_kept = keep_texts(payload.get("candidate_slot_ids"), candidate_slots, 2) or fallback["candidate_slot_ids"]
    raw_should_intro = bool(payload.get("should_introduce_character")) if payload.get("should_introduce_character") is not None else bool(fallback["should_introduce_character"])
    raw_should_refresh = bool(payload.get("should_refresh_role_functions")) if payload.get("should_refresh_role_functions") is not None else bool(fallback.get("should_refresh_role_functions"))
    role_refresh_targets_kept = role_refresh_targets
    role_refresh_suggestions_kept = role_refresh_suggestions or fallback.get("role_refresh_suggestions", [])
    max_new_core_entries = int(payload.get("max_new_core_entries") or fallback.get("max_new_core_entries") or 0)
    max_role_refreshes = int(payload.get("max_role_refreshes") or fallback.get("max_role_refreshes") or 0)

    if casting_strategy == "prefer_refresh_existing":
        should_introduce_character = False
        candidate_slot_ids_kept = []
        should_refresh_role_functions = bool(role_refresh_targets_kept or role_refresh_suggestions_kept)
        role_refresh_targets_kept = role_refresh_targets_kept[:1]
        role_refresh_suggestions_kept = [item for item in role_refresh_suggestions_kept if _text(item.get("character")) in role_refresh_targets_kept][:1]
        max_new_core_entries = 0
        max_role_refreshes = 1 if should_refresh_role_functions else 0
    elif casting_strategy == "introduce_one_new":
        should_introduce_character = bool(candidate_slot_ids_kept and raw_should_intro)
        candidate_slot_ids_kept = candidate_slot_ids_kept[:1] if should_introduce_character else []
        should_refresh_role_functions = False
        role_refresh_targets_kept = []
        role_refresh_suggestions_kept = []
        max_new_core_entries = 1 if should_introduce_character else 0
        max_role_refreshes = 0
    elif casting_strategy == "balanced_light":
        should_introduce_character = bool(candidate_slot_ids_kept and raw_should_intro)
        should_refresh_role_functions = bool(role_refresh_targets_kept or role_refresh_suggestions_kept) and raw_should_refresh
        candidate_slot_ids_kept = candidate_slot_ids_kept[:1] if should_introduce_character else []
        role_refresh_targets_kept = role_refresh_targets_kept[:1] if should_refresh_role_functions else []
        role_refresh_suggestions_kept = [item for item in role_refresh_suggestions_kept if _text(item.get("character")) in role_refresh_targets_kept][:1]
        max_new_core_entries = 1 if should_introduce_character else 0
        max_role_refreshes = 1 if should_refresh_role_functions else 0
    else:
        should_introduce_character = False
        candidate_slot_ids_kept = []
        should_refresh_role_functions = False
        role_refresh_targets_kept = []
        role_refresh_suggestions_kept = []
        max_new_core_entries = 0
        max_role_refreshes = 0

    normalized = {
        "stage_start_chapter": int(payload.get("stage_start_chapter") or fallback["stage_start_chapter"]),
        "stage_end_chapter": int(payload.get("stage_end_chapter") or fallback["stage_end_chapter"]),
        "next_window_start": int(payload.get("next_window_start") or fallback["next_window_start"]),
        "next_window_end": int(payload.get("next_window_end") or fallback["next_window_end"]),
        "focus_characters": keep_texts(payload.get("focus_characters"), candidate_characters, 4) or fallback["focus_characters"],
        "supporting_characters": keep_texts(payload.get("supporting_characters"), candidate_characters, 3) or fallback["supporting_characters"],
        "defer_characters": keep_texts(payload.get("defer_characters"), candidate_characters, 3),
        "priority_relation_ids": keep_texts(payload.get("priority_relation_ids"), candidate_relations, 3) or fallback["priority_relation_ids"],
        "light_touch_relation_ids": keep_texts(payload.get("light_touch_relation_ids"), candidate_relations, 3) or fallback["light_touch_relation_ids"],
        "defer_relation_ids": keep_texts(payload.get("defer_relation_ids"), candidate_relations, 3),
        "casting_strategy": casting_strategy,
        "casting_strategy_note": _text(payload.get("casting_strategy_note"), fallback.get("casting_strategy_note", ""))[:72],
        "max_new_core_entries": max(0, min(max_new_core_entries, 1)),
        "max_role_refreshes": max(0, min(max_role_refreshes, 1)),
        "should_introduce_character": should_introduce_character,
        "candidate_slot_ids": candidate_slot_ids_kept,
        "should_refresh_role_functions": should_refresh_role_functions,
        "role_refresh_targets": role_refresh_targets_kept,
        "role_refresh_suggestions": role_refresh_suggestions_kept,
        "next_window_tasks": _dedupe_texts(_safe_list(payload.get("next_window_tasks")), limit=5) or fallback["next_window_tasks"],
        "watchouts": _dedupe_texts(_safe_list(payload.get("watchouts")), limit=5) or fallback["watchouts"],
        "review_note": _text(payload.get("review_note"), fallback["review_note"])[:96],
        "source": _text(payload.get("source"), fallback.get("source", "heuristic")),
    }
    return normalized



def store_stage_character_review(story_bible: dict[str, Any], review: dict[str, Any], *, current_chapter_no: int) -> dict[str, Any]:
    normalized = normalize_stage_character_review(review, build_stage_character_review_snapshot(story_bible, current_chapter_no=current_chapter_no))
    normalized["review_chapter"] = int(current_chapter_no or 0)
    console = (story_bible or {}).setdefault("control_console", {})
    reviews = console.setdefault("stage_character_reviews", [])
    reviews.append(normalized)
    console["stage_character_reviews"] = reviews[-8:]
    console["latest_stage_character_review"] = normalized
    retrospective_state = (story_bible or {}).setdefault("retrospective_state", {})
    retrospective_state["last_stage_review_chapter"] = int(current_chapter_no or 0)
    retrospective_state["latest_stage_character_review"] = normalized
    retrospective_state["last_review_notes"] = [
        {
            "chapter_no": int(current_chapter_no or 0),
            "chapter_title": f"阶段复盘@{current_chapter_no}",
            "core_problem": _text((normalized.get("watchouts") or [""])[0]),
            "next_correction": _text((normalized.get("next_window_tasks") or [""])[0]),
        }
    ]
    retrospective_state["status"] = "stage_review_ready"
    return normalized



def stage_character_review_for_window(story_bible: dict[str, Any], *, current_chapter_no: int) -> dict[str, Any] | None:
    review = _latest_stage_review(story_bible)
    if not isinstance(review, dict):
        return None
    next_window_start = int(review.get("next_window_start", 0) or 0)
    next_window_end = int(review.get("next_window_end", 0) or 0)
    if next_window_start and next_window_start > current_chapter_no + 1:
        return None
    if next_window_end and current_chapter_no + 1 > next_window_end + 1:
        return None
    result = deepcopy(review)
    result["window_progress"] = build_stage_review_window_progress(story_bible, result)
    return result
