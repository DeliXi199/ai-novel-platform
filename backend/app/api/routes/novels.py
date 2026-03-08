from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.intervention import Intervention
from app.models.novel import Novel
from app.schemas.chapter import ChapterResponse
from app.schemas.intervention import InterventionCreate, InterventionResponse
from app.schemas.novel import NovelCreate, NovelResponse
from app.services.chapter_generation import generate_next_chapter, parse_reader_instruction
from app.services.novel_bootstrap import build_story_bible, generate_first_chapter, generate_title

router = APIRouter(prefix="/novels", tags=["novels"])


@router.post("", response_model=NovelResponse, status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelCreate, db: Session = Depends(get_db)):
    story_bible = build_story_bible(payload)
    title = generate_title(payload)

    novel = Novel(
        title=title,
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences,
        story_bible=story_bible,
        current_chapter_no=1,
    )
    db.add(novel)
    db.flush()

    chapter_title, chapter_content, generation_meta, summary_payload = generate_first_chapter(payload, story_bible)
    chapter = Chapter(
        novel_id=novel.id,
        chapter_no=1,
        title=chapter_title,
        content=chapter_content,
        generation_meta=generation_meta,
    )
    db.add(chapter)
    db.flush()

    summary = ChapterSummary(
        chapter_id=chapter.id,
        event_summary=summary_payload["event_summary"],
        character_updates=summary_payload["character_updates"],
        new_clues=summary_payload["new_clues"],
        open_hooks=summary_payload["open_hooks"],
        closed_hooks=summary_payload["closed_hooks"],
    )
    db.add(summary)
    db.commit()
    db.refresh(novel)
    return novel


@router.get("/{novel_id}", response_model=NovelResponse)
def get_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


@router.get("/{novel_id}/chapters/{chapter_no}", response_model=ChapterResponse)
def get_chapter(novel_id: int, chapter_no: int, db: Session = Depends(get_db)):
    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_no == chapter_no)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.post("/{novel_id}/interventions", response_model=InterventionResponse, status_code=status.HTTP_201_CREATED)
def create_intervention(novel_id: int, payload: InterventionCreate, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    parsed = parse_reader_instruction(payload.raw_instruction)
    intervention = Intervention(
        novel_id=novel_id,
        chapter_no=payload.chapter_no,
        raw_instruction=payload.raw_instruction,
        parsed_constraints=parsed,
        effective_chapter_span=payload.effective_chapter_span,
    )
    db.add(intervention)
    db.commit()
    db.refresh(intervention)
    return intervention


@router.post("/{novel_id}/next-chapter", response_model=ChapterResponse)
def create_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    chapter = generate_next_chapter(db, novel)
    return chapter
