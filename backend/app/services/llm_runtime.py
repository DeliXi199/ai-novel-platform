from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.prompt_templates import json_repair_system_prompt, json_repair_user_prompt

logger = logging.getLogger(__name__)

try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except Exception:  # pragma: no cover
    OpenAI = None
    APIConnectionError = APITimeoutError = AuthenticationError = RateLimitError = APIStatusError = Exception

_clients: dict[tuple[str, str | None, str | None, str], Any] = {}
_call_gates: dict[str, threading.Lock] = {}
_last_call_at_by_scope: dict[str, float] = {}
_trace_var: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("llm_trace", default=None)
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_trace_id", default=None)

_BOOTSTRAP_STAGE_PREFIXES = (
    "global_outline_generation",
    "arc_outline_generation",
)


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().strip('"').strip("'").strip()
    return cleaned or None


def normalize_base_url(value: str | None, *, provider: str) -> str | None:
    base = normalize_text(value)
    if not base:
        return None
    while base.endswith("/"):
        base = base[:-1]
    if provider == "deepseek" and base == "https://api.deepseek.com/v1":
        return "https://api.deepseek.com"
    return base


def mask_secret_tail(value: str | None) -> str | None:
    secret = normalize_text(value)
    if not secret:
        return None
    tail = secret[-4:] if len(secret) >= 4 else secret
    return f"****{tail}"


def provider_name() -> str:
    return (normalize_text(settings.llm_provider) or "openai").lower()


def is_bootstrap_stage(stage: str | None) -> bool:
    normalized = normalize_text(stage) or ""
    return any(normalized.startswith(prefix) for prefix in _BOOTSTRAP_STAGE_PREFIXES)


def provider_for_stage(stage: str | None = None) -> str:
    if is_bootstrap_stage(stage):
        override = normalize_text(getattr(settings, "bootstrap_llm_provider", None))
        if override:
            return override.lower()
    return provider_name()


def current_api_key(stage: str | None = None) -> str | None:
    provider = provider_for_stage(stage)
    env_candidates: dict[str, list[str]] = {
        "openai": ["OPENAI_API_KEY", "LLM_API_KEY", "API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY", "LLM_API_KEY", "API_KEY"],
        "groq": ["GROQ_API_KEY", "LLM_API_KEY", "API_KEY"],
    }
    configured: dict[str, str | None] = {
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
        "groq": settings.groq_api_key,
    }
    key = normalize_text(configured.get(provider))
    if key:
        return key
    for env_name in env_candidates.get(provider, []):
        key = normalize_text(os.getenv(env_name))
        if key:
            return key
    return None


def _deepseek_base_url_variant(base: str | None, variant: int) -> str | None:
    normalized = normalize_base_url(base, provider="deepseek")
    if not normalized or variant <= 0:
        return normalized
    if normalized.endswith("/v1"):
        return normalized[:-3]
    return f"{normalized}/v1"


def current_base_url(stage: str | None = None, *, variant: int = 0) -> str | None:
    provider = provider_for_stage(stage)
    env_candidates: dict[str, list[str]] = {
        "openai": ["OPENAI_BASE_URL", "LLM_BASE_URL", "BASE_URL"],
        "deepseek": ["DEEPSEEK_BASE_URL", "LLM_BASE_URL", "BASE_URL"],
        "groq": ["GROQ_BASE_URL", "LLM_BASE_URL", "BASE_URL"],
    }
    configured: dict[str, str | None] = {
        "openai": settings.openai_base_url,
        "deepseek": settings.deepseek_base_url,
        "groq": settings.groq_base_url,
    }
    base = normalize_base_url(configured.get(provider), provider=provider)
    if base:
        return _deepseek_base_url_variant(base, variant) if provider == "deepseek" else base
    for env_name in env_candidates.get(provider, []):
        base = normalize_base_url(os.getenv(env_name), provider=provider)
        if base:
            return _deepseek_base_url_variant(base, variant) if provider == "deepseek" else base
    return None


def current_model(stage: str | None = None) -> str:
    provider = provider_for_stage(stage)
    bootstrap_model = normalize_text(getattr(settings, "bootstrap_model", None)) if is_bootstrap_stage(stage) else None
    if provider == "deepseek" and is_bootstrap_stage(stage) and (bootstrap_model or normalize_text(settings.deepseek_model)) == "deepseek-reasoner" and getattr(settings, "bootstrap_prefer_non_reasoning", True):
        bootstrap_model = "deepseek-chat"
    if provider == "openai":
        return bootstrap_model or normalize_text(settings.openai_model) or "gpt-5.4"
    if provider == "deepseek":
        return bootstrap_model or normalize_text(settings.deepseek_model) or "deepseek-chat"
    if provider == "groq":
        return bootstrap_model or normalize_text(settings.groq_model) or "openai/gpt-oss-20b"
    raise GenerationError(
        code=ErrorCodes.PROVIDER_UNSUPPORTED,
        message=f"当前 LLM_PROVIDER={provider!r} 不受支持，仅支持 openai、deepseek 或 groq。",
        stage="provider_check",
        retryable=False,
        http_status=422,
        provider=provider,
    )


def current_timeout(stage: str | None = None) -> int:
    if is_bootstrap_stage(stage) and getattr(settings, "bootstrap_timeout_seconds", None):
        return int(settings.bootstrap_timeout_seconds)
    provider = provider_for_stage(stage)
    if provider == "openai":
        return settings.openai_timeout_seconds
    if provider == "deepseek":
        return settings.deepseek_timeout_seconds
    if provider == "groq":
        return settings.groq_timeout_seconds
    return 120


def current_max_output_tokens(stage: str | None = None) -> int:
    provider = provider_for_stage(stage)
    if provider == "openai":
        return settings.openai_max_output_tokens
    if provider == "deepseek":
        return settings.deepseek_max_output_tokens
    if provider == "groq":
        return settings.groq_max_output_tokens
    return 4000


def current_chapter_max_output_tokens(stage: str | None = None) -> int:
    provider = provider_for_stage(stage)
    if provider == "openai":
        return settings.openai_chapter_max_output_tokens
    if provider == "deepseek":
        return settings.deepseek_chapter_max_output_tokens
    if provider == "groq":
        return settings.groq_chapter_max_output_tokens
    return 1400


def begin_llm_trace(name: str) -> str:
    trace_id = f"{name}-{uuid.uuid4().hex[:12]}"
    _trace_var.set([])
    _trace_id_var.set(trace_id)
    return trace_id


def get_llm_trace() -> list[dict[str, Any]]:
    trace = _trace_var.get()
    if not trace:
        return []
    return [dict(item) for item in trace]


def clear_llm_trace() -> None:
    _trace_var.set(None)
    _trace_id_var.set(None)


def append_trace(event: dict[str, Any]) -> None:
    trace = _trace_var.get()
    if trace is None:
        return
    items = list(trace)
    items.append(event)
    if len(items) > settings.llm_trace_limit:
        items = items[-settings.llm_trace_limit :]
    _trace_var.set(items)


def throttle_llm_calls(stage: str | None = None) -> int:
    minimum = max(int(settings.llm_call_min_interval_ms), 0)
    if minimum <= 0:
        return 0

    scope = provider_for_stage(stage or "default")
    gate = _call_gates.setdefault(scope, threading.Lock())
    waited_ms = 0
    with gate:
        now = time.monotonic()
        last_at = _last_call_at_by_scope.get(scope, 0.0)
        remaining = (minimum / 1000.0) - (now - last_at)
        if remaining > 0:
            time.sleep(remaining)
            waited_ms = int(round(remaining * 1000))
        _last_call_at_by_scope[scope] = time.monotonic()
    return waited_ms


def response_request_id(response: Any) -> str | None:
    for attr in ("_request_id", "request_id", "id"):
        value = getattr(response, attr, None)
        if value:
            return str(value)
    return None


def extract_api_error_details(exc: Exception) -> dict[str, Any]:
    details: dict[str, Any] = {}
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        details["status_code"] = status_code

    request_id = getattr(exc, "request_id", None) or getattr(exc, "_request_id", None)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    interesting_headers = [
        "retry-after",
        "x-request-id",
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
    ]
    for name in interesting_headers:
        value = headers.get(name)
        if value is not None:
            details[name.replace("-", "_")] = value
    request_id = request_id or headers.get("x-request-id")
    if request_id:
        details["request_id"] = str(request_id)

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        message = body.get("message") or body.get("error")
        if isinstance(message, str):
            details["api_message"] = message[:300]
    return details


def require_generation_provider(stage: str) -> None:
    provider = provider_for_stage(stage)
    if provider not in {"openai", "deepseek", "groq"}:
        raise GenerationError(
            code=ErrorCodes.PROVIDER_UNSUPPORTED,
            message=f"当前 LLM_PROVIDER={provider!r} 不受支持，仅支持 openai、deepseek 或 groq。",
            stage=stage,
            retryable=False,
            http_status=422,
            provider=provider,
        )

    if OpenAI is None:
        raise GenerationError(
            code=ErrorCodes.PROVIDER_NOT_CONFIGURED,
            message="openai Python SDK 未安装，无法调用模型接口。",
            stage=stage,
            retryable=False,
            http_status=500,
            provider=provider,
        )

    if not current_api_key(stage):
        raise GenerationError(
            code=ErrorCodes.PROVIDER_NOT_CONFIGURED,
            message=f"{stage} 失败：未检测到 {provider} 的 API key 配置。",
            stage=stage,
            retryable=False,
            http_status=422,
            provider=provider,
        )


def is_openai_enabled() -> bool:
    try:
        require_generation_provider(stage="provider_check")
        return True
    except GenerationError:
        return False


def get_llm_runtime_config(stage: str | None = None) -> dict[str, Any]:
    provider = provider_for_stage(stage)
    payload = {
        "provider": provider,
        "model": current_model(stage) if provider in {"openai", "deepseek", "groq"} else None,
        "base_url": current_base_url(stage),
        "api_key_present": bool(current_api_key(stage)),
        "api_key_masked": mask_secret_tail(current_api_key(stage)),
        "timeout_seconds": current_timeout(stage),
    }
    if is_bootstrap_stage(stage):
        payload["requested_stage"] = stage
    return payload


def ping_generation_provider(stage: str = "llm_ping") -> dict[str, Any]:
    require_generation_provider(stage=stage)
    text = call_text_response(
        stage=stage,
        system_prompt="你是一个连接性测试助手。只输出 pong。",
        user_prompt="请只输出 pong",
        max_output_tokens=16,
    ).strip()
    return {**get_llm_runtime_config(stage), "ping_text": text[:32]}


def get_client(stage: str | None = None, *, base_url_variant: int = 0, timeout_seconds: int | None = None) -> Any:
    effective_stage = stage or "provider_check"
    require_generation_provider(stage=effective_stage)
    provider = provider_for_stage(effective_stage)
    effective_timeout = int(timeout_seconds or current_timeout(effective_stage))
    signature = (provider, current_api_key(effective_stage), current_base_url(effective_stage, variant=base_url_variant), str(effective_timeout))
    cached = _clients.get(signature)
    if cached is not None:
        return cached

    kwargs: dict[str, Any] = {
        "api_key": current_api_key(effective_stage),
        "timeout": effective_timeout,
        "max_retries": max(int(getattr(settings, "llm_api_max_retries", 0) or 0), 0),
    }
    base_url = current_base_url(effective_stage, variant=base_url_variant)
    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)
    _clients[signature] = client
    return client


def response_to_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    output = getattr(response, "output", None)
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for chunk in content:
                text_value = chunk.get("text") if isinstance(chunk, dict) else getattr(chunk, "text", None)
                if isinstance(text_value, str) and text_value:
                    chunks.append(text_value)
        return "\n".join(chunks).strip()
    return ""


def chat_completion_to_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text_value = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if isinstance(text_value, str) and text_value:
                chunks.append(text_value)
        return "\n".join(chunks).strip()
    return ""


def extract_json(text: str, *, stage: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message=f"{stage} 失败：模型没有返回任何可解析内容。",
            stage=stage,
            retryable=True,
            http_status=422,
            provider=provider_for_stage(stage),
            details={"trace_id": _trace_id_var.get()},
        )

    candidate = raw
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    possible_candidates = [candidate]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        possible_candidates.append(candidate[start : end + 1])

    for item in possible_candidates:
        try:
            return json.loads(item)
        except json.JSONDecodeError:
            continue

    raise GenerationError(
        code=ErrorCodes.MODEL_RESPONSE_INVALID,
        message=f"{stage} 失败：模型返回内容不是合法 JSON，可能被截断或格式混乱。",
        stage=stage,
        retryable=True,
        http_status=422,
        provider=provider_for_stage(stage),
        details={"response_head": raw[:500], "trace_id": _trace_id_var.get()},
    )


def call_text_response(*, stage: str, system_prompt: str, user_prompt: str, max_output_tokens: int | None = None, timeout_seconds: int | None = None) -> str:
    require_generation_provider(stage=stage)
    provider = provider_for_stage(stage)
    output_tokens = max_output_tokens or current_max_output_tokens(stage)
    retry_variants = 2 if provider == "deepseek" else 1
    last_connection_exc: APIConnectionError | None = None

    effective_timeout = int(timeout_seconds or current_timeout(stage))

    for base_variant in range(retry_variants):
        client = get_client(stage=stage, base_url_variant=base_variant, timeout_seconds=effective_timeout)
        request_kwargs: dict[str, Any] = {"model": current_model(stage)}
        base_url_used = current_base_url(stage, variant=base_variant)
        if provider in {"deepseek", "groq"}:
            request_kwargs.update(
                {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": output_tokens,
                    "stream": False,
                }
            )
        else:
            request_kwargs.update(
                {
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_output_tokens": output_tokens,
                    "store": False,
                }
            )
            if provider == "openai":
                request_kwargs["reasoning"] = {"effort": settings.openai_reasoning_effort}

        waited_ms = throttle_llm_calls(stage)
        started = time.perf_counter()
        trace_common = {
            "trace_id": _trace_id_var.get(),
            "stage": stage,
            "provider": provider,
            "model": request_kwargs["model"],
            "system_chars": len(system_prompt),
            "user_chars": len(user_prompt),
            "max_output_tokens": output_tokens,
            "waited_ms": waited_ms,
            "base_url": base_url_used,
            "base_url_variant": base_variant,
            "timeout_seconds": effective_timeout,
        }
        logger.info(
            "llm_call start trace=%s stage=%s provider=%s model=%s system_chars=%s user_chars=%s max_output_tokens=%s waited_ms=%s base_url=%s variant=%s",
            trace_common["trace_id"],
            stage,
            provider,
            request_kwargs["model"],
            len(system_prompt),
            len(user_prompt),
            output_tokens,
            waited_ms,
            base_url_used,
            base_variant,
        )

        try:
            response = client.chat.completions.create(**request_kwargs) if provider in {"deepseek", "groq"} else client.responses.create(**request_kwargs)
        except APITimeoutError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "base_url": base_url_used, "timeout_seconds": effective_timeout, **extract_api_error_details(exc)}
            append_trace({**trace_common, "status": "timeout", "duration_ms": duration_ms, "details": details})
            raise GenerationError(code=ErrorCodes.API_TIMEOUT, message=f"{stage} 失败：模型接口超时，请稍后重新生成。", stage=stage, retryable=True, http_status=503, provider=provider, details=details) from exc
        except AuthenticationError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "base_url": base_url_used, **extract_api_error_details(exc)}
            append_trace({**trace_common, "status": "auth_failed", "duration_ms": duration_ms, "details": details})
            raise GenerationError(code=ErrorCodes.API_AUTH_FAILED, message=f"{stage} 失败：API key 无效或没有权限访问当前模型。", stage=stage, retryable=False, http_status=401, provider=provider, details=details) from exc
        except RateLimitError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "base_url": base_url_used, **extract_api_error_details(exc)}
            append_trace({**trace_common, "status": "rate_limited", "duration_ms": duration_ms, "details": details})
            raise GenerationError(code=ErrorCodes.API_RATE_LIMITED, message=f"{stage} 失败：模型接口触发限流，请稍后重新生成。", stage=stage, retryable=True, http_status=429, provider=provider, details=details) from exc
        except APIConnectionError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "base_url": base_url_used, "base_url_variant": base_variant, **extract_api_error_details(exc)}
            append_trace({**trace_common, "status": "connection_failed", "duration_ms": duration_ms, "details": details})
            last_connection_exc = exc
            if provider == "deepseek" and base_variant < retry_variants - 1:
                logger.warning(
                    "llm_call connection retry trace=%s stage=%s provider=%s base_url=%s variant=%s",
                    trace_common["trace_id"],
                    stage,
                    provider,
                    base_url_used,
                    base_variant,
                )
                continue
            raise GenerationError(code=ErrorCodes.API_CONNECTION_FAILED, message=f"{stage} 失败：无法连接到模型接口，请检查网络或 base_url 配置。", stage=stage, retryable=True, http_status=503, provider=provider, details=details) from exc
        except APIStatusError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "base_url": base_url_used, **extract_api_error_details(exc)}
            append_trace({**trace_common, "status": "api_status_error", "duration_ms": duration_ms, "details": details})
            raise GenerationError(code=ErrorCodes.API_STATUS_ERROR, message=f"{stage} 失败：模型接口返回异常状态码 {getattr(exc, 'status_code', 'unknown')}。", stage=stage, retryable=True, http_status=503, provider=provider, details=details) from exc
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "base_url": base_url_used, "error_type": type(exc).__name__}
            append_trace({**trace_common, "status": "unexpected_error", "duration_ms": duration_ms, "details": details})
            raise GenerationError(code=ErrorCodes.API_STATUS_ERROR, message=f"{stage} 失败：调用模型接口时出现未识别错误。", stage=stage, retryable=True, http_status=503, provider=provider, details=details) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        text = chat_completion_to_text(response) if provider in {"deepseek", "groq"} else response_to_text(response)
        response_id = response_request_id(response)
        event = {**trace_common, "status": "success", "duration_ms": duration_ms, "response_chars": len(text)}
        if response_id:
            event["response_id"] = response_id
        append_trace(event)
        logger.info(
            "llm_call success trace=%s stage=%s duration_ms=%s response_chars=%s response_id=%s base_url=%s variant=%s",
            trace_common["trace_id"],
            stage,
            duration_ms,
            len(text),
            response_id,
            base_url_used,
            base_variant,
        )
        return text

    if last_connection_exc is not None:
        raise GenerationError(
            code=ErrorCodes.API_CONNECTION_FAILED,
            message=f"{stage} 失败：无法连接到模型接口，请检查网络或 base_url 配置。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=provider,
            details={"trace_id": _trace_id_var.get()},
        ) from last_connection_exc

    raise GenerationError(
        code=ErrorCodes.API_STATUS_ERROR,
        message=f"{stage} 失败：调用模型接口时出现未识别错误。",
        stage=stage,
        retryable=True,
        http_status=503,
        provider=provider,
        details={"trace_id": _trace_id_var.get()},
    )


def attempt_json_repair(*, stage: str, raw_text: str) -> dict[str, Any]:
    attempts = max(int(getattr(settings, "json_repair_attempts", 0)), 0)
    if attempts <= 0 or not (raw_text or "").strip():
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message=f"{stage} 失败：模型返回内容不是合法 JSON，且未启用修复重试。",
            stage=stage,
            retryable=True,
            http_status=422,
            provider=provider_for_stage(stage),
            details={"trace_id": _trace_id_var.get()},
        )

    last_exc: GenerationError | None = None
    for attempt_idx in range(1, attempts + 1):
        repaired_text = call_text_response(
            stage=f"{stage}_json_repair",
            system_prompt=json_repair_system_prompt(),
            user_prompt=json_repair_user_prompt(stage=stage, raw_text=raw_text[:12000]),
            max_output_tokens=max(int(getattr(settings, "json_repair_max_output_tokens", 2200)), 400),
        )
        try:
            data = extract_json(repaired_text, stage=stage)
            append_trace({
                "trace_id": _trace_id_var.get(),
                "stage": stage,
                "provider": provider_for_stage(stage),
                "status": "json_repaired",
                "attempt": attempt_idx,
                "raw_chars": len(raw_text),
                "repaired_chars": len(repaired_text),
            })
            return data
        except GenerationError as exc:
            last_exc = exc

    if last_exc:
        raise last_exc
    raise GenerationError(
        code=ErrorCodes.MODEL_RESPONSE_INVALID,
        message=f"{stage} 失败：JSON 修复重试后仍无合法结果。",
        stage=stage,
        retryable=True,
        http_status=422,
        provider=provider_for_stage(stage),
        details={"trace_id": _trace_id_var.get()},
    )


def call_json_response(*, stage: str, system_prompt: str, user_prompt: str, max_output_tokens: int | None = None, timeout_seconds: int | None = None) -> dict[str, Any]:
    regeneration_attempts = max(int(getattr(settings, "json_invalid_regeneration_attempts", 0)), 0)
    last_exc: GenerationError | None = None

    for attempt_idx in range(1, regeneration_attempts + 2):
        text = call_text_response(
            stage=stage,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        try:
            return extract_json(text, stage=stage)
        except GenerationError as exc:
            last_exc = exc
            if exc.code == ErrorCodes.MODEL_RESPONSE_INVALID:
                try:
                    return attempt_json_repair(stage=stage, raw_text=text)
                except GenerationError as repair_exc:
                    last_exc = repair_exc
            append_trace({
                "trace_id": _trace_id_var.get(),
                "stage": stage,
                "provider": provider_for_stage(stage),
                "status": "json_invalid_regenerate",
                "attempt": attempt_idx,
                "response_chars": len(text),
            })
            if attempt_idx > regeneration_attempts:
                raise last_exc

    if last_exc:
        raise last_exc
    raise GenerationError(
        code=ErrorCodes.MODEL_RESPONSE_INVALID,
        message=f"{stage} 失败：模型没有产出可用 JSON。",
        stage=stage,
        retryable=True,
        http_status=422,
        provider=provider_for_stage(stage),
        details={"trace_id": _trace_id_var.get()},
    )
