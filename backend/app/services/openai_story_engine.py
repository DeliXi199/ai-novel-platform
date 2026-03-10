from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.prompt_templates import (
    arc_outline_system_prompt,
    arc_outline_user_prompt,
    chapter_draft_system_prompt,
    chapter_draft_user_prompt,
    chapter_extension_system_prompt,
    chapter_extension_user_prompt,
    global_outline_system_prompt,
    global_outline_user_prompt,
    instruction_parse_system_prompt,
    instruction_parse_user_prompt,
    summary_system_prompt,
    summary_user_prompt,
)

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


class ChapterPlan(BaseModel):
    chapter_no: int
    title: str
    goal: str
    ending_hook: str
    chapter_type: str | None = None
    target_visible_chars_min: int | None = None
    target_visible_chars_max: int | None = None
    hook_style: str | None = None
    main_scene: str | None = None
    conflict: str | None = None
    opening_beat: str | None = None
    mid_turn: str | None = None
    discovery: str | None = None
    closing_image: str | None = None
    supporting_character_focus: str | None = None
    supporting_character_note: str | None = None
    writing_note: str | None = None


class StoryAct(BaseModel):
    act_no: int
    title: str
    purpose: str
    target_chapter_end: int
    summary: str


class GlobalOutlinePayload(BaseModel):
    story_positioning: dict[str, Any] = Field(default_factory=dict)
    acts: list[StoryAct]


class ArcOutlinePayload(BaseModel):
    arc_no: int
    start_chapter: int
    end_chapter: int
    focus: str
    bridge_note: str
    chapters: list[ChapterPlan]


class ChapterDraftPayload(BaseModel):
    title: str
    content: str


class ChapterSummaryPayload(BaseModel):
    event_summary: str
    character_updates: dict[str, Any] = Field(default_factory=dict)
    new_clues: list[str] = Field(default_factory=list)
    open_hooks: list[str] = Field(default_factory=list)
    closed_hooks: list[str] = Field(default_factory=list)


class ParsedInstructionPayload(BaseModel):
    character_focus: dict[str, float] = Field(default_factory=dict)
    tone: str | None = None
    pace: str | None = None
    protected_characters: list[str] = Field(default_factory=list)
    relationship_direction: str | None = None


_client: Any | None = None
_client_signature: tuple[str, str | None, str | None] | None = None
_call_gate = threading.Lock()
_last_call_at = 0.0
_trace_var: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("llm_trace", default=None)
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_trace_id", default=None)


def _provider() -> str:
    return settings.llm_provider.lower().strip()



def _current_api_key() -> str | None:
    provider = _provider()
    if provider == "openai":
        return settings.openai_api_key
    if provider == "deepseek":
        return settings.deepseek_api_key
    if provider == "groq":
        return settings.groq_api_key
    return None



def _current_base_url() -> str | None:
    provider = _provider()
    if provider == "openai":
        return settings.openai_base_url
    if provider == "deepseek":
        return settings.deepseek_base_url
    if provider == "groq":
        return settings.groq_base_url
    return None



def _current_model() -> str:
    provider = _provider()
    if provider == "openai":
        return settings.openai_model
    if provider == "deepseek":
        return settings.deepseek_model
    if provider == "groq":
        return settings.groq_model
    raise GenerationError(
        code=ErrorCodes.PROVIDER_UNSUPPORTED,
        message=f"当前 LLM_PROVIDER={provider!r} 不受支持，仅支持 openai、deepseek 或 groq。",
        stage="provider_check",
        retryable=False,
        http_status=422,
        provider=provider,
    )



def _current_timeout() -> int:
    provider = _provider()
    if provider == "openai":
        return settings.openai_timeout_seconds
    if provider == "deepseek":
        return settings.deepseek_timeout_seconds
    if provider == "groq":
        return settings.groq_timeout_seconds
    return 120



def _current_max_output_tokens() -> int:
    provider = _provider()
    if provider == "openai":
        return settings.openai_max_output_tokens
    if provider == "deepseek":
        return settings.deepseek_max_output_tokens
    if provider == "groq":
        return settings.groq_max_output_tokens
    return 4000



def _current_chapter_max_output_tokens() -> int:
    provider = _provider()
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



def _append_trace(event: dict[str, Any]) -> None:
    trace = _trace_var.get()
    if trace is None:
        return
    items = list(trace)
    items.append(event)
    if len(items) > settings.llm_trace_limit:
        items = items[-settings.llm_trace_limit :]
    _trace_var.set(items)



def _throttle_llm_calls() -> int:
    minimum = max(int(settings.llm_call_min_interval_ms), 0)
    if minimum <= 0:
        return 0

    global _last_call_at
    waited_ms = 0
    with _call_gate:
        now = time.monotonic()
        remaining = (minimum / 1000.0) - (now - _last_call_at)
        if remaining > 0:
            time.sleep(remaining)
            waited_ms = int(round(remaining * 1000))
        _last_call_at = time.monotonic()
    return waited_ms



def _response_request_id(response: Any) -> str | None:
    for attr in ("_request_id", "request_id", "id"):
        value = getattr(response, attr, None)
        if value:
            return str(value)
    return None



def _extract_api_error_details(exc: Exception) -> dict[str, Any]:
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
    provider = _provider()
    if provider not in {"openai", "deepseek", "groq"}:
        raise GenerationError(
            code=ErrorCodes.PROVIDER_UNSUPPORTED,
            message=f"{stage} 失败：当前 LLM_PROVIDER={provider!r} 不受支持，请改成 openai、deepseek 或 groq。",
            stage=stage,
            retryable=False,
            http_status=422,
            provider=provider,
        )
    if OpenAI is None:
        raise GenerationError(
            code=ErrorCodes.PROVIDER_NOT_CONFIGURED,
            message="未检测到 openai Python SDK，请先安装依赖后再重试。",
            stage=stage,
            retryable=False,
            http_status=500,
            provider=provider,
        )
    if not _current_api_key():
        missing_env = "OPENAI_API_KEY" if provider == "openai" else ("DEEPSEEK_API_KEY" if provider == "deepseek" else "GROQ_API_KEY")
        raise GenerationError(
            code=ErrorCodes.PROVIDER_NOT_CONFIGURED,
            message=f"{stage} 失败：缺少 {missing_env}，当前无法调用模型。",
            stage=stage,
            retryable=False,
            http_status=422,
            provider=provider,
            details={"missing_env": missing_env},
        )



def is_openai_enabled() -> bool:
    provider = _provider()
    if provider not in {"openai", "deepseek", "groq"}:
        return False
    return OpenAI is not None and bool(_current_api_key())



def _get_client() -> Any:
    global _client, _client_signature
    require_generation_provider(stage="llm_client_init")
    signature = (_provider(), _current_api_key(), _current_base_url())
    if _client is None or _client_signature != signature:
        kwargs: dict[str, Any] = {"api_key": _current_api_key(), "timeout": _current_timeout()}
        base_url = _current_base_url()
        if base_url:
            kwargs["base_url"] = base_url
        _client = OpenAI(**kwargs)
        _client_signature = signature
    return _client



def _response_to_text(response: Any) -> str:
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


def _chat_completion_to_text(response: Any) -> str:
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



def _extract_json(text: str, *, stage: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message=f"{stage} 失败：模型没有返回任何可解析内容。",
            stage=stage,
            retryable=True,
            http_status=422,
            provider=_provider(),
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
        provider=_provider(),
        details={"response_head": raw[:500], "trace_id": _trace_id_var.get()},
    )


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


def _split_summary_items(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw or raw in {"无", "None", "none", "null", "[]", "-"}:
        return []
    parts = re.split(r"[；;\n]+", raw)
    items: list[str] = []
    for part in parts:
        item = part.strip().lstrip("-•* ").strip()
        if item and item not in {"无", "None", "none", "null"}:
            items.append(item[:80])
    return items[:6]


def _truncate_visible(text: str, limit: int) -> str:
    return text.strip()[:limit].strip()


def _heuristic_chapter_summary(title: str, content: str) -> ChapterSummaryPayload:
    normalized = re.sub(r"\s+", " ", (content or "").strip())
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", normalized) if s.strip()]
    if sentences:
        event_summary = _truncate_visible("".join(sentences[:2]), 80)
    else:
        event_summary = _truncate_visible(normalized, 80) or f"{title}中主角推进了当前线索。"

    final_sentence = sentences[-1] if sentences else ""
    open_hooks: list[str] = []
    if final_sentence and any(token in final_sentence for token in ["却", "忽然", "竟", "发现", "听见", "看见", "异样", "不对", "未", "?", "？"]):
        open_hooks = [_truncate_visible(final_sentence, 60)]

    return ChapterSummaryPayload(
        event_summary=event_summary or f"{title}中主角推进了当前线索。",
        character_updates={},
        new_clues=[],
        open_hooks=open_hooks,
        closed_hooks=[],
    )


def _parse_labeled_summary(text: str) -> ChapterSummaryPayload:
    raw = (text or "").strip()
    if not raw:
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message="chapter_summary_generation 失败：模型没有返回任何可解析内容。",
            stage="chapter_summary_generation",
            retryable=True,
            http_status=422,
            provider=_provider(),
            details={"trace_id": _trace_id_var.get()},
        )

    labels = {
        "事件摘要": "event_summary",
        "人物变化": "character_updates_text",
        "新线索": "new_clues_text",
        "未回收钩子": "open_hooks_text",
        "已回收钩子": "closed_hooks_text",
    }
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        for label, key in labels.items():
            prefix = f"{label}："
            prefix2 = f"{label}:"
            if stripped.startswith(prefix):
                parsed[key] = stripped[len(prefix):].strip()
            elif stripped.startswith(prefix2):
                parsed[key] = stripped[len(prefix2):].strip()

    if not parsed.get("event_summary"):
        # Try to recover from accidental JSON first
        try:
            data = _extract_json(raw, stage="chapter_summary_generation")
            return ChapterSummaryPayload.model_validate(data)
        except Exception:
            raise GenerationError(
                code=ErrorCodes.MODEL_RESPONSE_INVALID,
                message="chapter_summary_generation 失败：模型摘要未按约定格式返回。",
                stage="chapter_summary_generation",
                retryable=True,
                http_status=422,
                provider=_provider(),
                details={"response_head": raw[:500], "trace_id": _trace_id_var.get()},
            )

    character_updates_raw = parsed.get("character_updates_text", "")
    character_updates = {} if character_updates_raw in {"", "无"} else {"notes": _truncate_visible(character_updates_raw, 120)}
    return ChapterSummaryPayload(
        event_summary=_truncate_visible(parsed.get("event_summary", ""), 80),
        character_updates=character_updates,
        new_clues=_split_summary_items(parsed.get("new_clues_text", "")),
        open_hooks=_split_summary_items(parsed.get("open_hooks_text", "")),
        closed_hooks=_split_summary_items(parsed.get("closed_hooks_text", "")),
    )


def _call_text_response(
    *,
    stage: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int | None = None,
) -> str:
    require_generation_provider(stage=stage)
    client = _get_client()
    provider = _provider()
    output_tokens = max_output_tokens or _current_max_output_tokens()
    request_kwargs: dict[str, Any] = {
        "model": _current_model(),
    }
    if provider == "deepseek":
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

    waited_ms = _throttle_llm_calls()
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
    }
    logger.info(
        "llm_call start trace=%s stage=%s provider=%s model=%s system_chars=%s user_chars=%s max_output_tokens=%s waited_ms=%s",
        trace_common["trace_id"],
        stage,
        provider,
        request_kwargs["model"],
        len(system_prompt),
        len(user_prompt),
        output_tokens,
        waited_ms,
    )

    try:
        if provider == "deepseek":
            response = client.chat.completions.create(**request_kwargs)
        else:
            response = client.responses.create(**request_kwargs)
    except APITimeoutError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, **_extract_api_error_details(exc)}
        _append_trace({**trace_common, "status": "timeout", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_TIMEOUT,
            message=f"{stage} 失败：模型接口超时，请稍后重新生成。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=provider,
            details=details,
        ) from exc
    except AuthenticationError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, **_extract_api_error_details(exc)}
        _append_trace({**trace_common, "status": "auth_failed", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_AUTH_FAILED,
            message=f"{stage} 失败：API key 无效或没有权限访问当前模型。",
            stage=stage,
            retryable=False,
            http_status=401,
            provider=provider,
            details=details,
        ) from exc
    except RateLimitError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, **_extract_api_error_details(exc)}
        _append_trace({**trace_common, "status": "rate_limited", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_RATE_LIMITED,
            message=f"{stage} 失败：模型接口触发限流，请稍后重新生成。",
            stage=stage,
            retryable=True,
            http_status=429,
            provider=provider,
            details=details,
        ) from exc
    except APIConnectionError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, **_extract_api_error_details(exc)}
        _append_trace({**trace_common, "status": "connection_failed", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_CONNECTION_FAILED,
            message=f"{stage} 失败：无法连接到模型接口，请检查网络或 base_url 配置。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=provider,
            details=details,
        ) from exc
    except APIStatusError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, **_extract_api_error_details(exc)}
        _append_trace({**trace_common, "status": "api_status_error", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_STATUS_ERROR,
            message=f"{stage} 失败：模型接口返回异常状态码 {getattr(exc, 'status_code', 'unknown')}。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=provider,
            details=details,
        ) from exc
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        details = {"trace_id": _trace_id_var.get(), "duration_ms": duration_ms, "error_type": type(exc).__name__}
        _append_trace({**trace_common, "status": "unexpected_error", "duration_ms": duration_ms, "details": details})
        raise GenerationError(
            code=ErrorCodes.API_STATUS_ERROR,
            message=f"{stage} 失败：调用模型接口时出现未识别错误。",
            stage=stage,
            retryable=True,
            http_status=503,
            provider=provider,
            details=details,
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    text = _chat_completion_to_text(response) if provider == "deepseek" else _response_to_text(response)
    response_id = _response_request_id(response)
    event = {
        **trace_common,
        "status": "success",
        "duration_ms": duration_ms,
        "response_chars": len(text),
    }
    if response_id:
        event["response_id"] = response_id
    _append_trace(event)
    logger.info(
        "llm_call success trace=%s stage=%s duration_ms=%s response_chars=%s response_id=%s",
        trace_common["trace_id"],
        stage,
        duration_ms,
        len(text),
        response_id,
    )
    return text



def _call_json_response(
    *,
    stage: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    text = _call_text_response(
        stage=stage,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_output_tokens=max_output_tokens,
    )
    return _extract_json(text, stage=stage)



def generate_global_outline(payload: dict[str, Any], story_bible: dict[str, Any], total_acts: int) -> GlobalOutlinePayload:
    data = _call_json_response(
        stage="global_outline_generation",
        system_prompt=global_outline_system_prompt(),
        user_prompt=global_outline_user_prompt(payload=payload, story_bible=story_bible, total_acts=total_acts),
        max_output_tokens=1800,
    )
    outline = GlobalOutlinePayload.model_validate(data)
    normalized: list[StoryAct] = []
    for idx, act in enumerate(outline.acts[:total_acts], start=1):
        act.act_no = idx
        if not act.title:
            act.title = f"第{idx}幕"
        if not act.purpose:
            act.purpose = "稳定推进主线"
        if not act.summary:
            act.summary = "主角被更大的局势逐步卷入。"
        if not act.target_chapter_end:
            act.target_chapter_end = idx * 10
        normalized.append(act)
    outline.acts = normalized
    return outline



def generate_arc_outline(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
    global_outline: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    start_chapter: int,
    end_chapter: int,
    arc_no: int,
) -> ArcOutlinePayload:
    data = _call_json_response(
        stage="arc_outline_generation",
        system_prompt=arc_outline_system_prompt(),
        user_prompt=arc_outline_user_prompt(
            payload=payload,
            story_bible=story_bible,
            global_outline=global_outline,
            recent_summaries=recent_summaries,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            arc_no=arc_no,
        ),
        max_output_tokens=2200,
    )
    outline = ArcOutlinePayload.model_validate(data)
    normalized: list[ChapterPlan] = []
    expected_no = start_chapter
    for ch in outline.chapters[: max(end_chapter - start_chapter + 1, 0)]:
        ch.chapter_no = expected_no
        if not ch.title:
            ch.title = f"第{expected_no}章"
        if not ch.goal:
            ch.goal = "推进当前主线"
        if not ch.ending_hook:
            ch.ending_hook = "新的疑点浮出水面"
        if ch.chapter_type not in {"probe", "progress", "turning_point"}:
            goal_text = f"{ch.goal or ''} {ch.conflict or ''} {ch.ending_hook or ''}"
            if any(token in goal_text for token in ["追", "逃", "转折", "对峙", "揭示", "矿", "伏击"]):
                ch.chapter_type = "turning_point"
            elif any(token in goal_text for token in ["查", "买", "换", "谈", "探路", "坊市", "交易", "跟踪"]):
                ch.chapter_type = "progress"
            else:
                ch.chapter_type = "probe"
        if not ch.target_visible_chars_min or not ch.target_visible_chars_max:
            if ch.chapter_type == "turning_point":
                ch.target_visible_chars_min = settings.chapter_turning_point_target_min_visible_chars
                ch.target_visible_chars_max = settings.chapter_turning_point_target_max_visible_chars
            elif ch.chapter_type == "progress":
                ch.target_visible_chars_min = settings.chapter_progress_target_min_visible_chars
                ch.target_visible_chars_max = settings.chapter_progress_target_max_visible_chars
            else:
                ch.target_visible_chars_min = settings.chapter_probe_target_min_visible_chars
                ch.target_visible_chars_max = settings.chapter_probe_target_max_visible_chars
        if not ch.hook_style:
            hook_cycle = ["异象", "人物选择", "危险逼近", "信息反转", "平稳过渡", "余味收束"]
            ch.hook_style = hook_cycle[(expected_no - start_chapter) % len(hook_cycle)]
        if not ch.opening_beat:
            ch.opening_beat = "开场先落在一个具体动作或眼前小异常上。"
        if not ch.mid_turn:
            ch.mid_turn = "中段加入一次受阻、遮掩或判断失误，让场面真正动起来。"
        if not ch.discovery:
            ch.discovery = "给出一个具体而可感的发现，推动本章信息增量。"
        if not ch.closing_image:
            ch.closing_image = "结尾收在一个可见可感的画面上，而不是抽象总结。"
        if ch.supporting_character_focus:
            ch.supporting_character_focus = str(ch.supporting_character_focus).strip()[:20]
        if ch.supporting_character_note:
            ch.supporting_character_note = str(ch.supporting_character_note).strip()[:80]
        normalized.append(ch)
        expected_no += 1
    outline.chapters = normalized
    outline.arc_no = arc_no
    outline.start_chapter = start_chapter
    outline.end_chapter = end_chapter
    return outline



def generate_chapter_from_plan(
    novel_context: dict[str, Any],
    chapter_plan: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
    target_words: int,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> ChapterDraftPayload:
    text = _call_text_response(
        stage="chapter_generation",
        system_prompt=chapter_draft_system_prompt(),
        user_prompt=chapter_draft_user_prompt(
            novel_context=novel_context,
            chapter_plan=chapter_plan,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            active_interventions=active_interventions,
            target_words=target_words,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
        ),
        max_output_tokens=_current_chapter_max_output_tokens(),
    )
    content = _clean_plain_chapter_text(text, expected_title=chapter_plan.get("title"))
    data = {
        "title": (chapter_plan.get("title") or "").strip() or f"第{chapter_plan.get('chapter_no', '')}章",
        "content": content,
    }
    return ChapterDraftPayload.model_validate(data)



def extend_chapter_text(
    *,
    chapter_plan: dict[str, Any],
    existing_content: str,
    reason: str,
    target_visible_chars_min: int,
    target_visible_chars_max: int,
) -> str:
    text = _call_text_response(
        stage="chapter_extension",
        system_prompt=chapter_extension_system_prompt(),
        user_prompt=chapter_extension_user_prompt(
            chapter_plan=chapter_plan,
            existing_content=existing_content,
            reason=reason,
            target_visible_chars_min=target_visible_chars_min,
            target_visible_chars_max=target_visible_chars_max,
        ),
        max_output_tokens=min(max(_current_chapter_max_output_tokens() // 2, 400), 900),
    )
    return _clean_plain_chapter_text(text, expected_title=None)


def summarize_chapter(title: str, content: str) -> ChapterSummaryPayload:
    mode = (getattr(settings, "chapter_summary_mode", "auto") or "auto").lower().strip()
    if mode == "heuristic" or (mode == "auto" and _provider() in {"groq", "deepseek"}):
        return _heuristic_chapter_summary(title, content)

    try:
        text = _call_text_response(
            stage="chapter_summary_generation",
            system_prompt=summary_system_prompt(),
            user_prompt=summary_user_prompt(chapter_title=title, chapter_content=content),
            max_output_tokens=settings.chapter_summary_max_output_tokens,
        )
        return _parse_labeled_summary(text)
    except GenerationError:
        if mode == "auto":
            return _heuristic_chapter_summary(title, content)
        raise



def parse_instruction_with_openai(raw_instruction: str) -> ParsedInstructionPayload:
    data = _call_json_response(
        stage="instruction_parse",
        system_prompt=instruction_parse_system_prompt(),
        user_prompt=instruction_parse_user_prompt(raw_instruction),
        max_output_tokens=600,
    )
    return ParsedInstructionPayload.model_validate(data)
