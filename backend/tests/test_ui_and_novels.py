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
        story_bible={"story_bible_meta": {"schema_version": 1}},
        current_chapter_no=3,
        status="planning_ready",
    )
    db.add(novel)
    db.flush()
    db.add_all(
        [
            Chapter(novel_id=novel.id, chapter_no=1, title="旧纸页", content="第一章正文内容，包含一些调查与铺垫。", generation_meta={}),
            Chapter(novel_id=novel.id, chapter_no=2, title="河滩碎骨", content="第二章正文内容，包含一段河滩调查与隐患升级。", generation_meta={}),
            Chapter(novel_id=novel.id, chapter_no=3, title="夜雨来客", content="第三章正文内容，包含雨夜敲门与突发威胁。", generation_meta={}),
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

    intervention_response = client.get(f"/api/v1/novels/{novel_id}/interventions")
    assert intervention_response.status_code == 200
    interventions = intervention_response.json()
    assert interventions["total"] == 1
    assert "不要急着爆发" in interventions["items"][0]["raw_instruction"]


def test_delete_tail_chapters_from_end(novel_id: int) -> None:
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
