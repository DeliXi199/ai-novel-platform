import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.prompt_templates import (
    bootstrap_system_prompt,
    bootstrap_user_prompt,
    instruction_parse_system_prompt,
    instruction_parse_user_prompt,
    next_chapter_system_prompt,
    next_chapter_user_prompt,
)

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


class GeneratedChapterPayload(BaseModel):
    title: str
    content: str
    event_summary: str
    character_updates: dict[str, Any] = Field(default_factory=dict)
    new_clues: list[str] = Field(default_factory=list)
    open_hooks: list[str] = Field(default_factory=list)
    closed_hooks: list[str] = Field(default_factory=list)
    generation_meta: dict[str, Any] = Field(default_factory=dict)


class ParsedInstructionPayload(BaseModel):
    character_focus: dict[str, float] = Field(default_factory=dict)
    tone: str | None = None
    pace: str | None = None
    protected_characters: list[str] = Field(default_factory=list)
    relationship_direction: str | None = None


_client: Any | None = None


def _provider() -> str:
    return settings.llm_provider.lower().strip()


def is_openai_enabled() -> bool:
    """
    保留旧函数名，避免改其他调用点。
    实际含义：只要 provider 不是 mock 且对应 key 已配置，就启用真实 LLM。
    """
    if OpenAI is None:
        return False

    provider = _provider()
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    return False


def _current_api_key() -> str | None:
    provider = _provider()
    if provider == "openai":
        return settings.openai_api_key
    if provider == "groq":
        return settings.groq_api_key
    return None


def _current_base_url() -> str | None:
    provider = _provider()
    if provider == "openai":
        return settings.openai_base_url
    if provider == "groq":
        return settings.groq_base_url
    return None


def _current_model() -> str:
    provider = _provider()
    if provider == "openai":
        return settings.openai_model
    if provider == "groq":
        return settings.groq_model
    raise ValueError(f"Unsupported provider: {provider}")


def _current_timeout() -> int:
    provider = _provider()
    if provider == "openai":
        return settings.openai_timeout_seconds
    if provider == "groq":
        return settings.groq_timeout_seconds
    return 120


def _current_max_output_tokens() -> int:
    provider = _provider()
    if provider == "openai":
        return settings.openai_max_output_tokens
    if provider == "groq":
        return settings.groq_max_output_tokens
    return 4000


def _get_client() -> Any:
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {
            "api_key": _current_api_key(),
            "timeout": _current_timeout(),
        }
        base_url = _current_base_url()
        if base_url:
            kwargs["base_url"] = base_url
        _client = OpenAI(**kwargs)
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


def _extract_json(text: str) -> dict:
    text = text.strip()

    # 先直接尝试完整 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 去掉 markdown code fence
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    # 截取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 如果是被截断的 JSON，尽量补齐
    if start != -1 and end == -1:
        candidate = text[start:]

        # 尝试简单补尾
        if candidate.count("{") > candidate.count("}"):
            candidate += "}" * (candidate.count("{") - candidate.count("}"))

        if candidate.count('"') % 2 == 1:
            candidate += '"'

        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError(f"Model response does not contain valid JSON: {text[:500]}")


def _call_json_response(
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    client = _get_client()
    provider = _provider()

    request_kwargs: dict[str, Any] = {
        "model": _current_model(),
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_output_tokens": max_output_tokens or _current_max_output_tokens(),
        "store": False,
    }

    if provider == "openai":
        request_kwargs["reasoning"] = {"effort": settings.openai_reasoning_effort}

    response = client.responses.create(**request_kwargs)
    text = _response_to_text(response)
    logger.info("LLM raw response head: %s", text[:300])
    return _extract_json(text)


def generate_bootstrap_chapter(
    payload: dict[str, Any],
    story_bible: dict[str, Any],
) -> GeneratedChapterPayload:
    data = _call_json_response(
        system_prompt=bootstrap_system_prompt(),
        user_prompt=bootstrap_user_prompt(
            payload=payload,
            story_bible=story_bible,
            target_words=settings.chapter_target_words,
        ),
    )
    chapter = GeneratedChapterPayload.model_validate(data)
    chapter.generation_meta = {
        **chapter.generation_meta,
        "generator": "responses_api",
        "provider": _provider(),
        "model": _current_model(),
    }
    return chapter


def generate_serial_chapter(
    novel_context: dict[str, Any],
    last_chapter: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
    active_interventions: list[dict[str, Any]],
) -> GeneratedChapterPayload:
    data = _call_json_response(
        system_prompt=next_chapter_system_prompt(),
        user_prompt=next_chapter_user_prompt(
            novel_context=novel_context,
            last_chapter=last_chapter,
            recent_summaries=recent_summaries,
            active_interventions=active_interventions,
            target_words=settings.chapter_target_words,
        ),
    )
    chapter = GeneratedChapterPayload.model_validate(data)
    chapter.generation_meta = {
        **chapter.generation_meta,
        "generator": "responses_api",
        "provider": _provider(),
        "model": _current_model(),
    }
    return chapter


def parse_instruction_with_openai(raw_instruction: str) -> ParsedInstructionPayload:
    """
    保留旧函数名，避免改其他调用点。
    现在它既可走 OpenAI，也可走 Groq。
    """
    data = _call_json_response(
        system_prompt=instruction_parse_system_prompt(),
        user_prompt=instruction_parse_user_prompt(raw_instruction),
        max_output_tokens=800,
    )
    return ParsedInstructionPayload.model_validate(data)
