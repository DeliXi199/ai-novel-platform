from __future__ import annotations

import re
from typing import Any

from app.services.hard_fact_guard_utils import (
    BREAKTHROUGH_MARKERS,
    CONCEAL_MARKERS,
    EXPOSED_TERMS,
    FALSE_DEAD_PATTERNS,
    HEALTHY_TERMS,
    HIDDEN_TERMS,
    ITEM_TERMS,
    LIGHT_INJURY_TERMS,
    REALM_PATTERN,
    RECOVERY_MARKERS,
    REGRESSION_MARKERS,
    REVIVAL_MARKERS,
    SEVERE_INJURY_TERMS,
    TRANSFER_MARKERS,
    _clean_text,
    _name_context_snippets,
    _text_blob,
    _window,
)


_SUMMARY_RESERVED_UPDATE_KEYS = {"notes", "__resource_updates__", "__monster_updates__", "__power_progress__"}


def _candidate_names(*, protagonist_name: str, plan: dict[str, Any] | None, summary: Any | None, reference_state: dict[str, Any] | None = None) -> list[str]:
    names: list[str] = []
    for candidate in [protagonist_name, (plan or {}).get("supporting_character_focus") if isinstance(plan, dict) else None]:
        text = _clean_text(candidate, 20)
        if text and text not in names:
            names.append(text)
    if summary is not None:
        updates = getattr(summary, "character_updates", None) or {}
        if isinstance(updates, dict):
            for key in updates.keys():
                clean_key = str(key).strip()
                if not clean_key or clean_key in _SUMMARY_RESERVED_UPDATE_KEYS or clean_key.startswith("__"):
                    continue
                text = _clean_text(clean_key, 20)
                if text and text not in names:
                    names.append(text)
    if isinstance(reference_state, dict):
        for bucket in ("realm", "life_status", "injury_status", "identity_exposure"):
            for key in list((reference_state.get(bucket) or {}).keys())[:8]:
                text = _clean_text(key, 20)
                if text and text not in names:
                    names.append(text)
    return names[:12]


def _find_realm_facts(text: str, names: list[str]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for name in names:
        for match in re.finditer(re.escape(name), text):
            snippet = _window(text, match.start(), match.end(), span=28)
            realm_match = REALM_PATTERN.search(snippet)
            if not realm_match:
                continue
            realm = realm_match.group(0)
            facts.append({
                "name": name,
                "realm": realm,
                "transition": any(marker in snippet for marker in BREAKTHROUGH_MARKERS + REGRESSION_MARKERS),
                "regression": any(marker in snippet for marker in REGRESSION_MARKERS),
                "evidence": _clean_text(snippet, 120),
            })
            break
    return facts


def _contains_false_dead(snippet: str) -> bool:
    return any(term in snippet for term in FALSE_DEAD_PATTERNS)


def _life_status_from_snippet(name: str, snippet: str) -> dict[str, Any] | None:
    clean = _clean_text(snippet, 160)
    if not clean or _contains_false_dead(clean):
        return None

    dead_patterns = [
        rf"{re.escape(name)}[^。！？；，,\n]{{0,10}}?(身死|死去|毙命|陨落|断气|被杀|被斩)",
        rf"(杀死|斩杀|害死|打死){re.escape(name)}",
        rf"{re.escape(name)}[^。！？；，,\n]{{0,6}}?的尸体",
    ]
    alive_patterns = [
        rf"{re.escape(name)}[^。！？；，,\n]{{0,10}}?(活着|未死|没死|还活着|苏醒|睁开眼|仍活着)",
    ]

    for pattern in dead_patterns:
        if re.search(pattern, clean):
            return {
                "name": name,
                "status": "dead",
                "revival": any(term in clean for term in REVIVAL_MARKERS),
                "evidence": _clean_text(clean, 120),
            }
    for pattern in alive_patterns:
        if re.search(pattern, clean):
            return {
                "name": name,
                "status": "alive",
                "revival": any(term in clean for term in REVIVAL_MARKERS),
                "evidence": _clean_text(clean, 120),
            }
    return None


def _find_life_status_facts(text: str, names: list[str]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for name in names:
        best: dict[str, Any] | None = None
        for snippet in _name_context_snippets(text, name, radius=1):
            match = _life_status_from_snippet(name, snippet)
            if not match:
                continue
            best = match
            if match.get("status") == "dead":
                break
        if best:
            facts.append(best)
    return facts


def _find_injury_facts(text: str, names: list[str]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for name in names:
        for match in re.finditer(re.escape(name), text):
            snippet = _window(text, match.start(), match.end(), span=28)
            status: str | None = None
            if any(term in snippet for term in SEVERE_INJURY_TERMS):
                status = "severe"
            elif any(term in snippet for term in LIGHT_INJURY_TERMS):
                status = "injured"
            elif any(term in snippet for term in HEALTHY_TERMS):
                status = "healthy"
            if not status:
                continue
            facts.append({
                "name": name,
                "status": status,
                "recovery": any(term in snippet for term in RECOVERY_MARKERS),
                "evidence": _clean_text(snippet, 120),
            })
            break
    return facts


def _find_identity_facts(text: str, names: list[str]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for name in names:
        for match in re.finditer(re.escape(name), text):
            snippet = _window(text, match.start(), match.end(), span=36)
            if any(re.search(pattern, snippet) for pattern in EXPOSED_TERMS):
                facts.append({"name": name, "status": "exposed", "concealed": any(term in snippet for term in CONCEAL_MARKERS), "evidence": _clean_text(snippet, 120)})
                break
            if any(re.search(pattern, snippet) for pattern in HIDDEN_TERMS):
                facts.append({"name": name, "status": "hidden", "concealed": any(term in snippet for term in CONCEAL_MARKERS), "evidence": _clean_text(snippet, 120)})
                break
    return facts


def _find_item_facts(text: str, names: list[str]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    item_pattern = "(?:" + "|".join(re.escape(term) for term in ITEM_TERMS) + ")"
    for name in names:
        regexes = [
            re.compile(re.escape(name) + rf"[^。；，\n]{{0,14}}?(收起|拿到|得到|握着|持有|带着|交给|递给|卖给|献给|丢了|失去|被夺走|被抢走|夺回|收回|找回)[^。；，\n]{{0,8}}?([\u4e00-\u9fa5]{{0,8}}{item_pattern})"),
            re.compile(re.escape(name) + rf"[^。；，\n]{{0,8}}?的([\u4e00-\u9fa5]{{0,8}}{item_pattern})"),
        ]
        for regex in regexes:
            match = regex.search(text)
            if not match:
                continue
            if len(match.groups()) >= 2 and match.group(2):
                verb = match.group(1)
                item = match.group(2)
            else:
                verb = "持有"
                item = match.group(1)
            item = _clean_text(item, 24)
            if not item or (name, item) in seen:
                continue
            seen.add((name, item))
            status = "held"
            owner = name
            transfer = False
            if verb in {"交给", "递给", "卖给", "献给"}:
                status = "transferred"
                transfer = True
            elif verb in {"丢了", "失去", "被夺走", "被抢走"}:
                status = "lost"
                transfer = True
            elif verb in {"夺回", "收回", "找回"}:
                status = "held"
                transfer = True
            facts.append({
                "item": item,
                "owner": owner,
                "status": status,
                "transfer": transfer or any(marker in match.group(0) for marker in TRANSFER_MARKERS),
                "evidence": _clean_text(match.group(0), 120),
            })
            break
    return facts


def extract_chapter_hard_facts(
    *,
    protagonist_name: str,
    chapter_no: int,
    chapter_title: str,
    content: str,
    plan: dict[str, Any] | None,
    summary: Any | None,
    reference_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updates = getattr(summary, "character_updates", None) or {}
    if isinstance(summary, str):
        summary_text = summary
    else:
        update_text = "\n".join(f"{name}:{value}" for name, value in updates.items() if name != "notes") if isinstance(updates, dict) else ""
        summary_text = _text_blob(
            getattr(summary, "event_summary", None),
            update_text,
            "\n".join(getattr(summary, "new_clues", None) or []),
        )
    source_text = _text_blob(summary_text, content)
    names = _candidate_names(protagonist_name=protagonist_name, plan=plan, summary=summary, reference_state=reference_state)
    return {
        "chapter_no": chapter_no,
        "chapter_title": chapter_title,
        "realm": _find_realm_facts(source_text, names),
        "life_status": _find_life_status_facts(source_text, names),
        "injury_status": _find_injury_facts(source_text, names),
        "identity_exposure": _find_identity_facts(source_text, names),
        "item_ownership": _find_item_facts(source_text, names),
    }
