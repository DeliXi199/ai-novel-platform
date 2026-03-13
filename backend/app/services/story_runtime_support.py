from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.models.novel import Novel
from app.services.hard_fact_guard import (
    build_hard_fact_guard_rules,
    ensure_hard_fact_guard,
    rebuild_hard_fact_guard_from_chapters,
)
from app.services.story_fact_ledger import _ensure_fact_ledger, _empty_fact_ledger, rebuild_fact_ledger_from_chapters

STORY_BIBLE_SCHEMA_VERSION = 2
STORY_BIBLE_ARCHITECTURE = "manual_architecture_v3_optimized"
DEFAULT_SERIAL_DELIVERY_MODE = "live_publish"


def build_serial_rules() -> dict[str, Any]:
    return {
        "published_chapters_immutable": True,
        "published_text_is_not_draft": True,
        "fact_priority": ["published_chapters", "stock_chapters", "planning_docs"],
        "fact_ledger_policy": {
            "enabled": True,
            "published_facts_locked": True,
            "stock_facts_promotable": True,
            "fallback_indexing": "chapter_title_and_summary",
        },
        "inventory_policy": {
            "unpublished_inventory_repairable": True,
            "repair_scope": "tail_only",
            "published_chapters_never_rewritten": True,
        },
        "batch_generation": {
            "sequential_only": True,
            "refresh_state_between_chapters": True,
            "parallel_generation_forbidden": True,
        },
        "daily_modes": ["live_publish", "stockpile"],
        "problem_resolution_policy": "一旦发现问题，优先调整后续结构、近纲、库存稿与后文承接，不回改已发布硬事实。",
        "ending_policy": "项目不能只会往前拖，必须在后期主动收束主线、人物、伏笔与主角成长。",
        "hard_fact_guard": build_hard_fact_guard_rules(),
    }



def _empty_long_term_state(delivery_mode: str = DEFAULT_SERIAL_DELIVERY_MODE) -> dict[str, Any]:
    return {
        "protagonist_state": {},
        "character_states": {},
        "foreshadowing_state": [],
        "history_summaries": [],
        "volume_progress": [],
        "fact_ledger": _empty_fact_ledger(),
        "chapter_release_state": {
            "delivery_mode": delivery_mode,
            "published_through": 0,
            "latest_generated_chapter": 0,
            "latest_available_chapter": 0,
            "stock_chapter_count": 0,
            "published_chapter_count": 0,
            "locked_chapter_count": 0,
            "chapters": {},
        },
    }



def _ensure_serial_runtime(story_bible: dict[str, Any]) -> dict[str, Any]:
    runtime = story_bible.setdefault("serial_runtime", {})
    runtime.setdefault("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)
    runtime.setdefault("supports_live_publish", True)
    runtime.setdefault("supports_stockpile", True)
    runtime.setdefault("last_publish_action", None)
    runtime.setdefault("continuity_mode", "strong_bridge")
    runtime.setdefault("previous_chapter_bridge", {})
    return runtime



def _ensure_story_bible_meta(story_bible: dict[str, Any]) -> dict[str, Any]:
    meta = story_bible.setdefault("story_bible_meta", {})
    meta["schema_version"] = STORY_BIBLE_SCHEMA_VERSION
    meta.setdefault("architecture", STORY_BIBLE_ARCHITECTURE)
    meta.setdefault("migration_notes", [
        "story_bible 增加 schema_version，用于后续兼容升级。",
        "control_console 与 workflow_state 继续由 ensure_story_architecture 自动补齐。",
    ])
    return story_bible



def _current_volume_card(story_bible: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    volume_cards = story_bible.get("volume_cards") or []
    if not volume_cards:
        return {}
    current = volume_cards[-1]
    for card in volume_cards:
        start = int(card.get("start_chapter", 0) or 0)
        end = int(card.get("end_chapter", 0) or 0)
        if start <= chapter_no <= end or (start <= chapter_no and end == 0):
            current = card
            break
    return current



def _build_initialization_packet(story_bible: dict[str, Any], current_chapter_no: int = 0) -> dict[str, Any]:
    current_volume = _current_volume_card(story_bible, max(current_chapter_no + 1, 1)) if story_bible.get("volume_cards") else {}
    console = story_bible.get("control_console") or {}
    return {
        "documents_only": True,
        "current_volume_card": current_volume,
        "near_7_chapter_outline": (console.get("near_7_chapter_outline") or [])[:7],
        "chapter_card_queue": (console.get("chapter_card_queue") or [])[:7],
        "contains_generated_text": False,
        "note": "初始化只准备当前卷与近期章节所需文档，不预生成正文。",
    }



def sync_long_term_state(story_bible: dict[str, Any], novel: Novel, chapters: list[Any] | None = None) -> dict[str, Any]:
    story_bible = _ensure_story_bible_meta(deepcopy(story_bible or {}))
    runtime = _ensure_serial_runtime(story_bible)
    console = story_bible.setdefault("control_console", {})
    _ensure_fact_ledger(story_bible)
    ensure_hard_fact_guard(story_bible)
    state = story_bible.setdefault("long_term_state", _empty_long_term_state(runtime.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)))
    state["protagonist_state"] = deepcopy(console.get("protagonist_state") or {})
    state["character_states"] = deepcopy(console.get("character_cards") or {})
    state["foreshadowing_state"] = deepcopy(console.get("foreshadowing") or [])
    state["history_summaries"] = deepcopy((console.get("recent_progress") or [])[-20:])
    state["volume_progress"] = deepcopy(story_bible.get("volume_cards") or [])

    release = state.setdefault("chapter_release_state", {})
    release["delivery_mode"] = runtime.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)
    release.setdefault("chapters", {})

    if chapters is not None:
        ordered = sorted(chapters, key=lambda item: int(getattr(item, "chapter_no", 0) or 0))
        release_map: dict[str, Any] = {}
        published_nos: list[int] = []
        latest_available = 0
        latest_generated = 0
        stock_count = 0
        for item in ordered:
            chapter_no = int(getattr(item, "chapter_no", 0) or 0)
            latest_generated = max(latest_generated, chapter_no)
            latest_available = max(latest_available, chapter_no)
            is_published = bool(getattr(item, "is_published", False))
            if is_published:
                published_nos.append(chapter_no)
            else:
                stock_count += 1
            release_map[str(chapter_no)] = {
                "chapter_no": chapter_no,
                "title": getattr(item, "title", ""),
                "serial_stage": getattr(item, "serial_stage", "stock") or "stock",
                "is_published": is_published,
                "locked_from_edit": bool(getattr(item, "locked_from_edit", False)),
                "published_at": getattr(getattr(item, "published_at", None), "isoformat", lambda: None)(),
                "created_at": getattr(getattr(item, "created_at", None), "isoformat", lambda: None)(),
            }
        published_through = 0
        for no in published_nos:
            if no == published_through + 1:
                published_through = no
            else:
                break
        release.update(
            {
                "published_through": published_through,
                "latest_generated_chapter": latest_generated,
                "latest_available_chapter": latest_available,
                "stock_chapter_count": stock_count,
                "published_chapter_count": len(published_nos),
                "locked_chapter_count": len(published_nos),
                "chapters": release_map,
            }
        )
        story_bible = rebuild_fact_ledger_from_chapters(story_bible, ordered)
        story_bible = rebuild_hard_fact_guard_from_chapters(story_bible, protagonist_name=novel.protagonist_name, chapters=ordered)
    state["fact_ledger"] = deepcopy(story_bible.get("fact_ledger") or _empty_fact_ledger())
    state["hard_fact_guard"] = deepcopy(story_bible.get("hard_fact_guard") or {})
    state["chapter_release_state"] = release
    story_bible["long_term_state"] = state
    story_bible["initialization_packet"] = _build_initialization_packet(story_bible, novel.current_chapter_no)
    return story_bible



def set_delivery_mode(story_bible: dict[str, Any], delivery_mode: str) -> dict[str, Any]:
    runtime = _ensure_serial_runtime(story_bible)
    runtime["delivery_mode"] = delivery_mode
    story_bible["serial_runtime"] = runtime
    state = story_bible.setdefault("long_term_state", _empty_long_term_state(delivery_mode))
    release = state.setdefault("chapter_release_state", {})
    release["delivery_mode"] = delivery_mode
    story_bible["long_term_state"] = state
    return story_bible
