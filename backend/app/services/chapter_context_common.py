from __future__ import annotations

import json
from typing import Any

from app.core.config import settings


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"



def _truncate_list(values: list[Any] | None, *, max_items: int, item_limit: int) -> list[str]:
    result: list[str] = []
    for item in values or []:
        text = _truncate_text(item, item_limit)
        if text:
            result.append(text)
        if len(result) >= max_items:
            break
    return result



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



def _normalize_hook(hook: Any) -> str:
    return "".join(str(hook or "").split())



def _json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False))



def _resolve_opening_reveal_guidance(story_bible: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    opening_constraints = (story_bible or {}).get("opening_constraints") or {}
    chapter_range = opening_constraints.get("opening_phase_chapter_range") or [1, 20]
    if not isinstance(chapter_range, list) or len(chapter_range) < 2:
        chapter_range = [1, 20]
    start_no = int(chapter_range[0] or 1)
    end_no = int(chapter_range[1] or 20)
    foundation_schedule = opening_constraints.get("foundation_reveal_schedule") or []
    power_schedule = opening_constraints.get("power_system_reveal_plan") or []

    def _pick_window(items: list[Any]) -> dict[str, Any]:
        for item in items:
            if not isinstance(item, dict):
                continue
            window = item.get("window") or []
            if isinstance(window, list) and len(window) >= 2:
                left = int(window[0] or 0)
                right = int(window[1] or 0)
                if left <= chapter_no <= right:
                    return item
        return items[0] if items and isinstance(items[0], dict) else {}

    foundation = _pick_window(foundation_schedule)
    power = _pick_window(power_schedule)
    in_opening = start_no <= int(chapter_no or 0) <= end_no
    guidance = {
        "in_opening_phase": in_opening,
        "chapter_range": [start_no, end_no],
        "current_window": foundation.get("window") or power.get("window") or [],
        "must_gradually_explain": _truncate_list(opening_constraints.get("must_gradually_explain"), max_items=5, item_limit=36),
        "foundation_focus": _truncate_list(foundation.get("focus"), max_items=4, item_limit=28),
        "foundation_delivery_rule": _truncate_text(foundation.get("delivery_rule"), 88),
        "power_system_focus": _truncate_list(power.get("reveal_topics") or foundation.get("power_system_focus"), max_items=4, item_limit=30),
        "reader_visible_goal": _truncate_text(power.get("reader_visible_goal"), 88),
    }
    return {key: value for key, value in guidance.items() if value not in ("", [], {}, None)}



def _tail_paragraphs(content: str, count: int = 2) -> list[str]:
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    if not blocks:
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if lines:
            blocks = [" ".join(lines)]
    return [_truncate_text(block, 220) for block in blocks[-count:]]



def _compact_scene_card(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw or {}
    card = {
        "main_scene": _truncate_text(payload.get("main_scene"), 42),
        "opening": _truncate_text(payload.get("opening") or payload.get("opening_beat"), 60),
        "middle": _truncate_text(payload.get("middle") or payload.get("mid_turn"), 60),
        "ending": _truncate_text(payload.get("ending") or payload.get("closing_image") or payload.get("ending_hook"), 60),
        "chapter_hook": _truncate_text(payload.get("chapter_hook") or payload.get("ending_hook"), 60),
        "supporting_character_focus": _truncate_text(payload.get("supporting_character_focus"), 24),
    }
    return {key: value for key, value in card.items() if value}



def _compact_scene_handoff_card(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw or {}
    card = {
        "scene_status_at_end": _truncate_text(payload.get("scene_status_at_end"), 16),
        "must_continue_same_scene": bool(payload.get("must_continue_same_scene")),
        "allowed_transition": _truncate_text(payload.get("allowed_transition"), 16),
        "next_opening_anchor": _truncate_text(payload.get("next_opening_anchor"), 120),
        "final_scene_name": _truncate_text(payload.get("final_scene_name"), 24),
        "final_scene_role": _truncate_text(payload.get("final_scene_role"), 16),
        "carry_over_items": _truncate_list(payload.get("carry_over_items"), max_items=4, item_limit=56),
        "carry_over_people": _truncate_list(payload.get("carry_over_people"), max_items=5, item_limit=20),
        "unfinished_actions": _truncate_list(payload.get("unfinished_actions"), max_items=4, item_limit=64),
        "forbidden_openings": _truncate_list(payload.get("forbidden_openings"), max_items=3, item_limit=40),
        "handoff_note": _truncate_text(payload.get("handoff_note"), 84),
        "next_scene_candidates": _compact_value(payload.get("next_scene_candidates") or [], text_limit=56),
    }
    return {key: value for key, value in card.items() if value not in (None, "", [], {})}



def _select_outline_window(global_outline: dict[str, Any], target_chapter_no: int) -> list[dict[str, Any]]:
    acts = global_outline.get("acts", []) if isinstance(global_outline, dict) else []
    if not acts:
        return []
    current_idx = len(acts) - 1
    for idx, act in enumerate(acts):
        target_end = int(act.get("target_chapter_end", 0) or 0)
        if target_chapter_no <= target_end or target_end == 0:
            current_idx = idx
            break
    selected = acts[current_idx : current_idx + 2]
    compact: list[dict[str, Any]] = []
    for act in selected:
        compact.append(
            {
                "act_no": int(act.get("act_no", 0) or 0),
                "title": _truncate_text(act.get("title"), 24),
                "purpose": _truncate_text(act.get("purpose"), 60),
                "summary": _truncate_text(act.get("summary"), 90),
                "target_chapter_end": int(act.get("target_chapter_end", 0) or 0),
            }
        )
    return compact



def _compact_arc(arc: dict[str, Any] | None) -> dict[str, Any]:
    if not arc:
        return {}
    return {
        "arc_no": int(arc.get("arc_no", 0) or 0),
        "start_chapter": int(arc.get("start_chapter", 0) or 0),
        "end_chapter": int(arc.get("end_chapter", 0) or 0),
        "focus": _truncate_text(arc.get("focus"), 70),
        "bridge_note": _truncate_text(arc.get("bridge_note"), 90),
    }



def _phase_rule(story_bible: dict[str, Any], next_no: int) -> str:
    pacing_rules = story_bible.get("pacing_rules", {}) if isinstance(story_bible, dict) else {}
    if next_no <= 3 and pacing_rules.get("first_three_chapters"):
        return _truncate_text(pacing_rules["first_three_chapters"], 80)
    if next_no <= 12 and pacing_rules.get("first_twelve_chapters"):
        return _truncate_text(pacing_rules["first_twelve_chapters"], 80)
    return _truncate_text(pacing_rules.get("overall"), 80)



def _collect_live_hooks(recent_summaries: list[dict[str, Any]]) -> list[str]:
    closed = {
        _normalize_hook(hook)
        for summary in recent_summaries
        for hook in summary.get("closed_hooks", [])
        if _normalize_hook(hook)
    }
    live_hooks: list[str] = []
    seen: set[str] = set()
    for summary in reversed(recent_summaries):
        for hook in summary.get("open_hooks", []):
            norm = _normalize_hook(hook)
            if not norm or norm in closed or norm in seen:
                continue
            seen.add(norm)
            live_hooks.append(_truncate_text(hook, 48))
            if len(live_hooks) >= settings.chapter_live_hook_limit:
                return live_hooks
    return live_hooks



def _published_and_stock_facts(story_bible: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger = (story_bible.get("fact_ledger") or {}) if isinstance(story_bible, dict) else {}
    published = ledger.get("published_facts") if isinstance(ledger.get("published_facts"), list) else []
    stock = ledger.get("stock_facts") if isinstance(ledger.get("stock_facts"), list) else []
    return published[-8:], stock[-6:]



def _unique_texts(values: list[Any] | None, *, limit: int, item_limit: int = 32) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _truncate_text(value, item_limit)
        if not text:
            continue
        norm = "".join(text.split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        items.append(text)
        if len(items) >= limit:
            break
    return items
