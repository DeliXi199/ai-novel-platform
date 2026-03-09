from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.services.openai_story_engine import (
    generate_serial_chapter,
    is_openai_enabled,
    parse_instruction_with_openai,
)


def _fallback_parse_reader_instruction(raw_instruction: str) -> dict:
    parsed = {
        "character_focus": {},
        "tone": None,
        "pace": None,
        "protected_characters": [],
        "relationship_direction": None,
    }

    if "轻松" in raw_instruction or "别太虐" in raw_instruction:
        parsed["tone"] = "lighter"
    if "黑暗" in raw_instruction or "压抑" in raw_instruction:
        parsed["tone"] = "darker"
    if "快一点" in raw_instruction or "节奏快" in raw_instruction:
        parsed["pace"] = "faster"
    if "慢一点" in raw_instruction or "慢热" in raw_instruction:
        parsed["pace"] = "slower"
    if "感情线强一点" in raw_instruction or "多点暧昧" in raw_instruction:
        parsed["relationship_direction"] = "stronger_romance"
    if "慢热感情" in raw_instruction:
        parsed["relationship_direction"] = "slow_burn"
    return parsed


def parse_reader_instruction(raw_instruction: str) -> dict:
    if is_openai_enabled():
        try:
            return parse_instruction_with_openai(raw_instruction).model_dump(mode="python")
        except Exception:
            return _fallback_parse_reader_instruction(raw_instruction)
    return _fallback_parse_reader_instruction(raw_instruction)


def collect_active_interventions(db: Session, novel_id: int, next_chapter_no: int) -> list[Intervention]:
    interventions = db.query(Intervention).filter(Intervention.novel_id == novel_id).all()
    active = []
    for item in interventions:
        end_chapter = item.chapter_no + item.effective_chapter_span
        if item.chapter_no < next_chapter_no <= end_chapter:
            active.append(item)
    return active


def _serialize_recent_summaries(db: Session, novel_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(ChapterSummary, Chapter)
        .join(Chapter, ChapterSummary.chapter_id == Chapter.id)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_no.desc())
        .limit(settings.chapter_recent_summary_limit)
        .all()
    )
    rows = list(reversed(rows))
    result: list[dict[str, Any]] = []
    for summary, chapter in rows:
        result.append(
            {
                "chapter_no": chapter.chapter_no,
                "chapter_title": chapter.title,
                "event_summary": summary.event_summary,
                "character_updates": summary.character_updates,
                "new_clues": summary.new_clues,
                "open_hooks": summary.open_hooks,
                "closed_hooks": summary.closed_hooks,
            }
        )
    return result


def _serialize_last_chapter(last_chapter: Chapter | None) -> dict[str, Any]:
    if not last_chapter:
        return {}
    return {
        "chapter_no": last_chapter.chapter_no,
        "title": last_chapter.title,
        "tail_excerpt": last_chapter.content[-1200:],
    }


def _serialize_novel_context(novel: Novel, next_no: int) -> dict[str, Any]:
    return {
        "novel_id": novel.id,
        "title": novel.title,
        "genre": novel.genre,
        "premise": novel.premise,
        "protagonist_name": novel.protagonist_name,
        "story_bible": novel.story_bible,
        "style_preferences": novel.style_preferences,
        "current_chapter_no": novel.current_chapter_no,
        "target_chapter_no": next_no,
    }


def _serialize_active_interventions(active_interventions: list[Intervention]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in active_interventions:
        result.append(
            {
                "intervention_id": item.id,
                "from_chapter": item.chapter_no,
                "effective_span": item.effective_chapter_span,
                "raw_instruction": item.raw_instruction,
                "parsed_constraints": item.parsed_constraints,
            }
        )
    return result


def generate_next_chapter(db: Session, novel: Novel) -> Chapter:
    next_no = novel.current_chapter_no + 1
    last_chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_no.desc())
        .first()
    )

    active_interventions = collect_active_interventions(db, novel.id, next_no)

    if is_openai_enabled():
        generated = generate_serial_chapter(
            novel_context=_serialize_novel_context(novel, next_no),
            last_chapter=_serialize_last_chapter(last_chapter),
            recent_summaries=_serialize_recent_summaries(db, novel.id),
            active_interventions=_serialize_active_interventions(active_interventions),
        )
        chapter_title = generated.title or f"第{next_no}章"
        content = generated.content
        generation_meta = {
            **generated.generation_meta,
            "based_on_chapter": last_chapter.chapter_no if last_chapter else None,
            "active_interventions": [i.id for i in active_interventions],
        }
        event_summary = generated.event_summary
        character_updates = generated.character_updates
        new_clues = generated.new_clues
        open_hooks = generated.open_hooks
        closed_hooks = generated.closed_hooks
    else:
        tone_hints = [i.parsed_constraints.get("tone") for i in active_interventions if i.parsed_constraints.get("tone")]
        pace_hints = [i.parsed_constraints.get("pace") for i in active_interventions if i.parsed_constraints.get("pace")]

        tone = tone_hints[-1] if tone_hints else "default"
        pace = pace_hints[-1] if pace_hints else "default"

        chapter_title = f"第{next_no}章 推进"
        content = (
            f"承接上一章，故事进入第{next_no}章。\n\n"
            f"主角 {novel.protagonist_name} 继续沿着主线前进。"
            f"当前故事题材为 {novel.genre}，背景核心是：{novel.premise}。\n\n"
            f"系统检测到的读者干预倾向：tone={tone}, pace={pace}。\n\n"
            f"因此这一章在叙事上会适度体现相应变化，同时继续推进主线。\n\n"
            f"上一章标题为《{last_chapter.title}》，而这一章将进一步展开冲突，并在结尾留下新的悬念。"
        )
        generation_meta = {
            "generator": "mock_chapter_generator",
            "based_on_chapter": last_chapter.chapter_no if last_chapter else None,
            "active_interventions": [i.id for i in active_interventions],
            "tone": tone,
            "pace": pace,
        }
        event_summary = f"第{next_no}章继续推进主线，并结合读者偏好微调叙事方向。"
        character_updates = {novel.protagonist_name: {"chapter_progress": next_no}}
        new_clues = [f"第{next_no}章新增剧情推进节点"]
        open_hooks = [f"第{next_no}章结尾悬念"]
        closed_hooks = []

    chapter = Chapter(
        novel_id=novel.id,
        chapter_no=next_no,
        title=chapter_title,
        content=content,
        generation_meta=generation_meta,
    )
    db.add(chapter)
    db.flush()

    summary = ChapterSummary(
        chapter_id=chapter.id,
        event_summary=event_summary,
        character_updates=character_updates,
        new_clues=new_clues,
        open_hooks=open_hooks,
        closed_hooks=closed_hooks,
    )
    db.add(summary)

    novel.current_chapter_no = next_no
    for item in active_interventions:
        item.applied = True

    db.commit()
    db.refresh(chapter)
    return chapter
