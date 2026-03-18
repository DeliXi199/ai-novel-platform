from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.services.hard_fact_guard_utils import _clean_text
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, is_openai_enabled, provider_name
from app.services.prompt_support import compact_json, middle_excerpt

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


def _compact_state_for_review(reference_state: dict[str, Any], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for category in ("realm", "life_status", "injury_status", "identity_exposure", "item_ownership"):
        bucket = reference_state.get(category) or {}
        keys: list[str] = []
        for conflict in conflicts:
            if conflict.get("category") != category:
                continue
            keys.append(str(conflict.get("subject") or ""))
            prev = conflict.get("previous")
            if prev is not None and category == "item_ownership":
                keys.append(str(prev))
        dedup = [key for idx, key in enumerate(keys) if key and key not in keys[:idx]]
        if dedup:
            compact[category] = {key: bucket.get(key) for key in dedup if key in bucket}
    return compact


def _hard_fact_review_system_prompt() -> str:
    return (
        "你是长篇网络连载小说的硬事实冲突复核器。\n"
        "任务：阅读当前章节内容、本地规则抽取出的硬事实和冲突报告，判断这些冲突是否为真正的高风险硬事实冲突。\n"
        "仅输出 JSON，不要输出额外说明。"
    )


def _hard_fact_review_user_prompt(*, chapter_no: int, chapter_title: str, serial_stage: str, content: str, reference_state: dict[str, Any], facts: dict[str, Any], conflicts: list[dict[str, Any]]) -> str:
    compact_conflicts = conflicts[:8]
    compact_facts = {key: facts.get(key) for key in list((facts or {}).keys())[:8]}
    compact_reference = _compact_state_for_review(reference_state, compact_conflicts)
    content_excerpt = middle_excerpt(content, max_chars=1800)
    return (
        f"chapter_no: {chapter_no}\n"
        f"chapter_title: {chapter_title}\n"
        f"serial_stage: {serial_stage}\n\n"
        "请复核下面这些本地规则判定出的硬事实冲突。\n"
        "对于每个 conflict，请给出：\n"
        "- index: 冲突索引（从 0 开始）\n"
        "- verdict: confirm / reject / uncertain\n"
        "- confidence: high / medium / low\n"
        "- reason: 20~60字中文简述\n\n"
        "判定标准：\n"
        "- confirm：确实构成高风险硬事实冲突，应拦截。\n"
        "- reject：只是关键词误判、语义歧义、叙述视角偏差，不应拦截。\n"
        "- uncertain：信息不足，但宁可保留为冲突。\n\n"
        "输出格式：\n"
        '{"decisions":[{"index":0,"verdict":"confirm|reject|uncertain","confidence":"high|medium|low","reason":"..."}]}\n\n'
        f"reference_state:\n{json.dumps(reference_state, ensure_ascii=False, indent=2)}\n\n"
        f"facts:\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        f"conflicts:\n{json.dumps(conflicts, ensure_ascii=False, indent=2)}\n\n"
        f"chapter_content:\n{content[:2500]}"
    )


def _should_use_llm_hard_fact_review() -> bool:
    return bool(getattr(settings, "enable_llm_hard_fact_review", True))


def _review_hard_fact_conflicts_with_llm(
    *,
    chapter_no: int,
    chapter_title: str,
    serial_stage: str,
    content: str,
    reference_state: dict[str, Any],
    facts: dict[str, Any],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not conflicts or not _should_use_llm_hard_fact_review():
        return None
    if not is_openai_enabled():
        return None

    limited = conflicts[: max(int(getattr(settings, "hard_fact_llm_max_conflicts_per_review", 4) or 4), 1)]
    try:
        data = call_json_response(
            stage="hard_fact_llm_review",
            system_prompt=_hard_fact_review_system_prompt(),
            user_prompt=_hard_fact_review_user_prompt(
                chapter_no=chapter_no,
                chapter_title=chapter_title,
                serial_stage=serial_stage,
                content=content,
                reference_state=_compact_state_for_review(reference_state, limited),
                facts=facts,
                conflicts=limited,
            ),
            max_output_tokens=int(getattr(settings, "hard_fact_llm_max_output_tokens", 700) or 700),
            timeout_seconds=int(getattr(settings, "hard_fact_llm_timeout_seconds", 25) or 25),
        )
        if isinstance(data, dict):
            return data
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message="hard_fact_llm_review 失败：AI 未返回有效的冲突复核结果。",
            stage="hard_fact_llm_review",
            retryable=True,
            http_status=422,
            provider=provider_name(),
        )
    except GenerationError:
        raise
    except Exception as exc:  # pragma: no cover - network/provider instability
        logger.warning("hard_fact_llm_review failed provider=%s chapter=%s error=%s", provider_name(), chapter_no, exc)
        _raise_ai_required_error(
            stage="hard_fact_llm_review",
            message="硬事实冲突复核失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )


def _apply_llm_review_to_report(report: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(review, dict):
        return report

    decisions_raw = review.get("decisions")
    if not isinstance(decisions_raw, list):
        return report

    decision_map: dict[int, dict[str, Any]] = {}
    for item in decisions_raw:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except Exception:
            continue
        decision_map[index] = item

    original_conflicts = list(report.get("conflicts") or [])
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reviewed: list[dict[str, Any]] = []
    for idx, conflict in enumerate(original_conflicts):
        decision = decision_map.get(idx) or {}
        verdict = str(decision.get("verdict") or "uncertain").strip().lower()
        annotated = {
            **conflict,
            "llm_review": {
                "verdict": verdict if verdict in {"confirm", "reject", "uncertain"} else "uncertain",
                "confidence": str(decision.get("confidence") or "").strip().lower() or None,
                "reason": _clean_text(decision.get("reason"), 160),
            },
        }
        reviewed.append(annotated)
        if verdict == "reject":
            rejected.append(annotated)
        else:
            kept.append(annotated)

    merged = dict(report)
    merged["conflicts"] = kept
    merged["conflict_count"] = len(kept)
    merged["passed"] = not kept
    merged["summary"] = "未发现高风险硬事实冲突。" if not kept else f"发现 {len(kept)} 条高风险硬事实冲突。"
    merged["llm_review"] = {
        "enabled": True,
        "rejected_conflict_count": len(rejected),
        "confirmed_or_kept_conflict_count": len(kept),
        "reviewed_conflict_count": len(reviewed),
        "decisions": [item.get("llm_review") for item in reviewed],
    }
    return merged
