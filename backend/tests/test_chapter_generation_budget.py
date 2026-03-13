import pytest

from app.services.chapter_generation import _compute_llm_timeout_seconds
from app.services.generation_exceptions import ErrorCodes, GenerationError


def test_compute_extension_timeout_allows_soft_floor_when_budget_below_hard_min(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chapter_generation._remaining_generation_budget_seconds", lambda *, started_at: 27)
    monkeypatch.setattr("app.services.chapter_generation.current_timeout", lambda stage=None: 120)
    monkeypatch.setattr("app.services.chapter_generation.settings.chapter_runtime_min_llm_timeout_seconds", 25)
    monkeypatch.setattr("app.services.chapter_generation.settings.chapter_extension_min_llm_timeout_seconds", 45)
    monkeypatch.setattr("app.services.chapter_generation.settings.chapter_extension_soft_min_timeout_seconds", 12)
    assert _compute_llm_timeout_seconds(
        started_at=0.0,
        chapter_no=2,
        stage="chapter_extension",
        reserve_seconds=0,
        attempt_no=2,
    ) == 27


def test_compute_extension_timeout_still_rejects_when_budget_too_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chapter_generation._remaining_generation_budget_seconds", lambda *, started_at: 9)
    monkeypatch.setattr("app.services.chapter_generation.current_timeout", lambda stage=None: 120)
    monkeypatch.setattr("app.services.chapter_generation.settings.chapter_runtime_min_llm_timeout_seconds", 25)
    monkeypatch.setattr("app.services.chapter_generation.settings.chapter_extension_min_llm_timeout_seconds", 45)
    monkeypatch.setattr("app.services.chapter_generation.settings.chapter_extension_soft_min_timeout_seconds", 12)
    with pytest.raises(GenerationError) as exc_info:
        _compute_llm_timeout_seconds(
            started_at=0.0,
            chapter_no=2,
            stage="chapter_extension",
            reserve_seconds=0,
            attempt_no=2,
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_PIPELINE_TIMEOUT


class _DummySession:
    def __init__(self) -> None:
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)


def test_auto_prepare_future_planning_prefetch_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.novel import Novel
    from app.services.chapter_generation import _auto_prepare_future_planning

    novel = Novel(
        id=1,
        title="测试书",
        genre="玄幻",
        premise="前提",
        protagonist_name="主角",
        story_bible={
            "active_arc": {"end_chapter": 2},
            "control_console": {"chapter_card_queue": []},
        },
        current_chapter_no=1,
    )
    db = _DummySession()

    monkeypatch.setattr("app.services.chapter_generation.ensure_story_architecture", lambda story_bible, novel_obj: story_bible)
    monkeypatch.setattr("app.services.chapter_generation.refresh_planning_views", lambda story_bible, current_no: story_bible)
    monkeypatch.setattr("app.services.chapter_generation.settings.arc_prefetch_threshold", 1)
    monkeypatch.setattr("app.services.chapter_generation.settings.planning_window_size", 3)

    def _fake_generate_and_store_pending_arc(db_session, novel_obj, recent_summaries, *, replace_existing=False):
        story_bible = dict(novel_obj.story_bible or {})
        story_bible["pending_arc"] = {"start_chapter": 3, "end_chapter": 7}
        novel_obj.story_bible = story_bible

    monkeypatch.setattr(
        "app.services.chapter_generation._generate_and_store_pending_arc",
        _fake_generate_and_store_pending_arc,
    )

    payload = _auto_prepare_future_planning(db, novel, current_chapter_no=1, recent_summaries=[])

    assert payload["auto_prefetched"] is True
    assert payload["arc_remaining"] == 1
    assert novel.story_bible["pending_arc"]["start_chapter"] == 3
    assert db.added[-1] is novel
