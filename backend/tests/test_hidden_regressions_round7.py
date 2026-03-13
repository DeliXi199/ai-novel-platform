from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models.chapter import Chapter
from app.models.chapter_summary import ChapterSummary
from app.models.novel import Novel
from app.services import chapter_generation as cg
from app.services.story_character_support import _build_chapter_retrospective


client = TestClient(app)


def test_frontend_module_assets_are_served() -> None:
    for path in [
        "/app/assets/app.js",
        "/app/assets/app/core.js",
        "/app/assets/app/ui_helpers.js",
        "/app/assets/app/renderers.js",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text.strip(), path



def test_build_chapter_retrospective_emits_timestamp() -> None:
    payload = _build_chapter_retrospective(
        chapter_no=4,
        chapter_title="雾里问路",
        plan={
            "event_type": "试探类",
            "progress_kind": "信息推进",
            "proactive_move": "主动试探摊主口风",
            "hook_kind": "新发现",
        },
        summary=SimpleNamespace(event_summary="主角从细节里确认了新的异常点。"),
        console={"chapter_retrospectives": []},
    )
    assert payload["chapter_no"] == 4
    assert payload["summary"]
    assert payload["created_at"].endswith("Z")



def test_generate_next_chapter_success_path_builds_continuity_bridge(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    novel = Novel(
        title="测试新章生成",
        genre="修仙",
        premise="主角在破庙附近追查异常气息。",
        protagonist_name="林玄",
        style_preferences={"tone": "冷峻克制"},
        story_bible={},
        current_chapter_no=0,
        status="planning_ready",
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    monkeypatch.setattr(cg, "begin_llm_trace", lambda trace_key: "trace-1")
    monkeypatch.setattr(cg, "clear_llm_trace", lambda: None)
    monkeypatch.setattr(cg, "get_llm_trace", lambda: [])
    monkeypatch.setattr(cg, "_acquire_generation_slot", lambda db, novel_id: "planning_ready")
    monkeypatch.setattr(cg, "_load_novel_or_404", lambda db, novel_id: db.query(Novel).filter(Novel.id == novel_id).first())
    monkeypatch.setattr(cg, "_release_generation_slot", lambda db, novel_id, status: None)
    monkeypatch.setattr(cg, "_ensure_generation_runtime_budget", lambda **kwargs: None)
    monkeypatch.setattr(cg, "_commit_runtime_snapshot", lambda db, novel, **kwargs: novel)
    monkeypatch.setattr(cg, "_auto_prepare_future_planning", lambda db, novel, **kwargs: {})
    monkeypatch.setattr(cg, "ensure_story_architecture", lambda story_bible, novel: story_bible or {})
    monkeypatch.setattr(cg, "refresh_planning_views", lambda story_bible, current_chapter_no: story_bible)
    monkeypatch.setattr(cg, "_ensure_outline_state", lambda story_bible: None)
    monkeypatch.setattr(cg, "_validate_required_planning_docs", lambda story_bible, chapter_no: None)
    monkeypatch.setattr(cg, "_validate_fact_ledger_state", lambda story_bible, chapter_no: None)
    monkeypatch.setattr(cg, "_promote_pending_arc_if_needed", lambda story_bible, next_chapter_no: None)

    plan = {
        "chapter_no": 1,
        "title": "破庙火痕",
        "goal": "确认破庙里的异常来源。",
        "opening_beat": "主角沿着火痕继续往内探。",
        "supporting_character_focus": "沈七",
        "event_type": "发现类",
        "progress_kind": "信息推进",
        "proactive_move": "主动试探破庙中的痕迹",
        "payoff_or_pressure": "确认了新的线索",
        "hook_kind": "新发现",
    }
    monkeypatch.setattr(cg, "_ensure_plan_for_chapter", lambda db, novel, next_no, recent_summaries: dict(plan))
    monkeypatch.setattr(cg, "_enrich_plan_agency", lambda novel, current_plan, **kwargs: current_plan)
    monkeypatch.setattr(cg, "collect_active_interventions", lambda db, novel_id, next_chapter_no: [])
    monkeypatch.setattr(cg, "_serialize_active_interventions", lambda active: [])
    monkeypatch.setattr(cg, "_serialize_last_chapter", lambda last_chapter, protagonist_name=None: {})
    monkeypatch.setattr(cg, "_save_pipeline_execution_packet", lambda **kwargs: {"scene_outline": ["破庙外观察", "入庙试探"]})
    monkeypatch.setattr(cg, "_serialize_novel_context", lambda novel, next_no, recent_summaries: {"story_memory": {}})
    monkeypatch.setattr(
        cg,
        "_fit_chapter_payload_budget",
        lambda **kwargs: (kwargs["novel_context"], kwargs["recent_summaries"], kwargs["serialized_last"], kwargs["serialized_active"], {"prompt_chars": 128}),
    )
    monkeypatch.setattr(
        cg,
        "_attempt_generate_validated_chapter",
        lambda **kwargs: (
            "破庙火痕",
            "林玄贴着断墙慢慢往里走。\n\n庙内灰烬里有一线尚未散尽的热意。",
            {"title": "破庙火痕"},
            dict(plan),
            {"target_visible_chars_min": 900, "target_visible_chars_max": 1600},
            {"quality_rejections": []},
        ),
    )
    monkeypatch.setattr(
        cg,
        "summarize_chapter",
        lambda title, content, request_timeout_seconds=None: SimpleNamespace(
            event_summary="主角确认破庙灰烬并非寻常残火。",
            character_updates={"沈七": {"态度": "警惕"}},
            new_clues=["灰烬中残留异热"],
            open_hooks=["是谁先到过破庙"],
            closed_hooks=[],
        ),
    )
    monkeypatch.setattr(
        cg,
        "validate_and_register_chapter",
        lambda *args, **kwargs: (
            kwargs.get("story_bible") or {},
            {"realm": [], "life_status": [], "injury_status": [], "identity_exposure": [], "item_ownership": []},
            {"passed": True, "conflict_count": 0},
        ),
    )
    monkeypatch.setattr(cg, "update_story_architecture_after_chapter", lambda **kwargs: kwargs["story_bible"])
    monkeypatch.setattr(cg, "sync_character_registry", lambda db, novel, **kwargs: None)
    monkeypatch.setattr(
        cg,
        "_mark_generated_chapter_delivery",
        lambda db, novel, chapter: (
            novel,
            {
                "delivery_mode": "live_publish",
                "serial_stage": "published",
                "is_published": True,
                "locked_from_edit": True,
                "published_at": None,
            },
        ),
    )
    monkeypatch.setattr(cg, "_set_live_runtime", lambda story_bible, **kwargs: story_bible)

    chapter = cg.generate_next_chapter(db, novel)

    assert chapter.chapter_no == 1
    assert chapter.title == "破庙火痕"
    assert chapter.generation_meta["continuity_bridge"]["last_two_paragraphs"]
    assert chapter.generation_meta["continuity_bridge"]["last_scene_card"]

    db_chapter = db.query(Chapter).filter(Chapter.novel_id == novel.id, Chapter.chapter_no == 1).one()
    db_summary = db.query(ChapterSummary).filter(ChapterSummary.chapter_id == db_chapter.id).one()
    assert db_summary.event_summary == "主角确认破庙灰烬并非寻常残火。"
