from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.novel import Novel
from app.schemas.novel import NovelCreate


DEFAULT_CONTINUITY_RULES = [
    "主角每章都要有行动、判断、试探、隐藏或反击，不能整章只被剧情推着走。",
    "每章都要有新变化：得到信息、失去退路、关系变化、暴露风险或世界认知升级。",
    "如果时间跨度超过一天，开头两段必须写明过渡。",
    "章末要么留下拉力，要么自然收在结果落地与人物选择上，不能停在半句。",
]


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


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
                "behavior_logic": "先观察和试探，再决定是否行动；轻易不把底牌摆到台面上。",
                "relationship_to_protagonist": "self",
                "hidden_secret": _golden_finger(payload),
                "current_plot_function": "推动视角、承接风险、做出选择。",
                "possible_change": "从被动求生转向更主动的布局。",
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
        "volume_reviews": [],
    }




def _chapter_cards_from_arc(arc: dict[str, Any] | None) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if not arc:
        return queue
    for chapter in _safe_list(arc.get("chapters")):
        queue.append(
            {
                "chapter_no": int(chapter.get("chapter_no", 0) or 0),
                "title": _text(chapter.get("title"), ""),
                "goal": _text(chapter.get("goal"), "推进当前主线"),
                "chapter_type": _text(chapter.get("chapter_type"), "progress"),
                "hook_style": _text(chapter.get("hook_style"), ""),
                "opening": _text(chapter.get("opening_beat"), ""),
                "middle": _text(chapter.get("mid_turn"), ""),
                "ending": _text(chapter.get("closing_image") or chapter.get("ending_hook"), ""),
                "hook": _text(chapter.get("ending_hook"), ""),
            }
        )
    return queue


def _workflow_state_from_arc(first_arc: dict[str, Any] | None) -> dict[str, Any]:
    planned_until = int((first_arc or {}).get("end_chapter", 0) or 0)
    return {
        "mode": "document_first_strict_pipeline",
        "init_generates_chapters": False,
        "strict_pipeline": [
            "project_card",
            "current_volume_card",
            "near_outline",
            "chapter_execution_card",
            "chapter_draft",
            "summary_and_review",
        ],
        "bootstrap_documents_ready": True,
        "bootstrap_generated_chapter_cards_until": planned_until,
        "current_pipeline": {
            "target_chapter_no": 1,
            "project_card_ready": True,
            "current_volume_ready": True,
            "near_outline_ready": planned_until > 0,
            "chapter_card_ready": planned_until > 0,
            "draft_ready": False,
            "summary_review_ready": False,
            "last_completed_stage": "bootstrap_documents",
            "last_completed_chapter_no": 0,
        },
    }


def refresh_planning_views(story_bible: dict[str, Any], current_chapter_no: int = 0) -> dict[str, Any]:
    console = story_bible.setdefault("control_console", {})
    workflow_state = story_bible.setdefault("workflow_state", _workflow_state_from_arc(story_bible.get("active_arc")))

    active_arc = story_bible.get("active_arc") or {}
    pending_arc = story_bible.get("pending_arc") or {}
    queue = [item for item in _chapter_cards_from_arc(active_arc) if int(item.get("chapter_no", 0) or 0) > current_chapter_no]
    if len(queue) < 7 and pending_arc:
        remaining = 7 - len(queue)
        queue.extend(_chapter_cards_from_arc(pending_arc)[:remaining])

    console["chapter_card_queue"] = queue[:7]
    console["planning_status"] = {
        "documents_only_bootstrap": True,
        "active_arc": {
            "arc_no": int(active_arc.get("arc_no", 0) or 0),
            "start_chapter": int(active_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(active_arc.get("end_chapter", 0) or 0),
            "focus": _text(active_arc.get("focus"), ""),
        },
        "pending_arc": {
            "arc_no": int(pending_arc.get("arc_no", 0) or 0),
            "start_chapter": int(pending_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(pending_arc.get("end_chapter", 0) or 0),
            "focus": _text(pending_arc.get("focus"), ""),
        } if pending_arc else None,
        "ready_chapter_cards": [int(item.get("chapter_no", 0) or 0) for item in queue[:7]],
    }

    if queue:
        console["near_7_chapter_outline"] = [
            {
                "chapter_no": int(item.get("chapter_no", 0) or 0),
                "title": _text(item.get("title"), f"第{item.get('chapter_no', '')}章"),
                "goal": _text(item.get("goal"), "推进当前主线"),
                "hook": _text(item.get("hook"), "新问题浮出"),
            }
            for item in queue[:7]
        ]

    workflow_state["bootstrap_generated_chapter_cards_until"] = max(
        int(workflow_state.get("bootstrap_generated_chapter_cards_until", 0) or 0),
        int((active_arc or {}).get("end_chapter", 0) or 0),
        int((pending_arc or {}).get("end_chapter", 0) or 0),
    )
    current_pipeline = workflow_state.setdefault("current_pipeline", {})
    current_pipeline.setdefault("target_chapter_no", current_chapter_no + 1)
    current_pipeline["project_card_ready"] = bool(story_bible.get("project_card"))
    current_pipeline["current_volume_ready"] = bool(story_bible.get("volume_cards"))
    current_pipeline["near_outline_ready"] = bool(queue)
    current_pipeline["chapter_card_ready"] = bool(queue and int(queue[0].get("chapter_no", 0) or 0) == current_chapter_no + 1)
    story_bible["workflow_state"] = workflow_state
    story_bible["control_console"] = console
    return story_bible


def set_pipeline_target(
    story_bible: dict[str, Any],
    *,
    next_chapter_no: int,
    execution_brief: dict[str, Any] | None = None,
    stage: str = "chapter_execution_card",
    last_completed_chapter_no: int | None = None,
) -> dict[str, Any]:
    story_bible = refresh_planning_views(story_bible, max(next_chapter_no - 1, 0))
    workflow_state = story_bible.setdefault("workflow_state", _workflow_state_from_arc(story_bible.get("active_arc")))
    pipeline = workflow_state.setdefault("current_pipeline", {})
    pipeline.update(
        {
            "target_chapter_no": next_chapter_no,
            "project_card_ready": bool(story_bible.get("project_card")),
            "current_volume_ready": bool(story_bible.get("volume_cards")),
            "near_outline_ready": bool((story_bible.get("control_console") or {}).get("chapter_card_queue")),
            "chapter_card_ready": execution_brief is not None,
            "draft_ready": False,
            "summary_review_ready": False,
            "last_completed_stage": stage,
        }
    )
    if last_completed_chapter_no is not None:
        pipeline["last_completed_chapter_no"] = last_completed_chapter_no
    if execution_brief is not None:
        console = story_bible.setdefault("control_console", {})
        console["current_execution_packet"] = execution_brief
        console["daily_workbench"] = execution_brief.get("daily_workbench", {})
    story_bible["workflow_state"] = workflow_state
    return story_bible


def compose_story_bible(
    payload: NovelCreate,
    title: str,
    base_story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    first_arc: dict[str, Any],
) -> dict[str, Any]:
    story_bible = deepcopy(base_story_bible)
    story_bible["project_card"] = build_project_card(payload, title, global_outline)
    story_bible["world_bible"] = _default_world_bible(payload)
    story_bible["cultivation_system"] = _default_cultivation_system(payload)
    story_bible["volume_cards"] = build_volume_cards(global_outline, first_arc)
    story_bible["control_console"] = build_control_console(payload, first_arc)
    story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    story_bible["daily_workflow"] = {
        "steps": [
            "回看昨天结尾",
            "确定今天这章的功能",
            "写三行章纲",
            "写正文时盯住主角行动、事件推进、新变化和章末拉力",
            "收工时留下明天提示",
        ],
        "quality_floor": [
            "主角有没有行动",
            "事件有没有推进",
            "有没有新变化",
            "节奏有没有拖",
            "结尾有没有拉力",
        ],
    }
    story_bible["planning_layers"] = {
        "global_outline_ready": bool(global_outline),
        "volume_cards_ready": True,
        "first_near_outline_ready": bool(first_arc),
        "first_chapter_cards_ready": bool((first_arc or {}).get("chapters")),
    }
    story_bible["workflow_state"] = _workflow_state_from_arc(first_arc)
    return refresh_planning_views(story_bible, 0)


def _current_volume_card(story_bible: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    volume_cards = _safe_list(story_bible.get("volume_cards"))
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


def update_volume_card_statuses(story_bible: dict[str, Any], current_chapter_no: int) -> None:
    for card in _safe_list(story_bible.get("volume_cards")):
        start = int(card.get("start_chapter", 0) or 0)
        end = int(card.get("end_chapter", 0) or 0)
        if current_chapter_no >= end > 0:
            card["status"] = "completed"
        elif start <= current_chapter_no + 1 <= max(end, start):
            card["status"] = "current"
        else:
            card["status"] = "planned"


def ensure_story_architecture(story_bible: dict[str, Any], novel: Novel) -> dict[str, Any]:
    story_bible = deepcopy(story_bible or {})
    payload = NovelCreate(
        genre=novel.genre,
        premise=novel.premise,
        protagonist_name=novel.protagonist_name,
        style_preferences=novel.style_preferences or {},
    )
    global_outline = story_bible.get("global_outline") or {}
    active_arc = story_bible.get("active_arc") or {}
    if "project_card" not in story_bible:
        story_bible["project_card"] = build_project_card(payload, novel.title, global_outline)
    if "world_bible" not in story_bible:
        story_bible["world_bible"] = _default_world_bible(payload)
    if "cultivation_system" not in story_bible:
        story_bible["cultivation_system"] = _default_cultivation_system(payload)
    if "volume_cards" not in story_bible:
        story_bible["volume_cards"] = build_volume_cards(global_outline, active_arc)
    if "control_console" not in story_bible:
        story_bible["control_console"] = build_control_console(payload, active_arc)
    if "continuity_rules" not in story_bible:
        story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    if "daily_workflow" not in story_bible:
        story_bible["daily_workflow"] = {
            "steps": ["回看昨天结尾", "确定今天这章的功能", "写三行章纲", "写正文", "留明天提示"],
            "quality_floor": ["主角有没有行动", "事件有没有推进", "有没有新变化", "节奏有没有拖", "结尾有没有拉力"],
        }
    if "planning_layers" not in story_bible:
        story_bible["planning_layers"] = {
            "global_outline_ready": bool(global_outline),
            "volume_cards_ready": bool(story_bible.get("volume_cards")),
            "first_near_outline_ready": bool(active_arc),
            "first_chapter_cards_ready": bool((active_arc or {}).get("chapters")),
        }
    if "workflow_state" not in story_bible:
        story_bible["workflow_state"] = _workflow_state_from_arc(active_arc)
    update_volume_card_statuses(story_bible, novel.current_chapter_no)
    return refresh_planning_views(story_bible, novel.current_chapter_no)


def build_execution_brief(
    *,
    story_bible: dict[str, Any],
    next_chapter_no: int,
    plan: dict[str, Any],
    last_chapter_tail: str,
) -> dict[str, Any]:
    console = story_bible.get("control_console") or {}
    current_volume = _current_volume_card(story_bible, next_chapter_no)
    today_function = _text(plan.get("goal"), "推进剧情")
    if plan.get("supporting_character_focus"):
        today_function += f" + 让{_text(plan.get('supporting_character_focus'))}在场面里立住"
    change_line = _text(plan.get("discovery") or plan.get("conflict"), "局势会在本章发生可感知的新变化。")
    tomorrow_hints = [
        f"明天从第{next_chapter_no}章结尾的后续局势接上。",
        f"明天最大冲突：{_text(plan.get('conflict') or plan.get('goal'), '继续推进当前矛盾。')}",
        f"明天章末可往‘{_text(plan.get('ending_hook'), '新问题浮出')}’方向留钩子。",
    ]
    return {
        "project_card": story_bible.get("project_card", {}),
        "current_volume_card": current_volume,
        "chapter_execution_card": {
            "chapter_function": today_function,
            "opening": _text(plan.get("opening_beat"), "顺着上一章结尾自然接入场景。"),
            "middle": _text(plan.get("mid_turn"), "中段加入受阻、试探或代价。"),
            "ending": _text(plan.get("closing_image"), "结尾落在具体画面、结果或新问题上。"),
            "chapter_change": change_line,
            "chapter_hook": _text(plan.get("ending_hook"), "留下继续追更的拉力。"),
        },
        "daily_workbench": {
            "yesterday_ending": _text(last_chapter_tail),
            "today_function": today_function,
            "three_line_outline": {
                "opening": _text(plan.get("opening_beat")),
                "middle": _text(plan.get("mid_turn")),
                "ending": _text(plan.get("closing_image") or plan.get("ending_hook")),
            },
            "tomorrow_hints": tomorrow_hints,
        },
        "quality_floor": [
            "主角必须在本章主动做出至少一次观察、判断、试探或反击。",
            "本章必须出现事件推进，而不是只补设定。",
            "本章必须产生新变化：信息、关系、风险、资源、退路至少改变其一。",
            "节奏不能拖成长段说明书。",
            "章末必须有拉力或结果落地。",
        ],
        "continuity_rules": _safe_list(story_bible.get("continuity_rules")) or list(DEFAULT_CONTINUITY_RULES),
    }


def _merge_character_card(console: dict[str, Any], name: str, defaults: dict[str, Any]) -> None:
    cards = console.setdefault("character_cards", {})
    existing = cards.get(name, {}) if isinstance(cards, dict) else {}
    merged = dict(defaults)
    merged.update({k: v for k, v in existing.items() if v not in (None, "", [], {})})
    cards[name] = merged


def sync_character_registry(
    db: Session,
    novel: Novel,
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    summary: Any,
) -> None:
    console = story_bible.get("control_console") or {}
    protagonist_state = console.get("protagonist_state") or {}
    cards = console.get("character_cards") or {}

    def upsert(name: str, role_type: str, core_profile: dict[str, Any], dynamic_state: dict[str, Any]) -> None:
        if not name:
            return
        row = (
            db.query(Character)
            .filter(Character.novel_id == novel.id, Character.name == name)
            .first()
        )
        if not row:
            row = Character(novel_id=novel.id, name=name, role_type=role_type)
        row.core_profile = core_profile
        row.dynamic_state = dynamic_state
        db.add(row)

    protagonist_name = novel.protagonist_name
    protagonist_card = cards.get(protagonist_name, {}) if isinstance(cards, dict) else {}
    upsert(
        protagonist_name,
        "protagonist",
        protagonist_card or {"name": protagonist_name, "role_type": "protagonist"},
        protagonist_state,
    )

    focus_name = _text(plan.get("supporting_character_focus"))
    if focus_name:
        note = _text(plan.get("supporting_character_note"), "本卷的重要配角，需要持续保持辨识度。")
        current = cards.get(focus_name, {}) if isinstance(cards, dict) else {}
        profile = current or {
            "name": focus_name,
            "role_type": "supporting",
            "current_plot_function": "本阶段重要配角",
            "behavior_logic": note,
        }
        dynamic_state = {
            "last_seen_chapter": int(plan.get("chapter_no", 0) or 0),
            "latest_note": note,
        }
        upsert(focus_name, "supporting", profile, dynamic_state)

    character_updates = getattr(summary, "character_updates", {}) or {}
    if isinstance(character_updates, dict):
        for name, state in character_updates.items():
            char_name = _text(name)
            if not char_name:
                continue
            current = cards.get(char_name, {}) if isinstance(cards, dict) else {}
            role_type = _text(current.get("role_type"), "supporting")
            profile = current or {"name": char_name, "role_type": role_type}
            dynamic_state = state if isinstance(state, dict) else {"latest_update": state}
            upsert(char_name, role_type, profile, dynamic_state)


def update_story_architecture_after_chapter(
    *,
    story_bible: dict[str, Any],
    novel: Novel,
    chapter_no: int,
    chapter_title: str,
    plan: dict[str, Any],
    summary: Any,
    last_chapter_tail: str,
) -> dict[str, Any]:
    story_bible = ensure_story_architecture(story_bible, novel)
    console = story_bible.setdefault("control_console", {})
    protagonist_state = console.setdefault("protagonist_state", {})
    protagonist_state["current_goal"] = _text(plan.get("ending_hook") or plan.get("goal"), protagonist_state.get("current_goal", ""))
    protagonist_state["current_status"] = _text(getattr(summary, "event_summary", None), protagonist_state.get("current_status", ""))

    volume_card = _current_volume_card(story_bible, chapter_no)
    update_volume_card_statuses(story_bible, chapter_no)

    daily = build_execution_brief(
        story_bible=story_bible,
        next_chapter_no=chapter_no + 1,
        plan=plan,
        last_chapter_tail=last_chapter_tail,
    )
    console["daily_workbench"] = daily["daily_workbench"]

    progress = console.setdefault("recent_progress", [])
    progress.append(
        {
            "chapter_no": chapter_no,
            "title": chapter_title,
            "event_summary": _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), "推进当前主线")),
            "new_change": _text(plan.get("discovery") or plan.get("conflict"), "局势发生了新的偏移。"),
            "chapter_hook": _text(plan.get("ending_hook"), "新的问题浮出。"),
        }
    )
    console["recent_progress"] = progress[-12:]

    near_progress = console.setdefault("near_30_progress", {})
    near_progress["current_position"] = f"已写到第{chapter_no}章"
    near_progress["current_volume_gap"] = _text(volume_card.get("main_conflict"), near_progress.get("current_volume_gap", ""))
    near_progress["next_big_payoff"] = _text(volume_card.get("cool_point"), near_progress.get("next_big_payoff", ""))
    near_progress["next_twist"] = _text(plan.get("ending_hook"), near_progress.get("next_twist", ""))

    timeline = console.setdefault("timeline", [])
    timeline.append(
        {
            "chapter_no": chapter_no,
            "event": _text(getattr(summary, "event_summary", None), _text(plan.get("goal"), "推进当前主线")),
        }
    )
    console["timeline"] = timeline[-30:]

    foreshadowing = console.setdefault("foreshadowing", [])
    existing_open = {str(item.get("surface_info", "")): item for item in foreshadowing if isinstance(item, dict)}
    for hook in getattr(summary, "open_hooks", []) or []:
        hook_text = _text(hook)
        if not hook_text:
            continue
        existing_open.setdefault(
            hook_text,
            {
                "name": hook_text[:24],
                "introduced_in_chapter": chapter_no,
                "surface_info": hook_text,
                "real_info": "待后续揭示",
                "known_by": [novel.protagonist_name],
                "expected_resolution": "待后续回收",
                "status": "open",
            },
        )
    foreshadowing = list(existing_open.values())
    closed = {_text(item) for item in (getattr(summary, "closed_hooks", []) or []) if _text(item)}
    for item in foreshadowing:
        if _text(item.get("surface_info")) in closed:
            item["status"] = "closed"
            item["expected_resolution"] = f"已在第{chapter_no}章阶段性回收"
    console["foreshadowing"] = foreshadowing[-30:]

    protagonist_name = novel.protagonist_name
    _merge_character_card(
        console,
        protagonist_name,
        {
            "name": protagonist_name,
            "role_type": "protagonist",
            "current_strength": _text(protagonist_state.get("current_realm"), "低阶求生阶段"),
            "current_plot_function": "推动视角、承接风险、做出选择。",
            "behavior_logic": "先观察和试探，再决定是否行动。",
            "relationship_to_protagonist": "self",
        },
    )
    focus_name = _text(plan.get("supporting_character_focus"))
    if focus_name:
        _merge_character_card(
            console,
            focus_name,
            {
                "name": focus_name,
                "role_type": "supporting",
                "temperament": _text(plan.get("supporting_character_note"), "本阶段的重要配角。"),
                "current_plot_function": "作为本章关键配角参与推进。",
                "relationship_to_protagonist": "待剧情更新",
                "possible_change": "关系可能由试探转向合作或对立。",
            },
        )
        relations = console.setdefault("relation_tracks", [])
        relations.append(
            {
                "subject": protagonist_name,
                "target": focus_name,
                "chapter_no": chapter_no,
                "change": _text(plan.get("conflict") or plan.get("goal"), "关系发生新的试探或位移。"),
            }
        )
        console["relation_tracks"] = relations[-20:]

    current_volume_end = int(volume_card.get("end_chapter", 0) or 0)
    if current_volume_end and chapter_no >= current_volume_end:
        reviews = console.setdefault("volume_reviews", [])
        reviews.append(
            {
                "volume_no": int(volume_card.get("volume_no", 0) or 0),
                "volume_name": _text(volume_card.get("volume_name"), f"第{volume_card.get('volume_no', '')}卷"),
                "mainline_advanced": True,
                "protagonist_growth": _text(protagonist_state.get("current_status"), "主角完成了一次阶段性成长与位置变化。"),
                "best_cool_point": _text(volume_card.get("cool_point"), "阶段性破局。"),
                "drag_point": "留待人工复盘微调。",
                "recovered_foreshadowing": [_text(x) for x in (getattr(summary, "closed_hooks", []) or []) if _text(x)],
                "unresolved_foreshadowing": [_text(item.get("surface_info")) for item in console.get("foreshadowing", []) if item.get("status") != "closed"][:6],
                "next_volume_newness": _text(volume_card.get("next_hook"), "下一卷会抬高地图、规则与代价。"),
            }
        )
        console["volume_reviews"] = reviews[-8:]

    next_outline = console.setdefault("near_7_chapter_outline", [])
    if next_outline and next_outline[0].get("chapter_no") == chapter_no:
        next_outline = next_outline[1:]
    console["near_7_chapter_outline"] = next_outline
    story_bible["control_console"] = console
    story_bible = refresh_planning_views(story_bible, chapter_no)
    return set_pipeline_target(story_bible, next_chapter_no=chapter_no + 1, stage="summary_and_review", last_completed_chapter_no=chapter_no)


def build_control_console_snapshot(novel: Novel) -> dict[str, Any]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    console = story_bible.get("control_console", {})
    return {
        "novel_id": novel.id,
        "title": novel.title,
        "project_card": story_bible.get("project_card", {}),
        "world_bible": story_bible.get("world_bible", {}),
        "cultivation_system": story_bible.get("cultivation_system", {}),
        "current_volume_card": _current_volume_card(story_bible, novel.current_chapter_no + 1),
        "control_console": console,
        "planning_layers": story_bible.get("planning_layers", {}),
        "planning_state": story_bible.get("workflow_state", {}),
        "continuity_rules": story_bible.get("continuity_rules", list(DEFAULT_CONTINUITY_RULES)),
        "daily_workflow": story_bible.get("daily_workflow", {}),
    }
