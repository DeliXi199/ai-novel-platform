from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.chapter_repair_pipeline import classify_chapter_repair
from app.services.chapter_retry_support import _attempt_generate_validated_chapter
from app.services.generation_exceptions import ErrorCodes, GenerationError


class _FakeDraft:
    def __init__(self, title: str, content: str):
        self.title = title
        self.content = content

    def model_dump(self, mode: str = "python"):
        return {"title": self.title, "content": self.content}


def _base_plan() -> dict:
    return {
        "chapter_no": 11,
        "title": "任务指派",
        "chapter_type": "progress",
        "event_type": "外部任务类",
        "progress_kind": "地点推进",
        "goal": "接下巡查任务并摸清山路情况",
        "conflict": "路线分叉，队伍必须拆分行动",
        "ending_hook": "主角在分组前注意到异常痕迹",
        "hook_style": "危险逼近",
        "hook_kind": "新威胁",
        "payoff_or_pressure": "任务拆分后风险抬高",
    }


def _base_targets() -> dict:
    return {
        "target_visible_chars_min": 1400,
        "target_visible_chars_max": 2200,
    }


def test_classify_chapter_repair_routes_incomplete_ending_to_append_inline_tail_first() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_ENDING_INCOMPLETE,
        message="结尾不完整",
        stage="chapter_quality",
        details={"ending_issue": "unclosed_quote"},
    )

    action = classify_chapter_repair(exc, attempt_plan=_base_plan(), targets=_base_targets())

    assert action is not None
    assert action.repair_type == "ending_incomplete"
    assert action.strategy_id == "ai_append_inline_tail"
    assert action.execution_mode == "append_inline_tail"


def test_classify_chapter_repair_escalates_to_rewrite_last_paragraph_after_failed_tail_fix() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_ENDING_INCOMPLETE,
        message="结尾不完整",
        stage="chapter_quality",
        details={"ending_issue": "missing_terminal_punctuation"},
    )

    action = classify_chapter_repair(
        exc,
        attempt_plan=_base_plan(),
        targets=_base_targets(),
        repair_trace=[
            {
                "attempt_no": 1,
                "repair_type": "ending_incomplete",
                "strategy_id": "ai_append_inline_tail",
                "status": "rejected",
            }
        ],
        attempt_no=1,
    )

    assert action is not None
    assert action.strategy_id == "ai_rewrite_last_paragraph"
    assert action.execution_mode == "replace_last_paragraph"


def test_classify_chapter_repair_routes_weak_ending_to_stronger_regeneration() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
        message="结尾钩子偏弱",
        stage="chapter_quality",
        details={"ending_pattern": "summary_wrap"},
    )

    action = classify_chapter_repair(exc, attempt_plan=_base_plan(), targets=_base_targets())

    assert action is not None
    assert action.repair_type == "weak_ending"
    assert action.strategy_id == "regenerate_stronger_ending"
    assert action.execution_mode == "insert_retry_attempt"
    assert action.retry_plan is not None
    assert action.retry_plan["ending_retry"]["reason"] == "weak_ending"


def test_attempt_generate_validated_chapter_applies_tail_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.chapter_retry_support as crs

    monkeypatch.setattr(crs, "_should_stop_retrying_for_budget", lambda **kwargs: False)
    monkeypatch.setattr(crs, "_ensure_generation_runtime_budget", lambda **kwargs: None)
    monkeypatch.setattr(crs, "_compute_llm_timeout_seconds", lambda **kwargs: 30)

    draft = _FakeDraft("任务指派", "李墨停在岔路口，回头说：\"分两组。")
    monkeypatch.setattr(crs, "generate_chapter_from_plan", lambda **kwargs: draft)

    state = {"seen": 0}

    def fake_validate(**kwargs):
        content = kwargs["content"]
        if state["seen"] == 0:
            state["seen"] += 1
            raise GenerationError(
                code=ErrorCodes.CHAPTER_ENDING_INCOMPLETE,
                message="模型返回的正文疑似被截断。",
                stage="chapter_quality",
                details={"ending_issue": "unclosed_quote", "tail": content[-20:]},
            )
        assert content.endswith("汇合。\"")

    monkeypatch.setattr(crs, "_validate_candidate_content", fake_validate)
    monkeypatch.setattr(
        crs,
        "execute_llm_repair",
        lambda action, **kwargs: SimpleNamespace(
            content='李墨停在岔路口，回头说："分两组。一个时辰后，回这里汇合。"',
            strategy_id=action.strategy_id,
            repair_type=action.repair_type,
        ),
    )

    title, content, payload, used_plan, targets, attempt_meta = _attempt_generate_validated_chapter(
        novel_context={},
        plan=_base_plan(),
        serialized_last={},
        recent_summaries=[],
        serialized_active=[],
        recent_full_texts=[],
        chapter_no=11,
        started_at=0.0,
    )

    assert title == "任务指派"
    assert content.endswith("汇合。\"")
    assert payload["ending_repair_mode"] == "ai_append_inline_tail"
    assert attempt_meta["repair_trace"][0]["strategy_id"] == "ai_append_inline_tail"
    assert attempt_meta["repair_trace"][0]["status"] == "applied"
    assert used_plan["title"] == "任务指派"
    assert targets["target_visible_chars_min"] >= 1000


def test_attempt_generate_validated_chapter_inserts_weak_ending_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.chapter_retry_support as crs

    monkeypatch.setattr(crs, "_should_stop_retrying_for_budget", lambda **kwargs: False)
    monkeypatch.setattr(crs, "_ensure_generation_runtime_budget", lambda **kwargs: None)
    monkeypatch.setattr(crs, "_compute_llm_timeout_seconds", lambda **kwargs: 30)

    drafts = iter(
        [
            _FakeDraft("任务指派", "队伍接下任务后暂且散去，众人各自回屋休息。"),
            _FakeDraft("任务指派", "队伍接下任务后，李墨当场改了分组，让方尘先探右路。山风里忽然传来细碎脚步声。"),
        ]
    )
    monkeypatch.setattr(crs, "generate_chapter_from_plan", lambda **kwargs: next(drafts))

    state = {"seen": 0}

    def fake_validate(**kwargs):
        content = kwargs["content"]
        if state["seen"] == 0:
            state["seen"] += 1
            raise GenerationError(
                code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
                message="本章结尾钩子偏弱。",
                stage="chapter_quality",
                details={"ending_pattern": "summary_wrap", "title": kwargs["title"]},
            )
        assert "脚步声" in content

    monkeypatch.setattr(crs, "_validate_candidate_content", fake_validate)

    title, content, payload, used_plan, targets, attempt_meta = _attempt_generate_validated_chapter(
        novel_context={},
        plan=_base_plan(),
        serialized_last={},
        recent_summaries=[],
        serialized_active=[],
        recent_full_texts=[],
        chapter_no=11,
        started_at=0.0,
    )

    assert title == "任务指派"
    assert "脚步声" in content
    assert payload.get("ending_repair_mode") is None
    assert attempt_meta["total_llm_attempts"] == 2
    assert attempt_meta["repair_trace"][0]["repair_type"] == "weak_ending"
    assert attempt_meta["repair_trace"][0]["strategy_id"] == "regenerate_stronger_ending"
    assert attempt_meta["repair_trace"][0]["status"] == "inserted_retry"
    assert used_plan["ending_retry"]["reason"] == "weak_ending"
