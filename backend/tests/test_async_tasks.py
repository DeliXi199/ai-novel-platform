from __future__ import annotations

from app.api.routes import novel_chapters
from app.services import async_tasks as async_tasks_service

from .test_ui_and_novels import TestingSessionLocal, client, seed_data
import pytest


@pytest.fixture(autouse=True)
def override_async_task_session(monkeypatch):
    monkeypatch.setattr(async_tasks_service, "create_session", TestingSessionLocal)


def test_enqueue_next_chapter_task_runs_to_completion(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_generate(db, novel):
        from app.models.chapter import Chapter

        chapter = Chapter(
            novel_id=novel.id,
            chapter_no=novel.current_chapter_no + 1,
            title="新章已到",
            content="这里是新章节正文。",
            generation_meta={"quality_rejections": []},
        )
        db.add(chapter)
        novel.current_chapter_no = chapter.chapter_no
        db.add(novel)
        db.commit()
        db.refresh(chapter)
        return chapter

    monkeypatch.setattr(async_tasks_service, "generate_next_chapter", fake_generate)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")
    assert response.status_code == 202
    payload = response.json()
    assert payload["task_type"] == "generate_next_chapter"
    assert payload["status"] == "succeeded"
    assert payload["result_payload"]["chapter_no"] == 4

    task_status = client.get(f"/api/v1/novels/{novel_id}/tasks/{payload['id']}")
    assert task_status.status_code == 200
    assert task_status.json()["status"] == "succeeded"


def test_enqueue_next_chapter_reuses_active_task(monkeypatch) -> None:
    novel_id = seed_data()

    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: None)

    first = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")
    second = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["reused_existing"] is True
    assert second.json()["id"] == first.json()["id"]


def test_enqueue_batch_generation_task_runs_to_completion(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_generate(db, novel):
        from app.models.chapter import Chapter

        chapter = Chapter(
            novel_id=novel.id,
            chapter_no=novel.current_chapter_no + 1,
            title=f"第{novel.current_chapter_no + 1}章",
            content="批量章节正文。",
            generation_meta={"quality_rejections": []},
        )
        db.add(chapter)
        novel.current_chapter_no = chapter.chapter_no
        db.add(novel)
        db.commit()
        db.refresh(chapter)
        return chapter

    monkeypatch.setattr(async_tasks_service, "generate_next_chapter", fake_generate)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapters", json={"count": 2})
    assert response.status_code == 202
    payload = response.json()
    assert payload["task_type"] == "generate_next_chapters_batch"
    assert payload["status"] == "succeeded"
    assert payload["result_payload"]["generated_count"] == 2
    assert payload["result_payload"]["ended_at_chapter"] == 5
    assert [item["chapter_no"] for item in payload["result_payload"]["chapters"]] == [4, 5]


def test_batch_generation_reuses_existing_generation_task(monkeypatch) -> None:
    novel_id = seed_data()

    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: None)

    first = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapters", json={"count": 3})
    second = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["reused_existing"] is True
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["task_type"] == "generate_next_chapters_batch"


def test_workspace_and_task_list_include_active_tasks(monkeypatch) -> None:
    novel_id = seed_data()

    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: None)
    enqueue = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapters", json={"count": 2})
    assert enqueue.status_code == 202
    task_id = enqueue.json()["id"]

    workspace = client.get(f"/api/v1/novels/{novel_id}/workspace")
    assert workspace.status_code == 200
    active_tasks = workspace.json()["active_tasks"]
    assert len(active_tasks) == 1
    assert active_tasks[0]["id"] == task_id

    task_list = client.get(f"/api/v1/novels/{novel_id}/tasks?status=active")
    assert task_list.status_code == 200
    assert task_list.json()["total"] == 1
    assert task_list.json()["items"][0]["id"] == task_id


def test_enqueue_tts_task_runs_to_completion(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_generate(chapter, payload=None, *, force_regenerate=False):
        chapter.generation_meta = {
            **(chapter.generation_meta or {}),
            "tts": {"voice": (payload or {}).get("voice") or "zh-CN-YunxiNeural"},
        }
        return {
            "novel_id": chapter.novel_id,
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "enabled": True,
            "ready": True,
            "generating": False,
            "stale": False,
            "voice": (payload or {}).get("voice") or "zh-CN-YunxiNeural",
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz",
            "audio_url": "/app/media/tts/test.mp3",
            "subtitle_url": "/app/media/tts/test.vtt",
            "file_size_bytes": 1234,
            "subtitle_file_size_bytes": 456,
            "generated_at": None,
            "reason": None,
            "voice_options": [{"value": "zh-CN-YunxiNeural", "label": "云希（男声，沉稳）"}],
            "generated_variants": [],
        }

    monkeypatch.setattr(async_tasks_service, "generate_chapter_tts", fake_generate)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(
        f"/api/v1/novels/{novel_id}/chapters/2/tts/tasks",
        json={"voice": "zh-CN-YunxiNeural", "force_regenerate": True},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["task_type"] == "generate_chapter_tts"
    assert payload["status"] == "succeeded"
    assert payload["result_payload"]["audio_url"] == "/app/media/tts/test.mp3"


def test_tts_status_marks_generating_when_async_task_exists(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_status(chapter, payload=None):
        return {
            "novel_id": chapter.novel_id,
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "enabled": True,
            "ready": False,
            "generating": False,
            "stale": False,
            "voice": "zh-CN-YunxiNeural",
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz",
            "audio_url": None,
            "subtitle_url": None,
            "file_size_bytes": None,
            "subtitle_file_size_bytes": None,
            "generated_at": None,
            "reason": "还没有生成本章朗读音频。",
            "voice_options": [{"value": "zh-CN-YunxiNeural", "label": "云希（男声，沉稳）"}],
            "generated_variants": [],
        }

    monkeypatch.setattr(novel_chapters, "get_chapter_tts_status", fake_status)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: None)
    enqueue = client.post(
        f"/api/v1/novels/{novel_id}/chapters/2/tts/tasks",
        json={"voice": "zh-CN-YunxiNeural", "force_regenerate": True},
    )
    assert enqueue.status_code == 202

    status = client.get(f"/api/v1/novels/{novel_id}/chapters/2/tts?voice=zh-CN-YunxiNeural")
    assert status.status_code == 200
    payload = status.json()
    assert payload["generating"] is True


def test_cancel_queued_task(monkeypatch) -> None:
    novel_id = seed_data()

    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: None)
    enqueue = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapters", json={"count": 3})
    assert enqueue.status_code == 202
    task_id = enqueue.json()["id"]

    cancelled = client.post(f"/api/v1/novels/{novel_id}/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    payload = cancelled.json()
    assert payload["status"] == "cancelled"
    assert payload["can_retry"] is True


def test_retry_failed_task_creates_new_task(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_fail(db, novel):
        raise RuntimeError("boom")

    def fake_success(db, novel):
        from app.models.chapter import Chapter

        chapter = Chapter(
            novel_id=novel.id,
            chapter_no=novel.current_chapter_no + 1,
            title="重试成功章",
            content="补写成功。",
            generation_meta={"quality_rejections": []},
        )
        db.add(chapter)
        novel.current_chapter_no = chapter.chapter_no
        db.add(novel)
        db.commit()
        db.refresh(chapter)
        return chapter

    monkeypatch.setattr(async_tasks_service, "generate_next_chapter", fake_fail)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    failed = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")
    assert failed.status_code == 202
    failed_payload = failed.json()
    assert failed_payload["status"] == "failed"

    monkeypatch.setattr(async_tasks_service, "generate_next_chapter", fake_success)
    retried = client.post(f"/api/v1/novels/{novel_id}/tasks/{failed_payload['id']}/retry")
    assert retried.status_code == 202
    retried_payload = retried.json()
    assert retried_payload["status"] == "succeeded"
    assert retried_payload["retry_of_task_id"] == failed_payload["id"]
    assert retried_payload["result_payload"]["chapter_no"] == 4


def test_cleanup_terminal_tasks_removes_old_history() -> None:
    novel_id = seed_data()
    db = TestingSessionLocal()
    try:
        old_a = async_tasks_service.AsyncTask(
            novel_id=novel_id,
            chapter_no=None,
            task_type=async_tasks_service.TASK_TYPE_NEXT_CHAPTER,
            owner_key=f"novel:{novel_id}:history:a",
            status="succeeded",
            progress_message="old-a",
            created_at=async_tasks_service._utcnow() - async_tasks_service.timedelta(days=30),
            updated_at=async_tasks_service._utcnow() - async_tasks_service.timedelta(days=30),
            finished_at=async_tasks_service._utcnow() - async_tasks_service.timedelta(days=30),
        )
        old_b = async_tasks_service.AsyncTask(
            novel_id=novel_id,
            chapter_no=None,
            task_type=async_tasks_service.TASK_TYPE_NEXT_CHAPTER,
            owner_key=f"novel:{novel_id}:history:b",
            status="failed",
            progress_message="old-b",
            created_at=async_tasks_service._utcnow() - async_tasks_service.timedelta(days=20),
            updated_at=async_tasks_service._utcnow() - async_tasks_service.timedelta(days=20),
            finished_at=async_tasks_service._utcnow() - async_tasks_service.timedelta(days=20),
        )
        recent = async_tasks_service.AsyncTask(
            novel_id=novel_id,
            chapter_no=None,
            task_type=async_tasks_service.TASK_TYPE_NEXT_CHAPTER,
            owner_key=f"novel:{novel_id}:history:c",
            status="succeeded",
            progress_message="recent",
            created_at=async_tasks_service._utcnow(),
            updated_at=async_tasks_service._utcnow(),
            finished_at=async_tasks_service._utcnow(),
        )
        db.add_all([old_a, old_b, recent])
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/v1/novels/{novel_id}/tasks/cleanup?keep_latest=1&older_than_days=14")
    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] >= 2

    remaining = client.get(f"/api/v1/novels/{novel_id}/tasks?limit=10").json()["items"]
    history_titles = {item["progress_message"] for item in remaining}
    assert "recent" in history_titles
    assert "old-a" not in history_titles
    assert "old-b" not in history_titles


def test_workspace_includes_recent_tasks(monkeypatch) -> None:
    novel_id = seed_data()
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: None)
    enqueue = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")
    assert enqueue.status_code == 202

    workspace = client.get(f"/api/v1/novels/{novel_id}/workspace")
    assert workspace.status_code == 200
    payload = workspace.json()
    assert len(payload["recent_tasks"]) >= 1
    assert payload["recent_tasks"][0]["id"] == enqueue.json()["id"]


def test_task_events_endpoint_returns_event_history(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_generate(db, novel):
        from app.models.chapter import Chapter

        chapter = Chapter(
            novel_id=novel.id,
            chapter_no=novel.current_chapter_no + 1,
            title="日志章",
            content="用于测试任务日志。",
            generation_meta={"quality_rejections": []},
        )
        db.add(chapter)
        novel.current_chapter_no = chapter.chapter_no
        db.add(novel)
        db.commit()
        db.refresh(chapter)
        return chapter

    monkeypatch.setattr(async_tasks_service, "generate_next_chapter", fake_generate)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")
    assert response.status_code == 202
    task_id = response.json()["id"]

    events = client.get(f"/api/v1/novels/{novel_id}/tasks/{task_id}/events?limit=20")
    assert events.status_code == 200
    payload = events.json()
    assert payload["task_id"] == task_id
    event_types = {item["event_type"] for item in payload["items"]}
    assert "queued" in event_types
    assert "running" in event_types
    assert "succeeded" in event_types




def test_next_chapter_task_events_capture_planning_refresh_progress(monkeypatch) -> None:
    novel_id = seed_data()

    def fake_generate(db, novel, *, progress_callback=None):
        from app.models.chapter import Chapter

        if progress_callback:
            progress_callback({
                "stage": "planning_refresh_check",
                "stage_label": "近5章规划检查",
                "message": "正在检查近5章规划：当前已规划到第8章，队列有3张章节卡。",
                "queue_size": 3,
                "planned_until": 8,
                "target_chapter_no": novel.current_chapter_no + 1,
            })
            progress_callback({
                "stage": "planning_refresh_running",
                "stage_label": "近5章规划刷新",
                "message": "正在刷新近5章规划：准备补到第9-13章。",
                "start_chapter": 9,
                "end_chapter": 13,
                "target_chapter_no": novel.current_chapter_no + 1,
            })
            progress_callback({
                "stage": "planning_refresh_completed",
                "stage_label": "近5章规划已更新",
                "message": "近5章规划已更新：新增第9-13章，当前可用章节卡覆盖到第13章。",
                "chapter_titles": ["旧账翻涌", "暗河试探", "门前问价", "借火", "落签"],
                "target_chapter_no": novel.current_chapter_no + 1,
            })

        chapter = Chapter(
            novel_id=novel.id,
            chapter_no=novel.current_chapter_no + 1,
            title="补规划日志章",
            content="这里是新章节正文。",
            generation_meta={"quality_rejections": []},
        )
        db.add(chapter)
        novel.current_chapter_no = chapter.chapter_no
        db.add(novel)
        db.commit()
        db.refresh(chapter)
        return chapter

    monkeypatch.setattr(async_tasks_service, "generate_next_chapter", fake_generate)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(f"/api/v1/novels/{novel_id}/tasks/next-chapter")
    assert response.status_code == 202
    payload = response.json()
    task_id = payload["id"]

    events = client.get(f"/api/v1/novels/{novel_id}/tasks/{task_id}/events?limit=20")
    assert events.status_code == 200
    items = events.json()["items"]
    assert any(item["payload"].get("stage") == "planning_refresh_check" for item in items)
    assert any(item["payload"].get("stage_label") == "近5章规划刷新" for item in items)
    assert any("近5章规划已更新" in (item.get("message") or "") for item in items)

def test_recover_orphaned_tasks_marks_active_tasks_failed() -> None:
    novel_id = seed_data()
    db = TestingSessionLocal()
    try:
        task = async_tasks_service.AsyncTask(
            novel_id=novel_id,
            chapter_no=None,
            task_type=async_tasks_service.TASK_TYPE_NEXT_CHAPTER,
            owner_key=f"novel:{novel_id}:stale",
            status="running",
            progress_message="还在执行中",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        result = async_tasks_service.recover_orphaned_tasks_on_startup(db)
        assert result["recovered_count"] >= 1

        recovered = async_tasks_service.get_task(db, novel_id=novel_id, task_id=task.id)
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.error_payload["code"] == async_tasks_service.TASK_ORPHANED_CODE

        events = async_tasks_service.list_task_events(db, novel_id=novel_id, task_id=task.id, limit=10)
        assert any(item.event_type == "recovered_orphaned" for item in events)
    finally:
        db.close()


def test_enqueue_bootstrap_task_runs_to_completion(monkeypatch) -> None:
    seed_data()

    def fake_run_bootstrap_pipeline(db, *, novel, payload, progress_callback=None):
        if progress_callback:
            progress_callback({
                "stage": "global_outline_generation",
                "stage_label": "全书总纲",
                "stage_description": "生成全书总纲",
                "message": "正在生成全书总纲。",
                "step_index": 3,
                "step_total": 6,
                "percent": 50,
            })
        novel.title = "任务化创建成功"
        novel.status = "planning_ready"
        novel.story_bible = {
            "workflow_state": {
                "bootstrap_state": {
                    "phase": "bootstrap",
                    "status": "completed",
                    "stage": "completed",
                    "message": "初始化完成，可以开始生成章节。",
                },
                "bootstrap_completed": True,
            }
        }
        db.add(novel)
        db.commit()
        db.refresh(novel)
        return novel

    monkeypatch.setattr(async_tasks_service, "run_bootstrap_pipeline", fake_run_bootstrap_pipeline)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(
        "/api/v1/novels/tasks/bootstrap",
        json={
            "genre": "修仙",
            "premise": "主角意外得到异宝，开始卷入宗门风波。",
            "protagonist_name": "许青",
            "style_preferences": {"tone": "冷峻克制"},
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["task_type"] == "bootstrap_novel"
    assert payload["status"] == "succeeded"
    assert payload["result_payload"]["title"] == "任务化创建成功"
    assert payload["progress_payload"]["stage"] == "global_outline_generation"
    assert payload["progress_payload"]["stage_label"] == "全书总纲"

    novel_id = payload["novel_id"]
    workspace = client.get(f"/api/v1/novels/{novel_id}/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["novel"]["title"] == "任务化创建成功"

    task_status = client.get(f"/api/v1/novels/{novel_id}/tasks/{payload['id']}")
    assert task_status.status_code == 200
    assert task_status.json()["task_type"] == "bootstrap_novel"


def test_bootstrap_task_events_capture_stage_progress(monkeypatch) -> None:
    seed_data()

    def fake_run_bootstrap_pipeline(db, *, novel, payload, progress_callback=None):
        if progress_callback:
            progress_callback({
                "stage": "story_engine_strategy_generation",
                "stage_label": "题材推进引擎",
                "stage_description": "分析题材结构",
                "message": "正在分析题材类型并生成前30章推进引擎。",
                "step_index": 2,
                "step_total": 6,
                "percent": 33,
            })
            progress_callback({
                "stage": "story_bible_finalize",
                "stage_label": "Story Bible 收口",
                "stage_description": "整理 Story Bible",
                "message": "正在整理 Story Bible、模板与长期状态。",
                "step_index": 6,
                "step_total": 6,
                "percent": 100,
            })
        novel.title = "阶段日志测试"
        novel.status = "planning_ready"
        novel.story_bible = {
            "workflow_state": {
                "bootstrap_state": {
                    "phase": "bootstrap",
                    "status": "completed",
                    "stage": "completed",
                    "message": "初始化完成，可以开始生成章节。",
                },
                "bootstrap_completed": True,
            }
        }
        db.add(novel)
        db.commit()
        db.refresh(novel)
        return novel

    monkeypatch.setattr(async_tasks_service, "run_bootstrap_pipeline", fake_run_bootstrap_pipeline)
    monkeypatch.setattr(async_tasks_service, "_submit_background_task", lambda task_id, runner: runner(task_id))

    response = client.post(
        "/api/v1/novels/tasks/bootstrap",
        json={
            "genre": "修仙",
            "premise": "主角意外得到异宝，开始卷入宗门风波。",
            "protagonist_name": "许青",
            "style_preferences": {"tone": "冷峻克制"},
        },
    )
    assert response.status_code == 202
    payload = response.json()
    novel_id = payload["novel_id"]
    task_id = payload["id"]

    events = client.get(f"/api/v1/novels/{novel_id}/tasks/{task_id}/events?limit=20")
    assert events.status_code == 200
    items = events.json()["items"]
    assert any(item["payload"].get("stage") == "story_engine_strategy_generation" for item in items)
    assert any(item["payload"].get("stage_label") == "Story Bible 收口" for item in items)
