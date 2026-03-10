from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError

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


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: str
    api_key: str | None
    base_url: str | None
    model: str
    timeout_seconds: int
    max_output_tokens: int
    chapter_max_output_tokens: int

    @property
    def client_signature(self) -> tuple[str, str | None, str | None]:
        return (self.provider, self.api_key, self.base_url)

    @property
    def throttle_scope(self) -> str:
        return f"{self.provider}:{self.base_url or 'default'}:{self.model}"


@dataclass(slots=True)
class _ThrottleState:
    lock: threading.Lock
    last_call_at: float = 0.0


_client: Any | None = None
_client_signature: tuple[str, str | None, str | None] | None = None
_throttle_states: dict[str, _ThrottleState] = {}
_throttle_states_lock = threading.Lock()
_trace_var: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("llm_trace", default=None)
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_trace_id", default=None)


def current_provider_config() -> ProviderConfig:
    provider = settings.llm_provider.lower().strip()
    if provider == "openai":
        return ProviderConfig(
            provider=provider,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=settings.openai_max_output_tokens,
            chapter_max_output_tokens=settings.openai_chapter_max_output_tokens,
        )
    if provider == "deepseek":
        return ProviderConfig(
            provider=provider,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_output_tokens=settings.deepseek_max_output_tokens,
            chapter_max_output_tokens=settings.deepseek_chapter_max_output_tokens,
        )
    if provider == "groq":
        return ProviderConfig(
            provider=provider,
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            timeout_seconds=settings.groq_timeout_seconds,
            max_output_tokens=settings.groq_max_output_tokens,
            chapter_max_output_tokens=settings.groq_chapter_max_output_tokens,
        )
    raise GenerationError(
        code=ErrorCodes.PROVIDER_UNSUPPORTED,
        message=f"当前 LLM_PROVIDER={provider!r} 不受支持，仅支持 openai、deepseek 或 groq。",
        stage="provider_check",
        retryable=False,
        http_status=422,
        provider=provider,
    )


def current_provider() -> str:
    return current_provider_config().provider


def current_max_output_tokens() -> int:
    return current_provider_config().max_output_tokens


def current_chapter_max_output_tokens() -> int:
    return current_provider_config().chapter_max_output_tokens


def current_trace_id() -> str | None:
    return _trace_id_var.get()


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


def _throttle_state_for(scope: str) -> _ThrottleState:
    with _throttle_states_lock:
        state = _throttle_states.get(scope)
        if state is None:
            state = _ThrottleState(lock=threading.Lock())
            _throttle_states[scope] = state
        return state


def throttle_llm_calls(config: ProviderConfig) -> int:
    minimum = max(int(settings.llm_call_min_interval_ms), 0)
    if minimum <= 0:
        return 0

    waited_ms = 0
    state = _throttle_state_for(config.throttle_scope)
    with state.lock:
        now = time.monotonic()
        remaining = (minimum / 1000.0) - (now - state.last_call_at)
        if remaining > 0:
            time.sleep(remaining)
            waited_ms = int(round(remaining * 1000))
        state.last_call_at = time.monotonic()
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


def require_generation_provider(stage: str) -> ProviderConfig:
    config = current_provider_config()
    if OpenAI is None:
        raise GenerationError(
            code=ErrorCodes.PROVIDER_NOT_CONFIGURED,
            message="未检测到 openai Python SDK，请先安装依赖后再重试。",
            stage=stage,
            retryable=False,
            http_status=500,
            provider=config.provider,
        )
    if not config.api_key:
        missing_env = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "groq": "GROQ_API_KEY",
        }[config.provider]
        raise GenerationError(
            code=ErrorCodes.PROVIDER_NOT_CONFIGURED,
            message=f"{stage} 失败：缺少 {missing_env}，当前无法调用模型。",
            stage=stage,
            retryable=False,
            http_status=422,
            provider=config.provider,
            details={"missing_env": missing_env},
        )
    return config


def is_llm_enabled() -> bool:
    try:
        config = current_provider_config()
    except GenerationError:
        return False
    return OpenAI is not None and bool(config.api_key)


def get_client() -> Any:
    global _client, _client_signature
    config = require_generation_provider(stage="llm_client_init")
    if _client is None or _client_signature != config.client_signature:
        kwargs: dict[str, Any] = {"api_key": config.api_key, "timeout": config.timeout_seconds}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        _client = OpenAI(**kwargs)
        _client_signature = config.client_signature
    return _client


def response_to_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content_item in getattr(item, "content", []) or []:
            text_value = getattr(content_item, "text", None)
            if text_value:
                chunks.append(text_value)
    return "\n".join(chunks).strip()


def chat_completion_to_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
            else:
                text_value = getattr(item, "text", None)
            if isinstance(text_value, str) and text_value:
                chunks.append(text_value)
        return "\n".join(chunks).strip()
    return ""


def call_text_response(
    *,
    stage: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int | None = None,
) -> str:
    config = require_generation_provider(stage=stage)
    client = get_client()
    output_tokens = max_output_tokens or config.max_output_tokens
    request_kwargs: dict[str, Any] = {"model": config.model}

    if config.provider == "deepseek":
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
        if config.provider == "openai":
            request_kwargs["reasoning"] = {"effort": settings.openai_reasoning_effort}

    waited_ms = throttle_llm_calls(config)
    started = time.perf_counter()
    trace_common = {
        "trace_id": current_trace_id(),
        "stage": stage,
        "provider": config.provider,
        "model": config.model,
        "throttle_scope": config.throttle_scope,
        "system_chars": len(system_prompt),
        "user_chars": len(user_prompt),
        "max_output_tokens": output_tokens,
        "waited_ms": waited_ms,
    }
    logger.info(
        "llm_call start trace=%s stage=%s provider=%s model=%s system_chars=%s user_chars=%s max_output_tokens=%s waited_ms=%s scope=%s",
        trace_common["trace_id"],
        stage,
        config.provider,
        config.model,
        len(system_prompt),
        len(user_prompt),
        output_tokens,
        waited_ms,
        config.throttle_scope,
    )

    try:
        if config.provider == "deepseek":
            response = client.chat.completions.create(**request_kwargs)
        else:
            response = client.responses.create(**request_kwargs)
    except APITimeoutError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": current_trace_id(), "duration_ms": duration_ms, **extract_api_error_details(exc)}
        append_trace({**trace_common, "status": "timeout", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_TIMEOUT,
            message=f"{stage} 失败：模型接口超时，请稍后重新生成。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=config.provider,
            details=details,
        ) from exc
    except AuthenticationError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": current_trace_id(), "duration_ms": duration_ms, **extract_api_error_details(exc)}
        append_trace({**trace_common, "status": "auth_failed", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_AUTH_FAILED,
            message=f"{stage} 失败：API key 无效或没有权限访问当前模型。",
            stage=stage,
            retryable=False,
            http_status=401,
            provider=config.provider,
            details=details,
        ) from exc
    except RateLimitError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": current_trace_id(), "duration_ms": duration_ms, **extract_api_error_details(exc)}
        append_trace({**trace_common, "status": "rate_limited", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_RATE_LIMITED,
            message=f"{stage} 失败：模型接口触发限流，请稍后重新生成。",
            stage=stage,
            retryable=True,
            http_status=429,
            provider=config.provider,
            details=details,
        ) from exc
    except APIConnectionError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": current_trace_id(), "duration_ms": duration_ms, **extract_api_error_details(exc)}
        append_trace({**trace_common, "status": "connection_failed", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_CONNECTION_FAILED,
            message=f"{stage} 失败：无法连接到模型接口，请检查网络或 base_url 配置。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=config.provider,
            details=details,
        ) from exc
    except APIStatusError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": current_trace_id(), "duration_ms": duration_ms, **extract_api_error_details(exc)}
        append_trace({**trace_common, "status": "api_status_error", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_STATUS_ERROR,
            message=f"{stage} 失败：模型接口返回异常状态码 {getattr(exc, 'status_code', 'unknown')}。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=config.provider,
            details=details,
        ) from exc
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": current_trace_id(), "duration_ms": duration_ms, "error_type": type(exc).__name__}
        append_trace({**trace_common, "status": "unexpected_error", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_STATUS_ERROR,
            message=f"{stage} 失败：调用模型接口时出现未识别错误。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=config.provider,
            details=details,
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    text = chat_completion_to_text(response) if config.provider == "deepseek" else response_to_text(response)
    response_id = response_request_id(response)
    event = {
        **trace_common,
        "status": "success",
        "duration_ms": duration_ms,
        "response_chars": len(text),
    }
    if response_id:
        event["response_id"] = response_id
    append_trace(event)
    logger.info(
        "llm_call success trace=%s stage=%s duration_ms=%s response_chars=%s response_id=%s scope=%s",
        trace_common["trace_id"],
        stage,
        duration_ms,
        len(text),
        response_id,
        config.throttle_scope,
    )
    return text
