from __future__ import annotations

import pytest

from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services import chapter_title_service as title_service


def _sample_plan() -> dict:
    return {
        "chapter_no": 8,
        "goal": "主角拿到账本并确认有人提前做了手脚",
        "conflict": "账房先生装傻，门外还有人盯梢",
        "ending_hook": "门后那张欠条让主角意识到旧案没有结束",
        "main_scene": "账房后门与旧仓房之间的窄巷",
        "proactive_move": "主角主动设局逼问账房先生",
        "progress_kind": "信息推进",
        "event_type": "试探类",
    }


def test_title_similarity_flags_near_duplicates() -> None:
    score = title_service.title_similarity("坊市试探", "市集试探")
    assert score >= 0.45
    assert title_service.title_similarity("门后欠条", "夜半微光") < score



def test_refine_generated_chapter_title_prefers_less_repetitive_candidate(monkeypatch) -> None:
    def fake_ai(**_: object):
        return [
            {"title": "坊市试探", "title_type": "地点型", "angle": "重复示例", "reason": "故意给个烂的", "source": "ai"},
            {"title": "门后欠条", "title_type": "物件型", "angle": "落在关键新物件", "reason": "更贴本章结果", "source": "ai"},
            {"title": "账房松口", "title_type": "结果型", "angle": "落在具体后果", "reason": "也可以", "source": "ai"},
        ]

    monkeypatch.setattr(title_service, "generate_chapter_title_candidates", fake_ai)

    result = title_service.refine_generated_chapter_title(
        chapter_no=8,
        original_title="坊市试探",
        content="主角借着交账的机会潜入后门，最后在门缝后发现一张旧欠条。",
        plan=_sample_plan(),
        recent_titles=["旧纸页", "坊市试探", "暗流再起", "夜半微光"],
        summary={"event_summary": "主角逼问账房先生，并在后门发现旧欠条。", "new_clues": ["旧欠条"], "open_hooks": ["旧案还没结束"]},
        timeout_seconds=8,
    )

    assert result.ai_attempted is True
    assert result.ai_succeeded is True
    assert result.final_title in {"门后欠条", "账房松口"}
    assert result.final_title != "坊市试探"
    assert result.candidates[0].title == result.final_title



def test_refine_generated_chapter_title_raises_when_ai_errors(monkeypatch) -> None:
    def fake_ai(**_: object):
        raise GenerationError(
            code=ErrorCodes.API_TIMEOUT,
            message="title refinement timeout",
            stage="chapter_title_refinement",
            retryable=True,
            http_status=504,
        )

    monkeypatch.setattr(title_service, "generate_chapter_title_candidates", fake_ai)

    with pytest.raises(GenerationError) as exc_info:
        title_service.refine_generated_chapter_title(
            chapter_no=8,
            original_title="旧纸页",
            content="主角在后门摸到一张欠条，确认旧案未了。",
            plan=_sample_plan(),
            recent_titles=["旧纸页", "坊市试探", "暗流再起"],
            summary={"event_summary": "主角摸到账簿后的关键欠条。", "new_clues": ["欠条"], "open_hooks": ["旧案未了"]},
            timeout_seconds=8,
        )

    assert exc_info.value.code == ErrorCodes.API_TIMEOUT
