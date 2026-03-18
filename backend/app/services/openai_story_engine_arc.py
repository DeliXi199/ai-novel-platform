from __future__ import annotations

"""Arc-planning and casting-review helpers extracted from the story engine.

This module owns arc casting review payloads and normalization/application logic so
arc planning code no longer depends on the giant story engine module for these
specialized concerns.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, is_openai_enabled, provider_name
from app.services.prompt_templates import (
    arc_casting_layout_review_system_prompt,
    arc_casting_layout_review_user_prompt,
)


class ArcCastingChapterDecision(BaseModel):
    chapter_no: int
    decision: str | None = None
    stage_casting_action: str | None = None
    stage_casting_target: str | None = None
    note: str | None = None


class ArcCastingLayoutReviewPayload(BaseModel):
    window_verdict: str | None = None
    chapter_adjustments: list[ArcCastingChapterDecision] = Field(default_factory=list)
    avoid_notes: list[str] = Field(default_factory=list)
    review_note: str | None = None


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


def _engine_is_openai_enabled() -> bool:
    try:
        from app.services import openai_story_engine as engine

        return bool(engine.is_openai_enabled())
    except Exception:
        return bool(is_openai_enabled())


def _engine__engine_call_json_response(**kwargs: Any) -> Any:
    try:
        from app.services import openai_story_engine as engine

        return engine._engine_call_json_response(**kwargs)
    except Exception:
        return _engine_call_json_response(**kwargs)


def _chapter_casting_fit_score(chapter: dict[str, Any], action: str) -> int:
    score = 0
    pace = str(chapter.get("pace") or "").strip()
    focus = str(chapter.get("focus") or chapter.get("event_type") or "").strip()
    conflict = str(chapter.get("conflict") or "").strip()
    ending_hook = str(chapter.get("ending_hook") or "").strip()
    progress_kind = str(chapter.get("progress_kind") or "").strip()
    if action == "new_core_entry":
        if pace in {"mid", "fast"}:
            score += 2
        if any(token in focus for token in ["关系", "发现", "试探", "交易", "任务", "危机"]):
            score += 2
        if any(token in ending_hook for token in ["盯上", "露面", "名字", "身份", "出手", "试探"]):
            score += 1
        if progress_kind in {"关系推进", "信息推进", "风险升级"}:
            score += 1
    elif action == "role_refresh":
        if pace in {"slow", "mid"}:
            score += 2
        if any(token in focus for token in ["关系", "发现", "反制", "任务", "潜入"]):
            score += 2
        if any(token in conflict for token in ["旧关系", "立场", "身份", "职责", "拉拢", "试探"]):
            score += 1
        if progress_kind in {"关系推进", "信息推进"}:
            score += 1
    return score


def _normalize_arc_casting_layout_review(
    source: dict[str, Any],
    *,
    arc_bundle: dict[str, Any],
    story_bible: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
) -> ArcCastingLayoutReviewPayload:
    chapters = [dict(ch) for ch in (arc_bundle.get("chapters") or []) if isinstance(ch, dict)]
    valid_chapters = {int(ch.get("chapter_no", 0) or 0): ch for ch in chapters if int(ch.get("chapter_no", 0) or 0) > 0}
    diagnostics = ((story_bible or {}).get("character_casting_state") or {}).get("arc_window_diagnostics") or {}
    workspace_state = (story_bible or {}).get("story_workspace") or {}
    retrospective_state = (story_bible or {}).get("retrospective_state") or {}
    review = (
        workspace_state.get("latest_stage_character_review")
        or retrospective_state.get("latest_stage_character_review")
        or (story_bible or {}).get("character_stage_review")
        or {}
    )
    strategy = str(review.get("casting_strategy") or diagnostics.get("recommended_strategy") or "hold_steady").strip() or "hold_steady"
    candidate_slots = {str(x).strip() for x in (review.get("candidate_slot_ids") or diagnostics.get("candidate_slot_ids") or []) if str(x).strip()}
    refresh_targets = {str(x).strip() for x in (review.get("role_refresh_targets") or diagnostics.get("role_refresh_targets") or []) if str(x).strip()}
    new_open = bool(review.get("should_introduce_character") if review.get("should_introduce_character") is not None else diagnostics.get("allow_new_core_entry", False))
    refresh_open = bool(review.get("should_refresh_role_functions") if review.get("should_refresh_role_functions") is not None else diagnostics.get("allow_role_refresh", False))
    max_new = max(0, int(review.get("max_new_core_entries") or diagnostics.get("max_new_core_entries") or 0))
    max_refresh = max(0, int(review.get("max_role_refreshes") or diagnostics.get("max_role_refreshes") or 0))

    adjustments: list[ArcCastingChapterDecision] = []
    for raw in source.get("chapter_adjustments") or []:
        if not isinstance(raw, dict):
            continue
        chapter_no = int(raw.get("chapter_no", 0) or 0)
        if chapter_no not in valid_chapters:
            continue
        decision = str(raw.get("decision") or "").strip() or "keep"
        action = str(raw.get("stage_casting_action") or valid_chapters[chapter_no].get("stage_casting_action") or "").strip() or None
        target = str(raw.get("stage_casting_target") or valid_chapters[chapter_no].get("stage_casting_target") or "").strip() or None
        note = str(raw.get("note") or "").strip()[:72] or None
        if action not in {"new_core_entry", "role_refresh"}:
            continue
        if decision not in {"keep", "drop", "move_here", "soft_consider"}:
            decision = "keep"
        if action == "new_core_entry":
            if not new_open or strategy == "prefer_refresh_existing":
                decision = "drop"
            if target and target not in candidate_slots:
                target = None
        elif action == "role_refresh":
            if not refresh_open or strategy == "introduce_one_new":
                decision = "drop"
            if target and target not in refresh_targets:
                target = None
        adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision=decision, stage_casting_action=action, stage_casting_target=target, note=note))

    if not adjustments:
        dominant = str(diagnostics.get("dominant_defer_cause") or "").strip()
        existing_actions = []
        for ch in chapters:
            action = str(ch.get("stage_casting_action") or "").strip()
            if action in {"new_core_entry", "role_refresh"}:
                existing_actions.append((int(ch.get("chapter_no", 0) or 0), action, str(ch.get("stage_casting_target") or "").strip() or None))
        if strategy == "hold_steady":
            for chapter_no, action, target in existing_actions:
                adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这一轮先稳住现有人物线。"))
        else:
            planned_by_action: dict[str, list[tuple[int, str | None]]] = {}
            for chapter_no, action, target in existing_actions:
                planned_by_action.setdefault(action, []).append((chapter_no, target))
            if dominant in {"chapter_fit", "pacing_mismatch"}:
                for action, rows in planned_by_action.items():
                    if action == "new_core_entry" and (strategy == "prefer_refresh_existing" or not new_open):
                        for chapter_no, target in rows:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这轮先别硬补新人。"))
                        continue
                    if action == "role_refresh" and (strategy == "introduce_one_new" or not refresh_open):
                        for chapter_no, target in rows:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这轮先别硬改旧角色作用位。"))
                        continue
                    best = None
                    best_score = -999
                    for ch in chapters:
                        score = _chapter_casting_fit_score(ch, action)
                        if score > best_score:
                            best = ch
                            best_score = score
                    if best and rows:
                        src_no, target = rows[0]
                        best_no = int(best.get("chapter_no", 0) or 0)
                        if best_no != src_no and best_score >= _chapter_casting_fit_score(valid_chapters[src_no], action) + 2:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=src_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这一章承压更重，人物投放先挪开。"))
                            adjustments.append(ArcCastingChapterDecision(chapter_no=best_no, decision="move_here", stage_casting_action=action, stage_casting_target=target, note="这一章更适合自然落地人物投放动作。"))
            elif dominant == "budget_pressure":
                keep_action = None
                if strategy == "prefer_refresh_existing":
                    keep_action = "role_refresh"
                elif strategy == "introduce_one_new":
                    keep_action = "new_core_entry"
                for action, rows in planned_by_action.items():
                    if keep_action and action != keep_action:
                        for chapter_no, target in rows:
                            adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="窗口预算偏紧，这轮先简化同类动作。"))
        if not adjustments and existing_actions:
            for chapter_no, action, target in existing_actions:
                src = valid_chapters.get(chapter_no, {})
                best = None
                best_score = -999
                for ch in chapters:
                    score = _chapter_casting_fit_score(ch, action)
                    if score > best_score:
                        best = ch
                        best_score = score
                src_score = _chapter_casting_fit_score(src, action)
                best_no = int((best or {}).get("chapter_no", 0) or 0)
                if best_no and best_no != chapter_no and best_score >= src_score + 2:
                    adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=target, note="这一章承压更重，人物投放先挪开。"))
                    adjustments.append(ArcCastingChapterDecision(chapter_no=best_no, decision="move_here", stage_casting_action=action, stage_casting_target=target, note="这一章更适合自然落地人物投放动作。"))
                else:
                    adjustments.append(ArcCastingChapterDecision(chapter_no=chapter_no, decision="keep", stage_casting_action=action, stage_casting_target=target, note="当前排法基本顺，先保持。"))

    filtered: list[ArcCastingChapterDecision] = []
    seen_new = 0
    seen_refresh = 0
    chapter_has_action: dict[int, bool] = {}
    for item in adjustments:
        action = item.stage_casting_action
        chapter_no = int(item.chapter_no or 0)
        if item.decision in {"move_here", "keep"} and action == "new_core_entry":
            if seen_new >= max_new or strategy == "prefer_refresh_existing" or not new_open:
                item = ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=item.stage_casting_target, note=item.note or "这轮新核心位名额不该再继续占用。")
            else:
                seen_new += 1
        elif item.decision in {"move_here", "keep"} and action == "role_refresh":
            if seen_refresh >= max_refresh or strategy == "introduce_one_new" or not refresh_open:
                item = ArcCastingChapterDecision(chapter_no=chapter_no, decision="drop", stage_casting_action=action, stage_casting_target=item.stage_casting_target, note=item.note or "这轮旧角色换功能名额不该再继续占用。")
            else:
                seen_refresh += 1
        if item.decision in {"move_here", "keep"} and chapter_has_action.get(chapter_no):
            item = ArcCastingChapterDecision(chapter_no=chapter_no, decision="soft_consider", stage_casting_action=action, stage_casting_target=item.stage_casting_target, note=item.note or "这一章已有别的人物投放动作，别同章双塞。")
        if item.decision in {"move_here", "keep"} and action:
            chapter_has_action[chapter_no] = True
        filtered.append(item)

    verdict = str(source.get("window_verdict") or "").strip()
    if verdict not in {"keep_current_layout", "shift_actions", "simplify_actions", "hold_steady"}:
        if any(item.decision == "move_here" for item in filtered):
            verdict = "shift_actions"
        elif any(item.decision == "drop" for item in filtered):
            verdict = "simplify_actions" if strategy in {"hold_steady", "prefer_refresh_existing", "introduce_one_new"} else "shift_actions"
        else:
            verdict = "keep_current_layout"

    avoid_notes = [str(x).strip()[:48] for x in (source.get("avoid_notes") or []) if str(x).strip()][:4]
    if not avoid_notes and diagnostics.get("summary"):
        avoid_notes.append(str(diagnostics.get("summary"))[:48])
    review_note = str(source.get("review_note") or "").strip()[:88]
    if not review_note:
        review_note = "这轮人物投放动作按窗口策略微调，尽量把动作落在更顺手的章节。"
    return ArcCastingLayoutReviewPayload(window_verdict=verdict, chapter_adjustments=filtered[:8], avoid_notes=avoid_notes, review_note=review_note)


def review_arc_casting_layout(
    *,
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    arc_bundle: dict[str, Any],
    request_timeout_seconds: int | None = None,
) -> ArcCastingLayoutReviewPayload:
    if not _engine_is_openai_enabled():
        return _normalize_arc_casting_layout_review(
            {"source": "heuristic"},
            arc_bundle=arc_bundle,
            story_bible=story_bible,
            recent_summaries=recent_summaries,
        )
    timeout_seconds = request_timeout_seconds or int(getattr(settings, "arc_casting_layout_review_timeout_seconds", 10) or 10)
    max_output_tokens = max(int(getattr(settings, "arc_casting_layout_review_max_output_tokens", 420) or 420), 180)
    try:
        data = _engine_call_json_response(
            stage="arc_casting_layout_review",
            system_prompt=arc_casting_layout_review_system_prompt(),
            user_prompt=arc_casting_layout_review_user_prompt(
                payload=payload,
                story_bible=story_bible,
                global_outline=global_outline,
                recent_summaries=recent_summaries,
                arc_bundle=arc_bundle,
            ),
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        return _normalize_arc_casting_layout_review(data, arc_bundle=arc_bundle, story_bible=story_bible, recent_summaries=recent_summaries)
    except GenerationError:
        raise
    except Exception:
        return _normalize_arc_casting_layout_review(
            {"source": "heuristic"},
            arc_bundle=arc_bundle,
            story_bible=story_bible,
            recent_summaries=recent_summaries,
        )


def apply_arc_casting_layout_review(
    arc_bundle: dict[str, Any],
    review: ArcCastingLayoutReviewPayload,
) -> dict[str, Any]:
    if not isinstance(arc_bundle, dict):
        return arc_bundle
    chapters = [dict(ch) for ch in (arc_bundle.get("chapters") or []) if isinstance(ch, dict)]
    chapter_map = {int(ch.get("chapter_no", 0) or 0): ch for ch in chapters}
    adjustments = sorted(review.chapter_adjustments, key=lambda item: (int(item.chapter_no or 0), 0 if item.decision == "drop" else 1))
    for item in adjustments:
        ch = chapter_map.get(int(item.chapter_no or 0))
        if not ch:
            continue
        if item.decision == "drop":
            ch.pop("stage_casting_action", None)
            ch.pop("stage_casting_target", None)
            ch.pop("stage_casting_note", None)
            ch["stage_casting_review_note"] = str(item.note or "AI复核后本章先不承担该人物投放动作。")[:72]
        elif item.decision in {"keep", "move_here"}:
            if item.stage_casting_action:
                ch["stage_casting_action"] = item.stage_casting_action
            if item.stage_casting_target:
                ch["stage_casting_target"] = item.stage_casting_target
            note = str(item.note or "AI复核后确认本章更适合承担这个人物投放动作。")[:72]
            ch["stage_casting_note"] = note
            ch["stage_casting_review_note"] = note
        elif item.decision == "soft_consider":
            ch["stage_casting_review_note"] = str(item.note or "这章只适合轻量考虑人物投放动作，别硬塞。")[:72]
    arc_bundle["chapters"] = [chapter_map[int(ch.get("chapter_no", 0) or 0)] for ch in chapters]
    arc_bundle["casting_layout_review"] = review.model_dump(mode="python")
    return arc_bundle


__all__ = [
    "ArcCastingChapterDecision",
    "ArcCastingLayoutReviewPayload",
    "apply_arc_casting_layout_review",
    "review_arc_casting_layout",
]
