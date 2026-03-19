from __future__ import annotations

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.config import settings
from app.services import openai_story_engine as engine
from app.services import openai_story_engine_selection as selection_engine
from app.services.chapter_preparation_selection_prompts import (
    merge_selection_system_prompt,
    merge_selection_user_prompt,
    preselection_system_prompt,
    preselection_user_prompt,
    selector_system_prompt,
    selector_user_prompt,
)


def adaptive_selector_timeout(base_timeout: int, max_timeout: int, prompt_chars: int, *, attempt: int, increment: int) -> int:
    adaptive_timeout = max(base_timeout, 1) + min(max(prompt_chars - 3600, 0) // 800, 8)
    return min(max_timeout, adaptive_timeout + (increment * max(attempt - 1, 0)))


def selector_trace_package(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in (trace or [])]



def normalize_preselection_payload(payload: selection_engine.ChapterPreparationShortlistPayload, planning_packet: dict[str, Any]) -> selection_engine.ChapterPreparationShortlistPayload:
    schedule_index = (planning_packet or {}).get('schedule_candidate_index') or {}
    appearance = schedule_index.get('appearance_candidates') or []
    relation_rows = schedule_index.get('relation_candidates') or []
    valid_characters = {str(item.get('name') or '').strip() for item in appearance if isinstance(item, dict) and str(item.get('name') or '').strip()}
    valid_relation_ids = {str(item.get('relation_id') or '').strip() for item in relation_rows if isinstance(item, dict) and str(item.get('relation_id') or '').strip()}
    card_entries = selection_engine._card_index_entries(planning_packet)
    valid_card_ids = {str(item.get('card_id') or '').strip() for item in card_entries if isinstance(item, dict) and str(item.get('card_id') or '').strip()}
    payoff_entries = (((planning_packet or {}).get('payoff_candidate_index') or {}).get('candidates') or [])
    valid_payoff_ids = {str(item.get('card_id') or '').strip() for item in payoff_entries if isinstance(item, dict) and str(item.get('card_id') or '').strip()}
    foreshadowing_index = ((planning_packet or {}).get('foreshadowing_candidate_index') or {})
    foreshadowing_parent_entries = (foreshadowing_index.get('parent_cards') or [])
    foreshadowing_child_entries = (foreshadowing_index.get('child_cards') or [])
    foreshadowing_candidate_entries = (foreshadowing_index.get('candidates') or [])
    valid_foreshadowing_parent_ids = {str(item.get('card_id') or '').strip() for item in foreshadowing_parent_entries if isinstance(item, dict) and str(item.get('card_id') or '').strip()}
    valid_foreshadowing_child_ids = {str(item.get('child_id') or '').strip() for item in foreshadowing_child_entries if isinstance(item, dict) and str(item.get('child_id') or '').strip()}
    valid_foreshadowing_candidate_ids = {str(item.get('candidate_id') or '').strip() for item in foreshadowing_candidate_entries if isinstance(item, dict) and str(item.get('candidate_id') or '').strip()}
    prompt_entries = (planning_packet or {}).get('prompt_strategy_index') or []
    valid_prompt_ids = {str(item.get('strategy_id') or '').strip() for item in prompt_entries if isinstance(item, dict) and str(item.get('strategy_id') or '').strip()}
    flow_entries = (planning_packet or {}).get('flow_template_index') or []
    valid_flow_ids = {str(item.get('flow_id') or '').strip() for item in flow_entries if isinstance(item, dict) and str(item.get('flow_id') or '').strip()}
    prompt_bundle = ((planning_packet or {}).get('prompt_bundle_index') or {}) if isinstance((planning_packet or {}).get('prompt_bundle_index') or {}, dict) else {}
    valid_flow_child_ids = {str(item.get('child_id') or item.get('card_id') or '').strip() for item in (prompt_bundle.get('flow_child_cards') or []) if isinstance(item, dict) and str(item.get('child_id') or item.get('card_id') or '').strip()}
    valid_writing_child_ids = {str(item.get('child_id') or item.get('card_id') or '').strip() for item in (prompt_bundle.get('writing_child_cards') or []) if isinstance(item, dict) and str(item.get('child_id') or item.get('card_id') or '').strip()}

    def _dedupe_keep(items: list[str], allowed: set[str], limit: int, *, resolver=None) -> list[str]:
        out = []
        seen = set()
        for item in items or []:
            raw = str(item or '').strip()
            if not raw:
                continue
            clean = resolver(raw) if resolver else raw
            clean = str(clean or '').strip()
            if not clean or clean in seen or clean not in allowed:
                continue
            seen.add(clean)
            out.append(clean)
            if len(out) >= limit:
                break
        return out

    return selection_engine.ChapterPreparationShortlistPayload(
        focus_characters=_dedupe_keep(payload.focus_characters, valid_characters, 4),
        main_relation_ids=_dedupe_keep(payload.main_relation_ids, valid_relation_ids, 3),
        card_candidate_ids=_dedupe_keep(payload.card_candidate_ids, valid_card_ids, 16),
        payoff_candidate_ids=_dedupe_keep(payload.payoff_candidate_ids, valid_payoff_ids, 3, resolver=lambda raw: selection_engine._resolve_selector_reference(raw, [item for item in payoff_entries if isinstance(item, dict)], primary_keys=['card_id'], prefix='payoff', name_keys=['name'])),
        foreshadowing_parent_card_ids=_dedupe_keep(payload.foreshadowing_parent_card_ids, valid_foreshadowing_parent_ids, 4),
        foreshadowing_child_card_ids=_dedupe_keep(payload.foreshadowing_child_card_ids, valid_foreshadowing_child_ids, 6),
        foreshadowing_candidate_ids=_dedupe_keep(payload.foreshadowing_candidate_ids, valid_foreshadowing_candidate_ids, 6, resolver=lambda raw: selection_engine._resolve_selector_reference(raw, [item for item in foreshadowing_candidate_entries if isinstance(item, dict)], primary_keys=['candidate_id'], prefix='foreshadow', name_keys=['display_label', 'selector_label', 'legacy_candidate_id', 'source_hook', 'child_card_name'])),
        scene_template_ids=[],
        flow_template_ids=_dedupe_keep(payload.flow_template_ids, valid_flow_ids, 4),
        flow_child_card_ids=_dedupe_keep(payload.flow_child_card_ids, valid_flow_child_ids, 6),
        prompt_strategy_ids=_dedupe_keep(payload.prompt_strategy_ids, valid_prompt_ids, 6),
        writing_child_card_ids=_dedupe_keep(payload.writing_child_card_ids, valid_writing_child_ids, 6),
        shortlist_note=str(payload.shortlist_note or '').strip() or 'AI 已基于全部压缩索引完成预筛。',
    )


def run_preparation_shortlist(*, chapter_plan: dict[str, Any], planning_packet: dict[str, Any], request_timeout_seconds: int | None) -> tuple[selection_engine.ChapterPreparationShortlistPayload, dict[str, Any]]:
    configured_timeout = max(int(getattr(settings, 'chapter_frontload_decision_timeout_seconds', 22) or 22), 14)
    max_timeout_seconds = max(int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42), configured_timeout)
    attempts_total = max(int(getattr(settings, 'chapter_frontload_decision_retry_attempts', 2) or 2), 1)
    timeout_increment_seconds = max(int(getattr(settings, 'chapter_frontload_decision_retry_timeout_increment_seconds', 10) or 10), 0)
    retry_backoff_ms = max(int(getattr(settings, 'chapter_frontload_decision_retry_backoff_ms', 800) or 800), 0)
    compact_after_attempt = max(int(getattr(settings, 'chapter_frontload_decision_prompt_compact_after_attempt', 2) or 2), 1)
    compact_threshold_chars = max(int(getattr(settings, 'chapter_frontload_decision_compact_prompt_threshold_chars', 7000) or 7000), 3000)
    max_output_tokens = max(int(getattr(settings, 'chapter_preparation_shortlist_max_output_tokens', 520) or 520), 280)
    last_generation_error: engine.GenerationError | None = None

    for attempt in range(1, attempts_total + 1):
        compact_mode = attempt >= compact_after_attempt
        trace_start = len(engine.get_llm_trace())
        user_prompt = preselection_user_prompt(chapter_plan=chapter_plan, planning_packet=planning_packet, compact_mode=compact_mode)
        if len(user_prompt) > compact_threshold_chars and not compact_mode:
            compact_mode = True
            user_prompt = preselection_user_prompt(chapter_plan=chapter_plan, planning_packet=planning_packet, compact_mode=True)
        timeout_seconds = adaptive_selector_timeout(max(request_timeout_seconds or 0, configured_timeout), max_timeout_seconds, len(user_prompt), attempt=attempt, increment=timeout_increment_seconds)
        try:
            data = engine.call_json_response(
                stage='chapter_prepare_shortlist',
                system_prompt=preselection_system_prompt(),
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
            )
            payload = normalize_preselection_payload(selection_engine.ChapterPreparationShortlistPayload.model_validate(data), planning_packet)
            return payload, {
                'attempt': attempt,
                'compact_mode': compact_mode,
                'timeout_seconds': timeout_seconds,
                'prompt_chars': len(user_prompt),
                'trace': selector_trace_package(engine.get_llm_trace()[trace_start:]),
            }
        except engine.GenerationError as exc:
            last_generation_error = exc
            details = dict(exc.details or {})
            details.update({
                'attempt': attempt,
                'attempts_total': attempts_total,
                'compact_mode': compact_mode,
                'timeout_seconds': timeout_seconds,
                'user_prompt_chars': len(user_prompt),
            })
            exc.details = details
            retryable_codes = {
                engine.ErrorCodes.API_TIMEOUT,
                engine.ErrorCodes.API_CONNECTION_FAILED,
                engine.ErrorCodes.API_STATUS_ERROR,
                engine.ErrorCodes.MODEL_RESPONSE_INVALID,
                engine.ErrorCodes.API_RATE_LIMITED,
            }
            if attempt >= attempts_total or exc.code not in retryable_codes or not bool(exc.retryable):
                raise
            if retry_backoff_ms > 0:
                time.sleep(retry_backoff_ms / 1000.0)
    if last_generation_error is not None:
        raise last_generation_error
    raise engine.GenerationError(
        code=engine.ErrorCodes.MODEL_RESPONSE_INVALID,
        message='chapter_prepare_shortlist 失败：AI 未返回可用 shortlist。',
        stage='chapter_prepare_shortlist',
        retryable=True,
        http_status=422,
        provider=engine.provider_name(),
    )


def run_selector_task(
    spec: selection_engine.SelectorTaskSpec,
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None,
    shortlist: dict[str, Any] | None,
) -> dict[str, Any]:
    attempts_total = max(int(getattr(settings, 'chapter_frontload_decision_retry_attempts', 2) or 2), 1)
    retry_backoff_ms = max(int(getattr(settings, 'chapter_frontload_decision_retry_backoff_ms', 800) or 800), 0)
    timeout_increment_seconds = max(int(getattr(settings, 'chapter_frontload_decision_retry_timeout_increment_seconds', 10) or 10), 0)
    compact_after_attempt = max(int(getattr(settings, 'chapter_frontload_decision_prompt_compact_after_attempt', 2) or 2), 1)
    compact_threshold_chars = max(int(getattr(settings, 'chapter_frontload_decision_compact_prompt_threshold_chars', 7000) or 7000), 3000)
    base_timeout = max(request_timeout_seconds or 0, spec.timeout_floor)
    last_generation_error: engine.GenerationError | None = None

    for attempt in range(1, attempts_total + 1):
        compact_mode = attempt >= compact_after_attempt
        trace_start = len(engine.get_llm_trace())
        user_prompt = selector_user_prompt(spec.name, chapter_plan=chapter_plan, planning_packet=planning_packet, compact_mode=compact_mode, shortlist=shortlist)
        if len(user_prompt) > compact_threshold_chars and not compact_mode:
            compact_mode = True
            user_prompt = selector_user_prompt(spec.name, chapter_plan=chapter_plan, planning_packet=planning_packet, compact_mode=True, shortlist=shortlist)
        timeout_seconds = adaptive_selector_timeout(base_timeout, spec.timeout_cap, len(user_prompt), attempt=attempt, increment=timeout_increment_seconds)
        try:
            data = engine.call_json_response(
                stage=spec.stage,
                system_prompt=spec.system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=spec.output_tokens,
                timeout_seconds=timeout_seconds,
            )
            payload_cls = {
                'schedule': selection_engine.CharacterRelationScheduleReviewPayload,
                'cards': selection_engine.ChapterCardSelectionPayload,
                'payoff': selection_engine.PayoffSelectionPayload,
                'foreshadowing': selection_engine.ForeshadowingSelectionPayload,
                'scene': selection_engine.SceneTemplateSelectionPayload,
                'prompt': selection_engine.PromptStrategySelectionPayload,
            }[spec.name]
            payload = payload_cls.model_validate(data)
            return {
                'payload': payload,
                'compact_mode': compact_mode,
                'timeout_seconds': timeout_seconds,
                'prompt_chars': len(user_prompt),
                'attempt': attempt,
                'trace': selector_trace_package(engine.get_llm_trace()[trace_start:]),
            }
        except engine.GenerationError as exc:
            last_generation_error = exc
            details = dict(exc.details or {})
            details.update({
                'selector': spec.name,
                'attempt': attempt,
                'attempts_total': attempts_total,
                'compact_mode': compact_mode,
                'timeout_seconds': timeout_seconds,
                'user_prompt_chars': len(user_prompt),
                'worker_trace': selector_trace_package(engine.get_llm_trace()[trace_start:]),
            })
            exc.details = details
            retryable_codes = {
                engine.ErrorCodes.API_TIMEOUT,
                engine.ErrorCodes.API_CONNECTION_FAILED,
                engine.ErrorCodes.API_STATUS_ERROR,
                engine.ErrorCodes.MODEL_RESPONSE_INVALID,
                engine.ErrorCodes.API_RATE_LIMITED,
            }
            if attempt >= attempts_total or exc.code not in retryable_codes or not bool(exc.retryable):
                raise
            if retry_backoff_ms > 0:
                time.sleep(retry_backoff_ms / 1000.0)
    if last_generation_error is not None:
        raise last_generation_error
    raise engine.GenerationError(
        code=engine.ErrorCodes.MODEL_RESPONSE_INVALID,
        message=f'{spec.stage} 失败：AI 未返回可用结果。',
        stage=spec.stage,
        retryable=True,
        http_status=422,
        provider=engine.provider_name(),
    )


def normalize_selector_output(name: str, payload: Any, *, chapter_plan: dict[str, Any], planning_packet: dict[str, Any], shortlist: dict[str, Any] | None = None) -> Any:
    if name == 'schedule':
        return selection_engine._normalize_schedule_review_payload(payload, planning_packet)
    if name == 'cards':
        selected_ids = selection_engine._enforce_required_card_ids(planning_packet, payload.selected_card_ids, chapter_plan=chapter_plan)
        return selection_engine.ChapterCardSelectionPayload(
            selected_card_ids=selected_ids[:12],
            selection_note=str(payload.selection_note or '').strip() or 'AI 已从聚焦卡片压缩索引中直接选定本章用卡。',
        )
    if name == 'payoff':
        return selection_engine._normalize_payoff_selection_payload(payload, planning_packet, shortlist)
    if name == 'foreshadowing':
        return selection_engine._normalize_foreshadowing_selection_payload(payload, planning_packet, shortlist)
    if name == 'prompt':
        return selection_engine._normalize_prompt_strategy_selection_payload(payload, planning_packet, shortlist)
    return payload


def run_parallel_preparation_selectors(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None,
    shortlist: dict[str, Any] | None,
    precomputed_selector_payloads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    specs = [
        selection_engine.SelectorTaskSpec(name='schedule', stage='chapter_prepare_schedule_selector', system_prompt=selector_system_prompt('schedule'), output_tokens=420, timeout_floor=max(min((request_timeout_seconds or 14), 18), 10), timeout_cap=max(int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42) - 8, 18)),
        selection_engine.SelectorTaskSpec(name='cards', stage='chapter_prepare_card_selector', system_prompt=selector_system_prompt('cards'), output_tokens=340, timeout_floor=max(min((request_timeout_seconds or 14), 18), 10), timeout_cap=max(int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42) - 8, 18)),
        selection_engine.SelectorTaskSpec(name='payoff', stage='chapter_prepare_payoff_selector', system_prompt=selector_system_prompt('payoff'), output_tokens=260, timeout_floor=max(min((request_timeout_seconds or 14), 18), 10), timeout_cap=max(int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42) - 10, 16)),
        selection_engine.SelectorTaskSpec(name='foreshadowing', stage='chapter_prepare_foreshadowing_selector', system_prompt=selector_system_prompt('foreshadowing'), output_tokens=max(int(getattr(settings, 'foreshadowing_selector_max_output_tokens', 320) or 320), 220), timeout_floor=max(min((request_timeout_seconds or 16), 20), 12), timeout_cap=max(int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42) - 8, 18)),
        selection_engine.SelectorTaskSpec(name='prompt', stage='chapter_prepare_prompt_selector', system_prompt=selector_system_prompt('prompt'), output_tokens=240, timeout_floor=max(min((request_timeout_seconds or 14), 18), 10), timeout_cap=max(int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42) - 12, 16)),
    ]
    precomputed_selector_payloads = dict(precomputed_selector_payloads or {})
    specs = [spec for spec in specs if spec.name not in precomputed_selector_payloads]
    max_workers = max(int(getattr(settings, 'chapter_preparation_parallel_max_workers', 4) or 4), 1)
    enabled = bool(getattr(settings, 'chapter_preparation_parallel_selection_enabled', True))
    worker_count = min(max_workers, len(specs)) if enabled else 1
    results: dict[str, Any] = {}
    trace: dict[str, Any] = {'mode': 'parallel_ai_selectors', 'parallel_enabled': enabled, 'worker_count': worker_count, 'selectors': {}}

    for name, payload in precomputed_selector_payloads.items():
        results[name] = normalize_selector_output(name, payload, chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist)
        trace['selectors'][name] = {
            'skipped': True,
            'reason': 'single_candidate_auto_select',
            'candidate_count': 1,
        }

    def _run_with_context(spec: selection_engine.SelectorTaskSpec) -> dict[str, Any]:
        return run_selector_task(spec, chapter_plan=chapter_plan, planning_packet=planning_packet, request_timeout_seconds=request_timeout_seconds, shortlist=shortlist)

    if not specs:
        return {'results': results, 'trace': trace}

    if worker_count <= 1:
        for spec in specs:
            outcome = _run_with_context(spec)
            results[spec.name] = normalize_selector_output(spec.name, outcome['payload'], chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist)
            trace['selectors'][spec.name] = {k: v for k, v in outcome.items() if k != 'payload'}
        return {'results': results, 'trace': trace}

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix='chapter-prep-selector') as executor:
        future_map = {}
        for spec in specs:
            ctx = contextvars.copy_context()
            future = executor.submit(lambda context=ctx, task_spec=spec: context.run(_run_with_context, task_spec))
            future_map[future] = spec
        for future in as_completed(future_map):
            spec = future_map[future]
            try:
                outcome = future.result()
            except engine.GenerationError:
                raise
            results[spec.name] = normalize_selector_output(spec.name, outcome['payload'], chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist)
            trace['selectors'][spec.name] = {k: v for k, v in outcome.items() if k != 'payload'}
    return {'results': results, 'trace': trace}


def merge_parallel_preparation_selection(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    selector_outputs: dict[str, Any],
    request_timeout_seconds: int | None,
    shortlist: dict[str, Any] | None,
) -> tuple[selection_engine.ChapterPreparationSelectionResult, dict[str, Any]]:
    attempts_total = max(int(getattr(settings, 'chapter_frontload_decision_retry_attempts', 2) or 2), 1)
    retry_backoff_ms = max(int(getattr(settings, 'chapter_frontload_decision_retry_backoff_ms', 800) or 800), 0)
    timeout_increment_seconds = max(int(getattr(settings, 'chapter_frontload_decision_retry_timeout_increment_seconds', 10) or 10), 0)
    compact_after_attempt = max(int(getattr(settings, 'chapter_frontload_decision_prompt_compact_after_attempt', 2) or 2), 1)
    compact_threshold_chars = max(int(getattr(settings, 'chapter_frontload_decision_compact_prompt_threshold_chars', 7000) or 7000), 3000)
    configured_timeout = int(getattr(settings, 'chapter_preparation_merge_timeout_seconds', 0) or 0) or max(int(getattr(settings, 'chapter_frontload_decision_timeout_seconds', 22) or 22), 18)
    max_timeout_seconds = max(int(getattr(settings, 'chapter_preparation_merge_max_timeout_seconds', 0) or 0), configured_timeout, int(getattr(settings, 'chapter_frontload_decision_max_timeout_seconds', 42) or 42))
    max_output_tokens = max(int(getattr(settings, 'chapter_preparation_merge_max_output_tokens', 720) or 720), 520)
    last_generation_error: engine.GenerationError | None = None
    trace_start = len(engine.get_llm_trace())

    for attempt in range(1, attempts_total + 1):
        compact_mode = attempt >= compact_after_attempt
        trace_start = len(engine.get_llm_trace())
        user_prompt = merge_selection_user_prompt(
            chapter_plan=chapter_plan,
            planning_packet=planning_packet,
            selector_outputs={key: value.model_dump(mode='python') if hasattr(value, 'model_dump') else value for key, value in selector_outputs.items()},
            compact_mode=compact_mode,
            shortlist=shortlist,
        )
        if len(user_prompt) > compact_threshold_chars and not compact_mode:
            compact_mode = True
            user_prompt = merge_selection_user_prompt(
                chapter_plan=chapter_plan,
                planning_packet=planning_packet,
                selector_outputs={key: value.model_dump(mode='python') if hasattr(value, 'model_dump') else value for key, value in selector_outputs.items()},
                compact_mode=True,
                shortlist=shortlist,
            )
        timeout_seconds = adaptive_selector_timeout(max(request_timeout_seconds or 0, configured_timeout), max_timeout_seconds, len(user_prompt), attempt=attempt, increment=timeout_increment_seconds)
        try:
            data = engine.call_json_response(
                stage='chapter_prepare_selection_merge',
                system_prompt=merge_selection_system_prompt(),
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
            )
            payload = selection_engine.ChapterFrontloadDecisionPayload.model_validate(data)
            result = selection_engine.ChapterPreparationSelectionResult(
                schedule_review=selection_engine._normalize_schedule_review_payload(payload.schedule_review, planning_packet),
                card_selection=normalize_selector_output('cards', payload.card_selection, chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist),
                payoff_selection=normalize_selector_output('payoff', payload.payoff_selection, chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist),
                foreshadowing_selection=normalize_selector_output('foreshadowing', payload.foreshadowing_selection, chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist),
                scene_selection=selection_engine.SceneTemplateSelectionPayload(),
                prompt_strategy_selection=normalize_selector_output('prompt', payload.prompt_strategy_selection, chapter_plan=chapter_plan, planning_packet=planning_packet, shortlist=shortlist),
                selection_trace={},
            )
            merge_trace = {
                'merge_stage': {
                    'attempt': attempt,
                    'compact_mode': compact_mode,
                    'timeout_seconds': timeout_seconds,
                    'prompt_chars': len(user_prompt),
                    'trace': selector_trace_package(engine.get_llm_trace()[trace_start:]),
                },
                'merge_fallback_used': False,
            }
            return result, merge_trace
        except engine.GenerationError as exc:
            last_generation_error = exc
            details = dict(exc.details or {})
            details.update({
                'attempt': attempt,
                'attempts_total': attempts_total,
                'compact_mode': compact_mode,
                'timeout_seconds': timeout_seconds,
                'user_prompt_chars': len(user_prompt),
            })
            exc.details = details
            retryable_codes = {
                engine.ErrorCodes.API_TIMEOUT,
                engine.ErrorCodes.API_CONNECTION_FAILED,
                engine.ErrorCodes.API_STATUS_ERROR,
                engine.ErrorCodes.MODEL_RESPONSE_INVALID,
                engine.ErrorCodes.API_RATE_LIMITED,
            }
            if attempt >= attempts_total or exc.code not in retryable_codes or not bool(exc.retryable):
                break
            if retry_backoff_ms > 0:
                time.sleep(retry_backoff_ms / 1000.0)

    raise engine.GenerationError(
        code=engine.ErrorCodes.MODEL_RESPONSE_INVALID,
        message='chapter_prepare_selection_merge 失败：AI 未能完成统一仲裁，系统已停止生成。',
        stage='chapter_prepare_selection_merge',
        retryable=bool(last_generation_error.retryable) if last_generation_error else True,
        http_status=422,
        provider=engine.provider_name(),
        details={
            'selector_outputs_present': sorted([key for key, value in (selector_outputs or {}).items() if value is not None]),
            'shortlist_present': bool(shortlist),
            'merge_trace': {
                'failed': True,
                'error': dict((last_generation_error.details or {})) if last_generation_error else {},
                'trace': selector_trace_package(engine.get_llm_trace()[trace_start:]),
            },
        },
    )


__all__ = [
    'adaptive_selector_timeout',
    'selector_trace_package',
    'normalize_preselection_payload',
    'run_preparation_shortlist',
    'run_selector_task',
    'normalize_selector_output',
    'run_parallel_preparation_selectors',
    'merge_parallel_preparation_selection',
]
