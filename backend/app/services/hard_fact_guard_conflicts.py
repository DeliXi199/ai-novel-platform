from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.hard_fact_guard_utils import _now_iso


def _state_entry(value: dict[str, Any], *, chapter_no: int, chapter_title: str) -> dict[str, Any]:
    return {**value, "chapter_no": chapter_no, "chapter_title": chapter_title, "updated_at": _now_iso()}


def _apply_facts_to_state(state: dict[str, Any], facts: dict[str, Any], *, chapter_no: int, chapter_title: str) -> dict[str, Any]:
    state = deepcopy(state)
    for item in facts.get("realm", []):
        state.setdefault("realm", {})[item["name"]] = _state_entry(item, chapter_no=chapter_no, chapter_title=chapter_title)
    for item in facts.get("life_status", []):
        state.setdefault("life_status", {})[item["name"]] = _state_entry(item, chapter_no=chapter_no, chapter_title=chapter_title)
    for item in facts.get("injury_status", []):
        state.setdefault("injury_status", {})[item["name"]] = _state_entry(item, chapter_no=chapter_no, chapter_title=chapter_title)
    for item in facts.get("identity_exposure", []):
        state.setdefault("identity_exposure", {})[item["name"]] = _state_entry(item, chapter_no=chapter_no, chapter_title=chapter_title)
    for item in facts.get("item_ownership", []):
        state.setdefault("item_ownership", {})[item["item"]] = _state_entry(item, chapter_no=chapter_no, chapter_title=chapter_title)
    return state


def _realm_conflicts(reference: dict[str, Any], new_items: list[dict[str, Any]], chapter_no: int) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    existing = reference.get("realm") or {}
    for item in new_items:
        prev = existing.get(item["name"])
        if not prev or prev.get("realm") == item.get("realm"):
            continue
        if item.get("transition"):
            continue
        conflicts.append({
            "category": "realm",
            "subject": item["name"],
            "previous": prev.get("realm"),
            "incoming": item.get("realm"),
            "previous_chapter_no": prev.get("chapter_no"),
            "incoming_chapter_no": chapter_no,
            "message": f"{item['name']} 的境界从 {prev.get('realm')} 直接变成 {item.get('realm')}，但本章没有明确突破/跌境说明。",
            "evidence": item.get("evidence"),
        })
    return conflicts


def _life_conflicts(reference: dict[str, Any], new_items: list[dict[str, Any]], chapter_no: int) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    existing = reference.get("life_status") or {}
    for item in new_items:
        prev = existing.get(item["name"])
        if not prev:
            continue
        if prev.get("status") == "dead" and item.get("status") == "alive" and not item.get("revival"):
            conflicts.append({
                "category": "life_status",
                "subject": item["name"],
                "previous": "dead",
                "incoming": "alive",
                "previous_chapter_no": prev.get("chapter_no"),
                "incoming_chapter_no": chapter_no,
                "message": f"{item['name']} 已在前文判定为死亡，本章又直接以存活状态出现，且没有复生/假死说明。",
                "evidence": item.get("evidence"),
            })
    return conflicts


def _injury_conflicts(reference: dict[str, Any], new_items: list[dict[str, Any]], chapter_no: int) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    existing = reference.get("injury_status") or {}
    for item in new_items:
        prev = existing.get(item["name"])
        if not prev:
            continue
        if prev.get("status") in {"severe", "injured"} and item.get("status") == "healthy" and not item.get("recovery"):
            conflicts.append({
                "category": "injury_status",
                "subject": item["name"],
                "previous": prev.get("status"),
                "incoming": item.get("status"),
                "previous_chapter_no": prev.get("chapter_no"),
                "incoming_chapter_no": chapter_no,
                "message": f"{item['name']} 前文仍处于受伤状态，本章却直接恢复为完好，缺少疗伤/恢复过程。",
                "evidence": item.get("evidence"),
            })
    return conflicts


def _identity_conflicts(reference: dict[str, Any], new_items: list[dict[str, Any]], chapter_no: int) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    existing = reference.get("identity_exposure") or {}
    for item in new_items:
        prev = existing.get(item["name"])
        if not prev:
            continue
        if prev.get("status") == "exposed" and item.get("status") == "hidden" and not item.get("concealed"):
            conflicts.append({
                "category": "identity_exposure",
                "subject": item["name"],
                "previous": "exposed",
                "incoming": "hidden",
                "previous_chapter_no": prev.get("chapter_no"),
                "incoming_chapter_no": chapter_no,
                "message": f"{item['name']} 的身份已在前文暴露，本章又直接回到未暴露状态，但没有补救/遮掩说明。",
                "evidence": item.get("evidence"),
            })
    return conflicts


def _item_conflicts(reference: dict[str, Any], new_items: list[dict[str, Any]], chapter_no: int) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    existing = reference.get("item_ownership") or {}
    for item in new_items:
        prev = existing.get(item["item"])
        if not prev:
            continue
        if prev.get("owner") != item.get("owner") and not item.get("transfer"):
            conflicts.append({
                "category": "item_ownership",
                "subject": item["item"],
                "previous": prev.get("owner"),
                "incoming": item.get("owner"),
                "previous_chapter_no": prev.get("chapter_no"),
                "incoming_chapter_no": chapter_no,
                "message": f"{item['item']} 前文归属 {prev.get('owner')}，本章变成 {item.get('owner')} 持有，但没有转移过程。",
                "evidence": item.get("evidence"),
            })
    return conflicts


def check_hard_fact_conflicts(reference_state: dict[str, Any], facts: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    conflicts = []
    conflicts.extend(_realm_conflicts(reference_state, facts.get("realm", []), chapter_no))
    conflicts.extend(_life_conflicts(reference_state, facts.get("life_status", []), chapter_no))
    conflicts.extend(_injury_conflicts(reference_state, facts.get("injury_status", []), chapter_no))
    conflicts.extend(_identity_conflicts(reference_state, facts.get("identity_exposure", []), chapter_no))
    conflicts.extend(_item_conflicts(reference_state, facts.get("item_ownership", []), chapter_no))
    return {
        "passed": not conflicts,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "summary": "未发现高风险硬事实冲突。" if not conflicts else f"发现 {len(conflicts)} 条高风险硬事实冲突。",
        "checked_at": _now_iso(),
    }
