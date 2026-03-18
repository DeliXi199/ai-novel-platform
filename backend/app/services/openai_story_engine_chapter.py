from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.services.chapter_quality import _progress_result_is_clear, _weak_ending
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import provider_name
from app.services.prompt_templates import (
    chapter_body_continue_system_prompt,
    chapter_body_continue_user_prompt,
    chapter_body_draft_system_prompt,
    chapter_body_draft_user_prompt,
    chapter_closing_system_prompt,
    chapter_closing_user_prompt,
    chapter_extension_system_prompt,
    chapter_extension_user_prompt,
)

logger = logging.getLogger(__name__)


class ChapterDraftPayload(BaseModel):
    title: str
    content: str
    body_segments: int = 1
    continuation_rounds: int = 0
    body_stop_reason: str = ""
    closing_reason: str = ""


def _clean_plain_chapter_text(text: str, *, expected_title: str | None = None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    candidate = raw
    if raw.startswith("```"):
        fence_lines = raw.splitlines()
        if len(fence_lines) >= 3:
            candidate = "\n".join(fence_lines[1:-1]).strip()

    stripped = candidate.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
        except Exception:
            data = None
        if isinstance(data, dict):
            maybe_content = data.get("content") or data.get("text") or data.get("body")
            if isinstance(maybe_content, str) and maybe_content.strip():
                candidate = maybe_content.strip()
        else:
            match = re.search(r'"content"\s*:\s*"([\s\S]*)"\s*}\s*$', stripped)
            if match:
                candidate = match.group(1)
                candidate = candidate.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")

    normalized = candidate.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]

    def _looks_like_title(line: str) -> bool:
        line = line.strip().strip("#").strip()
        if not line:
            return False
        if expected_title and line == expected_title.strip():
            return True
        if re.fullmatch(r"第\s*\d+\s*章[:：\s\-—]*.*", line):
            return True
        if line.startswith("标题：") or line.startswith("标题:"):
            return True
        return False

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and _looks_like_title(lines[0]):
        lines.pop(0)
    while lines and lines[0].strip() in {"正文：", "正文:", "内容：", "内容:"}:
        lines.pop(0)

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned




def _chapter_phase_visible_char_targets(
    *,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> dict[str, int]:
    total_min = max(int(target_visible_chars_min or 0), 200)
    total_max = max(int(target_visible_chars_max or 0), total_min + 120)
    reserve_min = max(int(getattr(settings, "chapter_closing_target_min_visible_chars", 180) or 180), 80)
    reserve_max = max(int(getattr(settings, "chapter_closing_target_max_visible_chars", 360) or 360), reserve_min)
    ratio = float(getattr(settings, "chapter_body_generation_ratio", 0.82) or 0.82)
    ratio = max(min(ratio, 0.92), 0.58)

    body_max = min(max(total_min, int(total_max * ratio)), max(total_max - reserve_min, total_min))
    body_min = max(int(body_max * 0.82), min(total_min, max(body_max - 260, 240)))
    closing_min = max(80, min(reserve_min, max(total_min - body_max, 80)))
    closing_max = max(closing_min, min(reserve_max, max(total_max - body_min, closing_min)))
    return {
        "body_min": body_min,
        "body_max": body_max,
        "closing_min": closing_min,
        "closing_max": closing_max,
    }


def _chapter_phase_timeouts(request_timeout_seconds: int | None, *, max_segments: int) -> tuple[int | None, int | None, int | None]:
    if request_timeout_seconds is None:
        return None, None, None
    total = max(int(request_timeout_seconds), 18)
    preferred_closing = max(int(getattr(settings, "chapter_closing_timeout_seconds", 28) or 28), 8)
    preferred_body_ratio = float(getattr(settings, "chapter_body_timeout_ratio", 0.76) or 0.76)
    preferred_body_ratio = max(min(preferred_body_ratio, 0.9), 0.58)
    preferred_body_min = max(int(getattr(settings, "chapter_body_min_timeout_seconds", 84) or 84), 12)
    preferred_continuation = max(
        int(getattr(settings, "chapter_continuation_preferred_timeout_seconds", 48) or 48),
        int(getattr(settings, "chapter_continuation_min_timeout_seconds", 36) or 36),
    )

    if total <= 28:
        closing_timeout = min(preferred_closing, max(total // 4, 8))
        body_budget = max(total - closing_timeout, 10)
    else:
        closing_timeout = min(preferred_closing, max(total // 5, 12))
        body_budget = max(total - closing_timeout, 12)

    segments = max(int(max_segments or 1), 1)
    if segments <= 1:
        return max(body_budget, min(preferred_body_min, total - 8)), None, closing_timeout

    initial_body_timeout = max(int(body_budget * preferred_body_ratio), min(preferred_body_min, body_budget))
    initial_body_timeout = min(initial_body_timeout, body_budget)
    continuation_timeout = min(preferred_continuation, max(body_budget - initial_body_timeout, 0))
    if continuation_timeout <= 0:
        continuation_timeout = preferred_continuation
    return initial_body_timeout, continuation_timeout, closing_timeout


def _remaining_request_budget_seconds(
    request_timeout_seconds: int | None,
    started_at: float,
    *,
    reserve_seconds: int = 0,
) -> int | None:
    if request_timeout_seconds is None:
        return None
    elapsed = max(time.monotonic() - started_at, 0.0)
    remaining = int(request_timeout_seconds - elapsed - reserve_seconds)
    return max(0, remaining)


def _resolve_safe_continuation_timeout(
    request_timeout_seconds: int | None,
    started_at: float,
    *,
    preferred_continuation_timeout: int | None,
    preferred_closing_timeout: int | None,
) -> int | None:
    if preferred_continuation_timeout is None:
        return None
    preferred = max(int(preferred_continuation_timeout), 8)
    hard_min = max(int(getattr(settings, "chapter_continuation_min_timeout_seconds", 36) or 36), 8)
    share = float(getattr(settings, "chapter_continuation_timeout_share", 0.62) or 0.62)
    share = max(min(share, 0.9), 0.35)
    closing_reserve = max(
        int(
            getattr(
                settings,
                "chapter_continuation_closing_reserve_seconds",
                max(preferred_closing_timeout or 0, int(getattr(settings, "chapter_closing_timeout_seconds", 28) or 28)),
            )
            or max(preferred_closing_timeout or 0, int(getattr(settings, "chapter_closing_timeout_seconds", 28) or 28))
        ),
        8,
    )
    remaining_total = _remaining_request_budget_seconds(request_timeout_seconds, started_at)
    if remaining_total is None:
        return preferred
    usable = max(remaining_total - closing_reserve, 0)
    if usable < hard_min:
        return None
    dynamic_timeout = max(hard_min, int(usable * share))
    return min(preferred, dynamic_timeout, usable)


def _resolve_safe_closing_timeout(
    request_timeout_seconds: int | None,
    started_at: float,
    *,
    preferred_closing_timeout: int | None,
) -> int | None:
    if preferred_closing_timeout is None:
        return None
    preferred = max(int(preferred_closing_timeout), 8)
    remaining_total = _remaining_request_budget_seconds(request_timeout_seconds, started_at)
    if remaining_total is None:
        return preferred
    minimum = max(min(preferred, 12), 8)
    if remaining_total >= preferred:
        return preferred
    if remaining_total >= minimum:
        return remaining_total
    return max(8, remaining_total)


def _chapter_max_total_visible_chars(target_visible_chars_max: int) -> int:
    configured_cap = max(int(getattr(settings, "chapter_body_total_visible_chars_cap", 0) or 0), 0)
    dynamic_floor = max(int(target_visible_chars_max * 1.85), target_visible_chars_max + 600)
    if configured_cap <= 0:
        return dynamic_floor
    return max(configured_cap, target_visible_chars_max + 200)


def _tail_is_stable_for_continue(text: str) -> bool:
    raw = (text or "").rstrip()
    if not raw:
        return False
    if raw[-1] not in "。！？!?…；;”』」》）)】":
        return False
    paired = (("“", "”"), ('"', '"'), ("『", "』"), ("「", "」"), ("（", "）"), ("(", ")"))
    for left, right in paired:
        if raw.count(left) > raw.count(right):
            return False
    return True


def _should_continue_body_generation(
    *,
    content: str,
    chapter_plan: dict[str, Any],
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    max_total_visible_chars: int,
    current_segments: int,
    max_segments: int,
) -> tuple[bool, str]:
    if current_segments >= max_segments:
        return False, "segment_cap_reached"

    current_len = len((content or "").strip())
    min_growth = max(int(getattr(settings, "chapter_body_continuation_min_growth_chars", 180) or 180), 20)
    force_closing_margin = max(int(getattr(settings, "chapter_body_force_closing_margin_chars", 220) or 220), 80)
    remaining_room = max_total_visible_chars - current_len
    if remaining_room < max(min_growth, force_closing_margin):
        return False, "budget_margin_reached"

    progress_kind = str(chapter_plan.get("progress_kind") or "").strip() or None
    progress_clear, _ = _progress_result_is_clear(content, progress_kind, chapter_plan=chapter_plan)
    weak_ending_pattern = _weak_ending(content)
    tail_stable = _tail_is_stable_for_continue(content)

    if current_len < target_visible_chars_min:
        return True, "below_target_min"
    if not tail_stable and current_len < max_total_visible_chars - force_closing_margin:
        return True, "tail_not_stable"
    if (not progress_clear) and current_len < min(target_visible_chars_max + force_closing_margin, max_total_visible_chars - force_closing_margin):
        return True, "progress_not_clear"
    if weak_ending_pattern and current_len < min(target_visible_chars_max + force_closing_margin, max_total_visible_chars - force_closing_margin):
        return True, "ending_still_weak"
    return False, "ready_for_closing"


def _should_run_chapter_closing(
    *,
    content: str,
    chapter_plan: dict[str, Any],
    target_visible_chars_min: int,
    body_stop_reason: str | None,
) -> tuple[bool, str]:
    current_len = len((content or "").strip())
    progress_kind = str(chapter_plan.get("progress_kind") or "").strip() or None
    progress_clear, _ = _progress_result_is_clear(content, progress_kind, chapter_plan=chapter_plan)
    weak_ending_pattern = _weak_ending(content)
    tail_stable = _tail_is_stable_for_continue(content)

    force_reasons = {
        "continuation_timeout_fallback_to_closing",
        "insufficient_time_for_safe_continuation",
        "continuation_growth_too_small",
    }
    if (body_stop_reason or "") in force_reasons:
        return True, str(body_stop_reason)
    if current_len < target_visible_chars_min:
        return True, "below_target_min"
    if not tail_stable:
        return True, "tail_not_stable"
    if weak_ending_pattern:
        return True, "ending_still_weak"
    if not progress_clear:
        return True, "progress_not_clear"
    return False, "body_ready_skip_closing"


def _dedupe_tail_overlap(base: str, addition: str, *, min_overlap: int = 8, max_overlap: int = 120) -> str:
    base_text = base or ""
    extra = addition or ""
    if not base_text or not extra:
        return extra
    limit = min(len(base_text), len(extra), max_overlap)
    for size in range(limit, min_overlap - 1, -1):
        if base_text[-size:] == extra[:size]:
            return extra[size:]
    return extra


def _merge_generated_closing(base: str, addition: str) -> str:
    base_text = (base or "").rstrip()
    extra = (addition or "").strip()
    if not extra:
        return base_text
    if not base_text:
        return extra
    if extra in base_text[-max(len(extra) + 24, 260):]:
        return base_text
    extra = _dedupe_tail_overlap(base_text, extra).lstrip()
    if not extra:
        return base_text
    terminal = "。！？!?…；;”』」》）)】"
    inline_starts = tuple("，。！？!?；;：:、）)】」』》」”’")
    if base_text[-1] in terminal and not extra.startswith(inline_starts):
        return f"{base_text}\n\n{extra}".strip()
    return f"{base_text}{extra}".strip()


def _generate_body_continuation(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    target_visible_chars_min: int,
    target_visible_chars_max: int,
    continuation_target_visible_chars_min: int,
    continuation_target_visible_chars_max: int,
    continuation_round: int,
    max_segments: int,
    timeout_seconds: int | None,
    call_text_response_fn,
) -> str:
    text = call_text_response_fn(
        stage="chapter_generation_continue",
        system_prompt=chapter_body_continue_system_prompt(),
        user_prompt=chapter_body_continue_user_prompt(
            chapter_plan=chapter_plan,
            existing_content=existing_content,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            continuation_target_visible_chars_min=continuation_target_visible_chars_min,
            continuation_target_visible_chars_max=continuation_target_visible_chars_max,
            continuation_round=continuation_round,
            max_segments=max_segments,
        ),
        max_output_tokens=max(int(getattr(settings, "chapter_body_continuation_max_output_tokens", 720) or 720), 220),
        timeout_seconds=timeout_seconds,
    )
    return _clean_plain_chapter_text(text, expected_title=None)


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
    *,
    call_text_response_fn,
    current_chapter_max_output_tokens_fn,
) -> ChapterDraftPayload:
    phase_targets = _chapter_phase_visible_char_targets(
        target_visible_chars_min=target_visible_chars_min,
        target_visible_chars_max=target_visible_chars_max,
    )
    generation_started_at = time.monotonic()
    max_segments = max(int(getattr(settings, "chapter_body_max_segments", 2) or 2), 1)
    body_timeout, continuation_timeout, closing_timeout = _chapter_phase_timeouts(
        request_timeout_seconds,
        max_segments=max_segments,
    )
    body_token_ratio = float(getattr(settings, "chapter_body_max_output_tokens_ratio", 0.78) or 0.78)
    body_token_ratio = max(min(body_token_ratio, 0.95), 0.45)
    body_max_output_tokens = min(
        current_chapter_max_output_tokens_fn(),
        max(int(current_chapter_max_output_tokens_fn() * body_token_ratio), 700),
    )

    body_text = call_text_response_fn(
        stage="chapter_generation_body",
        system_prompt=chapter_body_draft_system_prompt(),
        user_prompt=chapter_body_draft_user_prompt(
            novel_context=novel_context,
            chapter_plan=chapter_plan,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            active_interventions=active_interventions,
            target_words=target_words,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            body_target_visible_chars_min=phase_targets["body_min"],
            body_target_visible_chars_max=phase_targets["body_max"],
        ),
        max_output_tokens=body_max_output_tokens,
        timeout_seconds=body_timeout,
    )
    body_content = _clean_plain_chapter_text(body_text, expected_title=chapter_plan.get("title"))
    body_segments = 1
    continuation_rounds = 0
    body_stop_reason = "initial_body_complete"

    dynamic_enabled = bool(getattr(settings, "chapter_dynamic_continuation_enabled", True))
    continuation_target_min = max(int(getattr(settings, "chapter_body_continuation_target_min_visible_chars", 360) or 360), 120)
    continuation_target_max = max(
        int(getattr(settings, "chapter_body_continuation_target_max_visible_chars", 900) or 900),
        continuation_target_min,
    )
    min_growth = max(int(getattr(settings, "chapter_body_continuation_min_growth_chars", 180) or 180), 80)
    max_total_visible_chars = _chapter_max_total_visible_chars(target_visible_chars_max)

    while dynamic_enabled:
        should_continue, reason = _should_continue_body_generation(
            content=body_content,
            chapter_plan=chapter_plan,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            max_total_visible_chars=max_total_visible_chars,
            current_segments=body_segments,
            max_segments=max_segments,
        )
        body_stop_reason = reason
        if not should_continue:
            break

        remaining_room = max(max_total_visible_chars - len(body_content), 0)
        if remaining_room < min_growth:
            body_stop_reason = "growth_margin_reached"
            break

        dynamic_max = min(continuation_target_max, remaining_room)
        dynamic_min = min(continuation_target_min, dynamic_max)
        required_growth = max(min(dynamic_min // 3, 80), 24)
        if dynamic_max <= 0:
            body_stop_reason = "no_room_for_continuation"
            break

        round_continuation_timeout = _resolve_safe_continuation_timeout(
            request_timeout_seconds,
            generation_started_at,
            preferred_continuation_timeout=continuation_timeout,
            preferred_closing_timeout=closing_timeout,
        )
        if round_continuation_timeout is None:
            body_stop_reason = "insufficient_time_for_safe_continuation"
            break

        try:
            addition = _generate_body_continuation(
                chapter_plan=chapter_plan,
                existing_content=body_content,
                last_chapter=last_chapter,
                recent_summaries=recent_summaries,
                target_visible_chars_min=target_visible_chars_min,
                target_visible_chars_max=target_visible_chars_max,
                continuation_target_visible_chars_min=dynamic_min,
                continuation_target_visible_chars_max=dynamic_max,
                continuation_round=continuation_rounds + 1,
                max_segments=max_segments,
                timeout_seconds=round_continuation_timeout,
                call_text_response_fn=call_text_response_fn,
            )
        except GenerationError as exc:
            if exc.code == ErrorCodes.API_TIMEOUT and exc.stage == "chapter_generation_continue":
                logger.warning(
                    "chapter continuation timed out; falling back to closing novel_id_like=%s chapter_no=%s timeout=%s",
                    (chapter_plan.get("novel_id") or chapter_plan.get("trace_id") or "unknown"),
                    chapter_plan.get("chapter_no"),
                    round_continuation_timeout,
                )
                body_stop_reason = "continuation_timeout_fallback_to_closing"
                break
            raise
        merged = _merge_generated_closing(body_content, addition)
        growth = len(merged) - len(body_content)
        if growth < required_growth:
            body_stop_reason = "continuation_growth_too_small"
            break
        body_content = merged
        body_segments += 1
        continuation_rounds += 1

    final_content = body_content
    closing_reason = "chapter_closing_disabled"
    if getattr(settings, "chapter_closing_enabled", True):
        should_run_closing, closing_reason = _should_run_chapter_closing(
            content=body_content,
            chapter_plan=chapter_plan,
            target_visible_chars_min=target_visible_chars_min,
            body_stop_reason=body_stop_reason,
        )
        if should_run_closing:
            dynamic_closing_cap = max_total_visible_chars if continuation_rounds > 0 else target_visible_chars_max
            dynamic_closing_max = max(
                phase_targets["closing_min"],
                min(phase_targets["closing_max"], max(dynamic_closing_cap - len(body_content), phase_targets["closing_min"])),
            )
            dynamic_closing_min = min(phase_targets["closing_min"], dynamic_closing_max)
            effective_closing_timeout = _resolve_safe_closing_timeout(
                request_timeout_seconds,
                generation_started_at,
                preferred_closing_timeout=closing_timeout,
            )
            closing_text = call_text_response_fn(
                stage="chapter_generation_closing",
                system_prompt=chapter_closing_system_prompt(),
                user_prompt=chapter_closing_user_prompt(
                    chapter_plan=chapter_plan,
                    existing_content=body_content,
                    last_chapter=last_chapter,
                    recent_summaries=recent_summaries,
                    target_visible_chars_min=target_visible_chars_min,
                    target_visible_chars_max=dynamic_closing_cap,
                    closing_target_visible_chars_min=dynamic_closing_min,
                    closing_target_visible_chars_max=dynamic_closing_max,
                ),
                max_output_tokens=max(int(getattr(settings, "chapter_closing_max_output_tokens", 520) or 520), 180),
                timeout_seconds=effective_closing_timeout,
            )
            closing_content = _clean_plain_chapter_text(closing_text, expected_title=None)
            final_content = _merge_generated_closing(body_content, closing_content)
            if body_stop_reason == "initial_body_complete" and continuation_rounds > 0:
                body_stop_reason = "continued_then_closed"

    data = {
        "title": (chapter_plan.get("title") or "").strip() or f"第{chapter_plan.get('chapter_no', '')}章",
        "content": final_content,
        "body_segments": body_segments,
        "continuation_rounds": continuation_rounds,
        "body_stop_reason": body_stop_reason,
        "closing_reason": closing_reason,
    }
    return ChapterDraftPayload.model_validate(data)


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
    call_text_response_fn,
    current_chapter_max_output_tokens_fn,
) -> str:
    mode_token_budget = {
        "append_inline_tail": min(max(current_chapter_max_output_tokens_fn() // 4, 220), 420),
        "replace_last_paragraph": min(max(current_chapter_max_output_tokens_fn() // 3, 360), 620),
        "replace_last_two_paragraphs": min(max(current_chapter_max_output_tokens_fn() // 2, 520), 900),
    }
    text = call_text_response_fn(
        stage="chapter_extension",
        system_prompt=chapter_extension_system_prompt(repair_mode=repair_mode),
        user_prompt=chapter_extension_user_prompt(
            chapter_plan=chapter_plan,
            existing_content=existing_content,
            reason=reason,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
            repair_mode=repair_mode,
            ending_issue=ending_issue,
            repair_attempt_no=repair_attempt_no,
            previous_repair_modes=previous_repair_modes,
        ),
        max_output_tokens=mode_token_budget.get(repair_mode, min(max(current_chapter_max_output_tokens_fn() // 3, 360), 620)),
        timeout_seconds=request_timeout_seconds,
    )
    return _clean_plain_chapter_text(text, expected_title=None)



