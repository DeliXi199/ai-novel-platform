from __future__ import annotations

from copy import deepcopy
from typing import Any


MONSTER_SPECIES_HINTS = {
    "狼": "妖狼",
    "虎": "妖虎",
    "蛇": "妖蛇",
    "蟒": "妖蟒",
    "猿": "妖猿",
    "熊": "妖熊",
    "鹰": "妖禽",
    "雕": "妖禽",
    "蝠": "妖蝠",
    "蛛": "毒蛛",
    "蜈蚣": "毒虫",
    "蛟": "蛟类",
    "龙": "龙裔/龙属",
    "狐": "妖狐",
    "尸": "尸傀/尸类",
}


THREAT_TAG_HINTS = {
    "狼": ["速度", "围猎"],
    "虎": ["扑杀", "爆发"],
    "蛇": ["缠杀", "毒性"],
    "蟒": ["绞杀", "体型压制"],
    "猿": ["蛮力", "攀跃"],
    "熊": ["蛮力", "硬抗"],
    "鹰": ["俯冲", "视野"],
    "雕": ["俯冲", "高空"],
    "蝠": ["夜袭", "声波/群袭"],
    "蛛": ["毒性", "蛛网"],
    "蜈蚣": ["毒性", "甲壳"],
    "蛟": ["水战", "血脉威压"],
    "龙": ["血脉威压", "高位威胁"],
    "狐": ["魅惑", "狡诈"],
    "尸": ["尸毒", "悍不畏死"],
}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default



def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []



def infer_monster_species(name: str) -> str:
    clean = _text(name)
    for token, species in MONSTER_SPECIES_HINTS.items():
        if token in clean:
            return species
    return "妖兽/待细化"



def infer_monster_traits(name: str) -> list[str]:
    clean = _text(name)
    for token, tags in THREAT_TAG_HINTS.items():
        if token in clean:
            return list(tags)
    return ["待观察"]



def build_monster_card(
    raw_name: Any,
    *,
    current_realm: str,
    species_type: str = "",
    hostility: str = "待观察",
    status: str = "active",
    first_seen_chapter: int = 0,
    source: str = "seed",
    narrative_role: str = "阶段性怪物/异类威胁。",
    threat_note: str = "首次登场时要写清威胁层位、攻击方式与压迫感。",
    signature_traits: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    name = _text(raw_name)
    species = _text(species_type) or infer_monster_species(name)
    traits = [item for item in (_safe_list(signature_traits) or infer_monster_traits(name)) if _text(item)]
    card = {
        "name": name,
        "entity_type": "monster",
        "species_type": species,
        "current_realm": _text(current_realm, "待判定"),
        "current_strength": _text(current_realm, "待判定"),
        "threat_level": _text(current_realm, "待判定"),
        "hostility": _text(hostility, "待观察"),
        "intelligence_level": "待观察",
        "signature_traits": traits[:4],
        "resource_yield": [],
        "status": _text(status, "active"),
        "narrative_role": _text(narrative_role, "阶段性怪物/异类威胁。"),
        "threat_note": _text(threat_note, "首次登场时要写清威胁层位、攻击方式与压迫感。"),
        "first_appearance_rule": "怪物第一次完整登场时，必须自然点明它的大致实力层位或足以映照强弱的压迫细节。",
        "appearance_priority": "按遭遇与猎杀线索触发",
        "first_seen_chapter": int(first_seen_chapter or 0),
        "last_seen_chapter": int(first_seen_chapter or 0),
        "source": source,
    }
    return name, card



def ensure_monster_card_structure(card: dict[str, Any] | None, *, fallback_name: str = "", default_realm: str = "待判定") -> dict[str, Any]:
    payload = deepcopy(card or {})
    name = _text(payload.get("name") or fallback_name)
    payload["name"] = name
    payload.setdefault("entity_type", "monster")
    payload.setdefault("species_type", infer_monster_species(name))
    payload.setdefault("current_realm", default_realm)
    payload.setdefault("current_strength", _text(payload.get("current_realm"), default_realm))
    payload.setdefault("threat_level", _text(payload.get("current_strength"), default_realm))
    payload.setdefault("hostility", "待观察")
    payload.setdefault("intelligence_level", "待观察")
    payload.setdefault("signature_traits", infer_monster_traits(name))
    payload.setdefault("resource_yield", [])
    payload.setdefault("status", "active")
    payload.setdefault("narrative_role", "阶段性怪物/异类威胁。")
    payload.setdefault("threat_note", "首次登场时要写清威胁层位、攻击方式与压迫感。")
    payload.setdefault("first_appearance_rule", "怪物第一次完整登场时，必须自然点明它的大致实力层位或足以映照强弱的压迫细节。")
    payload.setdefault("appearance_priority", "按遭遇与猎杀线索触发")
    payload.setdefault("first_seen_chapter", 0)
    payload.setdefault("last_seen_chapter", int(payload.get("first_seen_chapter") or 0))
    payload.setdefault("source", "runtime")
    return payload
