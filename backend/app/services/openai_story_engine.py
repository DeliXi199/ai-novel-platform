from __future__ import annotations

import copy
import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.chapter_quality import _progress_result_is_clear, _weak_ending
from app.services.agency_modes import AGENCY_MODES
from app.services.openai_story_engine_selection import (
    ChapterCardSelectionPayload,
    ChapterFrontloadDecisionPayload,
    ChapterPreparationSelectionResult,
    ChapterPreparationShortlistPayload,
    PayoffSelectionPayload,
    PromptStrategySelectionPayload,
    SceneTemplateSelectionPayload,
    SelectorTaskSpec as _SelectorTaskSpec,
    _card_index_entries,
    _compact_for_prompt,
    _enforce_required_card_ids,
    _focused_card_index,
    _focused_payoff_candidate_index,
    _focused_prompt_bundle_index,
    _focused_scene_template_index,
    _focused_schedule_candidate_index,
    _pretty_json,
    _schedule_valid_character_names,
    _schedule_valid_relation_ids,
    _selection_scope,
    choose_chapter_card_selection as _selection_choose_chapter_card_selection,
)
from app.services.openai_story_engine_arc import (
    ArcCastingChapterDecision,
    ArcCastingLayoutReviewPayload,
    apply_arc_casting_layout_review,
    review_arc_casting_layout,
)
from app.services.openai_story_engine_review import (
    CharacterRelationScheduleReviewPayload,
    StageCharacterReviewPayload,
    _heuristic_character_relation_schedule_review,
    apply_schedule_review_to_packet,
    review_character_relation_schedule,
    review_stage_characters,
)
from app.services.openai_story_engine_bootstrap import (
    ArcOutlinePayload,
    ChapterPlan,
    GlobalOutlinePayload,
    ParsedInstructionPayload,
    PlannedRelationHint,
    StoryAct,
    StoryEngineDiagnosisPayload,
    StoryEngineStrategyBundlePayload,
    StoryStrategyCardPayload,
    ThirtyChapterPhase,
    _apply_flow_template_to_chapter,
    _choose_flow_template_for_chapter,
    _enforce_event_type_variety,
    _flow_match_score,
    _flow_templates_from_story_bible,
    _infer_event_type,
    _infer_hook_kind,
    _infer_progress_kind,
    _infer_proactive_move,
    _keyword_hit_count,
    generate_arc_outline as _bootstrap_generate_arc_outline,
    generate_global_outline as _bootstrap_generate_global_outline,
    generate_story_engine_diagnosis as _bootstrap_generate_story_engine_diagnosis,
    generate_story_engine_strategy_bundle as _bootstrap_generate_story_engine_strategy_bundle,
    generate_story_strategy_card as _bootstrap_generate_story_strategy_card,
    parse_instruction_with_openai as _bootstrap_parse_instruction_with_openai,
)
from app.services.openai_story_engine_chapter import (
    ChapterDraftPayload,
    _chapter_phase_timeouts,
    _chapter_phase_visible_char_targets,
    _clean_plain_chapter_text,
    _merge_generated_closing,
    _resolve_safe_closing_timeout,
    _resolve_safe_continuation_timeout,
    _should_continue_body_generation,
    _should_run_chapter_closing,
    _tail_is_stable_for_continue,
    extend_chapter_text as _chapter_extend_chapter_text,
    generate_chapter_from_plan as _chapter_generate_chapter_from_plan,
)
from app.services.openai_story_engine_summary import (
    ChapterSummaryPayload,
    ChapterSummaryTitlePackagePayload,
    ChapterTitleRefinementPayload,
    _normalize_chapter_summary_payload,
    _parse_labeled_summary,
    _truncate_visible,
    generate_chapter_summary_and_title_package as _summary_generate_chapter_summary_and_title_package,
    generate_chapter_title_candidates as _summary_generate_chapter_title_candidates,
    summarize_chapter as _summary_summarize_chapter,
)
from app.services.llm_runtime import (
    append_trace,
    begin_llm_trace,
    call_json_response,
    call_text_response,
    clear_llm_trace,
    current_chapter_max_output_tokens,
    extract_json,
    get_llm_runtime_config,
    get_llm_trace,
    is_openai_enabled,
    ping_generation_provider,
    provider_name,
)
from app.services.prompt_templates import (
    chapter_body_draft_system_prompt,
    chapter_body_draft_user_prompt,
    chapter_card_selector_system_prompt,
    chapter_card_selector_user_prompt,
    chapter_frontload_decision_system_prompt,
    chapter_frontload_decision_user_prompt,
    stage_character_review_system_prompt,
    stage_character_review_user_prompt,
    character_relation_schedule_review_system_prompt,
    character_relation_schedule_review_user_prompt,
    chapter_body_continue_system_prompt,
    chapter_body_continue_user_prompt,
    chapter_closing_system_prompt,
    chapter_closing_user_prompt,
    chapter_draft_system_prompt,
    chapter_draft_user_prompt,
    chapter_extension_system_prompt,
    chapter_extension_user_prompt,
    chapter_title_refinement_system_prompt,
    chapter_title_refinement_user_prompt,
    summary_system_prompt,
    summary_title_package_system_prompt,
    summary_title_package_user_prompt,
    summary_user_prompt,
)

logger = logging.getLogger(__name__)


def _raise_ai_required_error(*, stage: str, message: str, detail_reason: str = "", retryable: bool = True) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"{message}{('：' + detail_reason) if detail_reason else ''}",
        stage=stage,
        retryable=retryable,
        http_status=503,
        provider=provider_name(),
        details={"reason": detail_reason} if detail_reason else None,
    )



def choose_chapter_card_selection(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> ChapterCardSelectionPayload:
    """Compatibility shim; selection owns the primary implementation."""
    return _selection_choose_chapter_card_selection(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
    )



def run_chapter_preparation_selection(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> ChapterPreparationSelectionResult:
    """Compatibility shim for legacy callers.

    The stable boundary now lives in ``openai_story_engine_selection`` /
    ``chapter_preparation_selection``. Keep this wrapper so tests and older
    call sites that still patch the monolithic engine do not break.
    """
    from app.services.openai_story_engine_selection import run_chapter_preparation_selection as _impl

    return _impl(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
    )


def review_character_relation_schedule_and_select_cards(
    *,
    chapter_plan: dict[str, Any],
    planning_packet: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> tuple[CharacterRelationScheduleReviewPayload, ChapterCardSelectionPayload]:
    """Compatibility shim for legacy callers.

    Selection orchestration moved out of the monolithic engine; keep this
    wrapper for existing tests and monkeypatch-based overrides.
    """
    from app.services.openai_story_engine_selection import review_character_relation_schedule_and_select_cards as _impl

    return _impl(
        chapter_plan=chapter_plan,
        planning_packet=planning_packet,
        request_timeout_seconds=request_timeout_seconds,
    )



def generate_chapter_from_plan(
    novel_context: dict[str, Any],
    chapter_plan: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
    target_words: int,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    request_timeout_seconds: int | None = None,
) -> ChapterDraftPayload:
    return _chapter_generate_chapter_from_plan(
        novel_context=novel_context,
        chapter_plan=chapter_plan,
        last_chapter=last_chapter,
        recent_summaries=recent_summaries,
        active_interventions=active_interventions,
        target_words=target_words,
        target_visible_chars_min=target_visible_chars_min,
        target_visible_chars_max=target_visible_chars_max,
        request_timeout_seconds=request_timeout_seconds,
        call_text_response_fn=call_text_response,
        current_chapter_max_output_tokens_fn=current_chapter_max_output_tokens,
    )


def extend_chapter_text(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    repair_mode: str = "append_inline_tail",
    ending_issue: str | None = None,
    repair_attempt_no: int = 1,
    previous_repair_modes: list[str] | None = None,
    request_timeout_seconds: int | None = None,
) -> str:
    return _chapter_extend_chapter_text(
        chapter_plan=chapter_plan,
        existing_content=existing_content,
        reason=reason,
        target_visible_chars_min=target_visible_chars_min,
        target_visible_chars_max=target_visible_chars_max,
        repair_mode=repair_mode,
        ending_issue=ending_issue,
        repair_attempt_no=repair_attempt_no,
        previous_repair_modes=previous_repair_modes,
        request_timeout_seconds=request_timeout_seconds,
        call_text_response_fn=call_text_response,
        current_chapter_max_output_tokens_fn=current_chapter_max_output_tokens,
    )


def generate_chapter_title_candidates(
    *,
    chapter_no: int,
    original_title: str,
    chapter_plan: dict[str, Any],
    chapter_content: str,
    recent_titles: list[str],
    cooled_terms: list[str],
    summary: dict[str, Any] | None = None,
    candidate_count: int = 5,
    request_timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    return _summary_generate_chapter_title_candidates(
        chapter_no=chapter_no,
        original_title=original_title,
        chapter_plan=chapter_plan,
        chapter_content=chapter_content,
        recent_titles=recent_titles,
        cooled_terms=cooled_terms,
        summary=summary,
        candidate_count=candidate_count,
        request_timeout_seconds=request_timeout_seconds,
        call_json_response_fn=call_json_response,
        is_openai_enabled_fn=is_openai_enabled,
        provider_name_fn=provider_name,
    )


def summarize_chapter(title: str, content: str, request_timeout_seconds: int | None = None) -> ChapterSummaryPayload:
    return _summary_summarize_chapter(
        title,
        content,
        request_timeout_seconds=request_timeout_seconds,
        call_text_response_fn=call_text_response,
    )


def generate_chapter_summary_and_title_package(
    *,
    chapter_no: int,
    title: str,
    content: str,
    chapter_plan: dict[str, Any],
    recent_titles: list[str],
    cooled_terms: list[str],
    candidate_count: int = 5,
    request_timeout_seconds: int | None = None,
) -> ChapterSummaryTitlePackagePayload:
    return _summary_generate_chapter_summary_and_title_package(
        chapter_no=chapter_no,
        title=title,
        content=content,
        chapter_plan=chapter_plan,
        recent_titles=recent_titles,
        cooled_terms=cooled_terms,
        candidate_count=candidate_count,
        request_timeout_seconds=request_timeout_seconds,
        call_json_response_fn=call_json_response,
        is_openai_enabled_fn=is_openai_enabled,
        provider_name_fn=provider_name,
    )


def generate_story_engine_strategy_bundle(payload: dict[str, Any], story_bible: dict[str, Any]) -> StoryEngineStrategyBundlePayload:
    """Compatibility shim; bootstrap now owns strategy bundle generation."""
    return _bootstrap_generate_story_engine_strategy_bundle(payload=payload, story_bible=story_bible)


def generate_story_engine_diagnosis(payload: dict[str, Any], story_bible: dict[str, Any]) -> StoryEngineDiagnosisPayload:
    """Compatibility shim; bootstrap now owns story engine diagnosis."""
    return _bootstrap_generate_story_engine_diagnosis(payload=payload, story_bible=story_bible)


def generate_story_strategy_card(payload: dict[str, Any], story_bible: dict[str, Any]) -> StoryStrategyCardPayload:
    """Compatibility shim; bootstrap now owns strategy card generation."""
    return _bootstrap_generate_story_strategy_card(payload=payload, story_bible=story_bible)


def generate_global_outline(payload: dict[str, Any], story_bible: dict[str, Any], total_acts: int) -> GlobalOutlinePayload:
    """Compatibility shim; bootstrap now owns global outline generation."""
    return _bootstrap_generate_global_outline(payload=payload, story_bible=story_bible, total_acts=total_acts)


def generate_arc_outline(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    start_chapter: int,
    end_chapter: int,
    arc_no: int,
) -> ArcOutlinePayload:
    """Compatibility shim; bootstrap now owns arc outline generation."""
    return _bootstrap_generate_arc_outline(
        payload=payload,
        story_bible=story_bible,
        global_outline=global_outline,
        recent_summaries=recent_summaries,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        arc_no=arc_no,
    )


def parse_instruction_with_openai(raw_instruction: str) -> ParsedInstructionPayload:
    """Compatibility shim; bootstrap now owns instruction parsing."""
    return _bootstrap_parse_instruction_with_openai(raw_instruction)
