from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.hard_fact_guard import (
    compact_hard_fact_guard,
    ensure_hard_fact_guard,
)
from app.services.story_blueprint_builders import (
    _default_cultivation_system,
    _default_world_bible,
    _endgame_direction,
    _golden_finger,
    _mid_term_direction,
    _one_line_intro,
    _sell_line,
    _target_end,
    build_control_console,
    build_project_card,
    build_volume_cards,
)
from app.services.story_character_support import (
    _build_chapter_retrospective,
    _character_voice_pack,
    _recent_retrospective_feedback,
    _safe_list,
    _supporting_voice_template,
    _text,
)
from app.services.story_fact_ledger import (
    _compact_fact_text,
    _now_iso,
    promote_stock_fact_entries,
    record_chapter_fact_entries,
)
from app.services.story_runtime_support import (
    DEFAULT_SERIAL_DELIVERY_MODE,
    _build_initialization_packet,
    _current_volume_card,
    build_serial_rules,
    set_delivery_mode,
    sync_long_term_state,
)
from app.services.story_state import (
    ensure_control_console,
    ensure_planning_layers,
    ensure_serial_runtime,
    ensure_story_state_domains,
    ensure_workflow_state,
    update_story_state_bucket,
)

DEFAULT_CONTINUITY_RULES = [
    "主角每章都要有行动、判断、试探、隐藏或反击，不能整章只被剧情推着走。",
    "每章都要有新变化：得到信息、失去退路、关系变化、暴露风险或世界认知升级。",
    "最近两章若已经用了同类桥段，下一章必须换事件类型，不能连续三章都在同一结构里打转。",
    "如果时间跨度超过一天，开头两段必须写明过渡。",
    "章末要么留下拉力，要么自然收在结果落地与人物选择上，不能停在半句。",
]

DEFAULT_STRICT_PIPELINE = [
    "定位",
    "读状态",
    "章纲",
    "场景",
    "正文",
    "检查",
    "摘要",
    "状态更新",
    "发布状态标记",
    "下一章入口",
]



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
        "strict_pipeline": list(DEFAULT_STRICT_PIPELINE),
        "strict_pipeline_internal": [
            "project_card",
            "current_volume_card",
            "near_outline",
            "chapter_execution_card",
            "chapter_scene_outline",
            "chapter_draft",
            "quality_check",
            "summary_and_review",
            "publish_mark",
            "next_entry",
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
    story_bible = ensure_story_state_domains(story_bible, workflow_factory=_workflow_state_from_arc)
    console = ensure_control_console(story_bible)
    workflow_state = ensure_workflow_state(story_bible, workflow_factory=_workflow_state_from_arc)

    active_arc = story_bible.get("active_arc") or {}
    pending_arc = story_bible.get("pending_arc") or {}
    queue = [item for item in _chapter_cards_from_arc(active_arc) if int(item.get("chapter_no", 0) or 0) > current_chapter_no]
    if len(queue) < 7 and pending_arc:
        remaining = 7 - len(queue)
        queue.extend(_chapter_cards_from_arc(pending_arc)[:remaining])

    console["chapter_card_queue"] = queue[:7]
    outline_state = story_bible.get("outline_state") or {}
    console["planning_status"] = {
        "documents_only_bootstrap": True,
        "auto_planning_enabled": True,
        "planned_until": int(outline_state.get("planned_until", 0) or 0),
        "next_arc_no": int(outline_state.get("next_arc_no", 0) or 0),
        "active_arc": {
            "arc_no": int(active_arc.get("arc_no", 0) or 0),
            "start_chapter": int(active_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(active_arc.get("end_chapter", 0) or 0),
            "focus": _text(active_arc.get("focus"), ""),
            "bridge_note": _text(active_arc.get("bridge_note"), ""),
        },
        "pending_arc": {
            "arc_no": int(pending_arc.get("arc_no", 0) or 0),
            "start_chapter": int(pending_arc.get("start_chapter", 0) or 0),
            "end_chapter": int(pending_arc.get("end_chapter", 0) or 0),
            "focus": _text(pending_arc.get("focus"), ""),
            "bridge_note": _text(pending_arc.get("bridge_note"), ""),
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
    runtime = ensure_serial_runtime(story_bible)
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers["serial_rules_ready"] = bool(story_bible.get("serial_rules"))
    planning_layers["long_term_state_ready"] = True
    planning_layers["initialization_packet_ready"] = True
    story_bible["workflow_state"] = workflow_state
    story_bible["control_console"] = console
    story_bible["serial_runtime"] = runtime
    story_bible["initialization_packet"] = _build_initialization_packet(story_bible, current_chapter_no)
    update_story_state_bucket(
        story_bible,
        planning_window={
            "current_chapter_no": current_chapter_no,
            "planned_until": int(outline_state.get("planned_until", 0) or 0),
            "queue_size": len(queue[:7]),
            "active_arc_no": int(active_arc.get("arc_no", 0) or 0),
            "pending_arc_no": int((pending_arc or {}).get("arc_no", 0) or 0) if pending_arc else None,
        },
    )
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
    workflow_state = ensure_workflow_state(story_bible, workflow_factory=_workflow_state_from_arc)
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
        console = ensure_control_console(story_bible)
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
    story_bible = ensure_story_state_domains(deepcopy(base_story_bible), workflow_factory=_workflow_state_from_arc, active_arc=first_arc)
    story_bible["project_card"] = build_project_card(payload, title, global_outline)
    story_bible["world_bible"] = _default_world_bible(payload)
    story_bible["cultivation_system"] = _default_cultivation_system(payload)
    story_bible["volume_cards"] = build_volume_cards(global_outline, first_arc)
    story_bible["control_console"] = build_control_console(payload, first_arc)
    story_bible["serial_rules"] = build_serial_rules()
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
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers.clear()
    planning_layers.update({
        "global_outline_ready": bool(global_outline),
        "volume_cards_ready": True,
        "first_near_outline_ready": bool(first_arc),
        "first_chapter_cards_ready": bool((first_arc or {}).get("chapters")),
        "serial_rules_ready": True,
        "long_term_state_ready": True,
        "initialization_packet_ready": True,
    })
    story_bible["planning_layers"] = planning_layers
    story_bible["workflow_state"] = _workflow_state_from_arc(first_arc)
    story_bible = set_delivery_mode(story_bible, DEFAULT_SERIAL_DELIVERY_MODE)
    story_bible = refresh_planning_views(story_bible, 0)
    stub_novel = Novel(
        title=title,
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences or {},
        current_chapter_no=0,
    )
    return sync_long_term_state(story_bible, stub_novel, chapters=[])


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
    story_bible = ensure_story_state_domains(deepcopy(story_bible or {}), workflow_factory=_workflow_state_from_arc, active_arc=(story_bible or {}).get("active_arc") if isinstance(story_bible, dict) else None)
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
    if "serial_rules" not in story_bible:
        story_bible["serial_rules"] = build_serial_rules()
    if "continuity_rules" not in story_bible:
        story_bible["continuity_rules"] = list(DEFAULT_CONTINUITY_RULES)
    if "daily_workflow" not in story_bible:
        story_bible["daily_workflow"] = {
            "steps": ["回看昨天结尾", "确定今天这章的功能", "写三行章纲", "写正文", "留明天提示"],
            "quality_floor": ["主角有没有行动", "事件有没有推进", "有没有新变化", "节奏有没有拖", "结尾有没有拉力"],
        }
    planning_layers = ensure_planning_layers(story_bible)
    planning_layers.setdefault("global_outline_ready", bool(global_outline))
    planning_layers.setdefault("volume_cards_ready", bool(story_bible.get("volume_cards")))
    planning_layers.setdefault("first_near_outline_ready", bool(active_arc))
    planning_layers.setdefault("first_chapter_cards_ready", bool((active_arc or {}).get("chapters")))
    planning_layers.setdefault("serial_rules_ready", True)
    planning_layers.setdefault("long_term_state_ready", True)
    planning_layers.setdefault("initialization_packet_ready", True)
    story_bible["planning_layers"] = planning_layers
    if "workflow_state" not in story_bible:
        story_bible["workflow_state"] = _workflow_state_from_arc(active_arc)
    story_bible = set_delivery_mode(story_bible, (story_bible.get("serial_runtime") or {}).get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE))
    ensure_hard_fact_guard(story_bible)
    update_volume_card_statuses(story_bible, novel.current_chapter_no)
    story_bible = refresh_planning_views(story_bible, novel.current_chapter_no)
    return sync_long_term_state(story_bible, novel)


def build_execution_brief(
    *,
    story_bible: dict[str, Any],
    next_chapter_no: int,
    plan: dict[str, Any],
    last_chapter_tail: str,
) -> dict[str, Any]:
    console = ensure_control_console(story_bible)
    current_volume = _current_volume_card(story_bible, next_chapter_no)
    today_function = _text(plan.get("goal"), "推进剧情")
    if plan.get("supporting_character_focus"):
        today_function += f" + 让{_text(plan.get('supporting_character_focus'))}在场面里立住"
    change_line = _text(plan.get("discovery") or plan.get("conflict"), "局势会在本章发生可感知的新变化。")
    focus_name = _text(plan.get("supporting_character_focus"))
    character_focus_card = {}
    if focus_name:
        character_focus_card = ((console.get("character_cards") or {}).get(focus_name) or {}) if isinstance(console.get("character_cards"), dict) else {}
    character_voice_pack = _character_voice_pack(character_focus_card) if character_focus_card else {}
    retrospective_feedback = _recent_retrospective_feedback(console)
    tomorrow_hints = [
        f"明天从第{next_chapter_no}章结尾的后续局势接上。",
        f"明天最大冲突：{_text(plan.get('conflict') or plan.get('goal'), '继续推进当前矛盾。')}",
        f"明天章末可往‘{_text(plan.get('ending_hook'), '新问题浮出')}’方向留钩子。",
    ]
    long_term_state = story_bible.get("long_term_state") or {}
    release_state = (long_term_state.get("chapter_release_state") or {})
    return {
        "project_card": story_bible.get("project_card", {}),
        "current_volume_card": current_volume,
        "chapter_execution_card": {
            "chapter_function": today_function,
            "event_type": _text(plan.get("event_type"), "试探类"),
            "progress_kind": _text(plan.get("progress_kind"), "信息推进"),
            "agency_mode": _text(plan.get("agency_mode_label") or plan.get("agency_mode"), "通用主动推进"),
            "proactive_move": _text(plan.get("proactive_move"), "主角必须主动做出判断并推动局势前进。"),
            "payoff_or_pressure": _text(plan.get("payoff_or_pressure"), "本章必须给出明确回报或压力升级。"),
            "hook_kind": _text(plan.get("hook_kind"), "更大谜团"),
            "opening": _text(plan.get("opening_beat"), "顺着上一章结尾自然接入场景。"),
            "middle": _text(plan.get("mid_turn"), "中段加入受阻、试探或代价。"),
            "ending": _text(plan.get("closing_image"), "结尾落在具体画面、结果或新问题上。"),
            "agency_summary": _text(plan.get("agency_style_summary")),
            "chapter_change": change_line,
            "chapter_hook": _text(plan.get("ending_hook"), "留下继续追更的拉力。"),
        },
        "scene_outline": [
            {"scene_no": 1, "purpose": _text(plan.get("opening_beat"), "承接上一章结尾并定位本章场景")},
            {"scene_no": 2, "purpose": _text(plan.get("mid_turn"), "中段制造受阻、试探或发现")},
            {"scene_no": 3, "purpose": _text(plan.get("closing_image") or plan.get("ending_hook"), "结尾落到结果、钩子或下一章入口")},
        ],
        "serial_context": {
            "delivery_mode": release_state.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE),
            "published_through": int(release_state.get("published_through", 0) or 0),
            "latest_available_chapter": int(release_state.get("latest_available_chapter", 0) or 0),
            "fact_priority": (story_bible.get("serial_rules") or {}).get("fact_priority", []),
        },
        "character_focus_card": character_focus_card,
        "character_voice_pack": character_voice_pack,
        "chapter_retrospective_feedback": retrospective_feedback,
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
            "主角必须在本章主动做出至少一次观察、判断、试探、设局、争资源、验证、表态或反击。",
            "本章不能重复最近两章的主事件类型。",
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
        palette = _supporting_voice_template(focus_name, note)
        profile = current or {
            "name": focus_name,
            "role_type": "supporting",
            "current_plot_function": "本阶段重要配角",
            "role_archetype": palette.get("role_archetype"),
            "speech_style": _text(note, _text(palette.get("speech_style"))),
            "work_style": _text(palette.get("work_style")),
            "current_desire": _text(palette.get("private_goal"), "先保住自己的利益，再决定是否靠近主角。"),
            "attitude_to_protagonist": "待观察",
            "recent_impact": "刚在当前剧情中留下存在感。",
            "do_not_break": ["不能只会盘问和警告", "要保留角色自己的利益与语气"],
            "behavior_logic": _text(palette.get("work_style"), note),
            "pressure_response": _text(palette.get("pressure_response")),
            "small_tell": _text(palette.get("small_tell")),
            "taboo": _text(palette.get("taboo")),
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
    console = ensure_control_console(story_bible)
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

    retrospective = _build_chapter_retrospective(
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        plan=plan,
        summary=summary,
        console=console,
    )
    retrospectives = console.setdefault("chapter_retrospectives", [])
    retrospectives.append(retrospective)
    console["chapter_retrospectives"] = retrospectives[-12:]

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
        palette = _supporting_voice_template(focus_name, _text(plan.get("supporting_character_note")))
        _merge_character_card(
            console,
            focus_name,
            {
                "name": focus_name,
                "role_type": "supporting",
                "role_archetype": _text(palette.get("role_archetype")),
                "temperament": _text(plan.get("supporting_character_note"), "本阶段的重要配角。"),
                "speech_style": _text(plan.get("supporting_character_note"), _text(palette.get("speech_style"), "说话方式需要有辨识度。")),
                "work_style": _text(palette.get("work_style"), _text(plan.get("conflict") or plan.get("goal"), "做事有自己的算盘与顾虑。")),
                "current_desire": _text(plan.get("goal"), _text(palette.get("private_goal"), "在当前局势中争取自己的利益。")),
                "attitude_to_protagonist": "试探中",
                "recent_impact": _text(plan.get("ending_hook") or plan.get("conflict"), "给主角带来新的局势变化。"),
                "current_plot_function": "作为本章关键配角参与推进。",
                "relationship_to_protagonist": "待剧情更新",
                "possible_change": "关系可能由试探转向合作或对立。",
                "pressure_response": _text(palette.get("pressure_response")),
                "small_tell": _text(palette.get("small_tell")),
                "taboo": _text(palette.get("taboo")),
                "do_not_break": ["不能所有配角都说同一种话", "不能只剩功能没有人格"],
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
    delivery_mode = ((story_bible.get("serial_runtime") or {}).get("delivery_mode") or DEFAULT_SERIAL_DELIVERY_MODE)
    serial_stage = "published" if delivery_mode == "live_publish" else "stock"
    story_bible = record_chapter_fact_entries(
        story_bible,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        summary=summary,
        plan=plan,
        serial_stage=serial_stage,
        fallback_content=_text(getattr(summary, "event_summary", None), _text(plan.get("goal"), chapter_title)),
    )
    story_bible["control_console"] = console
    runtime = ensure_serial_runtime(story_bible)
    runtime["last_chapter_review"] = retrospective
    story_bible["serial_runtime"] = runtime
    story_bible = refresh_planning_views(story_bible, chapter_no)
    story_bible = set_pipeline_target(story_bible, next_chapter_no=chapter_no + 1, stage="summary_and_review", last_completed_chapter_no=chapter_no)
    update_story_state_bucket(
        story_bible,
        last_chapter_update={
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "delivery_mode": delivery_mode,
            "recent_progress_count": len(console.get("recent_progress", [])),
        },
    )
    return sync_long_term_state(story_bible, novel)


def build_control_console_snapshot(novel: Novel) -> dict[str, Any]:
    story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    console = ensure_control_console(story_bible)
    return {
        "novel_id": novel.id,
        "title": novel.title,
        "project_card": story_bible.get("project_card", {}),
        "world_bible": story_bible.get("world_bible", {}),
        "cultivation_system": story_bible.get("cultivation_system", {}),
        "serial_rules": story_bible.get("serial_rules", {}),
        "serial_runtime": story_bible.get("serial_runtime", {}),
        "fact_ledger": story_bible.get("fact_ledger", {}),
        "hard_fact_guard": compact_hard_fact_guard(story_bible.get("hard_fact_guard", {})),
        "long_term_state": story_bible.get("long_term_state", {}),
        "initialization_packet": story_bible.get("initialization_packet", {}),
        "current_volume_card": _current_volume_card(story_bible, novel.current_chapter_no + 1),
        "control_console": console,
        "planning_layers": story_bible.get("planning_layers", {}),
        "planning_state": story_bible.get("workflow_state", {}),
        "continuity_rules": story_bible.get("continuity_rules", list(DEFAULT_CONTINUITY_RULES)),
        "daily_workflow": story_bible.get("daily_workflow", {}),
        "story_state": story_bible.get("story_state", {}),
    }
