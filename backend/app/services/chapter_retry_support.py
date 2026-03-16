from __future__ import annotations

import logging
import time
from typing import Any

from app.core.config import settings
from app.models.novel import Novel
from app.services.agency_modes import apply_agency_mode_to_plan, select_agency_mode
from app.services.chapter_generation_support import _similarity
from app.services.chapter_quality import build_quality_feedback, validate_chapter_content
from app.services.chapter_repair_pipeline import classify_chapter_repair, execute_llm_repair
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.openai_story_engine import generate_chapter_from_plan
from app.services.chapter_runtime_support import (
    _compute_llm_timeout_seconds,
    _ensure_generation_runtime_budget,
    _should_stop_retrying_for_budget,
)

logger = logging.getLogger(__name__)


def _chapter_length_targets(plan: dict[str, Any]) -> dict[str, int | str]:
    chapter_type = str(plan.get("chapter_type") or "").strip().lower()
    if chapter_type not in {"probe", "progress", "turning_point"}:
        goal_text = f"{plan.get('goal') or ''} {plan.get('conflict') or ''} {plan.get('ending_hook') or ''}"
        if any(token in goal_text for token in ["追", "逃", "转折", "对峙", "揭示", "伏击", "矿"]):
            chapter_type = "turning_point"
        elif any(token in goal_text for token in ["查", "换", "买", "谈", "坊市", "交易", "跟踪"]):
            chapter_type = "progress"
        else:
            chapter_type = "probe"

    if chapter_type == "turning_point":
        target_min = settings.chapter_turning_point_target_min_visible_chars
        target_max = settings.chapter_turning_point_target_max_visible_chars
    elif chapter_type == "progress":
        target_min = settings.chapter_progress_target_min_visible_chars
        target_max = settings.chapter_progress_target_max_visible_chars
    else:
        target_min = settings.chapter_probe_target_min_visible_chars
        target_max = settings.chapter_probe_target_max_visible_chars

    if int(plan.get("target_visible_chars_min") or 0) > 0:
        target_min = int(plan["target_visible_chars_min"])
    if int(plan.get("target_visible_chars_max") or 0) > 0:
        target_max = int(plan["target_visible_chars_max"])

    hard_min = min(settings.chapter_hard_min_visible_chars, target_min)
    target_words = max(settings.chapter_target_words, int((target_min + target_max) / 2 * 0.9))
    return {
        "chapter_type": chapter_type,
        "target_visible_chars_min": target_min,
        "target_visible_chars_max": target_max,
        "hard_min_visible_chars": hard_min,
        "target_words": target_words,
    }




def _enrich_plan_agency(
    novel: Novel,
    plan: dict[str, Any],
    *,
    recent_plan_meta: list[dict[str, Any]] | None = None,
    preferred_mode: str | None = None,
    exclude_modes: set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    mode_spec = select_agency_mode(
        plan,
        genre_text=f"{novel.genre} {(novel.style_preferences or {}).get('story_engine', '')}",
        premise_text=novel.premise or "",
        style_preferences=novel.style_preferences or {},
        protagonist_name=novel.protagonist_name or "",
        recent_plan_meta=recent_plan_meta,
        preferred_mode=preferred_mode,
        exclude_modes=exclude_modes,
    )
    enriched = apply_agency_mode_to_plan(plan, mode_spec, recent_plan_meta=recent_plan_meta, force=force)
    plan.clear()
    plan.update(enriched)
    return plan



def _is_agency_failure(exc: GenerationError) -> bool:
    if exc.code != ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK:
        return False
    message = str(exc.message or "")
    details = exc.details if isinstance(exc.details, dict) else {}
    return ("主动性不足" in message) or ("proactive_hits" in details) or ("passive_drift_hits" in details)



def _stronger_proactive_move(plan: dict[str, Any]) -> str:
    progress_kind = str(plan.get("progress_kind") or "").strip()
    event_type = str(plan.get("event_type") or "").strip()
    current = str(plan.get("proactive_move") or "").strip()
    weak_tokens = {"主动做出判断并推动局势前进", "主动做出判断并推动局势前进。", "谨慎应对", "观察局势", "主动应对"}
    if current and current not in weak_tokens and len(current) >= 6:
        return current
    mapping = {
        "信息推进": "主动设问试探并当场验证异常",
        "关系推进": "主动递话换条件并试出对方立场",
        "资源推进": "主动压价换资源并藏住真实底牌",
        "实力推进": "主动冒一次险验证手段上限",
        "风险升级": "主动布置退路后抢先反制",
        "地点推进": "主动借口切入新地点并先摸规矩",
    }
    fallback = {
        "冲突类": "主动抢先一步试探并逼出回应",
        "危机爆发": "主动脱身并保住关键筹码",
        "资源获取类": "主动压价换取资源并拿回主动权",
        "关系推进类": "主动递话设问并交换条件",
    }
    return mapping.get(progress_kind) or fallback.get(event_type) or "主动先手试探并逼出回应"



def _make_agency_retry_plan(
    plan: dict[str, Any],
    *,
    details: dict[str, Any] | None = None,
    novel: Novel | None = None,
    recent_plan_meta: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    retry_plan = dict(plan)
    current_mode = str(plan.get("agency_mode") or "").strip()
    if novel is not None:
        retry_plan = _enrich_plan_agency(
            novel,
            retry_plan,
            recent_plan_meta=recent_plan_meta,
            exclude_modes={current_mode} if current_mode else None,
            force=True,
        )
    proactive_move = _stronger_proactive_move(retry_plan)
    opening = str(retry_plan.get("opening_beat") or "").strip()
    mid_turn = str(retry_plan.get("mid_turn") or "").strip()
    discovery = str(retry_plan.get("discovery") or "").strip()
    closing = str(retry_plan.get("closing_image") or retry_plan.get("ending_hook") or "").strip()
    note = (retry_plan.get("writing_note") or "").strip()
    passive_hits = int(((details or {}).get("passive_drift_hits") or 0))
    proactive_hits = int(((details or {}).get("proactive_hits") or 0))
    agency_fit_hits = int(((details or {}).get("agency_fit_hits") or 0))
    retry_label = str(retry_plan.get("agency_mode_label") or retry_plan.get("agency_mode") or "新的主动方式")
    from_label = str(plan.get("agency_mode_label") or plan.get("agency_mode") or "原主动方式")
    correction = (
        f"上一版草稿主角主动性不足（proactive_hits={proactive_hits}, passive_drift_hits={passive_hits}, agency_fit_hits={agency_fit_hits}）。"
        f"这次把本章主动方式切到“{retry_label}”，不要重复上一版“{from_label}”写法。"
        f"主动作要写实：{proactive_move}。"
        "开头两段内就让主角先动手、先开口、先试探、先验证或先改条件，别先站着看。"
        "中段受阻后，主角必须立刻追加第二个动作，形成‘先手 -> 受阻 -> 调整/加码 -> 结果’的完整链条。"
        "结尾的变化最好直接由主角本章的先手动作引发。"
    )
    retry_plan["proactive_move"] = proactive_move
    retry_plan["opening_beat"] = (opening + "；开场前两段就让主角先做动作、试探、验证或改条件，别先被动观察。").strip('；')
    retry_plan["mid_turn"] = (mid_turn + "；受阻后主角必须再追一步，主动换方法、换筹码、设局、藏证或反制。").strip('；')
    retry_plan["discovery"] = (discovery + "；这份发现必须来自主角亲手验证、试出来、逼出来或换出来。").strip('；')
    retry_plan["closing_image"] = (closing + "；收尾落在主角先手后的具体后果、筹码变化、关系变动或对手反应上。").strip('；')
    retry_plan["writing_note"] = f"{note}；{correction}".strip('；') if note else correction
    retry_plan["retry_focus"] = "agency"
    retry_plan["retry_feedback"] = {
        "problem": "上一版草稿主角偏被动",
        "switch_mode_from": from_label,
        "switch_mode_to": retry_label,
        "required_fix": proactive_move,
        "must_have_chain": "主角先手 -> 外界反应 -> 主角调整或加码",
        "forbidden": ["站着听", "只是观察", "压下念头", "没有立刻行动"],
    }
    return retry_plan





def _build_attempt_plans(plan: dict[str, Any]) -> list[dict[str, Any]]:
    max_attempts = max(int(settings.chapter_draft_max_attempts), 1)
    attempts: list[dict[str, Any]] = [dict(plan)]
    if max_attempts <= 1:
        return attempts

    base_note = (plan.get("writing_note") or "").strip()
    variants = [
        "进一步拉开与最近章节的句式距离，换开场动作、换感官、换结尾方式，减少‘不是错觉/心跳快了/若有若无/温凉/微弱’这类高频表达，并至少写出一两句更有棱角的具体句子。",
        "把配角写得更像人：给重复出现的人物一个职业习惯、说话方式、利益诉求或顾虑，不要只让他负责抛信息。若有反派或帮众，要补一处让人记住的危险细节。",
        "本章必须让主角显式主动一次：试探、设局、换取资源、引导误判、借规则或抢先出手，不要只写被动应对。",
        "前两段内就让主角先动手、先设问、先压价或先换条件，形成‘主角先手 -> 外界反应 -> 主角加码’的动作链，不要先站着看局势。",
        "这次章末可以平稳过渡或余味收束，不必硬留悬念，但必须有结果落地或人物选择，而且不能用‘回去休息/明日再看’这种平钩子。",
        "对话和动作链要更分人，避免所有角色都用同一种冷硬叙述腔；主角在离别、损失、抉择处，情绪再沉半层，但通过动作和停顿去表现。",
    ]

    for i, extra in enumerate(variants, start=1):
        variant = dict(plan)
        compact_after = int(getattr(settings, "chapter_retry_compact_prompt_after_attempt", 2) or 2)
        variant["retry_prompt_mode"] = "compact" if i + 1 >= compact_after else variant.get("retry_prompt_mode")
        merged = f"{base_note}；{extra}" if base_note else extra
        variant["writing_note"] = merged
        if i >= 3 and variant.get("hook_style") not in {"平稳过渡", "余味收束"}:
            variant["hook_style"] = "平稳过渡"
            if variant.get("ending_hook"):
                variant["ending_hook"] = f"{variant['ending_hook']}（也可改为自然过渡收束）"
        attempts.append(variant)
        if len(attempts) >= max_attempts:
            break
    return attempts[:max_attempts]




def _validate_candidate_content(
    *,
    title: str,
    content: str,
    targets: dict[str, int | str],
    recent_full_texts: list[str],
    attempt_plan: dict[str, Any],
    recent_plan_meta: list[dict[str, Any]] | None,
) -> None:
    validate_chapter_content(
        title=title,
        content=content,
        min_visible_chars=int(targets["target_visible_chars_min"]),
        hard_min_visible_chars=int(targets["hard_min_visible_chars"]),
        recent_chapter_texts=recent_full_texts,
        similarity_checker=_similarity,
        max_similarity=settings.chapter_similarity_threshold,
        target_visible_chars_max=int(targets["target_visible_chars_max"]),
        hook_style=str(attempt_plan.get("hook_style") or ""),
        chapter_plan=attempt_plan,
        recent_plan_meta=recent_plan_meta,
    )



def _record_quality_rejection(
    exc: GenerationError,
    *,
    quality_rejections: list[dict[str, Any]],
    attempt_no: int,
    attempt_plan: dict[str, Any],
    repair_attempt: bool = False,
    repair_mode: str | None = None,
) -> None:
    if exc.stage != "chapter_quality":
        return
    quality_feedback = build_quality_feedback(exc)
    quality_feedback["attempt_no"] = attempt_no
    quality_feedback["plan_title"] = attempt_plan.get("title")
    if repair_attempt:
        quality_feedback["repair_attempt"] = True
    if repair_mode:
        quality_feedback["repair_mode"] = repair_mode
    quality_rejections.append(quality_feedback)
    if isinstance(exc.details, dict):
        exc.details = {**exc.details, "quality_feedback": quality_feedback, "quality_rejections": quality_rejections[-6:]}



def _make_success_payload(
    *,
    content: str,
    draft_payload: dict[str, Any],
    repair_mode: str | None = None,
    repair_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(draft_payload)
    payload["content"] = content
    if repair_mode:
        payload["ending_repair_mode"] = repair_mode
    if repair_trace:
        payload["repair_trace"] = repair_trace
    return payload



def _attempt_generate_validated_chapter(
    *,
    novel_context: dict[str, Any],
    plan: dict[str, Any],
    serialized_last: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    serialized_active: list[dict[str, Any]],
    recent_full_texts: list[str],
    recent_plan_meta: list[dict[str, Any]] | None = None,
    chapter_no: int,
    started_at: float,
    novel_ref: Novel | None = None,
) -> tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    attempts = _build_attempt_plans(plan)
    last_error: Exception | None = None
    total_llm_attempt_cap = max(int(getattr(settings, "chapter_total_llm_attempt_cap", 2) or 2), 1)
    quality_rejections: list[dict[str, Any]] = []
    repair_trace: list[dict[str, Any]] = []
    repair_budgets = {
        "too_short": max(int(getattr(settings, "chapter_too_short_retry_attempts", 0) or 0), 0),
        "ending_incomplete": max(int(getattr(settings, "chapter_tail_fix_attempts", 0) or 0), 0),
        "weak_ending": max(int(getattr(settings, "chapter_weak_ending_retry_attempts", 0) or 0), 0),
        "too_messy": max(int(getattr(settings, "chapter_too_messy_retry_attempts", 0) or 0), 0),
    }
    idx = 0
    llm_attempt_count = 0
    while idx < len(attempts):
        if llm_attempt_count >= total_llm_attempt_cap:
            break
        attempt_plan = attempts[idx]
        attempt_no = idx + 1
        if _should_stop_retrying_for_budget(started_at=started_at, attempt_no=attempt_no):
            break
        _ensure_generation_runtime_budget(started_at=started_at, stage="chapter_generation", chapter_no=chapter_no, attempt_no=attempt_no)
        llm_attempt_count += 1
        logger.info("chapter_draft attempt novel_chapter=%s attempt=%s/%s title=%s", chapter_no, attempt_no, len(attempts), attempt_plan.get("title"))
        targets = _chapter_length_targets(attempt_plan)
        chapter_timeout = _compute_llm_timeout_seconds(
            started_at=started_at,
            chapter_no=chapter_no,
            stage="chapter_generation",
            reserve_seconds=max(int(getattr(settings, "chapter_runtime_summary_reserve_seconds", 12) or 12), 0) + 8,
            attempt_no=attempt_no,
        )
        draft = generate_chapter_from_plan(
            novel_context=novel_context,
            chapter_plan=attempt_plan,
            last_chapter=serialized_last,
            recent_summaries=recent_summaries,
            active_interventions=serialized_active,
            target_words=int(targets["target_words"]),
            target_visible_chars_min=int(targets["target_visible_chars_min"]),
            target_visible_chars_max=int(targets["target_visible_chars_max"]),
            request_timeout_seconds=chapter_timeout,
        )
        title = draft.title or attempt_plan["title"]
        content = draft.content
        try:
            _validate_candidate_content(
                title=title,
                content=content,
                targets=targets,
                recent_full_texts=recent_full_texts,
                attempt_plan=attempt_plan,
                recent_plan_meta=recent_plan_meta,
            )
            return title, content, draft.model_dump(mode="python"), attempt_plan, targets, {
                "total_llm_attempts": llm_attempt_count,
                "quality_rejections": quality_rejections,
                "llm_attempt_cap": total_llm_attempt_cap,
                "repair_trace": repair_trace,
            }
        except GenerationError as exc:
            last_error = exc
            _record_quality_rejection(exc, quality_rejections=quality_rejections, attempt_no=attempt_no, attempt_plan=attempt_plan)
            repair_action = classify_chapter_repair(
                exc,
                attempt_plan=attempt_plan,
                targets=targets,
                repair_trace=repair_trace,
                attempt_no=attempt_no,
            )
            while repair_action and repair_budgets.get(repair_action.repair_type, 0) > 0:
                repair_trace.append({
                    "attempt_no": attempt_no,
                    "repair_type": repair_action.repair_type,
                    "strategy_id": repair_action.strategy_id,
                    "reason": repair_action.reason,
                    "status": "scheduled",
                })
                if repair_action.execution_mode in {"append_inline_tail", "replace_last_paragraph", "replace_last_two_paragraphs"}:
                    _ensure_generation_runtime_budget(started_at=started_at, stage="chapter_extension", chapter_no=chapter_no, attempt_no=attempt_no)
                    extension_timeout = _compute_llm_timeout_seconds(
                        started_at=started_at,
                        chapter_no=chapter_no,
                        stage="chapter_extension",
                        reserve_seconds=max(int(getattr(settings, "chapter_runtime_summary_reserve_seconds", 12) or 12), 0) + 2,
                        attempt_no=attempt_no,
                    )
                    repair_budgets[repair_action.repair_type] -= 1
                    repaired_result = execute_llm_repair(
                        repair_action,
                        title=title,
                        content=content,
                        plan=attempt_plan,
                        targets=targets,
                        request_timeout_seconds=extension_timeout,
                    )
                    if repaired_result:
                        delay_ms = max(int(repair_action.delay_ms or 0), 0)
                        if delay_ms:
                            time.sleep(delay_ms / 1000.0)
                        try:
                            _validate_candidate_content(
                                title=title,
                                content=repaired_result.content,
                                targets=targets,
                                recent_full_texts=recent_full_texts,
                                attempt_plan=attempt_plan,
                                recent_plan_meta=recent_plan_meta,
                            )
                            repair_trace[-1]["status"] = "applied"
                            return title, repaired_result.content, _make_success_payload(
                                content=repaired_result.content,
                                draft_payload=draft.model_dump(mode="python"),
                                repair_mode=repaired_result.strategy_id,
                                repair_trace=repair_trace,
                            ), attempt_plan, targets, {
                                "total_llm_attempts": llm_attempt_count,
                                "quality_rejections": quality_rejections,
                                "llm_attempt_cap": total_llm_attempt_cap,
                                "repair_trace": repair_trace,
                            }
                        except GenerationError as repair_exc:
                            last_error = repair_exc
                            repair_trace[-1]["status"] = "rejected"
                            _record_quality_rejection(
                                repair_exc,
                                quality_rejections=quality_rejections,
                                attempt_no=attempt_no,
                                attempt_plan=attempt_plan,
                                repair_attempt=True,
                                repair_mode=repaired_result.strategy_id,
                            )
                            repair_action = classify_chapter_repair(
                                repair_exc,
                                attempt_plan=attempt_plan,
                                targets=targets,
                                repair_trace=repair_trace,
                                attempt_no=attempt_no,
                            )
                            continue
                    else:
                        repair_trace[-1]["status"] = "no_change"
                    break
                elif repair_action.execution_mode == "insert_retry_attempt" and repair_action.retry_plan:
                    repair_budgets[repair_action.repair_type] -= 1
                    attempts.insert(idx + 1, repair_action.retry_plan)
                    repair_trace[-1]["status"] = "inserted_retry"
                    delay_ms = max(int(repair_action.delay_ms or 0), 0)
                    if delay_ms:
                        time.sleep(delay_ms / 1000.0)
                    idx += 1
                    continue
                break
            if idx >= len(attempts) - 1:
                break
        idx += 1
    if isinstance(last_error, GenerationError):
        details = dict(last_error.details or {})
        details.setdefault("quality_rejections", quality_rejections[-6:])
        details.setdefault("llm_attempt_cap", total_llm_attempt_cap)
        details.setdefault("llm_attempt_count", llm_attempt_count)
        details.setdefault("repair_trace", repair_trace[-8:])
        last_error.details = details
        raise last_error
    if last_error:
        raise last_error
    raise RuntimeError("chapter generation unexpectedly exited without result")
