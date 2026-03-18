from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Callable

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, current_api_key
from app.services.prompt_support import compact_json
from app.services.story_character_support import _safe_list, _text
from app.services.story_fact_ledger import _now_iso

LOCAL_CONSTRAINT_STAGE = "local_constraint_reasoning"
_RETRYABLE_CODES = {
    ErrorCodes.API_TIMEOUT,
    ErrorCodes.API_CONNECTION_FAILED,
    ErrorCodes.API_RATE_LIMITED,
    ErrorCodes.API_STATUS_ERROR,
    ErrorCodes.MODEL_RESPONSE_INVALID,
}


def build_constraint_reasoning_state() -> dict[str, Any]:
    return {
        "version": 1,
        "status": "foundation_ready",
        "last_task_type": None,
        "last_scope": None,
        "last_chapter": 0,
        "last_run_used_ai": False,
        "last_run_at": None,
        "history": [],
    }



def ensure_constraint_reasoning_state(story_bible: dict[str, Any]) -> dict[str, Any]:
    state = story_bible.setdefault("constraint_reasoning_state", build_constraint_reasoning_state())
    defaults = build_constraint_reasoning_state()
    for key, value in defaults.items():
        if key not in state:
            state[key] = deepcopy(value)
    return state



def _ai_enabled() -> bool:
    return bool(getattr(settings, "local_constraint_reasoning_ai_enabled", True)) and bool(current_api_key(LOCAL_CONSTRAINT_STAGE))



def _raise_ai_required_error(*, task_type: str, scope: str, chapter_no: int = 0, detail_reason: str, retryable: bool) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"{task_type} 失败：AI 不可用，已停止生成。{detail_reason}",
        stage=LOCAL_CONSTRAINT_STAGE,
        retryable=retryable,
        http_status=503 if retryable else 400,
        details={
            "task_type": _text(task_type),
            "scope": _text(scope),
            "chapter_no": int(chapter_no or 0),
            "reason": detail_reason,
        },
    )



def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    if isinstance(base, list) and isinstance(override, list):
        return deepcopy(override or base)
    if override in (None, "", [], {}):
        return deepcopy(base)
    return deepcopy(override)



def _record_history(
    *,
    story_bible: dict[str, Any],
    task_type: str,
    scope: str,
    chapter_no: int,
    used_ai: bool,
    result: dict[str, Any],
    note: dict[str, Any] | None = None,
) -> None:
    state = ensure_constraint_reasoning_state(story_bible)
    state["last_task_type"] = task_type
    state["last_scope"] = scope
    state["last_chapter"] = chapter_no
    state["last_run_used_ai"] = bool(used_ai)
    state["last_run_at"] = _now_iso()
    history = state.setdefault("history", [])
    item = {
        "task_type": task_type,
        "scope": scope,
        "chapter_no": chapter_no,
        "used_ai": bool(used_ai),
        "at": _now_iso(),
        "result_keys": list((result or {}).keys())[:8],
    }
    if note:
        item["note"] = deepcopy(note)
    history.append(item)
    state["history"] = history[-20:]



def _build_reasoning_prompts(*, packet: dict[str, Any], baseline_result: dict[str, Any], compact_mode: bool) -> tuple[str, str, dict[str, int]]:
    local_text_limit = 68 if compact_mode else 96
    local_max_items = 6 if compact_mode else 8
    fallback_text_limit = 56 if compact_mode else 80
    fallback_max_items = 5 if compact_mode else 7
    compact_local_context = compact_json(packet["local_context"], max_depth=3, max_items=local_max_items, text_limit=local_text_limit)
    compact_hard_constraints = compact_json(packet["hard_constraints"], max_depth=2, max_items=8, text_limit=72 if compact_mode else 96)
    compact_soft_goals = compact_json(packet["soft_goals"], max_depth=2, max_items=8, text_limit=72 if compact_mode else 96)
    compact_contract = compact_json(packet["output_contract"], max_depth=3, max_items=7, text_limit=64 if compact_mode else 88)
    compact_baseline = compact_json(baseline_result, max_depth=2, max_items=fallback_max_items, text_limit=fallback_text_limit)

    system_prompt = (
        "你是一个只在局部约束包内思考的小说规划助手。"
        "只能依据给定 local_context / hard_constraints / soft_goals 输出结果，"
        "不得扩写全书设定，不得发明未被约束包支持的硬事实。"
        "输出必须是 JSON，对不确定处要保守，不得突破硬约束。"
        "优先返回相对本地约束种子结果真正需要修改的字段，没必要把整份表重写一遍。"
    )
    user_prompt = (
        "请基于下面的局部约束包完成任务。\n\n"
        f"【任务类型】\n{packet['task_type']}\n\n"
        f"【任务范围】\n{packet['scope']}\n\n"
        f"【局部上下文】\n{compact_local_context}\n\n"
        f"【硬约束】\n{compact_hard_constraints}\n\n"
        f"【软目标】\n{compact_soft_goals}\n\n"
        f"【输出契约】\n{compact_contract}\n\n"
        f"【本地约束种子结果】\n{compact_baseline}\n\n"
        "请输出 JSON，格式如下：\n"
        "{\n"
        '  "result": { ... },\n'
        '  "reason": "一句中文说明",\n'
        '  "confidence": "high|medium|low",\n'
        '  "constraint_checks": ["列出你遵守了哪些关键硬约束"]\n'
        "}\n"
        "重要：result 只需要返回相对【本地约束种子结果】需要改动或补充的字段。"
        "未写出的资源项与字段，系统会自动沿用本地约束种子结果。"
        "若无需改动，可令 result 为 {}。"
    )
    prompt_stats = {
        "system_chars": len(system_prompt),
        "user_chars": len(user_prompt),
        "compact_mode": int(compact_mode),
    }
    return system_prompt, user_prompt, prompt_stats



def _retryable_constraint_error(exc: GenerationError) -> bool:
    return bool(exc.retryable) and exc.code in _RETRYABLE_CODES



def _build_attempt_error_details(*, exc: GenerationError, attempt: int, attempts_total: int, compact_mode: bool, timeout_seconds: int, max_output_tokens: int, prompt_stats: dict[str, int], baseline_result: dict[str, Any]) -> dict[str, Any]:
    details = dict(exc.details or {})
    details.update(
        {
            "reasoning_attempt": attempt,
            "reasoning_attempts_total": attempts_total,
            "reasoning_compact_mode": compact_mode,
            "reasoning_timeout_seconds": timeout_seconds,
            "reasoning_max_output_tokens": max_output_tokens,
            "reasoning_prompt_stats": prompt_stats,
            "reasoning_seed_keys": list((baseline_result or {}).keys())[:8],
        }
    )
    return details



def run_local_constraint_reasoning(
    *,
    story_bible: dict[str, Any],
    task_type: str,
    scope: str,
    chapter_no: int = 0,
    allow_ai: bool = True,
    local_context: dict[str, Any] | None = None,
    hard_constraints: list[str] | None = None,
    soft_goals: list[str] | None = None,
    output_contract: dict[str, Any] | None = None,
    baseline_builder: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    packet = {
        "task_type": _text(task_type),
        "scope": _text(scope),
        "chapter_no": int(chapter_no or 0),
        "local_context": deepcopy(local_context or {}),
        "hard_constraints": [item for item in _safe_list(hard_constraints) if _text(item)],
        "soft_goals": [item for item in _safe_list(soft_goals) if _text(item)],
        "output_contract": deepcopy(output_contract or {}),
    }
    baseline_result = baseline_builder(packet) or {}
    if not allow_ai:
        _record_history(
            story_bible=story_bible,
            task_type=task_type,
            scope=scope,
            chapter_no=chapter_no,
            used_ai=False,
            result={},
            note={"reason": "allow_ai_disabled"},
        )
        _raise_ai_required_error(
            task_type=task_type,
            scope=scope,
            chapter_no=chapter_no,
            detail_reason="调用方未允许本阶段使用 AI。新系统不再返回本地替代结果。",
            retryable=False,
        )
    if not _ai_enabled():
        _record_history(
            story_bible=story_bible,
            task_type=task_type,
            scope=scope,
            chapter_no=chapter_no,
            used_ai=False,
            result={},
            note={"reason": "ai_unavailable"},
        )
        _raise_ai_required_error(
            task_type=task_type,
            scope=scope,
            chapter_no=chapter_no,
            detail_reason="当前没有可用的 AI 配置或密钥。",
            retryable=False,
        )

    attempts_total = max(int(getattr(settings, "local_constraint_reasoning_retry_attempts", 2) or 2), 1)
    base_timeout_seconds = max(int(getattr(settings, "local_constraint_reasoning_timeout_seconds", 30) or 30), 8)
    timeout_increment_seconds = max(int(getattr(settings, "local_constraint_reasoning_retry_timeout_increment_seconds", 10) or 10), 0)
    base_max_output_tokens = max(int(getattr(settings, "local_constraint_reasoning_max_output_tokens", 720) or 720), 280)
    retry_backoff_ms = max(int(getattr(settings, "local_constraint_reasoning_retry_backoff_ms", 600) or 600), 0)

    last_generation_error: GenerationError | None = None

    for attempt in range(1, attempts_total + 1):
        compact_mode = attempt > 1
        timeout_seconds = base_timeout_seconds + (timeout_increment_seconds * (attempt - 1))
        if compact_mode:
            max_output_tokens = max(320, min(base_max_output_tokens, 560))
        else:
            max_output_tokens = base_max_output_tokens
        system_prompt, user_prompt, prompt_stats = _build_reasoning_prompts(packet=packet, baseline_result=baseline_result, compact_mode=compact_mode)

        try:
            data = call_json_response(
                stage=LOCAL_CONSTRAINT_STAGE,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
            )
            candidate = data.get("result") if isinstance(data, dict) else None
            merged = _deep_merge(baseline_result, candidate if isinstance(candidate, dict) else {})
            reason = _text((data or {}).get("reason"), "AI 已在局部约束下生成结果。")
            confidence = _text((data or {}).get("confidence"), "medium")
            _record_history(
                story_bible=story_bible,
                task_type=task_type,
                scope=scope,
                chapter_no=chapter_no,
                used_ai=True,
                result=merged,
                note={
                    "attempt": attempt,
                    "attempts_total": attempts_total,
                    "compact_mode": compact_mode,
                    "timeout_seconds": timeout_seconds,
                    "max_output_tokens": max_output_tokens,
                    "prompt_stats": prompt_stats,
                },
            )
            return {
                "task_type": _text(task_type),
                "scope": _text(scope),
                "chapter_no": int(chapter_no or 0),
                "used_ai": True,
                "result": merged,
                "reason": reason,
                "confidence": confidence,
                "constraint_checks": _safe_list((data or {}).get("constraint_checks")),
                "attempt": attempt,
                "attempts_total": attempts_total,
                "compact_mode": compact_mode,
            }
        except GenerationError as exc:
            last_generation_error = exc
            exc.details = _build_attempt_error_details(
                exc=exc,
                attempt=attempt,
                attempts_total=attempts_total,
                compact_mode=compact_mode,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
                prompt_stats=prompt_stats,
                baseline_result=baseline_result,
            )
            if attempt >= attempts_total or not _retryable_constraint_error(exc):
                _record_history(
                    story_bible=story_bible,
                    task_type=task_type,
                    scope=scope,
                    chapter_no=chapter_no,
                    used_ai=False,
                    result={},
                    note={
                        "attempt": attempt,
                        "attempts_total": attempts_total,
                        "error_code": exc.code,
                        "compact_mode": compact_mode,
                    },
                )
                raise exc
            if retry_backoff_ms > 0:
                time.sleep(retry_backoff_ms / 1000.0)
        except Exception as exc:  # pragma: no cover - network/env dependent
            _record_history(
                story_bible=story_bible,
                task_type=task_type,
                scope=scope,
                chapter_no=chapter_no,
                used_ai=False,
                result={},
                note={"reason": "unexpected_exception", "error_type": type(exc).__name__},
            )
            _raise_ai_required_error(
                task_type=task_type,
                scope=scope,
                chapter_no=chapter_no,
                detail_reason=f"AI 约束推理调用失败：{exc}",
                retryable=True,
            )

    if last_generation_error is not None:
        raise last_generation_error

    _raise_ai_required_error(
        task_type=task_type,
        scope=scope,
        chapter_no=chapter_no,
        detail_reason="AI 约束推理未返回可用结果。",
        retryable=True,
    )
