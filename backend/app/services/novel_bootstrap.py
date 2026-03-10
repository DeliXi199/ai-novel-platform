from __future__ import annotations

from app.core.config import settings
from app.schemas.novel import NovelCreate
from app.services.openai_story_engine import (
    generate_arc_outline,
    generate_global_outline,
)
from app.services.story_architecture import compose_story_bible


def build_base_story_bible(payload: NovelCreate) -> dict:
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
        },
        "pacing_rules": {
            "overall": "慢热、单场景、少设定堆砌、强调因果与细节",
            "first_three_chapters": "先写主角处境与异常线索，不要直接进入宏大场面",
            "first_twelve_chapters": "逐步抬高风险与世界观，不要过快升级",
        },
        "characterization_rules": [
            "配角不能只做剧情按钮，要带一点自己的私心、职业习惯、说话方式或防备心理。",
            "重复出现的配角至少要有一个可辨认的小动作、小习惯或固定顾虑。",
            "像掌柜、摊主、帮众这类边角人物，也要先像人，再推动剧情。",
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
            "林玄的情绪应当克制，但在损失、离别、受辱、做选择时，要多写半寸心理重量。",
            "不要直接喊痛苦或感动，而是通过物件、迟疑、手势、视线回避和呼吸变化落出来。",
        ],
        "ending_rules": [
            "章末不必每次都硬留悬念。",
            "有的章末可以收在人物选择、结果落地或平稳过渡上。",
            "只有真正需要时，才用异象、反转或危险逼近做强钩子。",
        ],
    }



def generate_title(payload: NovelCreate) -> str:
    genre_prefix_map = {
        "都市悬疑": "迷雾档案",
        "校园恋爱": "青春回声",
        "仙侠成长": "问道长歌",
        "凡人流修仙": "命运序章",
        "西幻冒险": "灰烬王冠",
        "末世生存": "余烬之城",
    }
    prefix = genre_prefix_map.get(payload.genre, "命运序章")
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

    return {
        "arc_no": arc_no,
        "start_chapter": start_chapter,
        "end_chapter": end_chapter,
        "focus": " / ".join(seen_focus[:2]) if seen_focus else "稳定推进当前阶段主线。",
        "bridge_note": " ".join(seen_bridge[:2]) if seen_bridge else "这一段先稳住承接，再把风险轻轻抬高。",
        "chapters": chapters,
    }



def build_story_bible(payload: NovelCreate, title: str, global_outline: dict, first_arc: dict) -> dict:
    base = build_base_story_bible(payload)
    return compose_story_bible(payload, title, base, global_outline, first_arc)
