from __future__ import annotations

from typing import Any

from app.schemas.novel import NovelCreate
from app.services.story_character_support import _safe_list, _text

def _sell_line(payload: NovelCreate) -> str:
    style = payload.style_preferences or {}
    sell_point = _text(style.get("sell_point"))
    if sell_point:
        return sell_point
    premise = _text(payload.premise)
    protagonist = _text(payload.protagonist_name, "主角")
    if "修" in premise or "仙" in payload.genre:
        return f"{protagonist}在‘{premise}’中低调求生、稳扎稳打，靠有限手段一步步撬开更大的修真局。"
    return f"{protagonist}围绕‘{premise}’展开持续升级的连载故事。"


def _one_line_intro(payload: NovelCreate, title: str) -> str:
    style = payload.style_preferences or {}
    if style.get("one_line_intro"):
        return _text(style.get("one_line_intro"))
    return f"《{title}》讲的是{payload.protagonist_name}在‘{payload.premise}’之中一边求生、一边逼近真相的故事。"


def _golden_finger(payload: NovelCreate) -> str:
    style = payload.style_preferences or {}
    return _text(style.get("golden_finger"), "尚未明示的异常线索 / 核心机缘，需要通过试探逐步兑现。")


def _mid_term_direction(global_outline: dict[str, Any]) -> str:
    acts = _safe_list(global_outline.get("acts"))
    if len(acts) >= 2:
        return _text(acts[1].get("summary"), "中期进入更高层的资源、势力与真相博弈。")
    if acts:
        return _text(acts[-1].get("summary"), "中期扩大地图、势力与冲突层级。")
    return "中期扩大地图、势力与冲突层级。"


def _endgame_direction(global_outline: dict[str, Any], payload: NovelCreate) -> str:
    acts = _safe_list(global_outline.get("acts"))
    if acts:
        return _text(acts[-1].get("summary"), f"围绕‘{payload.premise}’收束主线、人物与主题。")
    return f"围绕‘{payload.premise}’收束主线、人物与主题。"


def _target_end(acts: list[dict[str, Any]], idx: int) -> int:
    act = acts[idx]
    raw = int(act.get("target_chapter_end", 0) or 0)
    if raw > 0:
        return raw
    return (idx + 1) * 12


def build_volume_cards(global_outline: dict[str, Any], first_arc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    acts = _safe_list(global_outline.get("acts"))
    cards: list[dict[str, Any]] = []
    start = 1
    first_arc_focus = _text((first_arc or {}).get("focus"), "确认线索、避免暴露、获取立足资源")
    for idx, act in enumerate(acts, start=1):
        end = _target_end(acts, idx - 1)
        cards.append(
            {
                "volume_no": idx,
                "volume_name": _text(act.get("title"), f"第{idx}卷"),
                "start_chapter": start,
                "end_chapter": end,
                "volume_goal": _text(act.get("purpose"), "推进当前主线并建立更高层局势。"),
                "main_conflict": _text(act.get("summary"), "主角在更大的压力与真相前被迫行动。"),
                "cool_point": first_arc_focus if idx == 1 else "资源争夺、势力试探与阶段性破局。",
                "major_crisis": "暴露风险抬高、主角失去原有安全区，必须用更主动的方式破局。",
                "volume_result": "主角获得新的立足资本、情报或关系位阶。",
                "volume_loss": "付出资源、时间、名声、退路或信任代价。",
                "next_hook": "卷尾将主角推向更高层的地图、规则或敌意。",
                "status": "planned",
            }
        )
        start = end + 1
    if not cards:
        cards.append(
            {
                "volume_no": 1,
                "volume_name": "第一卷",
                "start_chapter": 1,
                "end_chapter": max(int((first_arc or {}).get("end_chapter", 0) or 10), 10),
                "volume_goal": "建立主角处境、异常线索与早期生存压力。",
                "main_conflict": "主角必须在谨慎求生与主动试探之间找到平衡。",
                "cool_point": first_arc_focus,
                "major_crisis": "一旦暴露底牌，主角会迅速失去当前立足点。",
                "volume_result": "拿到第一份立足资本。",
                "volume_loss": "失去原本平静或退路。",
                "next_hook": "更大的局势开始显影。",
                "status": "planned",
            }
        )
    return cards


def _default_world_bible(payload: NovelCreate) -> dict[str, Any]:
    return {
        "world_scale": _text(payload.style_preferences.get("world_scale"), "先以当前活动区域为主，逐步扩展到更高层地图。"),
        "mortals_vs_cultivators": _text(payload.style_preferences.get("mortals_vs_cultivators"), "凡人与修士存在明显权力与资源差距，凡人区是风险缓冲层也是压迫来源。"),
        "resource_controllers": _text(payload.style_preferences.get("resource_controllers"), "宗门、地头势力、家族或黑市掌控关键资源。"),
        "factions": _safe_list(payload.style_preferences.get("factions")) or ["宗门", "世家", "散修", "黑市/帮派", "妖魔或异类势力"],
        "higher_world_exists": bool(payload.style_preferences.get("higher_world_exists", True)),
    }


def _default_cultivation_system(payload: NovelCreate) -> dict[str, Any]:
    return {
        "realms": _safe_list(payload.style_preferences.get("realms")) or ["炼气", "筑基", "金丹", "元婴"],
        "gap_rules": _text(payload.style_preferences.get("gap_rules"), "小境界可凭准备、地形、信息差与底牌拉扯；大境界压制原则上不可硬跨。"),
        "breakthrough_conditions": _text(payload.style_preferences.get("breakthrough_conditions"), "需要资源、时机、心境与风险承受能力，不是纯数字累加。"),
        "combat_styles": _text(payload.style_preferences.get("combat_styles"), "不同境界不仅数值更高，还体现在信息掌控、法器质量、持续力与战斗方式差异上。"),
        "cross_realm_rule": _text(payload.style_preferences.get("cross_realm_rule"), "越阶战必须靠准备、代价、环境和对手失误成立，不能常态化。"),
    }


def build_project_card(payload: NovelCreate, title: str, global_outline: dict[str, Any]) -> dict[str, Any]:
    return {
        "book_title": title,
        "genre_positioning": _text(payload.genre),
        "core_sell_point": _sell_line(payload),
        "one_line_intro": _one_line_intro(payload, title),
        "protagonist": {
            "name": _text(payload.protagonist_name),
            "core_desire": _text(payload.style_preferences.get("core_desire"), "先活下去，再争取更稳的立足点与主动权。"),
            "core_fear": _text(payload.style_preferences.get("core_fear"), "秘密暴露、失去退路、被更高位者盯上。"),
            "advantage": _text(payload.style_preferences.get("advantage"), "谨慎、耐心、肯观察，有能力从细节里找生机。"),
            "flaw": _text(payload.style_preferences.get("flaw"), "过度克制，容易把代价都压到自己身上。"),
        },
        "golden_finger": _golden_finger(payload),
        "first_30_chapter_mainline": _text(payload.style_preferences.get("first_30_chapter_mainline"), "围绕异常线索、立足资本与暴露风险展开，先求活，再争资源。"),
        "mid_term_direction": _mid_term_direction(global_outline),
        "endgame_direction": _endgame_direction(global_outline, payload),
    }


def build_control_console(payload: NovelCreate, first_arc: dict[str, Any] | None = None) -> dict[str, Any]:
    protagonist_name = _text(payload.protagonist_name)
    active_arc = first_arc or {}
    near_window = []
    for chapter in _safe_list(active_arc.get("chapters"))[:7]:
        near_window.append(
            {
                "chapter_no": int(chapter.get("chapter_no", 0) or 0),
                "title": _text(chapter.get("title"), f"第{chapter.get('chapter_no', '')}章"),
                "goal": _text(chapter.get("goal"), "推进当前主线"),
                "hook": _text(chapter.get("ending_hook"), "新问题浮出"),
                "event_type": _text(chapter.get("event_type"), "试探类"),
                "progress_kind": _text(chapter.get("progress_kind"), "信息推进"),
            }
        )
    return {
        "protagonist_state": {
            "current_realm": _text(payload.style_preferences.get("initial_realm"), "未显明确高阶境界，处于低阶求生阶段"),
            "combat_positioning": _text(payload.style_preferences.get("initial_combat_positioning"), "偏弱但谨慎，有特定场景下的应对手段。"),
            "main_skill": _text(payload.style_preferences.get("main_skill"), "观察、试探、藏拙、借力打力"),
            "core_methods": _safe_list(payload.style_preferences.get("core_methods")) or ["观察", "试探", "遮掩", "反击"],
            "ultimate_card": _text(payload.style_preferences.get("ultimate_card"), "尚未完全兑现的异常线索 / 核心机缘"),
            "current_limits": _text(payload.style_preferences.get("current_limits"), "资源少、力量弱、退路窄，不能轻易暴露。"),
            "current_resources": _safe_list(payload.style_preferences.get("current_resources")) or ["零碎资源", "有限情报", "尚未稳定的机缘"],
            "current_status": _text(payload.style_preferences.get("current_status"), "谨慎维持日常，边试探边隐藏。"),
            "current_goal": _text((active_arc or {}).get("focus"), "确认线索、避免暴露、拿到小资源。"),
            "main_enemy": _text(payload.style_preferences.get("initial_enemy"), "更高位的规则、资源压迫与潜在盯梢者。"),
            "exposure_risk": _text(payload.style_preferences.get("exposure_risk"), "异常一旦被看穿，主角会迅速失去安全区。"),
            "agency_cycle": {"recent_passive_chapters": 0, "force_proactive_before": 3},
        },
        "power_ledger": {
            "realm_weight_notes": "每个境界都要长期保持压迫感，不能前重后轻。",
            "same_realm_layers": "同境界内也分准备充分者、普通者、老手与天才。",
            "cross_realm_rules": _text(payload.style_preferences.get("cross_realm_rule"), "越阶战只能靠情报差、环境、代价与一次性底牌成立。"),
            "hard_no_cross_lines": ["大境界碾压不可常态硬跨", "受伤与消耗不能写了就忘"],
            "special_combat_features": _safe_list(payload.style_preferences.get("special_combat_features")) or ["信息差", "地形", "法器/材料", "时间差"],
        },
        "character_cards": {
            protagonist_name: {
                "name": protagonist_name,
                "role_type": "protagonist",
                "camp": "主角阵营",
                "current_strength": _text(payload.style_preferences.get("initial_realm"), "低阶求生阶段"),
                "core_desire": _text(payload.style_preferences.get("core_desire"), "活下去并掌握主动权。"),
                "core_fear": _text(payload.style_preferences.get("core_fear"), "秘密暴露、连累自己或身边人。"),
                "temperament": _text(payload.style_preferences.get("temperament"), "克制、警醒、耐心。"),
                "speech_style": "简短、留后手、尽量不把真实判断一次说满。",
                "work_style": "先观察和试探，再决定是否行动；轻易不把底牌摆到台面上。",
                "current_desire": _text(payload.style_preferences.get("core_desire"), "活下去并掌握主动权。"),
                "attitude_to_protagonist": "self",
                "recent_impact": "当前仍在为主线做出选择并承担代价。",
                "behavior_logic": "先观察和试探，再决定是否行动；轻易不把底牌摆到台面上。",
                "relationship_to_protagonist": "self",
                "hidden_secret": _golden_finger(payload),
                "current_plot_function": "推动视角、承接风险、做出选择。",
                "possible_change": "从被动求生转向更主动的布局。",
                "do_not_break": ["谨慎不等于停滞", "关键抉择时必须体现主动判断"],
            }
        },
        "relation_tracks": [],
        "foreshadowing": [],
        "timeline": [],
        "near_7_chapter_outline": near_window,
        "near_30_progress": {
            "current_position": "开书区 / 前30章",
            "current_volume_gap": "还在建立立足点与第一次上瘾点。",
            "next_big_payoff": _text((active_arc or {}).get("focus"), "第一次关键破局。"),
            "next_twist": _text((active_arc or {}).get("bridge_note"), "线索会把主角引向更危险的边缘试探。"),
        },
        "daily_workbench": {
            "yesterday_ending": "",
            "today_function": "",
            "three_line_outline": {"opening": "", "middle": "", "ending": ""},
            "tomorrow_hints": [],
        },
        "chapter_retrospectives": [],
        "volume_reviews": [],
    }




