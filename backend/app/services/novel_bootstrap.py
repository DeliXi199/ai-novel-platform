from __future__ import annotations

from app.core.config import settings
from app.schemas.novel import NovelCreate
from app.services.openai_story_engine import (
    generate_arc_outline,
    generate_global_outline,
    generate_story_engine_diagnosis,
    generate_story_engine_strategy_bundle as generate_story_engine_strategy_bundle_payload,
    generate_story_strategy_card,
)
from app.services.openai_story_engine_arc import (
    apply_arc_casting_layout_review,
    review_arc_casting_layout,
)
from app.services.story_architecture import compose_story_bible
from app.services.payoff_compensation_support import apply_payoff_window_event_bias_to_plan, payoff_window_event_bias


def _text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _truncate_text(value: object, limit: int = 120) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _append_unique_sentence(base: str, addition: str, *, limit: int = 140) -> str:
    left = _text(base)
    right = _text(addition)
    if not right:
        return left
    if right in left:
        return _truncate_text(left, limit)
    joined = f"{left}；{right}" if left else right
    return _truncate_text(joined, limit)


def _planning_payoff_compensation_window(story_bible: dict, *, start_chapter: int, end_chapter: int) -> dict:
    retrospective_state = (story_bible or {}).get("retrospective_state") or {}
    payload = retrospective_state.get("pending_payoff_compensation") or {}
    if not isinstance(payload, dict) or not payload or not bool(payload.get("enabled", True)):
        return {}
    chapter_biases = payload.get("chapter_biases") or []
    overlaps: list[dict] = []
    for item in chapter_biases:
        if not isinstance(item, dict):
            continue
        chapter_no = int(item.get("chapter_no", 0) or 0)
        if start_chapter <= chapter_no <= end_chapter:
            role = _text(item.get("bias") or item.get("window_role"), "primary_repay")
            priority = _text(item.get("priority") or payload.get("priority"), "medium")
            bias_payload = payoff_window_event_bias(role, priority=priority)
            overlaps.append({
                "chapter_no": chapter_no,
                "bias": role,
                "priority": priority,
                "note": _text(item.get("note") or payload.get("note") or payload.get("reason")),
                "preferred_event_types": list(bias_payload.get("preferred_event_types") or []),
                "limited_event_types": list(bias_payload.get("limited_event_types") or []),
                "preferred_progress_kinds": list(bias_payload.get("preferred_progress_kinds") or []),
                "event_bias_note": _text(bias_payload.get("event_bias_note")),
            })
    if not overlaps:
        return {}
    source_chapter_no = int(payload.get("source_chapter_no", 0) or 0)
    note = _text(payload.get("note") or payload.get("reason"), "上一章兑现偏虚，接下来 1-2 章要追回一次明确回报。")
    hint_lines = [
        f"这次追账来自第{source_chapter_no}章，先把读者应得的回报追回来。" if source_chapter_no else "当前窗口里有待追回的回报。",
        "第一顺位章节优先给明确落袋，别继续纯蓄压。",
    ]
    if len(overlaps) >= 2:
        hint_lines.append("若两章都受影响，前一章追回，后一章稳住余波并换一种显影方式。")
    if bool(payload.get("should_reduce_pressure", True)):
        hint_lines.append("补偿窗口里适度降低继续只抬风险的比例。")
    event_guidance = []
    for item in overlaps[:2]:
        chapter_no = int(item.get("chapter_no", 0) or 0)
        preferred = " / ".join([_text(name) for name in (item.get("preferred_event_types") or [])[:3] if _text(name)])
        limited = " / ".join([_text(name) for name in (item.get("limited_event_types") or [])[:2] if _text(name)])
        if preferred:
            line = f"第{chapter_no}章优先安排{preferred}"
            if limited:
                line += f"，少用{limited}"
            event_guidance.append(line)
    return {
        "source_chapter_no": source_chapter_no,
        "priority": _text(payload.get("priority"), "medium"),
        "note": note,
        "target_chapter_no": int(payload.get("target_chapter_no", 0) or 0),
        "window_end_chapter_no": int(payload.get("window_end_chapter_no", 0) or 0),
        "overlapping_chapters": overlaps,
        "hint_lines": hint_lines[:4],
        "event_guidance": event_guidance[:2],
        "should_reduce_pressure": bool(payload.get("should_reduce_pressure", True)),
    }


def _apply_payoff_compensation_window_to_bundle(bundle: dict, story_bible: dict, *, start_chapter: int, end_chapter: int) -> dict:
    window = _planning_payoff_compensation_window(story_bible, start_chapter=start_chapter, end_chapter=end_chapter)
    if not window:
        return bundle
    chapter_bias_map = {int(item.get("chapter_no", 0) or 0): item for item in (window.get("overlapping_chapters") or []) if isinstance(item, dict)}
    chapters = bundle.get("chapters") or []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter_no = int(chapter.get("chapter_no", 0) or 0)
        bias = chapter_bias_map.get(chapter_no)
        if not bias:
            continue
        role = _text(bias.get("bias"), "primary_repay")
        priority = _text(bias.get("priority"), _text(window.get("priority"), "medium")).lower()
        note = _text(bias.get("note") or window.get("note"))
        compensation = {
            "enabled": True,
            "source_chapter_no": int(window.get("source_chapter_no", 0) or 0),
            "target_chapter_no": chapter_no,
            "priority": priority,
            "note": note,
            "reason": note,
            "window_role": role,
            "window_end_chapter_no": int(window.get("window_end_chapter_no", 0) or 0),
            "should_reduce_pressure": bool(window.get("should_reduce_pressure", True)),
        }
        chapter["payoff_compensation"] = compensation
        chapter["payoff_window_bias"] = role
        prior_events = [
            _text(item.get("event_type"))
            for item in chapters
            if isinstance(item, dict) and int(item.get("chapter_no", 0) or 0) < chapter_no and _text(item.get("event_type"))
        ]
        adjusted = apply_payoff_window_event_bias_to_plan(
            chapter,
            role=role,
            priority=priority,
            note=note,
            recent_event_types=prior_events[-2:],
        )
        chapter.update(adjusted)
        if role == "primary_repay":
            chapter["payoff_level"] = "strong" if priority == "high" else "medium"
            chapter["payoff_or_pressure"] = _append_unique_sentence(chapter.get("payoff_or_pressure"), "本章优先补一次明确回报落袋，不要继续只蓄压。")
            chapter.setdefault("reader_payoff", "本章要把读者应得的回报真正拿到手。")
            chapter.setdefault("new_pressure", "回报落袋后立刻带出新的盯防、代价或后患。")
            chapter["writing_note"] = _append_unique_sentence(chapter.get("writing_note"), note or "这一章先把兑现追回来，再把后患接上。")
        else:
            if _text(chapter.get("payoff_level")).lower() not in {"medium", "strong"}:
                chapter["payoff_level"] = "medium"
            chapter["payoff_or_pressure"] = _append_unique_sentence(chapter.get("payoff_or_pressure"), "本章至少保留一次可感回收，别重新连续两章只抬压力。")
            chapter["writing_note"] = _append_unique_sentence(chapter.get("writing_note"), note or "这一章负责稳住兑现余波，并换一种显影方式。")
    bundle["planning_payoff_compensation"] = window
    if window.get("hint_lines"):
        bundle["bridge_note"] = _append_unique_sentence(bundle.get("bridge_note"), " ".join([_text(item) for item in (window.get("hint_lines") or [])[:2] if _text(item)]), limit=180)
    if window.get("event_guidance"):
        bundle["bridge_note"] = _append_unique_sentence(bundle.get("bridge_note"), " ".join([_text(item) for item in (window.get("event_guidance") or [])[:2] if _text(item)]), limit=180)
    return bundle



def _story_text(payload: NovelCreate) -> str:
    style = payload.style_preferences or {}
    parts = [
        payload.genre,
        payload.premise,
        str(style.get("tone") or ""),
        str(style.get("story_engine") or style.get("opening_mode") or ""),
    ]
    return " ".join(part for part in parts if part).lower()



def _opening_pacing_rules(
    payload: NovelCreate,
    story_engine_diagnosis: dict[str, object] | None = None,
    story_strategy_card: dict[str, object] | None = None,
) -> dict[str, str]:
    diagnosis = story_engine_diagnosis or {}
    strategy = story_strategy_card or {}
    if diagnosis:
        phase_1 = (strategy.get("chapter_1_to_10") or {}) if isinstance(strategy, dict) else {}
        phase_2 = (strategy.get("chapter_11_to_20") or {}) if isinstance(strategy, dict) else {}
        frequent = "、".join([str(item).strip() for item in (phase_1.get("frequent_elements") or []) if str(item).strip()][:4]) or "资源、关系、局势与结果"
        limited = "、".join([str(item).strip() for item in (phase_1.get("limited_elements") or []) if str(item).strip()][:3]) or "重复被怀疑后被动应付"
        must_haves = "、".join([str(item).strip() for item in (diagnosis.get("early_must_haves") or []) if str(item).strip()][:4]) or "现实压力、第一轮有效收益、主线入口"
        return {
            "overall": str(diagnosis.get("opening_drive") or "前期先把主角处境、第一轮目标和主线引擎钉牢。"),
            "first_three_chapters": f"前3章先完成这些必要建立：{must_haves}。",
            "first_twelve_chapters": f"前12章优先轮换{frequent}，主动限制{limited}；到中前段要完成：{str(phase_2.get('stage_mission') or strategy.get('first_30_mainline_summary') or '阶段推进')}",
        }
    story_text = _story_text(payload)
    if any(token in story_text for token in ["金手指", "机缘", "外挂", "神器"]):
        return {
            "overall": "允许更早出现机缘兑现、能力试错与升级反馈，但要同时写清代价、限制与后果。",
            "first_three_chapters": "前3章可以较快给出第一轮能力或机缘反馈，不必强压成纯调查。",
            "first_twelve_chapters": "前12章要让机缘、资源、人际与小冲突交替推进，不能只围着同一条线索打转。",
        }
    if any(token in story_text for token in ["凡人", "苟", "低调", "求生"]):
        return {
            "overall": "慢热、单场景、少设定堆砌、强调因果与细节。",
            "first_three_chapters": "先写主角处境与风险试探，不要直接进入宏大场面。",
            "first_twelve_chapters": "逐步抬高风险与世界观，不要过快升级。",
        }
    if any(token in story_text for token in ["宗门", "学院", "试炼", "天才", "大比"]):
        return {
            "overall": "成长、竞争与世界展开并行，允许更早进入宗门、师承、试炼或比斗。",
            "first_three_chapters": "尽早建立主角的起点差距、竞争目标和第一轮入局压力。",
            "first_twelve_chapters": "前12章要持续给成长反馈、关系变化与阶段性胜负，不要只写试探。",
        }
    return {
        "overall": "贴合题材定位推进，强调具体目标、代价和结果，不要套固定开局模板。",
        "first_three_chapters": "先把主角处境、第一轮目标和主线引擎钉牢。",
        "first_twelve_chapters": "前12章持续轮换资源、关系、地图、冲突与成长反馈，不要让同一线索长期垄断。",
    }



def generate_story_engine_diagnosis_bundle(payload: NovelCreate, story_bible: dict[str, object]) -> dict:
    diagnosis = generate_story_engine_diagnosis(payload.model_dump(mode="python"), story_bible)
    return diagnosis.model_dump(mode="python")


def generate_story_strategy_bundle(payload: NovelCreate, story_bible: dict[str, object]) -> dict:
    strategy = generate_story_strategy_card(payload.model_dump(mode="python"), story_bible)
    return strategy.model_dump(mode="python")


def generate_story_engine_strategy_bundle(payload: NovelCreate, story_bible: dict[str, object]) -> tuple[dict, dict]:
    bundle = generate_story_engine_strategy_bundle_payload(payload.model_dump(mode="python"), story_bible)
    return bundle.story_engine_diagnosis.model_dump(mode="python"), bundle.story_strategy_card.model_dump(mode="python")


def build_base_story_bible(
    payload: NovelCreate,
    story_engine_diagnosis: dict[str, object] | None = None,
    story_strategy_card: dict[str, object] | None = None,
) -> dict:
    genre = payload.genre.strip()
    premise = payload.premise.strip()
    protagonist = payload.protagonist_name.strip()

    return {
        "genre": genre,
        "premise": premise,
        "protagonist": protagonist,
        "narrative_style": payload.style_preferences.get("tone", "连载小说风格"),
        "reader_preferences": payload.style_preferences,
        "core_conflict": f"围绕‘{premise}’展开的主线冲突。",
        "forbidden_rules": payload.style_preferences.get("forbidden", []),
        "target_words_per_chapter": settings.chapter_target_words,
        "bootstrap_initial_chapters": settings.bootstrap_initial_chapters,
        "outline_engine": {
            "global_outline_acts": settings.global_outline_acts,
            "arc_outline_size": settings.arc_outline_size,
            "planning_window_size": settings.planning_window_size,
            "arc_prefetch_threshold": settings.arc_prefetch_threshold,
        },
        "workflow_mode": {
            "bootstrap_documents_only": True,
            "strict_manual_pipeline": settings.planning_strict_mode,
            "chapter_generation_sequence": [
                "project_card",
                "current_volume_card",
                "near_outline",
                "chapter_execution_card",
                "chapter_draft",
                "summary_and_review",
            ],
        },
        "quality_guardrails": {
            "chapter_min_visible_chars": settings.chapter_min_visible_chars,
            "chapter_max_similarity": settings.chapter_similarity_threshold,
            "forbid_silent_fallback": True,
            "enforce_event_type_variety": True,
            "enforce_protagonist_agency": False,
            "enforce_effective_progress": True,
            "enforce_hook_strength": True,
        },
        "story_engine_diagnosis": story_engine_diagnosis or {},
        "story_strategy_card": story_strategy_card or {},
        "pacing_rules": _opening_pacing_rules(payload, story_engine_diagnosis=story_engine_diagnosis, story_strategy_card=story_strategy_card),
        "characterization_rules": [
            "配角不能只做剧情按钮，要带一点自己的私心、职业习惯、说话方式或防备心理。",
            "重复出现的配角至少要有一个可辨认的小动作、小习惯或固定顾虑。",
            "像掌柜、摊主、帮众这类边角人物，也要先像人，再推动剧情。",
            "同一种身份的配角也要区分：有人绕着说、有人压着说、有人表面温和实则套话。",
        ],
        "language_rules": [
            "整体保持冷峻克制，但不要整章都安全平顺，至少留一两句更具体、更有棱角的表达。",
            "少用温凉、微弱、片刻、没有再说什么这类安全词，能用动作和物件就不用抽象氛围词。",
            "重要情绪不要一笔带过，要让它落在停顿、回避、握紧、收起、沉默或处理旧物的动作上。",
        ],
        "antagonist_rules": [
            "反派或帮派人物不能只会威胁，要给读者一处记得住的细节：口头禅、伤疤、洁癖、做事逻辑或对上位者的惧怕。",
            "底层反派也要有自己的算盘，不要都写成同一种横蛮嘴脸。",
        ],
        "protagonist_emotion_rules": [
            f"{protagonist}的情绪应当克制，但在损失、离别、受辱、做选择时，要多写半寸心理重量。",
            "不要直接喊痛苦或感动，而是通过物件、迟疑、手势、视线回避和呼吸变化落出来。",
        ],
        "ending_rules": [
            "章末不必每次都硬留悬念。",
            "有的章末可以收在人物选择、结果落地或平稳过渡上。",
            "只有真正需要时，才用异象、反转或危险逼近做强钩子。",
            "但无论是否强悬念，章节结尾都必须回答：下一章为什么还值得继续看。",
        ],
        "chapter_planner_rules": [
            "不能连续三章使用同一种主事件类型。",
            "每章必须明确写出推进结果：信息、关系、资源、实力、风险、地点至少改变其一。",
            "每2到3章至少安排一次主角主动布局、试探、设局、争资源或制造信息差。",
            "不能把重复盘问、重复怀疑、重复隐藏秘密当成推进本身。",
        ],
    }



def generate_title(payload: NovelCreate) -> str:
    style = payload.style_preferences or {}
    custom = str(style.get("title_prefix") or style.get("title") or "").strip()
    if custom:
        return custom if ("：" in custom or "-" in custom) else f"{custom}：{payload.protagonist_name}的故事"

    genre_prefix_map = {
        "都市悬疑": "迷雾档案",
        "校园恋爱": "青春回声",
        "仙侠成长": "问道长歌",
        "凡人流修仙": "命运序章",
        "金手指修仙": "仙路机缘",
        "宗门修仙": "问仙录",
        "西幻冒险": "灰烬王冠",
        "末世生存": "余烬之城",
    }
    prefix = genre_prefix_map.get(payload.genre)
    if not prefix:
        if "修" in payload.genre or "仙" in payload.genre:
            prefix = "问仙纪"
        else:
            prefix = "命运序章"
    return f"{prefix}：{payload.protagonist_name}的故事"



def generate_global_story_outline(payload: NovelCreate, story_bible: dict[str, object]) -> dict:
    outline = generate_global_outline(
        payload.model_dump(mode="python"),
        story_bible,
        settings.global_outline_acts,
    )
    return outline.model_dump(mode="python")



def generate_arc_outline_bundle(
    payload: NovelCreate,
    story_bible: dict,
    global_outline: dict,
    start_chapter: int,
    end_chapter: int,
    arc_no: int,
    recent_summaries: list[dict] | None = None,
) -> dict:
    chunk_size = max(int(getattr(settings, "arc_outline_chunk_size", 1)), 1)
    recent = recent_summaries or []
    chapters: list[dict] = []
    focus_parts: list[str] = []
    bridge_parts: list[str] = []

    cursor = start_chapter
    while cursor <= end_chapter:
        chunk_end = min(cursor + chunk_size - 1, end_chapter)
        outline = generate_arc_outline(
            payload=payload.model_dump(mode="python"),
            story_bible=story_bible,
            global_outline=global_outline,
            recent_summaries=recent,
            start_chapter=cursor,
            end_chapter=chunk_end,
            arc_no=arc_no,
        )
        dumped = outline.model_dump(mode="python")
        if dumped.get("focus"):
            focus_parts.append(str(dumped["focus"]).strip())
        if dumped.get("bridge_note"):
            bridge_parts.append(str(dumped["bridge_note"]).strip())
        chapters.extend(dumped.get("chapters", []))
        cursor = chunk_end + 1

    seen_focus: list[str] = []
    for item in focus_parts:
        if item and item not in seen_focus:
            seen_focus.append(item)
    seen_bridge: list[str] = []
    for item in bridge_parts:
        if item and item not in seen_bridge:
            seen_bridge.append(item)

    bundle = {
        "arc_no": arc_no,
        "start_chapter": start_chapter,
        "end_chapter": end_chapter,
        "focus": " / ".join(seen_focus[:2]) if seen_focus else "稳定推进当前阶段主线。",
        "bridge_note": " ".join(seen_bridge[:2]) if seen_bridge else "这一段先稳住承接，再把风险轻轻抬高。",
        "chapters": chapters,
    }
    review = review_arc_casting_layout(
        payload=payload.model_dump(mode="python"),
        story_bible=story_bible,
        global_outline=global_outline,
        recent_summaries=recent,
        arc_bundle=bundle,
    )
    bundle = apply_arc_casting_layout_review(bundle, review)
    return _apply_payoff_compensation_window_to_bundle(bundle, story_bible, start_chapter=start_chapter, end_chapter=end_chapter)



def build_story_bible(
    payload: NovelCreate,
    title: str,
    global_outline: dict,
    first_arc: dict,
    story_engine_diagnosis: dict[str, object] | None = None,
    story_strategy_card: dict[str, object] | None = None,
) -> dict:
    base = build_base_story_bible(payload, story_engine_diagnosis=story_engine_diagnosis, story_strategy_card=story_strategy_card)
    return compose_story_bible(
        payload,
        title,
        base,
        global_outline,
        first_arc,
        story_engine_diagnosis=story_engine_diagnosis,
        story_strategy_card=story_strategy_card,
    )
