from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel


def parse_reader_instruction(raw_instruction: str) -> dict:
    text = raw_instruction.lower()
    parsed = {
        "character_focus": {},
        "tone": None,
        "pace": None,
        "protected_characters": [],
    }

    if "轻松" in raw_instruction or "别太虐" in raw_instruction:
        parsed["tone"] = "lighter"
    if "黑暗" in raw_instruction or "压抑" in raw_instruction:
        parsed["tone"] = "darker"
    if "快一点" in raw_instruction or "节奏快" in raw_instruction:
        parsed["pace"] = "faster"
    if "慢一点" in raw_instruction or "慢热" in raw_instruction:
        parsed["pace"] = "slower"

    # 很简化的占位逻辑：后续可以换成 LLM / rule parser
    return parsed


def collect_active_interventions(db: Session, novel_id: int, next_chapter_no: int) -> list[Intervention]:
    interventions = db.query(Intervention).filter(Intervention.novel_id == novel_id).all()
    active = []
    for item in interventions:
        end_chapter = item.chapter_no + item.effective_chapter_span
        if item.chapter_no < next_chapter_no <= end_chapter:
            active.append(item)
    return active


def generate_next_chapter(db: Session, novel: Novel) -> Chapter:
    next_no = novel.current_chapter_no + 1
    last_chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_no.desc())
        .first()
    )

    active_interventions = collect_active_interventions(db, novel.id, next_no)
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
        event_summary=f"第{next_no}章继续推进主线，并结合读者偏好微调叙事方向。",
        character_updates={novel.protagonist_name: {"chapter_progress": next_no}},
        new_clues=[f"第{next_no}章新增剧情推进节点"],
        open_hooks=[f"第{next_no}章结尾悬念"],
        closed_hooks=[],
    )
    db.add(summary)

    novel.current_chapter_no = next_no
    for item in active_interventions:
        item.applied = True

    db.commit()
    db.refresh(chapter)
    return chapter
