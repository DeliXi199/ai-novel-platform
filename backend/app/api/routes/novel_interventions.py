from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.intervention import Intervention
from app.schemas.intervention import InterventionCreate, InterventionListResponse, InterventionResponse
from app.services.chapter_generation import parse_reader_instruction

from .novel_common import ensure_bootstrap_not_running, require_novel

router = APIRouter(prefix="/novels", tags=["novels"])


@router.get("/{novel_id}/interventions", response_model=InterventionListResponse)
def list_interventions(novel_id: int, db: Session = Depends(get_db)):
    require_novel(db, novel_id)
    items = (
        db.query(Intervention)
        .filter(Intervention.novel_id == novel_id)
        .order_by(Intervention.created_at.desc(), Intervention.id.desc())
        .all()
    )
    return {"novel_id": novel_id, "total": len(items), "items": items}


@router.post("/{novel_id}/interventions", response_model=InterventionResponse, status_code=status.HTTP_201_CREATED)
def create_intervention(novel_id: int, payload: InterventionCreate, db: Session = Depends(get_db)):
    novel = require_novel(db, novel_id)
    ensure_bootstrap_not_running(novel, action="插入人工干预")

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
