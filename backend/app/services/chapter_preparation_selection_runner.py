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
    has_foreshadowing = bool((((planning_packet or {}).get('foreshadowing_candidate_index') or {}).get('candidates') or []))
    has_prompt = bool((planning_packet or {}).get('prompt_strategy_index'))
    if not any([has_schedule, has_cards, has_payoff, has_foreshadowing, has_prompt]):
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

    selection_scope = selection_engine._selection_scope(planning_packet, shortlist)
    selection_layers = selection_engine._selection_layer_overview(planning_packet, shortlist)
    focused_payoff = selection_scope.get('payoff') or {}
    focused_foreshadowing = selection_scope.get('foreshadowing') or {}
    focused_payoff_candidates = [
        item for item in (focused_payoff.get('candidates') or [])
        if isinstance(item, dict)
    ]
    focused_foreshadowing_candidates = [
        item for item in (focused_foreshadowing.get('candidates') or [])
        if isinstance(item, dict)
    ]
    focused_foreshadowing_parents = [
        item for item in (focused_foreshadowing.get('parent_cards') or [])
        if isinstance(item, dict)
    ]
    focused_foreshadowing_children = [
        item for item in (focused_foreshadowing.get('child_cards') or [])
        if isinstance(item, dict)
    ]
    payoff_families = [str(item.get('family') or '').strip() for item in focused_payoff_candidates if str(item.get('family') or '').strip()]
    focused_parent_ids = [str(item.get('card_id') or '').strip() for item in focused_foreshadowing_parents if str(item.get('card_id') or '').strip()]
    focused_child_ids = [str(item.get('child_id') or '').strip() for item in focused_foreshadowing_children if str(item.get('child_id') or '').strip()]
    focus_path = focused_foreshadowing.get('focus_path') or {}

    precomputed_selector_payloads: dict[str, Any] = {}
    candidate_overview = {
        'payoff': {
            'candidate_count': len(focused_payoff_candidates),
            'candidate_ids': [str(item.get('card_id') or '').strip() for item in focused_payoff_candidates if str(item.get('card_id') or '').strip()],
            'candidate_labels': [str(item.get('name') or '').strip() for item in focused_payoff_candidates if str(item.get('name') or '').strip()],
            'selector_keys': [str(item.get('selector_key') or '').strip() for item in focused_payoff_candidates if str(item.get('selector_key') or '').strip()],
            'family_count': len(set(payoff_families)),
            'families': list(dict.fromkeys(payoff_families))[:6],
            'auto_selected': False,
            'auto_selected_id': '',
        },
        'foreshadowing': {
            'candidate_count': len(focused_foreshadowing_candidates),
            'candidate_ids': [str(item.get('candidate_id') or '').strip() for item in focused_foreshadowing_candidates if str(item.get('candidate_id') or '').strip()],
            'candidate_labels': [str(item.get('display_label') or item.get('selector_label') or item.get('source_hook') or '').strip() for item in focused_foreshadowing_candidates if str(item.get('display_label') or item.get('selector_label') or item.get('source_hook') or '').strip()],
            'legacy_candidate_ids': [str(item.get('legacy_candidate_id') or '').strip() for item in focused_foreshadowing_candidates if str(item.get('legacy_candidate_id') or '').strip()],
            'selector_keys': [str(item.get('selector_key') or '').strip() for item in focused_foreshadowing_candidates if str(item.get('selector_key') or '').strip()],
            'parent_count': len(focused_parent_ids),
            'parent_ids': focused_parent_ids,
            'parent_labels': [str(item.get('name') or '').strip() for item in focused_foreshadowing_parents if str(item.get('name') or '').strip()],
            'child_count': len(focused_child_ids),
            'child_ids': focused_child_ids,
            'child_labels': [str(item.get('name') or '').strip() for item in focused_foreshadowing_children if str(item.get('name') or '').strip()],
            'path_summary': {
                'parent_filter_mode': str(focus_path.get('parent_filter_mode') or ''),
                'child_filter_mode': str(focus_path.get('child_filter_mode') or ''),
                'candidate_filter_mode': str(focus_path.get('candidate_filter_mode') or ''),
            },
            'layer_singletons': {
                'parent': len(focused_parent_ids) == 1,
                'child': len(focused_child_ids) == 1,
                'candidate': len(focused_foreshadowing_candidates) == 1,
            },
            'auto_selected': False,
            'auto_selected_id': '',
        },
    }

    if len(focused_payoff_candidates) == 1:
        only_payoff = str(focused_payoff_candidates[0].get('card_id') or '').strip()
        precomputed_selector_payloads['payoff'] = selection_engine.PayoffSelectionPayload(
            selected_card_id=only_payoff,
            selection_note='聚焦爽点候选仅 1 条，已自动锁定，无需再让 AI 终选。',
        )
        candidate_overview['payoff']['auto_selected'] = True
        candidate_overview['payoff']['auto_selected_id'] = only_payoff

    if len(focused_foreshadowing_candidates) == 1:
        only_foreshadow = str(focused_foreshadowing_candidates[0].get('candidate_id') or '').strip()
        precomputed_selector_payloads['foreshadowing'] = selection_engine.ForeshadowingSelectionPayload(
            selected_primary_candidate_id=only_foreshadow,
            selected_supporting_candidate_ids=[],
            selection_note='聚焦伏笔候选仅 1 条，已自动锁定，无需再让 AI 终选。',
        )
        candidate_overview['foreshadowing']['auto_selected'] = True
        candidate_overview['foreshadowing']['auto_selected_id'] = only_foreshadow

    parallel_result = run_parallel_preparation_selectors(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
        shortlist=shortlist,
        precomputed_selector_payloads=precomputed_selector_payloads,
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
        'selection_scope': selection_scope,
        'candidate_overview': candidate_overview,
        'selection_layers': selection_layers,
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
