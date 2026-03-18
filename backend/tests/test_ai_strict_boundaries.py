from __future__ import annotations

import pytest

from app.schemas.novel import NovelCreate
from app.services.constraint_reasoning import run_local_constraint_reasoning
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.story_blueprint_builders import build_project_card
from app.services import chapter_title_service as title_service


def _sample_payload() -> NovelCreate:
    return NovelCreate(
        genre="修仙",
        premise="主角在边城账房里摸索求生，同时被旧案卷入更大的局势。",
        protagonist_name="陆沉",
        style_preferences={},
    )


def test_build_project_card_requires_creation_ai_outputs() -> None:
    with pytest.raises(GenerationError) as exc_info:
        build_project_card(
            _sample_payload(),
            "旧账风波",
            {"acts": []},
            story_engine_diagnosis=None,
            story_strategy_card={"story_promise": "先站稳脚跟"},
        )

    assert exc_info.value.code == ErrorCodes.AI_REQUIRED_UNAVAILABLE
    assert exc_info.value.stage == "project_card_build"
    assert exc_info.value.details == {"missing_payload": "story_engine_diagnosis"}


def test_title_refinement_from_candidates_raises_without_ai_candidates() -> None:
    with pytest.raises(GenerationError) as exc_info:
        title_service.refine_generated_chapter_title_from_candidates(
            chapter_no=8,
            original_title="旧纸页",
            plan={"goal": "拿到账本", "conflict": "有人盯梢"},
            recent_titles=["旧纸页", "坊市试探"],
            summary={"event_summary": "主角确认旧案未了。"},
            raw_candidates=[],
            ai_attempted=True,
            ai_succeeded=False,
            ai_error={"message": "title refinement timeout", "retryable": True, "http_status": 504},
        )

    assert exc_info.value.code == ErrorCodes.AI_REQUIRED_UNAVAILABLE
    assert exc_info.value.http_status == 504
    assert "title refinement timeout" in exc_info.value.message


def test_constraint_reasoning_disallows_local_only_return() -> None:
    with pytest.raises(GenerationError) as exc_info:
        run_local_constraint_reasoning(
            story_bible={},
            task_type="resource_capability_plan",
            scope="chapter_planning",
            chapter_no=3,
            allow_ai=False,
            local_context={"selected_resources": ["青锋剑"]},
            hard_constraints=["不能凭空新增资源"],
            soft_goals=["让资源服务本章目标"],
            output_contract={"type": "dict"},
            baseline_builder=lambda _: {"青锋剑": {"should_use": True}},
        )

    assert exc_info.value.code == ErrorCodes.AI_REQUIRED_UNAVAILABLE
    assert exc_info.value.stage == "local_constraint_reasoning"
    assert "不再返回本地替代结果" in exc_info.value.message
