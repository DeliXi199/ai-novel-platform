from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from app.core.config import settings
from app.services.chapter_context_common import _json_size, _truncate_text


def _fit_chapter_payload_budget(
    novel_context: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    serialized_last: dict[str, Any],
    serialized_active: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    budget = settings.chapter_prompt_max_chars
    before = _json_size(novel_context) + _json_size(recent_summaries) + _json_size(serialized_last) + _json_size(serialized_active)

    def total_size() -> int:
        return _json_size(novel_context) + _json_size(recent_summaries) + _json_size(serialized_last) + _json_size(serialized_active)

    if total_size() > budget and serialized_last.get("tail_excerpt"):
        serialized_last["tail_excerpt"] = _truncate_text(serialized_last["tail_excerpt"], min(260, settings.chapter_last_excerpt_chars))
        bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else None
        if bridge is not None:
            bridge["tail_excerpt"] = serialized_last["tail_excerpt"]

    if total_size() > budget and isinstance(serialized_last.get("last_two_paragraphs"), list) and len(serialized_last["last_two_paragraphs"]) > 1:
        serialized_last["last_two_paragraphs"] = serialized_last["last_two_paragraphs"][-1:]
        bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else None
        if bridge is not None:
            bridge["last_two_paragraphs"] = list(serialized_last["last_two_paragraphs"])

    if total_size() > budget and isinstance(serialized_last.get("unresolved_action_chain"), list) and len(serialized_last["unresolved_action_chain"]) > 2:
        serialized_last["unresolved_action_chain"] = serialized_last["unresolved_action_chain"][:2]
        bridge = serialized_last.get("continuity_bridge") if isinstance(serialized_last.get("continuity_bridge"), dict) else None
        if bridge is not None:
            bridge["unresolved_action_chain"] = list(serialized_last["unresolved_action_chain"])

    if total_size() > budget and len(recent_summaries) > 1:
        recent_summaries = recent_summaries[-1:]

    if total_size() > budget and len(serialized_active) > 1:
        serialized_active = serialized_active[-1:]

    story_memory = novel_context.get("story_memory") if isinstance(novel_context, dict) else None
    if total_size() > budget and isinstance(story_memory, dict):
        if isinstance(story_memory.get("global_direction"), list) and len(story_memory["global_direction"]) > 1:
            story_memory["global_direction"] = story_memory["global_direction"][:1]
        if isinstance(story_memory.get("live_hooks"), list) and len(story_memory["live_hooks"]) > 3:
            story_memory["live_hooks"] = story_memory["live_hooks"][:3]
        if isinstance(story_memory.get("core_conflict"), str):
            story_memory["core_conflict"] = _truncate_text(story_memory["core_conflict"], 80)
        if isinstance(story_memory.get("phase_rule"), str):
            story_memory["phase_rule"] = _truncate_text(story_memory["phase_rule"], 60)

    if total_size() > budget:
        novel_context["premise"] = _truncate_text(novel_context.get("premise"), 120)

    stats = {
        "context_mode": novel_context.get("context_mode", settings.chapter_context_mode),
        "payload_chars_before": before,
        "payload_chars_after": total_size(),
        "budget": budget,
        "recent_summary_count": len(recent_summaries),
        "active_intervention_count": len(serialized_active),
        "last_excerpt_chars": len(serialized_last.get("tail_excerpt", "")),
        "continuity_bridge_chars": _json_size(serialized_last.get("continuity_bridge", {})) if serialized_last.get("continuity_bridge") else 0,
    }
    return novel_context, recent_summaries, serialized_last, serialized_active, stats



def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a[:1500], b[:1500]).ratio()
