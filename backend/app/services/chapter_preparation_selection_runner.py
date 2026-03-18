from __future__ import annotations

from typing import Any

from app.services import openai_story_engine as engine
from app.services import openai_story_engine_selection as selection_engine
from app.services.chapter_preparation_selection_execution import (
    merge_parallel_preparation_selection,
    run_parallel_preparation_selectors,
    run_preparation_shortlist,
)


def run_chapter_preparation_selection(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> selection_engine.ChapterPreparationSelectionResult:
    has_schedule = bool((planning_packet or {}).get('character_relation_schedule'))
    has_cards = bool(selection_engine._card_index_entries(planning_packet))
    has_payoff = bool((((planning_packet or {}).get('payoff_candidate_index') or {}).get('candidates') or []))
    has_scene = bool((((planning_packet or {}).get('scene_template_index') or {}).get('scene_templates') or []))
    has_prompt = bool((planning_packet or {}).get('prompt_strategy_index'))
    if not any([has_schedule, has_cards, has_payoff, has_scene, has_prompt]):
        return selection_engine.ChapterPreparationSelectionResult()
    if not selection_engine.is_openai_enabled():
        selection_engine.raise_ai_required_error(
            stage='chapter_frontload_decision',
            message='章节准备阶段筛选需要可用的 AI，当前已停止生成',
            detail_reason='当前没有可用的 AI 配置或密钥。',
            retryable=False,
        )

    shortlist_payload, shortlist_trace = run_preparation_shortlist(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
    )
    shortlist = shortlist_payload.model_dump(mode='python')
    parallel_result = run_parallel_preparation_selectors(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
        shortlist=shortlist,
    )
    selector_outputs = parallel_result['results']
    merged_result, merge_trace = merge_parallel_preparation_selection(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        selector_outputs=selector_outputs,
        request_timeout_seconds=request_timeout_seconds,
        shortlist=shortlist,
    )
    merged_result.selection_trace = {
        'shortlist_stage': {
            **(shortlist_trace or {}),
            'result': shortlist,
        },
        'selection_scope': selection_engine._selection_scope(planning_packet, shortlist),
        **(parallel_result.get('trace') or {}),
        **(merge_trace or {}),
        'selector_outputs': {
            key: value.model_dump(mode='python') if hasattr(value, 'model_dump') else value
            for key, value in selector_outputs.items()
        },
    }
    if not merged_result.card_selection.selected_card_ids:
        raise engine.GenerationError(
            code=engine.ErrorCodes.MODEL_RESPONSE_INVALID,
            message='chapter_prepare_selection_merge 失败：AI 未返回有效的章节卡选择结果。',
            stage='chapter_prepare_selection_merge',
            retryable=True,
            http_status=422,
            provider=engine.provider_name(),
        )
    return merged_result


def review_character_relation_schedule_and_select_cards(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> tuple[selection_engine.CharacterRelationScheduleReviewPayload, selection_engine.ChapterCardSelectionPayload]:
    result = run_chapter_preparation_selection(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
    )
    return result.schedule_review, result.card_selection


__all__ = [
    'run_chapter_preparation_selection',
    'review_character_relation_schedule_and_select_cards',
]
