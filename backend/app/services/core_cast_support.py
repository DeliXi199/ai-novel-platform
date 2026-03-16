from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from app.services.story_character_support import apply_character_template_defaults, pick_character_template


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


MASTER_SLOT_LIBRARY: list[dict[str, Any]] = [
    {
        "slot_template_id": "mutual_help_early",
        "binding_pattern": "先帮后反帮",
        "entry_phase": "前期",
        "entry_chapter_window": [1, 4],
        "first_entry_mission": "先在现实难关里帮主角稳住一口气。",
        "long_term_relation_line": "前期帮主角更多，后面会轮到主角反过来帮他/她。",
        "appearance_frequency": "高频",
        "initial_relation": "谨慎接近",
        "preferred_role_tags": ["互助", "生存", "资源线"],
        "preferred_profiles": ["loner", "balanced", "group", "multi_faction"],
        "importance_tier": "核心配角",
    },
    {
        "slot_template_id": "enemy_to_friend",
        "binding_pattern": "先敌后友",
        "entry_phase": "前期",
        "entry_chapter_window": [2, 6],
        "first_entry_mission": "先给主角制造一次正面冲突或误判。",
        "long_term_relation_line": "先互相看不顺眼，后面因共同风险或利益慢慢变成伙伴。",
        "appearance_frequency": "中频",
        "initial_relation": "敌意试探",
        "preferred_role_tags": ["冲突", "敌转友", "火药味"],
        "preferred_profiles": ["balanced", "group", "multi_faction"],
        "importance_tier": "核心配角",
    },
    {
        "slot_template_id": "trade_partner",
        "binding_pattern": "交易成线",
        "entry_phase": "中前期",
        "entry_chapter_window": [4, 9],
        "first_entry_mission": "带来一条资源、情报或渠道交换线。",
        "long_term_relation_line": "先交易合作，后面在利益与情分之间摇摆。",
        "appearance_frequency": "中频",
        "initial_relation": "互相利用",
        "preferred_role_tags": ["交易", "资源", "渠道"],
        "preferred_profiles": ["balanced", "group", "multi_faction"],
        "importance_tier": "重要配角",
    },
    {
        "slot_template_id": "pressure_source",
        "binding_pattern": "长期压迫源",
        "entry_phase": "中前期",
        "entry_chapter_window": [5, 10],
        "first_entry_mission": "代表一股具体压力，抬高主角行动代价。",
        "long_term_relation_line": "不一定一直在场，但会持续影响主角的选择和风险。",
        "appearance_frequency": "低频",
        "initial_relation": "压迫/盯防",
        "preferred_role_tags": ["势力线", "压迫", "高位压力"],
        "preferred_profiles": ["group", "multi_faction", "balanced"],
        "importance_tier": "重要配角",
    },
    {
        "slot_template_id": "shared_suffering",
        "binding_pattern": "共患难绑定",
        "entry_phase": "中期",
        "entry_chapter_window": [8, 14],
        "first_entry_mission": "和主角一起扛一次局面，建立更深绑定。",
        "long_term_relation_line": "关系会因共同吃过苦而变重，不容易再回到路人状态。",
        "appearance_frequency": "中频",
        "initial_relation": "被迫同路",
        "preferred_role_tags": ["共患难", "绑定", "团队"],
        "preferred_profiles": ["group", "balanced", "loner"],
        "importance_tier": "核心配角",
    },
    {
        "slot_template_id": "old_debt_return",
        "binding_pattern": "旧账回潮",
        "entry_phase": "中期",
        "entry_chapter_window": [10, 18],
        "first_entry_mission": "把旧线索、旧债或旧因果重新拖回台面。",
        "long_term_relation_line": "看似是旧事回潮，实际会改写主角之后的关系判断。",
        "appearance_frequency": "低频",
        "initial_relation": "旧因果未清",
        "preferred_role_tags": ["旧账", "因果", "回潮"],
        "preferred_profiles": ["loner", "balanced", "multi_faction"],
        "importance_tier": "重要配角",
    },
    {
        "slot_template_id": "remote_ally",
        "binding_pattern": "远端盟友",
        "entry_phase": "中期",
        "entry_chapter_window": [12, 20],
        "first_entry_mission": "带主角看见更大地图或更远处的机会。",
        "long_term_relation_line": "平时不高频出现，但关键节点能拉主角一把或给出新方向。",
        "appearance_frequency": "低频",
        "initial_relation": "陌生但可接近",
        "preferred_role_tags": ["地图升级", "盟友", "新世界"],
        "preferred_profiles": ["group", "multi_faction", "balanced"],
        "importance_tier": "重要配角",
    },
    {
        "slot_template_id": "group_anchor",
        "binding_pattern": "团队锚点",
        "entry_phase": "中前期",
        "entry_chapter_window": [3, 8],
        "first_entry_mission": "充当团队、同门、组织或小圈子的情感锚点。",
        "long_term_relation_line": "不仅能推动剧情，还能承接主角在群体中的关系变化。",
        "appearance_frequency": "高频",
        "initial_relation": "同路观察",
        "preferred_role_tags": ["同门", "团队", "群像"],
        "preferred_profiles": ["group", "multi_faction"],
        "importance_tier": "核心配角",
    },
    {
        "slot_template_id": "mirror_rival",
        "binding_pattern": "镜像对照",
        "entry_phase": "中期",
        "entry_chapter_window": [11, 19],
        "first_entry_mission": "以相似处境或相反选择，照出主角的路。",
        "long_term_relation_line": "既像对手也像镜子，能放大主角的价值观选择。",
        "appearance_frequency": "中频",
        "initial_relation": "对照竞争",
        "preferred_role_tags": ["镜像", "竞争", "选择"],
        "preferred_profiles": ["balanced", "multi_faction", "group"],
        "importance_tier": "重要配角",
    },
    {
        "slot_template_id": "late_key_pivot",
        "binding_pattern": "关键反转位",
        "entry_phase": "中后段",
        "entry_chapter_window": [16, 26],
        "first_entry_mission": "在关键处改变一条人物线或势力线的走向。",
        "long_term_relation_line": "前面可以只埋影子，真正登场后负责把旧线翻面。",
        "appearance_frequency": "低频",
        "initial_relation": "暂未明确",
        "preferred_role_tags": ["反转", "伏笔兑现", "翻面"],
        "preferred_profiles": ["balanced", "multi_faction", "group", "loner"],
        "importance_tier": "重要配角",
    },
]


PROFILE_RULES = {
    "loner": {"count_range": [3, 5], "basis": "偏单人求生/苟住推进，核心配角不宜过多。"},
    "balanced": {"count_range": [4, 6], "basis": "常规成长连载，主角线和关系线并重。"},
    "group": {"count_range": [5, 8], "basis": "宗门/学院/团队/帮派类，重要配角需要更丰富。"},
    "multi_faction": {"count_range": [6, 9], "basis": "多势力博弈或群像结构，核心配角人数适当上调。"},
}


ANCHOR_SURNAMES = ["沈", "顾", "苏", "陆", "谢", "裴", "宁", "宋", "温", "程", "秦", "韩", "柳", "周", "乔", "林"]
ANCHOR_GIVEN_POOL_A = ["青", "沉", "晚", "昭", "知", "行", "遥", "烬", "砚", "岚", "微", "照", "霁", "衡", "弦", "舟"]
ANCHOR_GIVEN_POOL_B = ["河", "川", "雪", "宁", "霜", "月", "岫", "棠", "言", "舟", "野", "桥", "竹", "安", "歌", "临"]


def _seed_text(*parts: Any) -> str:
    payload = "|".join(_text(part) for part in parts if _text(part))
    return payload or "core-cast-default"


def _seed_int(*parts: Any) -> int:
    digest = hashlib.md5(_seed_text(*parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _style_map(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        raw = payload.get("style_preferences")
        return raw if isinstance(raw, dict) else {}
    raw = getattr(payload, "style_preferences", None)
    return raw if isinstance(raw, dict) else {}


def _genre_text(payload: Any) -> str:
    if isinstance(payload, dict):
        return _text(payload.get("genre"))
    return _text(getattr(payload, "genre", None))


def _premise_text(payload: Any) -> str:
    if isinstance(payload, dict):
        return _text(payload.get("premise"))
    return _text(getattr(payload, "premise", None))


def _protagonist_name(payload: Any) -> str:
    if isinstance(payload, dict):
        return _text(payload.get("protagonist_name"), "主角")
    return _text(getattr(payload, "protagonist_name", None), "主角")


def detect_core_cast_profile(payload: Any) -> str:
    style = _style_map(payload)
    text_blob = " ".join(
        [
            _genre_text(payload),
            _premise_text(payload),
            _text(style.get("story_engine")),
            _text(style.get("world_scale")),
            _text(style.get("opening_mode")),
            " ".join(str(item) for item in (style.get("factions") or [])),
        ]
    ).lower()
    faction_count = len(style.get("factions") or [])
    if any(token in text_blob for token in ["宗门", "学院", "门派", "同门", "团队", "帮派", "结伴", "群像"]) or faction_count >= 5:
        return "group"
    if any(token in text_blob for token in ["朝堂", "权谋", "世家", "城邦", "多势力", "博弈"]) or faction_count >= 7:
        return "multi_faction"
    if any(token in text_blob for token in ["凡人", "苟", "求生", "逃亡", "边城", "荒野", "孤身", "独自"]):
        return "loner"
    return "balanced"


def estimate_core_cast_count(payload: Any) -> tuple[str, int, list[int], str]:
    profile = detect_core_cast_profile(payload)
    rule = PROFILE_RULES.get(profile, PROFILE_RULES["balanced"])
    low, high = rule["count_range"]
    span = max(high - low + 1, 1)
    seed = _seed_int(_genre_text(payload), _premise_text(payload), json.dumps(_style_map(payload), ensure_ascii=False, sort_keys=True))
    count = low + (seed % span)
    return profile, count, [low, high], rule["basis"]


def _slot_library_for_profile(profile: str, *, seed: int) -> list[dict[str, Any]]:
    preferred = [item for item in MASTER_SLOT_LIBRARY if profile in item.get("preferred_profiles", [])]
    fallback = [item for item in MASTER_SLOT_LIBRARY if item not in preferred]
    ordered = preferred + fallback
    shift = seed % len(ordered) if ordered else 0
    if shift:
        ordered = ordered[shift:] + ordered[:shift]
    return ordered


def _anchor_target_count(slots: list[dict[str, Any]]) -> int:
    early_slots = [slot for slot in slots if isinstance(slot, dict) and int(((slot.get("entry_chapter_window") or [9])[0] or 9)) <= 6]
    if not early_slots:
        return 0
    if len(early_slots) == 1:
        return 1
    return 2


def _character_name_for_slot(payload: Any, slot: dict[str, Any], *, used_names: set[str], index: int) -> str:
    seed = _seed_int(
        _genre_text(payload),
        _premise_text(payload),
        _protagonist_name(payload),
        _text(slot.get("slot_id")),
        _text(slot.get("binding_pattern")),
        index,
    )
    attempts = len(ANCHOR_SURNAMES) * len(ANCHOR_GIVEN_POOL_A)
    for offset in range(max(attempts, 1)):
        local = seed + offset * 7
        surname = ANCHOR_SURNAMES[local % len(ANCHOR_SURNAMES)]
        given = ANCHOR_GIVEN_POOL_A[(local // len(ANCHOR_SURNAMES)) % len(ANCHOR_GIVEN_POOL_A)] + ANCHOR_GIVEN_POOL_B[(local // 3) % len(ANCHOR_GIVEN_POOL_B)]
        candidate = f"{surname}{given}"
        if candidate not in used_names and candidate != _protagonist_name(payload):
            used_names.add(candidate)
            return candidate
    fallback = f"配角{index}号"
    used_names.add(fallback)
    return fallback


def _anchor_template_fallback(slot: dict[str, Any], *, name: str) -> str:
    binding = _text(slot.get("binding_pattern"))
    mission = _text(slot.get("first_entry_mission"))
    tags = " ".join(_text(item) for item in (slot.get("preferred_role_tags") or []))
    blob = f"{binding} {mission} {tags} {name}"
    if any(token in blob for token in ["敌", "压迫", "竞争", "镜像", "执法"]):
        return "wounded_pride_rival"
    if any(token in blob for token in ["交易", "渠道", "情报", "掌柜"]):
        return "calculating_trade_partner"
    if any(token in blob for token in ["团队", "同门", "锚点", "结伴"]):
        return "dry_humor_teammate"
    if any(token in blob for token in ["疗", "丹", "救", "医"]):
        return "merciful_healer_with_edges"
    if any(token in blob for token in ["旧账", "旧因果", "回潮"]):
        return "old_debt_cynic"
    if any(token in blob for token in ["远端", "盟友", "新世界", "地图升级"]):
        return "silken_negotiator"
    return "starter_hard_shell_soft_core"


def _anchor_role_hint(slot: dict[str, Any]) -> str:
    tags = [_text(item) for item in (slot.get("preferred_role_tags") or []) if _text(item)]
    parts = [
        _text(slot.get("binding_pattern")),
        _text(slot.get("entry_phase")),
        *tags[:3],
    ]
    return " / ".join(part for part in parts if part)


def _build_anchored_characters(payload: Any, slots: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    target = _anchor_target_count(slots)
    if target <= 0:
        return 0, []
    ranked = sorted(
        [slot for slot in slots if isinstance(slot, dict)],
        key=lambda item: (
            int(((item.get("entry_chapter_window") or [99])[0] or 99)),
            0 if _text(item.get("importance_tier")) == "核心配角" else 1,
            0 if _text(item.get("appearance_frequency")) == "高频" else 1,
            _text(item.get("slot_id")),
        ),
    )
    selected = ranked[:target]
    used_names: set[str] = set()
    anchored: list[dict[str, Any]] = []
    for idx, slot in enumerate(selected, start=1):
        name = _character_name_for_slot(payload, slot, used_names=used_names, index=idx)
        fallback_id = _anchor_template_fallback(slot, name=name)
        entry_window = list(slot.get("entry_chapter_window") or [max(1, idx), max(3, idx + 3)])
        anchored.append(
            {
                "anchor_id": f"ACC{idx:02d}",
                "slot_id": _text(slot.get("slot_id")),
                "name": name,
                "entry_phase": _text(slot.get("entry_phase"), "前期"),
                "entry_chapter_window": entry_window,
                "binding_pattern": _text(slot.get("binding_pattern")),
                "first_entry_mission": _text(slot.get("first_entry_mission")),
                "long_term_relation_line": _text(slot.get("long_term_relation_line")),
                "appearance_frequency": _text(slot.get("appearance_frequency"), "中频"),
                "importance_tier": _text(slot.get("importance_tier"), "重要配角"),
                "initial_relation": _text(slot.get("initial_relation"), "待观察"),
                "preferred_role_tags": list(slot.get("preferred_role_tags") or []),
                "template_fallback_id": fallback_id,
                "role_hint": _anchor_role_hint(slot),
                "anchor_status": "reserved",
            }
        )
        slot["reserved_character"] = name
        slot["reserved_template_id"] = fallback_id
        slot["reservation_status"] = "reserved"
    return target, anchored


def build_core_cast_state(payload: Any) -> dict[str, Any]:
    profile, count, count_range, basis = estimate_core_cast_count(payload)
    seed = _seed_int(_genre_text(payload), _premise_text(payload), _protagonist_name(payload))
    slots: list[dict[str, Any]] = []
    for idx, template in enumerate(_slot_library_for_profile(profile, seed=seed)[:count], start=1):
        slots.append(
            {
                "slot_id": f"CC{idx:02d}",
                "slot_name": f"核心配角{idx}号位",
                "slot_template_id": _text(template.get("slot_template_id")),
                "binding_pattern": _text(template.get("binding_pattern")),
                "entry_phase": _text(template.get("entry_phase"), "中前期"),
                "entry_chapter_window": list(template.get("entry_chapter_window") or [max(1, idx), max(3, idx + 3)]),
                "first_entry_mission": _text(template.get("first_entry_mission")),
                "long_term_relation_line": _text(template.get("long_term_relation_line")),
                "appearance_frequency": _text(template.get("appearance_frequency"), "中频"),
                "initial_relation": _text(template.get("initial_relation"), "待观察"),
                "preferred_role_tags": list(template.get("preferred_role_tags") or []),
                "importance_tier": _text(template.get("importance_tier"), "核心配角"),
                "status": "unbound",
                "bound_character": "",
                "bound_chapter": 0,
                "last_appeared_chapter": 0,
                "appearance_history": [],
                "phase_progress": "待登场",
            }
        )
    anchored_target_count, anchored_characters = _build_anchored_characters(payload, slots)
    return {
        "version": 1,
        "status": "planned",
        "profile": profile,
        "count_range": count_range,
        "target_count": count,
        "anchored_target_count": anchored_target_count,
        "planning_basis": basis,
        "selection_note": "人数按题材/背景浮动，先规划名额和阶段，不让重要配角一口气挤满前期。",
        "slots": slots,
        "anchored_characters": anchored_characters,
        "active_bindings": {},
        "chapter_binding_history": [],
    }


def empty_core_cast_state() -> dict[str, Any]:
    return {
        "version": 1,
        "status": "foundation_ready",
        "profile": "balanced",
        "count_range": [4, 6],
        "target_count": 0,
        "anchored_target_count": 0,
        "planning_basis": "待初始化后生成。",
        "selection_note": "重要配角先按名额与阶段规划，再逐步绑定到具体人物。",
        "slots": [],
        "anchored_characters": [],
        "active_bindings": {},
        "chapter_binding_history": [],
    }


def ensure_core_cast_state_shape(state: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(state) if isinstance(state, dict) else empty_core_cast_state()
    defaults = empty_core_cast_state()
    for key, value in defaults.items():
        payload.setdefault(key, deepcopy(value))
    if not isinstance(payload.get("slots"), list):
        payload["slots"] = []
    if not isinstance(payload.get("active_bindings"), dict):
        payload["active_bindings"] = {}
    if not isinstance(payload.get("chapter_binding_history"), list):
        payload["chapter_binding_history"] = []
    if not isinstance(payload.get("anchored_characters"), list):
        payload["anchored_characters"] = []
    for slot in payload["slots"]:
        if not isinstance(slot, dict):
            continue
        slot.setdefault("slot_id", "")
        slot.setdefault("slot_name", "核心配角位")
        slot.setdefault("binding_pattern", "待补充")
        slot.setdefault("entry_phase", "中前期")
        slot.setdefault("entry_chapter_window", [1, 6])
        slot.setdefault("first_entry_mission", "待补充")
        slot.setdefault("long_term_relation_line", "待补充")
        slot.setdefault("appearance_frequency", "中频")
        slot.setdefault("initial_relation", "待观察")
        slot.setdefault("preferred_role_tags", [])
        slot.setdefault("importance_tier", "重要配角")
        slot.setdefault("status", "unbound")
        slot.setdefault("bound_character", "")
        slot.setdefault("reserved_character", "")
        slot.setdefault("reserved_template_id", "")
        slot.setdefault("reservation_status", "")
        slot.setdefault("bound_chapter", 0)
        slot.setdefault("last_appeared_chapter", 0)
        slot.setdefault("appearance_history", [])
        slot.setdefault("phase_progress", "待登场")
    for item in payload["anchored_characters"]:
        if not isinstance(item, dict):
            continue
        item.setdefault("anchor_id", "")
        item.setdefault("slot_id", "")
        item.setdefault("name", "")
        item.setdefault("entry_phase", "前期")
        item.setdefault("entry_chapter_window", [1, 4])
        item.setdefault("binding_pattern", "待补充")
        item.setdefault("first_entry_mission", "待补充")
        item.setdefault("long_term_relation_line", "待补充")
        item.setdefault("appearance_frequency", "中频")
        item.setdefault("importance_tier", "重要配角")
        item.setdefault("initial_relation", "待观察")
        item.setdefault("preferred_role_tags", [])
        item.setdefault("template_fallback_id", "starter_hard_shell_soft_core")
        item.setdefault("role_hint", "")
        item.setdefault("anchor_status", "reserved")
    return payload


def summarize_core_cast_state(state: dict[str, Any] | None, *, chapter_no: int = 0, limit: int = 4) -> dict[str, Any]:
    payload = ensure_core_cast_state_shape(state)
    slots = []
    for slot in payload.get("slots", []):
        if not isinstance(slot, dict):
            continue
        window = slot.get("entry_chapter_window") or [0, 0]
        start = int(window[0] or 0) if isinstance(window, list) and window else 0
        end = int(window[1] or 0) if isinstance(window, list) and len(window) > 1 else start
        due = ""
        if chapter_no > 0:
            if start <= chapter_no <= max(end, start):
                due = "当前阶段"
            elif chapter_no < start:
                due = f"第{start}章前后"
            else:
                due = "已过窗口/可补"
        slots.append(
            {
                "slot_id": _text(slot.get("slot_id")),
                "entry_phase": _text(slot.get("entry_phase")),
                "entry_window": [start, end],
                "binding_pattern": _text(slot.get("binding_pattern")),
                "first_entry_mission": _text(slot.get("first_entry_mission"))[:28],
                "appearance_frequency": _text(slot.get("appearance_frequency")),
                "bound_character": _text(slot.get("bound_character")),
                "status": _text(slot.get("status")),
                "due": due,
            }
        )
        if len(slots) >= limit:
            break
    return {
        "profile": payload.get("profile"),
        "target_count": payload.get("target_count"),
        "anchored_target_count": payload.get("anchored_target_count"),
        "planning_basis": _text(payload.get("planning_basis"))[:40],
        "anchored_characters": [
            {
                "slot_id": _text(item.get("slot_id")),
                "name": _text(item.get("name")),
                "entry_window": list(item.get("entry_chapter_window") or [])[:2],
                "binding_pattern": _text(item.get("binding_pattern"))[:20],
                "anchor_status": _text(item.get("anchor_status"), "reserved"),
            }
            for item in (payload.get("anchored_characters") or [])[:2]
            if isinstance(item, dict)
        ],
        "slots": slots,
    }


def _slot_score(slot: dict[str, Any], *, chapter_no: int, note: str = "") -> float:
    if not isinstance(slot, dict):
        return -999.0
    if _text(slot.get("bound_character")):
        return -999.0
    window = slot.get("entry_chapter_window") or [chapter_no, chapter_no]
    start = int(window[0] or chapter_no) if isinstance(window, list) and window else chapter_no
    end = int(window[1] or start) if isinstance(window, list) and len(window) > 1 else start
    if start <= chapter_no <= max(end, start):
        score = 50.0
    elif chapter_no < start:
        score = max(10.0, 26.0 - (start - chapter_no) * 4.0)
    else:
        score = max(16.0, 32.0 - (chapter_no - end) * 2.5)
    if _text(slot.get("importance_tier")) == "核心配角":
        score += 6.0
    if _text(slot.get("appearance_frequency")) == "高频":
        score += 4.0
    note_text = _text(note)
    if note_text:
        for token in slot.get("preferred_role_tags") or []:
            token_text = _text(token)
            if token_text and token_text in note_text:
                score += 3.0
    return score


def materialize_anchored_core_cast(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
) -> list[str]:
    state = ensure_core_cast_state_shape(story_bible.get("core_cast_state"))
    story_bible["core_cast_state"] = state
    domains = story_bible.setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    console = story_bible.setdefault("control_console", {})
    cards = console.setdefault("character_cards", {})
    slot_index = {
        _text(slot.get("slot_id")): slot
        for slot in state.get("slots", [])
        if isinstance(slot, dict) and _text(slot.get("slot_id"))
    }
    created: list[str] = []
    for anchor in state.get("anchored_characters", []):
        if not isinstance(anchor, dict):
            continue
        name = _text(anchor.get("name"))
        slot_id = _text(anchor.get("slot_id"))
        if not name or not slot_id or name == protagonist_name:
            continue
        slot = slot_index.get(slot_id) or {}
        template = pick_character_template(
            story_bible,
            name=name,
            note=f"{_text(anchor.get('first_entry_mission'))} {_text(anchor.get('long_term_relation_line'))}",
            role_hint=_text(anchor.get("role_hint"), _text(anchor.get("binding_pattern"))),
            relation_hint=_text(anchor.get("initial_relation")),
            fallback_id=_text(anchor.get("template_fallback_id"), "starter_hard_shell_soft_core"),
        )
        entry_window = list(anchor.get("entry_chapter_window") or slot.get("entry_chapter_window") or [1, 4])
        base_card = {
            "name": name,
            "entity_type": "character",
            "role_type": "supporting",
            "importance_tier": _text(anchor.get("importance_tier"), "重要配角"),
            "protagonist_relation_level": _text(anchor.get("initial_relation"), "待观察"),
            "narrative_priority": 86 if _text(anchor.get("importance_tier")) == "核心配角" else 78,
            "current_goal": _text(anchor.get("first_entry_mission"), "在合适窗口进入主线，并与主角形成长期关系线。"),
            "relationship_index": {},
            "resource_refs": [],
            "faction_refs": [],
            "status": "anchored_planned",
            "first_planned_chapter": int(entry_window[0] or 1) if entry_window else 1,
            "entry_phase": _text(anchor.get("entry_phase"), _text(slot.get("entry_phase"))),
            "entry_chapter_window": entry_window,
            "first_entry_mission": _text(anchor.get("first_entry_mission"), _text(slot.get("first_entry_mission"))),
            "long_term_relation_line": _text(anchor.get("long_term_relation_line"), _text(slot.get("long_term_relation_line"))),
            "appearance_frequency": _text(anchor.get("appearance_frequency"), _text(slot.get("appearance_frequency"), "中频")),
            "binding_pattern": _text(anchor.get("binding_pattern"), _text(slot.get("binding_pattern"))),
            "core_cast_slot_id": slot_id,
            "core_cast_anchor": True,
            "core_cast_anchor_status": _text(anchor.get("anchor_status"), "reserved"),
            "tracking_level": "core_cast",
        }
        if not isinstance(characters.get(name), dict):
            characters[name] = apply_character_template_defaults(base_card, template)
            created.append(name)
        else:
            card = characters[name]
            card.setdefault("core_cast_slot_id", slot_id)
            card.setdefault("core_cast_anchor", True)
            card.setdefault("core_cast_anchor_status", _text(anchor.get("anchor_status"), "reserved"))
            card.setdefault("entry_chapter_window", entry_window)
            card.setdefault("binding_pattern", _text(anchor.get("binding_pattern"), _text(slot.get("binding_pattern"))))
            card.setdefault("long_term_relation_line", _text(anchor.get("long_term_relation_line"), _text(slot.get("long_term_relation_line"))))
            card.setdefault("appearance_frequency", _text(anchor.get("appearance_frequency"), _text(slot.get("appearance_frequency"), "中频")))
            card.setdefault("tracking_level", "core_cast")
            characters[name] = apply_character_template_defaults(card, template)

        legacy_base = {
            "name": name,
            "role_type": "supporting",
            "relationship_to_protagonist": _text(anchor.get("initial_relation"), "待观察"),
            "current_plot_function": _text(anchor.get("first_entry_mission"), "作为前期预实体化核心配角，在合适窗口落入剧情。"),
            "possible_change": _text(anchor.get("long_term_relation_line"), "关系线会在后续章节持续变化。"),
            "current_desire": _text(anchor.get("first_entry_mission"), "先在当前局势中站住，再决定与主角的关系方向。"),
            "core_cast_slot_id": slot_id,
            "core_cast_anchor": True,
            "core_cast_anchor_status": _text(anchor.get("anchor_status"), "reserved"),
        }
        if not isinstance(cards.get(name), dict):
            cards[name] = apply_character_template_defaults(legacy_base, template)
        else:
            legacy = cards[name]
            legacy.setdefault("core_cast_slot_id", slot_id)
            legacy.setdefault("core_cast_anchor", True)
            legacy.setdefault("core_cast_anchor_status", _text(anchor.get("anchor_status"), "reserved"))
            legacy.setdefault("current_plot_function", _text(anchor.get("first_entry_mission"), "作为长期关键配角推进关系线。"))
            legacy.setdefault("possible_change", _text(anchor.get("long_term_relation_line"), "待后续发展"))
            cards[name] = apply_character_template_defaults(legacy, template)

        if isinstance(slot, dict):
            slot.setdefault("reserved_character", name)
            slot.setdefault("reserved_template_id", _text(anchor.get("template_fallback_id"), "starter_hard_shell_soft_core"))
            slot.setdefault("reservation_status", _text(anchor.get("anchor_status"), "reserved"))
    return created


def bind_character_to_core_slot(
    story_bible: dict[str, Any],
    *,
    character_name: str,
    chapter_no: int,
    note: str = "",
    protagonist_name: str = "",
) -> str | None:
    clean_name = _text(character_name)
    if not clean_name or clean_name == protagonist_name:
        return None
    state = ensure_core_cast_state_shape(story_bible.get("core_cast_state"))
    story_bible["core_cast_state"] = state
    active_bindings = state.setdefault("active_bindings", {})
    if clean_name in active_bindings:
        return _text(active_bindings.get(clean_name)) or None
    slots = [slot for slot in state.get("slots", []) if isinstance(slot, dict)]
    if not slots:
        return None
    reserved_match = next(
        (
            slot
            for slot in slots
            if not _text(slot.get("bound_character")) and _text(slot.get("reserved_character")) == clean_name
        ),
        None,
    )
    ranked = sorted(slots, key=lambda slot: _slot_score(slot, chapter_no=chapter_no, note=note), reverse=True)
    chosen = reserved_match or (ranked[0] if ranked and _slot_score(ranked[0], chapter_no=chapter_no, note=note) > -100 else None)
    if not chosen:
        return None
    slot_id = _text(chosen.get("slot_id"))
    chosen["bound_character"] = clean_name
    chosen["reserved_character"] = _text(chosen.get("reserved_character"), clean_name)
    chosen["reservation_status"] = "activated"
    chosen["bound_chapter"] = chapter_no
    chosen["last_appeared_chapter"] = chapter_no
    chosen["appearance_history"] = [chapter_no]
    chosen["status"] = "bound"
    chosen["phase_progress"] = "已登场"
    active_bindings[clean_name] = slot_id
    history = state.setdefault("chapter_binding_history", [])
    history.append({"chapter_no": chapter_no, "character": clean_name, "slot_id": slot_id, "reason": _text(note)[:40]})
    state["chapter_binding_history"] = history[-20:]
    for item in state.get("anchored_characters", []):
        if isinstance(item, dict) and _text(item.get("slot_id")) == slot_id:
            item["name"] = clean_name
            item["anchor_status"] = "activated"
    domains = story_bible.setdefault("story_domains", {})
    characters = domains.setdefault("characters", {})
    card = characters.get(clean_name)
    if isinstance(card, dict):
        card["core_cast_slot_id"] = slot_id
        card["core_cast_anchor"] = bool(_text(chosen.get("reserved_character")))
        card["core_cast_anchor_status"] = _text(chosen.get("reservation_status"), "activated")
        card["entry_phase"] = _text(chosen.get("entry_phase"))
        card["entry_chapter_window"] = list(chosen.get("entry_chapter_window") or [])
        card["first_entry_mission"] = _text(chosen.get("first_entry_mission"))
        card["long_term_relation_line"] = _text(chosen.get("long_term_relation_line"))
        card["appearance_frequency"] = _text(chosen.get("appearance_frequency"))
        card["binding_pattern"] = _text(chosen.get("binding_pattern"))
        card["protagonist_relation_level"] = _text(card.get("protagonist_relation_level"), _text(chosen.get("initial_relation"), "待观察"))
        card["importance_tier"] = _text(chosen.get("importance_tier"), _text(card.get("importance_tier"), "重要配角"))
        card["narrative_priority"] = max(int(card.get("narrative_priority") or 0), 86 if card.get("importance_tier") == "核心配角" else 78)
        card["tracking_level"] = "core_cast"
    console = story_bible.setdefault("control_console", {})
    cards = console.setdefault("character_cards", {})
    legacy = cards.get(clean_name)
    if isinstance(legacy, dict):
        legacy.setdefault("role_archetype", _text(chosen.get("binding_pattern"), "核心配角"))
        legacy["core_cast_anchor"] = bool(_text(chosen.get("reserved_character")))
        legacy["core_cast_anchor_status"] = _text(chosen.get("reservation_status"), "activated")
        legacy["relationship_to_protagonist"] = _text(chosen.get("initial_relation"), _text(legacy.get("relationship_to_protagonist"), "待观察"))
        legacy["current_plot_function"] = _text(chosen.get("first_entry_mission"), _text(legacy.get("current_plot_function"), "作为长期关键配角推进关系线。"))
        legacy["possible_change"] = _text(chosen.get("long_term_relation_line"), _text(legacy.get("possible_change"), "待后续发展"))
    return slot_id


def update_core_cast_after_chapter(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    onstage_characters: list[str] | None,
) -> None:
    state = ensure_core_cast_state_shape(story_bible.get("core_cast_state"))
    story_bible["core_cast_state"] = state
    seen = {_text(name) for name in (onstage_characters or []) if _text(name)}
    for slot in state.get("slots", []):
        if not isinstance(slot, dict):
            continue
        bound = _text(slot.get("bound_character"))
        if not bound:
            continue
        if bound in seen:
            slot["last_appeared_chapter"] = chapter_no
            history = [int(item) for item in slot.get("appearance_history") or [] if str(item).isdigit()]
            if chapter_no not in history:
                history.append(chapter_no)
            slot["appearance_history"] = history[-12:]
            slot["status"] = "active"
            slot["phase_progress"] = "推进中"
    for item in state.get("anchored_characters", []):
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if name and name in seen:
            item["anchor_status"] = "active"


def core_cast_guidance_for_chapter(story_bible: dict[str, Any], *, chapter_no: int, focus_name: str = "") -> dict[str, Any]:
    state = ensure_core_cast_state_shape(story_bible.get("core_cast_state"))
    focus = _text(focus_name)
    active: list[dict[str, Any]] = []
    due_slots: list[dict[str, Any]] = []
    anchored_upcoming: list[dict[str, Any]] = []
    for slot in state.get("slots", []):
        if not isinstance(slot, dict):
            continue
        window = slot.get("entry_chapter_window") or [0, 0]
        start = int(window[0] or 0) if isinstance(window, list) and window else 0
        end = int(window[1] or 0) if isinstance(window, list) and len(window) > 1 else start
        bound = _text(slot.get("bound_character"))
        if bound:
            active.append(
                {
                    "slot_id": _text(slot.get("slot_id")),
                    "character": bound,
                    "appearance_frequency": _text(slot.get("appearance_frequency")),
                    "long_term_relation_line": _text(slot.get("long_term_relation_line"))[:42],
                    "last_appeared_chapter": int(slot.get("last_appeared_chapter") or 0),
                    "focus_match": bool(focus and focus == bound),
                }
            )
        elif chapter_no <= max(end, start) + 1:
            due_slots.append(
                {
                    "slot_id": _text(slot.get("slot_id")),
                    "reserved_character": _text(slot.get("reserved_character")),
                    "entry_phase": _text(slot.get("entry_phase")),
                    "entry_window": [start, end],
                    "binding_pattern": _text(slot.get("binding_pattern")),
                    "first_entry_mission": _text(slot.get("first_entry_mission"))[:36],
                    "appearance_frequency": _text(slot.get("appearance_frequency")),
                }
            )
            if _text(slot.get("reserved_character")):
                anchored_upcoming.append(
                    {
                        "slot_id": _text(slot.get("slot_id")),
                        "character": _text(slot.get("reserved_character")),
                        "entry_window": [start, end],
                        "binding_pattern": _text(slot.get("binding_pattern")),
                        "first_entry_mission": _text(slot.get("first_entry_mission"))[:36],
                        "appearance_frequency": _text(slot.get("appearance_frequency")),
                        "focus_match": bool(focus and focus == _text(slot.get("reserved_character"))),
                    }
                )
    active.sort(key=lambda item: ((0 if item.get("focus_match") else 1), -(int(item.get("last_appeared_chapter") or 0))), reverse=False)
    due_slots.sort(key=lambda item: (int((item.get("entry_window") or [999])[0] or 999), _text(item.get("slot_id"))))
    anchored_upcoming.sort(key=lambda item: ((0 if item.get("focus_match") else 1), int((item.get("entry_window") or [999])[0] or 999), _text(item.get("slot_id"))))
    return {
        "target_count": int(state.get("target_count") or 0),
        "anchored_target_count": int(state.get("anchored_target_count") or 0),
        "profile": _text(state.get("profile")),
        "selection_note": _text(state.get("selection_note"))[:56],
        "active_core_characters": active[:4],
        "anchored_upcoming_characters": anchored_upcoming[:2],
        "due_unbound_slots": due_slots[:3],
        "guidance": "核心配角应分批登场：前期可先把1到2个关键人物实体化并保留到对应窗口，再按频率推进，剩余名额只在轮到阶段时引入。",
    }
