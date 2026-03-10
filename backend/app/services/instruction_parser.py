from __future__ import annotations

import re
from typing import Any

from app.services.llm_types import ParsedInstructionPayload
from app.services.openai_story_engine import parse_instruction_with_openai


TONE_KEYWORDS = {
    "lighter": ["轻松", "轻一点", "温柔", "温暖", "治愈", "别太压抑", "不要太压抑", "不要太沉重"],
    "darker": ["压抑", "黑暗", "阴冷", "惨一点", "更狠", "更残酷", "更沉重"],
    "tenser": ["紧张", "更刺激", "悬一点", "更悬", "压迫感"],
    "calmer": ["平稳", "日常", "收一收", "缓一点", "别那么炸"],
}
PACE_KEYWORDS = {
    "faster": ["快一点", "节奏快", "推进快", "别拖", "faster"],
    "slower": ["慢一点", "慢热", "放慢", "铺垫多一点", "slower"],
}
RELATIONSHIP_KEYWORDS = {
    "closer": ["拉近关系", "更亲近", "暧昧", "培养感情", "和解", "信任增加"],
    "distant": ["疏远", "保持距离", "别太快在一起", "信任下降"],
    "conflict": ["对立", "冲突升级", "关系紧张"],
}
PROTECT_PATTERNS = [
    r"别让(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})(?:死|出事|受伤|黑化|下线)",
    r"(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})不能(?:死|出事|受伤|黑化|下线)",
    r"保护(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})",
]
FOCUS_PATTERNS = [
    (r"多写(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})", 0.75),
    (r"重点写(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})", 0.9),
    (r"给(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})多一点戏份", 0.8),
    (r"(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})戏份多一点", 0.8),
    (r"少写(?P<name>[\u4e00-\u9fffA-Za-z0-9_·]{1,12})", 0.2),
]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def heuristic_parse_instruction(raw_instruction: str) -> dict[str, Any]:
    lowered = raw_instruction.lower()
    parsed: dict[str, Any] = {
        "character_focus": {},
        "tone": None,
        "pace": None,
        "protected_characters": [],
        "relationship_direction": None,
    }

    for tone, keywords in TONE_KEYWORDS.items():
        if any(keyword in raw_instruction or keyword in lowered for keyword in keywords):
            parsed["tone"] = tone
            break

    for pace, keywords in PACE_KEYWORDS.items():
        if any(keyword in raw_instruction or keyword in lowered for keyword in keywords):
            parsed["pace"] = pace
            break

    for relation, keywords in RELATIONSHIP_KEYWORDS.items():
        if any(keyword in raw_instruction or keyword in lowered for keyword in keywords):
            parsed["relationship_direction"] = relation
            break

    protected: list[str] = []
    for pattern in PROTECT_PATTERNS:
        for match in re.finditer(pattern, raw_instruction):
            protected.append(match.group("name"))
    parsed["protected_characters"] = _dedupe_preserve_order(protected)[:6]

    focus: dict[str, float] = {}
    for pattern, weight in FOCUS_PATTERNS:
        for match in re.finditer(pattern, raw_instruction):
            name = match.group("name").strip()
            if name:
                focus[name] = max(focus.get(name, 0.0), weight)

    if not focus and "主角" in raw_instruction:
        focus["主角"] = 0.65
    parsed["character_focus"] = focus
    return parsed


def merge_instruction_constraints(*constraints: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "character_focus": {},
        "tone": None,
        "pace": None,
        "protected_characters": [],
        "relationship_direction": None,
    }
    for item in constraints:
        if not item:
            continue
        merged["character_focus"].update(item.get("character_focus") or {})
        merged["tone"] = item.get("tone") or merged["tone"]
        merged["pace"] = item.get("pace") or merged["pace"]
        merged["relationship_direction"] = item.get("relationship_direction") or merged["relationship_direction"]
        merged["protected_characters"] = _dedupe_preserve_order(
            merged["protected_characters"] + list(item.get("protected_characters") or [])
        )[:6]
    return merged


def parse_reader_instruction(raw_instruction: str) -> dict[str, Any]:
    heuristic = heuristic_parse_instruction(raw_instruction)
    try:
        model_result = parse_instruction_with_openai(raw_instruction).model_dump(mode="python")
        merged = merge_instruction_constraints(heuristic, model_result)
        return ParsedInstructionPayload.model_validate(merged).model_dump(mode="python")
    except Exception:
        return ParsedInstructionPayload.model_validate(heuristic).model_dump(mode="python")
