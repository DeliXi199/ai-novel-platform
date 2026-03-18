from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.services.constraint_reasoning import run_local_constraint_reasoning
from app.services.story_fact_ledger import _now_iso

CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
UNIT_VALUES = {"十": 10, "百": 100, "千": 1000, "万": 10000}
COUNTABLE_UNITS = {"块", "枚", "张", "瓶", "包", "袋", "份", "株", "棵", "颗", "滴", "缕", "片", "卷", "斤", "两", "升", "斗", "坛", "桶", "箱", "盒", "支", "根", "缸"}
ENTITY_UNITS = {"把", "件", "柄", "面", "尊", "座", "套", "副", "盏", "口", "柄", "杆", "只", "头", "匹", "艘", "辆", "扇", "册", "页", "枚"}
STACKABLE_NAME_HINTS = ["灵石", "符", "符箓", "丹", "丹药", "药材", "药草", "草", "矿", "矿石", "晶", "箭", "箭矢", "毒粉", "材料", "卷轴"]
ENTITY_NAME_HINTS = ["剑", "刀", "枪", "弓", "盾", "甲", "衣", "袍", "炉", "鼎", "镜", "印", "旗", "铃", "珠", "令牌", "玉佩", "古镜", "罗盘", "飞舟", "舟", "戒", "扳指", "地图", "残图", "钥匙"]
CORE_RESOURCE_KEYWORDS = ["金手指", "古镜", "系统", "外挂", "本命", "传承", "血脉", "异火", "印记", "命灯", "天书"]
RESOURCE_ACTION_PATTERNS = (
    ("consume", ["消耗", "耗掉", "花掉", "用掉", "支付", "祭出", "服下", "吞下", "燃掉", "烧掉"]),
    ("transfer_out", ["交给", "卖给", "换出", "押给", "献上", "归还", "送出", "赔给"]),
    ("gain", ["获得", "拿到", "得到", "收获", "换到", "买到", "捡到", "截获", "赚到", "领到"]),
    ("transfer_in", ["接过", "收下", "拿回", "追回", "取回"]),
    ("expose", ["暴露", "露出", "显露", "被看见", "被识破"]),
    ("damage", ["损坏", "破碎", "裂开", "耗损"]),
)

RESOURCE_FUNCTION_HINTS = {
    "灵石": {
        "resource_kind": "修行材料",
        "core_functions": ["补充灵气", "作为交易货币", "驱动阵法/法器"],
        "activation_rules": ["通常以炼化、支付或灌注的方式使用"],
        "usage_limits": ["数量减少后必须同步扣减"],
        "costs": ["消耗数量"],
        "side_effects": [],
        "growth_path": {"can_evolve": False, "current_stage": "稳定", "next_unlock_hint": "无"},
        "unlock_state": {"level": "已知", "known_abilities": ["补充灵气", "交易支付"], "locked_abilities": [], "cooldown": "无", "last_trigger": None},
        "ability_summary": "常规修行资源，可补灵气、做交易和驱动部分器物。",
    },
    "符": {
        "resource_kind": "一次性法具",
        "core_functions": ["临时攻击/防御/遁走", "制造一次性效果"],
        "activation_rules": ["需要祭出、催动或注入灵力后生效"],
        "usage_limits": ["多数符箓一次性使用"],
        "costs": ["消耗数量", "可能消耗灵力"],
        "side_effects": ["容易暴露手段与底牌"],
        "growth_path": {"can_evolve": False, "current_stage": "稳定", "next_unlock_hint": "无"},
        "unlock_state": {"level": "已知", "known_abilities": ["短时爆发", "保命脱身"], "locked_abilities": [], "cooldown": "无", "last_trigger": None},
        "ability_summary": "一次性法具，适合应急攻击、防御与保命。",
    },
    "丹": {
        "resource_kind": "消耗丹药",
        "core_functions": ["疗伤恢复", "补益修为", "短时稳住状态"],
        "activation_rules": ["通常以服用、含化或配合运功的方式生效"],
        "usage_limits": ["药力有限，不宜连续滥用"],
        "costs": ["消耗数量", "可能累积丹毒或后遗反噬"],
        "side_effects": ["服用过量可能留下隐患"],
        "growth_path": {"can_evolve": False, "current_stage": "稳定", "next_unlock_hint": "无"},
        "unlock_state": {"level": "已知", "known_abilities": ["疗伤", "回气"], "locked_abilities": [], "cooldown": "视药力而定", "last_trigger": None},
        "ability_summary": "常规丹药，主要承担恢复、疗伤与短时修为补益。",
    },
    "药": {
        "resource_kind": "材料/药物",
        "core_functions": ["炼药配方材料", "基础疗伤或辅助"],
        "activation_rules": ["需煎制、炼化、服食或配伍后使用"],
        "usage_limits": ["单独使用时效果有限"],
        "costs": ["消耗数量", "可能需要额外配伍材料"],
        "side_effects": [],
        "growth_path": {"can_evolve": False, "current_stage": "稳定", "next_unlock_hint": "无"},
        "unlock_state": {"level": "已知", "known_abilities": ["疗伤辅助", "炼药材料"], "locked_abilities": [], "cooldown": "无", "last_trigger": None},
        "ability_summary": "常规药材/药物，更多服务于疗伤、炼药和阶段性辅助。",
    },
    "剑": {
        "resource_kind": "装备/法器",
        "core_functions": ["近战攻伐", "承载灵力或术式"],
        "activation_rules": ["需要持有、祭炼或灌注灵力后发挥全部效果"],
        "usage_limits": ["器物强度受持有者修为与祭炼程度限制"],
        "costs": ["可能损耗灵力或器物耐久"],
        "side_effects": ["高调使用可能暴露身份与路数"],
        "growth_path": {"can_evolve": True, "current_stage": "未祭炼/待观察", "next_unlock_hint": "祭炼或绑定后可提升契合度"},
        "unlock_state": {"level": "已知", "known_abilities": ["攻伐", "载灵"], "locked_abilities": ["更深层器灵/禁制"], "cooldown": "无", "last_trigger": None},
        "ability_summary": "装备型资源，承担攻伐与灵力承载作用。",
    },
    "镜": {
        "resource_kind": "核心器物",
        "core_functions": ["映照异常", "窥测线索", "在关键时刻提供额外信息"],
        "activation_rules": ["往往需被动触发或在特定场景/代价下启用"],
        "usage_limits": ["功能未完全明朗，不能当全能外挂使用"],
        "costs": ["可能消耗精神、灵力或引来窥探"],
        "side_effects": ["过度动用容易暴露异常或反噬"],
        "growth_path": {"can_evolve": True, "current_stage": "部分解锁", "next_unlock_hint": "在更高风险或更高境界下显露新能力"},
        "unlock_state": {"level": "部分解锁", "known_abilities": ["映照异常", "提供线索"], "locked_abilities": ["更深层能力待触发"], "cooldown": "待观察", "last_trigger": None},
        "ability_summary": "疑似核心机缘器物，偏向信息、映照与异常触发。",
    },
    "金手指": {
        "resource_kind": "能力核心",
        "core_functions": ["提供超常信息/能力入口", "关键时刻改写局势"],
        "activation_rules": ["只能在设定允许的触发条件下启用"],
        "usage_limits": ["不能无代价、无限制地解决所有问题"],
        "costs": ["通常伴随代价、冷却、暴露或未知风险"],
        "side_effects": ["过度使用可能招来反噬或引来外部注意"],
        "growth_path": {"can_evolve": True, "current_stage": "初始/待展开", "next_unlock_hint": "随章节推进分层解锁"},
        "unlock_state": {"level": "部分解锁", "known_abilities": ["基础功能"], "locked_abilities": ["深层功能"], "cooldown": "待观察", "last_trigger": None},
        "ability_summary": "主角核心外挂资源，必须严格受条件、代价和成长节奏约束。",
    },
}

QUANTITY_PATTERN = re.compile(r"^\s*([零一二两三四五六七八九十百千万\d]+)([\u4e00-\u9fff])(.+?)\s*$")
NEARBY_NUMBER_PATTERN = re.compile(r"([零一二两三四五六七八九十百千万\d]+)")


def _text(value: Any) -> str:
    return str(value or "").strip()



def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []



def parse_chinese_number(value: str | None) -> int | None:
    text = _text(value)
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    for ch in text:
        if ch in CHINESE_DIGITS:
            current = CHINESE_DIGITS[ch]
            continue
        unit = UNIT_VALUES.get(ch)
        if unit is None:
            return None
        if current == 0:
            current = 1
        if unit >= 10000:
            total = (total + current) * unit
            current = 0
            continue
        total += current * unit
        current = 0
    total += current
    if total == 0 and text in {"十", "百", "千", "万"}:
        return UNIT_VALUES[text]
    return total or None



def _guess_default_unit(name: str, *, stackable: bool) -> str:
    if not name:
        return "件"
    if "灵石" in name:
        return "块"
    if "符" in name:
        return "张"
    if "丹" in name:
        return "枚"
    if "药材" in name or "药草" in name or name.endswith("草"):
        return "株"
    if "箭" in name:
        return "支"
    if "剑" in name or "刀" in name or "枪" in name or "弓" in name:
        return "把"
    if stackable:
        return "份"
    return "件"



def _guess_stackable(name: str, unit: str | None) -> bool:
    unit_text = _text(unit)
    if unit_text in COUNTABLE_UNITS:
        return True
    if unit_text in ENTITY_UNITS:
        return False
    if any(hint in name for hint in STACKABLE_NAME_HINTS):
        return True
    if any(hint in name for hint in ENTITY_NAME_HINTS):
        return False
    return False



def _resource_hint_key(name: str) -> str:
    for key in RESOURCE_FUNCTION_HINTS:
        if key in name:
            return key
    return ""



def _guess_resource_scope(name: str, resource_type: str) -> str:
    text_blob = f"{name} {resource_type}"
    if any(keyword in text_blob for keyword in CORE_RESOURCE_KEYWORDS):
        return "核心资源"
    if any(token in text_blob for token in ["本命", "绑定", "核心", "传承"]):
        return "核心资源"
    return "普通资源"



def _guess_resource_kind(name: str, *, stackable: bool, quantity_mode: str) -> str:
    hint_key = _resource_hint_key(name)
    if hint_key:
        return _text((RESOURCE_FUNCTION_HINTS.get(hint_key) or {}).get("resource_kind")) or ("能力核心" if hint_key == "金手指" else "待细化资源")
    if quantity_mode == "countable":
        return "消耗/材料"
    if stackable:
        return "消耗/材料"
    return "装备/实体"



def _default_capability_profile(name: str, *, resource_type: str, quantity_mode: str, stackable: bool) -> dict[str, Any]:
    hint_key = _resource_hint_key(name)
    hint = deepcopy(RESOURCE_FUNCTION_HINTS.get(hint_key) or {})
    scope = _guess_resource_scope(name, resource_type)
    resource_kind = _text(hint.get("resource_kind")) or _guess_resource_kind(name, stackable=stackable, quantity_mode=quantity_mode)
    core_functions = _safe_list(hint.get("core_functions")) or (["阶段性资源功能待细化"] if scope != "核心资源" else ["核心能力待细化"])
    activation_rules = _safe_list(hint.get("activation_rules")) or ["必须在本章规划和设定允许范围内使用。"]
    usage_limits = _safe_list(hint.get("usage_limits")) or ["不可无条件解决所有问题。"]
    costs = _safe_list(hint.get("costs")) or (["消耗数量"] if quantity_mode == "countable" else ["可能消耗灵力/体力/暴露度"])
    side_effects = _safe_list(hint.get("side_effects"))
    growth_path = hint.get("growth_path") if isinstance(hint.get("growth_path"), dict) else {"can_evolve": False, "current_stage": "待观察", "next_unlock_hint": "无"}
    unlock_state = hint.get("unlock_state") if isinstance(hint.get("unlock_state"), dict) else {"level": "已知", "known_abilities": core_functions[:2], "locked_abilities": [], "cooldown": "无", "last_trigger": None}
    summary = _text(hint.get("ability_summary")) or ("这是主角强绑定的核心资源，能力要逐步解锁。" if scope == "核心资源" else "这是常规资源，主要服务于当下剧情与生存。")
    hard_rules = [
        "能力使用不得突破当前设定边界。",
        "数量、冷却、暴露和已知/未知能力必须前后一致。",
    ]
    if scope == "核心资源":
        hard_rules.append("核心资源不能无代价、无条件、无限次解决问题。")
    return {
        "resource_scope": scope,
        "resource_kind": resource_kind,
        "core_functions": core_functions,
        "ability_summary": summary,
        "ability_details": {
            "summary": summary,
            "abilities": [
                {
                    "name": item,
                    "effect": item,
                    "trigger": activation_rules[min(idx, len(activation_rules) - 1)],
                    "limits": usage_limits[min(idx, len(usage_limits) - 1)],
                    "cost": costs[min(idx, len(costs) - 1)],
                    "risk": side_effects[min(idx, len(side_effects) - 1)] if side_effects else "待观察",
                }
                for idx, item in enumerate(core_functions[:3])
            ],
        },
        "activation_rules": activation_rules,
        "usage_limits": usage_limits,
        "costs": costs,
        "side_effects": side_effects,
        "growth_path": growth_path,
        "unlock_state": unlock_state,
        "constraint_profile": {
            "hard_rules": hard_rules,
            "soft_preferences": ["优先让资源服务当前章节目标，而不是抢戏。", "核心资源的能力暴露与成长节奏要克制。"],
        },
        "last_capability_update": {
            "source": "seed",
            "at": _now_iso(),
            "note": "按名称与类型补齐资源能力档案。",
        },
    }



def parse_resource_seed(raw_value: Any) -> dict[str, Any]:
    raw = _text(raw_value)
    if not raw:
        return {
            "name": "",
            "display_name": "",
            "quantity": 0,
            "unit": "件",
            "stackable": False,
            "quantity_sensitive": True,
            "quantity_mode": "entity",
        }
    quantity = 1
    unit = ""
    name = raw
    matched = QUANTITY_PATTERN.match(raw)
    if matched:
        maybe_number, maybe_unit, maybe_name = matched.groups()
        parsed_number = parse_chinese_number(maybe_number)
        if parsed_number is not None and _text(maybe_name):
            quantity = parsed_number
            unit = maybe_unit
            name = _text(maybe_name)
    stackable = _guess_stackable(name, unit)
    if not unit:
        unit = _guess_default_unit(name, stackable=stackable)
    quantity_mode = "countable" if stackable else "entity"
    return {
        "name": name,
        "display_name": raw,
        "quantity": quantity,
        "unit": unit,
        "stackable": stackable,
        "quantity_sensitive": True,
        "quantity_mode": quantity_mode,
    }



def normalize_resource_name(raw_value: Any) -> str:
    return _text(parse_resource_seed(raw_value).get("name"))



def normalize_resource_refs(values: list[Any] | None) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        name = normalize_resource_name(value)
        if not name or name in seen:
            continue
        seen.add(name)
        refs.append(name)
    return refs



def build_resource_card(
    raw_value: Any,
    *,
    owner: str,
    resource_type: str,
    status: str,
    rarity: str,
    exposure_risk: str,
    narrative_role: str,
    recent_change: str,
    source: str = "seed",
) -> tuple[str, dict[str, Any]]:
    seed = parse_resource_seed(raw_value)
    name = _text(seed.get("name"))
    profile = _default_capability_profile(
        name,
        resource_type=_text(resource_type),
        quantity_mode=_text(seed.get("quantity_mode")),
        stackable=bool(seed.get("stackable")),
    )
    card = {
        "name": name,
        "display_name": _text(seed.get("display_name")) or name,
        "entity_type": "resource",
        "resource_type": _text(resource_type),
        "owner": _text(owner),
        "status": _text(status),
        "rarity": _text(rarity),
        "exposure_risk": _text(exposure_risk),
        "narrative_role": _text(narrative_role),
        "recent_change": _text(recent_change),
        "quantity": int(seed.get("quantity") or 0),
        "unit": _text(seed.get("unit")) or "件",
        "stackable": bool(seed.get("stackable")),
        "quantity_sensitive": bool(seed.get("quantity_sensitive", True)),
        "quantity_mode": _text(seed.get("quantity_mode")) or "entity",
        "quantity_note": "数量敏感，后续章节必须保持前后一致。",
        "importance_tier": "阶段级",
        "importance_score": 58,
        "resource_tier": "阶段级",
        "tracking_level": "standard",
        "appearance_priority": "当前阶段优先",
        "plot_relevance": "待后续章节评估。",
        "binding_target": _text(owner),
        "last_quantity_change": {
            "source": source,
            "action": "init",
            "delta": 0,
            "quantity_after": int(seed.get("quantity") or 0),
            "note": _text(recent_change),
        },
        **profile,
    }
    card["last_capability_update"] = {
        "source": source,
        "at": _now_iso(),
        "note": "初始化资源能力档案。",
    }
    return name, card



def ensure_resource_card_structure(card: dict[str, Any] | None, *, fallback_name: str = "", owner: str | None = None) -> dict[str, Any]:
    payload = deepcopy(card or {})
    raw_name = _text(payload.get("display_name") or payload.get("name") or fallback_name)
    seed = parse_resource_seed(raw_name)
    explicit_name = _text(payload.get("name"))
    seed_name = _text(seed.get("name"))
    if explicit_name and explicit_name != raw_name:
        name = explicit_name
    else:
        name = seed_name or explicit_name or _text(fallback_name)
    stackable = bool(payload.get("stackable")) if "stackable" in payload else bool(seed.get("stackable"))
    quantity = payload.get("quantity")
    if quantity in (None, ""):
        quantity = seed.get("quantity")
    try:
        quantity = int(quantity)
    except Exception:
        quantity = int(seed.get("quantity") or 1)
    unit = _text(payload.get("unit") or seed.get("unit") or _guess_default_unit(name, stackable=stackable)) or "件"
    payload.setdefault("display_name", raw_name or name)
    payload["name"] = name
    payload.setdefault("entity_type", "resource")
    payload.setdefault("resource_type", "待细化资源")
    payload.setdefault("owner", _text(owner) or _text(payload.get("owner")))
    payload.setdefault("status", "持有中")
    payload.setdefault("rarity", "普通/待判定")
    payload.setdefault("exposure_risk", "待观察")
    payload.setdefault("narrative_role", "资源状态待后续章节细化。")
    payload.setdefault("recent_change", "结构补齐。")
    payload["quantity"] = max(quantity, 0)
    payload["unit"] = unit
    payload["stackable"] = stackable
    payload.setdefault("quantity_sensitive", True)
    payload.setdefault("quantity_mode", "countable" if stackable else "entity")
    payload.setdefault("quantity_note", "数量敏感，后续章节必须保持前后一致。")
    payload.setdefault("importance_tier", "阶段级")
    payload.setdefault("importance_score", 58)
    payload.setdefault("resource_tier", payload.get("importance_tier") or "阶段级")
    payload.setdefault("tracking_level", "standard")
    payload.setdefault("appearance_priority", "当前阶段优先")
    payload.setdefault("plot_relevance", "待后续章节评估。")
    payload.setdefault("binding_target", _text(owner) or _text(payload.get("owner")))
    payload.setdefault(
        "last_quantity_change",
        {
            "source": "migration",
            "action": "normalize",
            "delta": 0,
            "quantity_after": payload["quantity"],
            "note": _text(payload.get("recent_change")) or "结构补齐。",
        },
    )
    profile = _default_capability_profile(
        name,
        resource_type=_text(payload.get("resource_type")),
        quantity_mode=_text(payload.get("quantity_mode")),
        stackable=bool(payload.get("stackable")),
    )
    for key, value in profile.items():
        if key not in payload or payload.get(key) in (None, "", [], {}):
            payload[key] = deepcopy(value)
        elif isinstance(payload.get(key), dict) and isinstance(value, dict):
            merged = deepcopy(value)
            merged.update(payload.get(key) or {})
            payload[key] = merged
    payload.setdefault(
        "last_capability_update",
        {
            "source": "migration",
            "at": _now_iso(),
            "note": "资源能力档案已补齐。",
        },
    )
    return payload



def infer_resource_plan_entry(resource_name: str, card: dict[str, Any], plan_text: str) -> dict[str, Any]:
    action = "carry_over"
    note = "本章默认承接上章资源状态。"
    matched_delta: int | None = None
    if resource_name and resource_name in plan_text:
        escaped_name = re.escape(resource_name)
        for candidate_action, keywords in RESOURCE_ACTION_PATTERNS:
            for keyword in keywords:
                patterns = [
                    rf"{keyword}[^，。；、\n]{{0,6}}?{escaped_name}",
                    rf"{escaped_name}[^，。；、\n]{{0,6}}?{keyword}",
                ]
                matched_segment = None
                for pattern in patterns:
                    match = re.search(pattern, plan_text)
                    if match:
                        matched_segment = match.group(0)
                        break
                if matched_segment:
                    action = candidate_action
                    note = matched_segment.strip()
                    number_match = None
                    for maybe in reversed(list(NEARBY_NUMBER_PATTERN.finditer(matched_segment))):
                        parsed = parse_chinese_number(maybe.group(1))
                        if parsed is not None:
                            number_match = parsed
                            break
                    matched_delta = number_match
                    break
            if action != "carry_over":
                break
    start_quantity = int(card.get("quantity") or 0)
    end_quantity = start_quantity
    delta = 0
    if matched_delta is not None:
        if action in {"gain", "transfer_in"}:
            delta = matched_delta
            end_quantity = start_quantity + matched_delta
        elif action in {"consume", "transfer_out", "damage"}:
            delta = -matched_delta
            end_quantity = max(start_quantity - matched_delta, 0)
        else:
            delta = 0
    return {
        "resource_name": resource_name,
        "start_quantity": start_quantity,
        "unit": _text(card.get("unit")) or "件",
        "stackable": bool(card.get("stackable")),
        "quantity_sensitive": bool(card.get("quantity_sensitive", True)),
        "planned_action": action,
        "delta_hint": delta,
        "end_quantity_hint": end_quantity,
        "note": note,
    }



def _capability_fallback_entry(resource_name: str, card: dict[str, Any], plan_text: str) -> dict[str, Any]:
    normalized = ensure_resource_card_structure(card, fallback_name=resource_name, owner=_text(card.get("owner")))
    text_blob = f"{plan_text}\n{normalized.get('ability_summary')}\n{normalized.get('recent_change')}"
    mentioned = resource_name in plan_text if resource_name else False
    scope = _text(normalized.get("resource_scope")) or "普通资源"
    should_use = bool(mentioned)
    if scope == "核心资源":
        should_use = True
    usage_role = "承接上章资源状态"
    if mentioned:
        if any(token in text_blob for token in ["试", "探", "验", "照", "看", "映"]):
            usage_role = "验证/试探"
        elif any(token in text_blob for token in ["逃", "守", "保命"]):
            usage_role = "保命/应急"
        elif any(token in text_blob for token in ["换", "买", "卖", "付"]):
            usage_role = "交易/支付"
        elif any(token in text_blob for token in ["斗", "杀", "战", "斩"]):
            usage_role = "攻防/对抗"
        else:
            usage_role = "服务当前章推进"
    trigger = (_safe_list(normalized.get("activation_rules")) or ["按设定条件触发"])[0]
    hard_constraints = _safe_list(((normalized.get("constraint_profile") or {}).get("hard_rules")))[:3]
    expected_costs = _safe_list(normalized.get("costs"))[:2]
    expected_risks = _safe_list(normalized.get("side_effects"))[:2]
    unlock_change = "维持当前解锁状态"
    if scope == "核心资源" and any(token in text_blob for token in ["第一次", "异动", "发热", "震", "回应", "共鸣", "照出"]):
        unlock_change = "允许出现一次小幅解锁或异常回应，但不能越界成万能解题。"
    cooldown_after_use = _text((((normalized.get("unlock_state") or {}).get("cooldown")))) or "无"
    continuity_note = "若本章调用该资源，必须和上一章已有状态、数量与已知能力保持一致。"
    return {
        "resource_name": resource_name,
        "resource_scope": scope,
        "resource_kind": _text(normalized.get("resource_kind")),
        "should_use": should_use,
        "usage_role": usage_role,
        "capability_focus": _safe_list(normalized.get("core_functions"))[:3],
        "trigger_window": trigger,
        "hard_constraints": hard_constraints,
        "expected_costs": expected_costs,
        "expected_risks": expected_risks,
        "unlock_change": unlock_change,
        "cooldown_after_use": cooldown_after_use,
        "continuity_note": continuity_note,
        "ability_summary": _text(normalized.get("ability_summary")),
    }



def build_resource_capability_plan(
    *,
    story_bible: dict[str, Any],
    protagonist_name: str,
    plan: dict[str, Any],
    resources: dict[str, Any],
    selected_resources: list[str],
    recent_summaries: list[dict[str, Any]] | None = None,
    serialized_last: dict[str, Any] | None = None,
    allow_ai: bool = True,
) -> dict[str, Any]:
    plan_text = "\n".join(
        str(item or "")
        for item in [
            plan.get("title"),
            plan.get("goal"),
            plan.get("conflict"),
            plan.get("main_scene"),
            plan.get("opening_beat"),
            plan.get("mid_turn"),
            plan.get("discovery"),
            plan.get("ending_hook"),
            plan.get("supporting_character_note"),
        ]
        if _text(item)
    )
    fallback_map: dict[str, Any] = {}
    selected_cards: dict[str, Any] = {}
    for name in selected_resources or []:
        card = ensure_resource_card_structure(resources.get(name) or {}, fallback_name=name, owner=protagonist_name)
        resources[name] = card
        selected_cards[name] = {
            "name": card.get("name"),
            "resource_scope": card.get("resource_scope"),
            "resource_kind": card.get("resource_kind"),
            "quantity": int(card.get("quantity") or 0),
            "unit": card.get("unit"),
            "importance_tier": card.get("importance_tier") or card.get("resource_tier"),
            "ability_summary": card.get("ability_summary"),
            "core_functions": _safe_list(card.get("core_functions"))[:3],
            "activation_rules": _safe_list(card.get("activation_rules"))[:2],
            "usage_limits": _safe_list(card.get("usage_limits"))[:2],
            "costs": _safe_list(card.get("costs"))[:2],
            "side_effects": _safe_list(card.get("side_effects"))[:2],
            "unlock_state": card.get("unlock_state") or {},
        }
        fallback_map[name] = _capability_fallback_entry(name, card, plan_text)

    local_context = {
        "protagonist_name": protagonist_name,
        "chapter_plan": {
            "chapter_no": int(plan.get("chapter_no", 0) or 0),
            "title": _text(plan.get("title")),
            "goal": _text(plan.get("goal")),
            "conflict": _text(plan.get("conflict")),
            "event_type": _text(plan.get("event_type")),
            "progress_kind": _text(plan.get("progress_kind")),
            "hook": _text(plan.get("ending_hook") or plan.get("hook_style")),
        },
        "selected_resources": selected_cards,
        "recent_summaries": [
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "title": _text(item.get("title")),
                "event_summary": _text(item.get("event_summary") or item.get("summary")),
                "open_hooks": _safe_list(item.get("open_hooks"))[:3],
            }
            for item in (recent_summaries or [])[-3:]
            if isinstance(item, dict)
        ],
        "last_chapter_tail": {
            "tail_excerpt": _text((serialized_last or {}).get("tail_excerpt")),
            "opening_anchor": _text((((serialized_last or {}).get("continuity_bridge") or {}).get("opening_anchor"))),
            "unresolved_action_chain": _safe_list((((serialized_last or {}).get("continuity_bridge") or {}).get("unresolved_action_chain")))[:3],
        },
    }
    hard_constraints = [
        "只能使用当前 selected_resources 中已经存在的资源卡，不得凭空新增能力。",
        "资源能力使用必须服从 quantity / unit / unlock_state / activation_rules / usage_limits。",
        "核心资源可以显露新层次，但只能小步推进，不得直接写成万能外挂。",
        "若资源本章不该用，可以明确保持承接状态，不必强行出手。",
        "输出必须覆盖每个 selected_resource。",
    ]
    soft_goals = [
        "让资源真正服务本章目标、冲突和连续性，不要像库存表。",
        "优先保持能力边界、代价和风险可感。",
        "若某资源适合留给下一章，也要给出保留原因。",
    ]
    output_contract = {
        "type": "dict",
        "required_resource_fields": [
            "resource_name",
            "resource_scope",
            "resource_kind",
            "should_use",
            "usage_role",
            "capability_focus",
            "trigger_window",
            "hard_constraints",
            "expected_costs",
            "expected_risks",
            "unlock_change",
            "cooldown_after_use",
            "continuity_note",
            "ability_summary",
        ],
        "top_level_meta": ["__meta__"],
    }

    def _fallback_builder(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "__meta__": {
                "reasoning_mode": "local_constraints_seed",
                "selected_count": len(fallback_map),
                "summary": "已按资源名称、能力档案和当前章节拍表生成约束种子结果。",
            },
            **deepcopy(fallback_map),
        }

    reasoning = run_local_constraint_reasoning(
        story_bible=story_bible,
        task_type="resource_capability_plan",
        scope="chapter_planning",
        chapter_no=int(plan.get("chapter_no", 0) or 0),
        allow_ai=allow_ai,
        local_context=local_context,
        hard_constraints=hard_constraints,
        soft_goals=soft_goals,
        output_contract=output_contract,
        baseline_builder=_fallback_builder,
    )
    result = reasoning.get("result") if isinstance(reasoning, dict) else {}
    if not isinstance(result, dict):
        result = _fallback_builder({})
    result.setdefault(
        "__meta__",
        {
            "reasoning_mode": "local_constraints_ai",
            "selected_count": len(fallback_map),
        },
    )
    result["__meta__"].update(
        {
            "used_ai": bool(reasoning.get("used_ai")),
            "reason": _text(reasoning.get("reason")),
            "confidence": _text(reasoning.get("confidence")),
        }
    )
    for name, fallback_entry in fallback_map.items():
        merged = deepcopy(fallback_entry)
        candidate = result.get(name)
        if isinstance(candidate, dict):
            merged.update({key: value for key, value in candidate.items() if value not in (None, "", [], {})})
        result[name] = merged
    return result



def apply_resource_plan(resources: dict[str, Any], resource_plan: dict[str, Any], *, chapter_no: int) -> None:
    for name, entry in (resource_plan or {}).items():
        card = resources.get(name)
        if not isinstance(card, dict):
            continue
        delta = entry.get("delta_hint")
        if not isinstance(delta, int) or delta == 0:
            continue
        current_quantity = int(card.get("quantity") or 0)
        new_quantity = max(current_quantity + delta, 0)
        card["quantity"] = new_quantity
        action = _text(entry.get("planned_action")) or "update"
        unit = _text(card.get("unit")) or "件"
        card["recent_change"] = f"第{chapter_no}章按规划{action} {abs(delta)}{unit}。"
        card["last_quantity_change"] = {
            "source": "chapter_plan_packet",
            "chapter_no": chapter_no,
            "action": action,
            "delta": delta,
            "quantity_after": new_quantity,
            "note": _text(entry.get("note")) or _text(card.get("recent_change")),
        }



def apply_resource_capability_plan(resources: dict[str, Any], resource_capability_plan: dict[str, Any], *, chapter_no: int) -> None:
    for name, entry in (resource_capability_plan or {}).items():
        if name == "__meta__":
            continue
        card = resources.get(name)
        if not isinstance(card, dict) or not isinstance(entry, dict):
            continue
        normalized = ensure_resource_card_structure(card, fallback_name=name, owner=_text(card.get("owner")))
        should_use = bool(entry.get("should_use"))
        unlock_change = _text(entry.get("unlock_change"))
        cooldown = _text(entry.get("cooldown_after_use"))
        risks = _safe_list(entry.get("expected_risks"))[:2]
        costs = _safe_list(entry.get("expected_costs"))[:2]
        if should_use:
            normalized["recent_change"] = f"第{chapter_no}章资源能力按规划参与：{_text(entry.get('usage_role')) or '服务当前章推进'}。"
            normalized["last_capability_update"] = {
                "source": "chapter_plan_packet",
                "at": _now_iso(),
                "chapter_no": chapter_no,
                "usage_role": _text(entry.get("usage_role")),
                "unlock_change": unlock_change,
                "costs": costs,
                "risks": risks,
            }
            unlock_state = normalized.setdefault("unlock_state", {})
            if unlock_change and any(token in unlock_change for token in ["解锁", "部分解锁", "新层次"]):
                unlock_state["level"] = "部分解锁" if "部分" in unlock_change else "已知"
            if cooldown:
                unlock_state["cooldown"] = cooldown
            unlock_state["last_trigger"] = {
                "chapter_no": chapter_no,
                "usage_role": _text(entry.get("usage_role")),
            }
            if risks:
                normalized["exposure_risk"] = "；".join(str(item) for item in risks[:2])
        resources[name] = normalized
