from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import (
    call_json_response,
    call_text_response,
    extract_json,
    is_openai_enabled,
    provider_name,
)
from app.services.prompt_templates import (
    chapter_title_refinement_system_prompt,
    chapter_title_refinement_user_prompt,
    summary_system_prompt,
    summary_title_package_system_prompt,
    summary_title_package_user_prompt,
    summary_user_prompt,
)

logger = logging.getLogger(__name__)


class ChapterSummaryPayload(BaseModel):
    event_summary: str
    character_updates: dict[str, Any] = Field(default_factory=dict)
    new_clues: list[str] = Field(default_factory=list)
    open_hooks: list[str] = Field(default_factory=list)
    closed_hooks: list[str] = Field(default_factory=list)


class ChapterTitleCandidate(BaseModel):
    title: str
    title_type: str | None = None
    angle: str | None = None
    reason: str | None = None


class ChapterTitleRefinementPayload(BaseModel):
    recommended_title: str
    candidates: list[ChapterTitleCandidate] = Field(default_factory=list)


class ChapterSummaryTitlePackagePayload(BaseModel):
    summary: ChapterSummaryPayload
    title_refinement: ChapterTitleRefinementPayload



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



def _normalize_summary_items(items: list[Any] | None, *, limit: int = 6, item_limit: int = 80) -> list[str]:
    results: list[str] = []
    for item in items or []:
        text = _truncate_visible(str(item or "").strip(), item_limit)
        if text and text not in {"无", "None", "none", "null"}:
            results.append(text)
        if len(results) >= limit:
            break
    return results



def _normalize_chapter_summary_payload(payload: ChapterSummaryPayload) -> ChapterSummaryPayload:
    character_updates = payload.character_updates if isinstance(payload.character_updates, dict) else {}
    return ChapterSummaryPayload(
        event_summary=_truncate_visible(str(payload.event_summary or "").strip(), 80),
        character_updates=character_updates,
        new_clues=_normalize_summary_items(payload.new_clues, limit=6, item_limit=80),
        open_hooks=_normalize_summary_items(payload.open_hooks, limit=6, item_limit=80),
        closed_hooks=_normalize_summary_items(payload.closed_hooks, limit=6, item_limit=80),
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
            provider=provider_name_fn(),
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
                parsed[key] = stripped[len(prefix) :].strip()
            elif stripped.startswith(prefix2):
                parsed[key] = stripped[len(prefix2) :].strip()

    if not parsed.get("event_summary"):
        try:
            data = extract_json(raw, stage="chapter_summary_generation")
            return ChapterSummaryPayload.model_validate(data)
        except Exception:
            raise GenerationError(
                code=ErrorCodes.MODEL_RESPONSE_INVALID,
                message="chapter_summary_generation 失败：模型摘要未按约定格式返回。",
                stage="chapter_summary_generation",
                retryable=True,
                http_status=422,
                provider=provider_name_fn(),
                details={"response_head": raw[:500]},
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
    call_json_response_fn=call_json_response,
    is_openai_enabled_fn=is_openai_enabled,
    provider_name_fn=provider_name,
) -> list[dict[str, Any]]:
    if not is_openai_enabled_fn():
        raise GenerationError(
            code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
            message="章节标题精修需要可用的 AI，但当前未检测到可用模型配置。",
            stage="chapter_title_refinement",
            retryable=True,
            http_status=503,
            provider=provider_name_fn(),
        )

    content = (chapter_content or "").strip()
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    opening_excerpt = _truncate_visible(paragraphs[0] if paragraphs else normalized, 220)
    closing_excerpt = _truncate_visible(paragraphs[-1] if paragraphs else normalized[-220:], 220)
    content_digest = {
        "opening_excerpt": opening_excerpt,
        "closing_excerpt": closing_excerpt,
        "content_length": len(content),
    }
    summary_payload = summary or {}
    data = call_json_response_fn(
        stage="chapter_title_refinement",
        system_prompt=chapter_title_refinement_system_prompt(),
        user_prompt=chapter_title_refinement_user_prompt(
            chapter_no=chapter_no,
            original_title=original_title,
            chapter_plan=chapter_plan,
            content_digest=content_digest,
            summary_payload=summary_payload,
            recent_titles=recent_titles,
            cooled_terms=cooled_terms,
            candidate_count=candidate_count,
        ),
        max_output_tokens=max(int(getattr(settings, "chapter_title_max_output_tokens", 900) or 900), 320),
        timeout_seconds=request_timeout_seconds,
    )
    payload = ChapterTitleRefinementPayload.model_validate(data)
    results: list[dict[str, Any]] = []
    if payload.recommended_title:
        results.append(
            {
                "title": payload.recommended_title,
                "title_type": "推荐标题",
                "angle": "模型推荐",
                "reason": "模型认为它最贴近成稿且更不易重复。",
                "source": "ai_recommended",
            }
        )
    for item in payload.candidates[: max(candidate_count, 1)]:
        if not item.title:
            continue
        results.append(
            {
                "title": item.title,
                "title_type": item.title_type,
                "angle": item.angle,
                "reason": item.reason,
                "source": "ai",
            }
        )
    return results



def summarize_chapter(
    title: str,
    content: str,
    request_timeout_seconds: int | None = None,
    *,
    call_text_response_fn=call_text_response,
) -> ChapterSummaryPayload:
    mode = (getattr(settings, "chapter_summary_mode", "llm") or "llm").lower().strip()
    if mode != "llm":
        logger.info("chapter_summary_mode=%s ignored; chapter summary now always uses AI", mode)
    text = call_text_response_fn(
        stage="chapter_summary_generation",
        system_prompt=summary_system_prompt(),
        user_prompt=summary_user_prompt(chapter_title=title, chapter_content=content),
        max_output_tokens=settings.chapter_summary_max_output_tokens,
        timeout_seconds=request_timeout_seconds,
    )
    return _normalize_chapter_summary_payload(_parse_labeled_summary(text))



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
    call_json_response_fn=call_json_response,
    is_openai_enabled_fn=is_openai_enabled,
    provider_name_fn=provider_name,
) -> ChapterSummaryTitlePackagePayload:
    if not is_openai_enabled_fn():
        raise GenerationError(
            code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
            message="章节摘要与标题精修需要可用的 AI，但当前未检测到可用模型配置。",
            stage="chapter_summary_title_package",
            retryable=True,
            http_status=503,
            provider=provider_name_fn(),
        )

    data = call_json_response_fn(
        stage="chapter_summary_title_package",
        system_prompt=summary_title_package_system_prompt(),
        user_prompt=summary_title_package_user_prompt(
            chapter_no=chapter_no,
            chapter_title=title,
            chapter_plan=chapter_plan,
            chapter_content=content,
            recent_titles=recent_titles,
            cooled_terms=cooled_terms,
            candidate_count=max(int(candidate_count or 0), 3),
        ),
        max_output_tokens=max(
            int(getattr(settings, "chapter_summary_title_package_max_output_tokens", 1200) or 1200),
            int(getattr(settings, "chapter_summary_max_output_tokens", 320) or 320) + 320,
        ),
        timeout_seconds=request_timeout_seconds,
    )
    payload = ChapterSummaryTitlePackagePayload.model_validate(data)
    payload.summary = _normalize_chapter_summary_payload(payload.summary)
    return payload
