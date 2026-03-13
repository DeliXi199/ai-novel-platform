from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.chapter import Chapter
from app.models.intervention import Intervention
from app.models.novel import Novel


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)



def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)



def seed_data() -> int:
    db = TestingSessionLocal()
    db.query(Intervention).delete()
    db.query(Chapter).delete()
    db.query(Novel).delete()
    novel = Novel(
        title="测试小说",
        genre="修仙",
        premise="主角从药铺后院捡到异物，卷入风波。",
        protagonist_name="林玄",
        style_preferences={"tone": "冷峻克制"},
        story_bible={
            "story_bible_meta": {"schema_version": 1},
            "serial_runtime": {"delivery_mode": "stockpile"},
        },
        current_chapter_no=3,
        status="planning_ready",
    )
    db.add(novel)
    db.flush()
    db.add_all(
        [
            Chapter(
                novel_id=novel.id,
                chapter_no=1,
                title="旧纸页",
                content="第一章正文内容，包含一些调查与铺垫。",
                generation_meta={},
                serial_stage="published",
                is_published=True,
                locked_from_edit=True,
            ),
            Chapter(
                novel_id=novel.id,
                chapter_no=2,
                title="河滩碎骨",
                content="第二章正文内容，包含一段河滩调查与隐患升级。",
                generation_meta={},
                serial_stage="stock",
                is_published=False,
                locked_from_edit=False,
            ),
            Chapter(
                novel_id=novel.id,
                chapter_no=3,
                title="夜雨来客",
                content="第三章正文内容，包含雨夜敲门与突发威胁。",
                generation_meta={},
                serial_stage="stock",
                is_published=False,
                locked_from_edit=False,
            ),
            Intervention(
                novel_id=novel.id,
                chapter_no=4,
                raw_instruction="最近三章不要急着爆发，先加重不安感。",
                parsed_constraints={"tone": "压抑"},
                effective_chapter_span=3,
                applied=False,
            ),
        ]
    )
    db.commit()
    novel_id = novel.id
    db.close()
    return novel_id


@pytest.fixture(autouse=True)
def reset_db():
    seed_data()


@pytest.fixture()
def novel_id() -> int:
    return client.get("/api/v1/novels").json()["items"][0]["id"]



def test_ui_route_serves_index() -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert "AI Novel Studio" in response.text
    assert "/app/assets/app.js" in response.text



def test_reader_route_serves_index() -> None:
    response = client.get("/app/reader?novelId=1&chapterNo=1")
    assert response.status_code == 200
    assert "沉浸阅读模式" in response.text


def test_index_contains_catalog_templates() -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert 'id="bookshelfItemTemplate"' in response.text
    assert 'id="chapterCardTemplate"' in response.text



def test_get_chapter_detail_returns_content(novel_id: int) -> None:
    response = client.get(f"/api/v1/novels/{novel_id}/chapters/2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["chapter_no"] == 2
    assert payload["content"]
    assert payload["title"] == "河滩碎骨"
    assert payload["serial_stage"] == "stock"
    assert payload["is_published"] is False



def test_list_novels_returns_bookshelf_items() -> None:
    response = client.get("/api/v1/novels")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "测试小说"
    assert "story_bible" not in payload["items"][0]



def test_list_chapters_and_interventions(novel_id: int) -> None:
    chapter_response = client.get(f"/api/v1/novels/{novel_id}/chapters")
    assert chapter_response.status_code == 200
    chapters = chapter_response.json()
    assert chapters["total"] == 3
    assert chapters["items"][0]["chapter_no"] == 1
    assert chapters["items"][0]["content_preview"]
    assert chapters["items"][0]["char_count"] > 0
    assert chapters["items"][0]["is_published"] is True
    assert chapters["items"][1]["serial_stage"] == "stock"

    intervention_response = client.get(f"/api/v1/novels/{novel_id}/interventions")
    assert intervention_response.status_code == 200
    interventions = intervention_response.json()
    assert interventions["total"] == 1
    assert "不要急着爆发" in interventions["items"][0]["raw_instruction"]



def test_delete_tail_chapters_only_allows_unpublished_tail(novel_id: int) -> None:
    response = client.post(
        f"/api/v1/novels/{novel_id}/chapters/delete-tail",
        json={"from_chapter_no": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] == 2
    assert payload["deleted_chapter_nos"] == [2, 3]
    assert payload["current_chapter_no"] == 1

    chapters = client.get(f"/api/v1/novels/{novel_id}/chapters").json()
    assert chapters["total"] == 1
    assert chapters["items"][0]["chapter_no"] == 1



def test_delete_tail_chapters_rejects_published_content(novel_id: int) -> None:
    response = client.post(
        f"/api/v1/novels/{novel_id}/chapters/delete-tail",
        json={"chapter_nos": [1, 2, 3]},
    )
    assert response.status_code == 409
    assert "已发布章节不可删除" in response.json()["detail"]



def test_publish_stock_chapters_in_order(novel_id: int) -> None:
    response = client.post(
        f"/api/v1/novels/{novel_id}/chapters/publish-batch",
        json={"count": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["published_count"] == 2
    assert payload["published_chapter_nos"] == [2, 3]
    assert payload["published_through"] == 3

    serial_state = client.get(f"/api/v1/novels/{novel_id}/serial-state").json()
    release_state = serial_state["long_term_state"]["chapter_release_state"]
    assert release_state["published_through"] == 3
    assert release_state["stock_chapter_count"] == 0





def test_serial_state_includes_fact_ledger(novel_id: int) -> None:
    response = client.get(f"/api/v1/novels/{novel_id}/serial-state")
    assert response.status_code == 200
    payload = response.json()
    assert "fact_ledger" in payload
    assert "published_facts" in payload["fact_ledger"]
    assert payload["fact_ledger"]["published_facts"]
    assert "hard_fact_guard" in payload
    assert payload["hard_fact_guard"]["enabled"] is True



def test_fact_ledger_endpoint_and_publish_promotion(novel_id: int) -> None:
    before = client.get(f"/api/v1/novels/{novel_id}/facts").json()
    assert before["published_fact_count"] >= 1
    assert before["stock_fact_count"] >= 1

    publish = client.post(f"/api/v1/novels/{novel_id}/chapters/publish-batch", json={"count": 2})
    assert publish.status_code == 200

    after = client.get(f"/api/v1/novels/{novel_id}/facts").json()
    assert after["stock_fact_count"] == 0
    chapter_nos = [item["chapter_no"] for item in after["fact_ledger"]["published_facts"]]
    assert 2 in chapter_nos and 3 in chapter_nos



def test_hard_fact_endpoint_exposes_guard(novel_id: int) -> None:
    response = client.get(f"/api/v1/novels/{novel_id}/hard-facts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["hard_fact_guard"]["enabled"] is True
    assert "published_state" in payload["hard_fact_guard"]


def test_control_console_and_serial_state_expose_story_state(novel_id: int) -> None:
    console_payload = client.get(f"/api/v1/novels/{novel_id}/control-console").json()
    assert "story_state" in console_payload
    assert "planning_window" in console_payload["story_state"]

    serial_payload = client.get(f"/api/v1/novels/{novel_id}/serial-state").json()
    assert "story_state" in serial_payload
    assert serial_payload["story_state"]["planning_window"]["planned_until"] >= 0


def test_publish_stock_chapters_rejects_hard_fact_conflict(novel_id: int) -> None:
    db = TestingSessionLocal()
    try:
        chapter1 = db.query(Chapter).filter(Chapter.novel_id == novel_id, Chapter.chapter_no == 1).first()
        chapter2 = db.query(Chapter).filter(Chapter.novel_id == novel_id, Chapter.chapter_no == 2).first()
        assert chapter1 is not None and chapter2 is not None
        chapter1.content = "林玄压下躁动的灵气，终于在黎明前真正踏入筑基境。"
        chapter2.content = "林玄仍只是炼气三层，连院门外的风都不敢硬接。"
        db.add(chapter1)
        db.add(chapter2)
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/v1/novels/{novel_id}/chapters/publish-batch", json={"count": 1})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "CHAPTER_HARD_FACT_CONFLICT"
    assert "境界" in str(detail["details"])

def test_update_serial_mode(novel_id: int) -> None:
    response = client.post(
        f"/api/v1/novels/{novel_id}/serial-mode",
        json={"delivery_mode": "live_publish"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_mode"] == "live_publish"
    assert payload["serial_runtime"]["delivery_mode"] == "live_publish"



def test_delete_tail_chapters_rejects_non_tail_request(novel_id: int) -> None:
    response = client.post(
        f"/api/v1/novels/{novel_id}/chapters/delete-tail",
        json={"chapter_nos": [1, 2]},
    )
    assert response.status_code == 400
    assert "连续" in response.json()["detail"]



def test_delete_novel(novel_id: int) -> None:
    response = client.delete(f"/api/v1/novels/{novel_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_novel_id"] == novel_id
    assert payload["deleted_chapter_count"] == 3

    shelf = client.get("/api/v1/novels").json()
    assert shelf["total"] == 0



def test_serial_state_exposes_strong_continuity_runtime(novel_id: int) -> None:
    response = client.get(f"/api/v1/novels/{novel_id}/serial-state")
    assert response.status_code == 200
    payload = response.json()
    runtime = payload["serial_runtime"]
    assert runtime["continuity_mode"] == "strong_bridge"
    assert "previous_chapter_bridge" in runtime


def test_create_novel_persists_failed_bootstrap_record(monkeypatch) -> None:
    from app.services.generation_exceptions import GenerationError

    def _boom(*_args, **_kwargs):
        raise GenerationError(
            code="API_TIMEOUT",
            message="bootstrap failed",
            stage="global_outline_generation",
            retryable=True,
            http_status=503,
            provider="deepseek",
        )

    monkeypatch.setattr("app.services.novel_lifecycle.generate_global_story_outline", _boom)

    response = client.post(
        "/api/v1/novels",
        json={
            "genre": "修仙",
            "premise": "主角被迫卷入旧案。",
            "protagonist_name": "周野",
            "style_preferences": {"tone": "冷峻"},
        },
    )
    assert response.status_code == 503
    payload = response.json()["detail"]
    assert payload["novel"]["status"] == "bootstrap_failed"
    assert payload["novel"]["bootstrap_state"]["stage"] == "global_outline_generation"

    shelf = client.get("/api/v1/novels?q=周野").json()
    assert shelf["total"] == 1
    assert shelf["items"][0]["status"] == "bootstrap_failed"


def test_retry_bootstrap_endpoint_recovers_failed_novel(monkeypatch) -> None:
    from app.services.generation_exceptions import GenerationError

    def _fail_once(*_args, **_kwargs):
        raise GenerationError(
            code="API_TIMEOUT",
            message="bootstrap failed",
            stage="global_outline_generation",
            retryable=True,
            http_status=503,
            provider="deepseek",
        )

    monkeypatch.setattr("app.services.novel_lifecycle.generate_global_story_outline", _fail_once)
    create = client.post(
        "/api/v1/novels",
        json={
            "genre": "修仙",
            "premise": "主角被迫卷入旧案。",
            "protagonist_name": "沈墨",
            "style_preferences": {"tone": "冷峻"},
        },
    )
    assert create.status_code == 503
    novel_id = create.json()["detail"]["novel"]["id"]

    monkeypatch.setattr(
        "app.services.novel_lifecycle.generate_global_story_outline",
        lambda *_args, **_kwargs: {"acts": [{"act_no": 1, "summary": "开局卷入风波"}]},
    )
    monkeypatch.setattr(
        "app.services.novel_lifecycle.generate_arc_outline_bundle",
        lambda *_args, **_kwargs: {
            "arc_no": 1,
            "start_chapter": 1,
            "end_chapter": 7,
            "focus": "起势",
            "bridge_note": "承上启下",
            "chapters": [{"chapter_no": 1, "goal": "开局"}],
        },
    )

    response = client.post(f"/api/v1/novels/{novel_id}/bootstrap/retry")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planning_ready"
    assert payload["story_bible"]["workflow_state"]["bootstrap_state"]["status"] == "completed"


def test_serial_state_get_does_not_persist_story_bible(novel_id: int) -> None:
    db = TestingSessionLocal()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        assert novel is not None
        original_story_bible = dict(novel.story_bible or {})
    finally:
        db.close()

    response = client.get(f"/api/v1/novels/{novel_id}/serial-state")
    assert response.status_code == 200

    db = TestingSessionLocal()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        assert novel is not None
        assert novel.story_bible == original_story_bible
    finally:
        db.close()


def test_failed_generation_feedback_is_exposed_for_retry_prompt() -> None:
    from app.services.chapter_generation import _persist_generation_failure_snapshot, _serialize_novel_context

    db = TestingSessionLocal()
    try:
        db.query(Intervention).delete()
        db.query(Chapter).delete()
        db.query(Novel).delete()
        novel = Novel(
            title="测试书",
            genre="修仙",
            premise="主角卷入旧案。",
            protagonist_name="方尘",
            style_preferences={},
            story_bible={},
            status="planning_ready",
            current_chapter_no=0,
        )
        db.add(novel)
        db.commit()
        db.refresh(novel)

        _persist_generation_failure_snapshot(
            db,
            novel_id=novel.id,
            restore_status="planning_ready",
            next_chapter_no=1,
            stage="chapter_quality",
            message="本章主角主动性不足，仍然像被动应付，不适合直接入库。",
            details={"proactive_hits": 0, "passive_drift_hits": 3},
        )
        db.refresh(novel)
        context = _serialize_novel_context(novel, 1, [])
        runtime = ((context.get("story_memory") or {}).get("workflow_runtime") or {})
        assert runtime.get("retry_feedback", {}).get("problem") == "上一版草稿主角偏被动"
    finally:
        db.close()
