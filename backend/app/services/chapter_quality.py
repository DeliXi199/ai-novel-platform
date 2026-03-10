from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from app.services.generation_exceptions import ErrorCodes, GenerationError


FORBIDDEN_REGEX_RULES: list[tuple[str, str]] = [
    (r"上一章《", "正文混入了上一章回顾模板"),
    (r"他今晚冒险来到这里，只为一件事", "正文出现了明显的固定任务模板句"),
    (r"可就在他以为.*新的异样还是冒了出来", "正文出现了明显的固定结尾模板句"),
    (r"在凡人流修仙这样的处境里", "正文混入了题材说明式模板句"),
    (r"请只输出 JSON|schema|提示词|读者可以看到|本章任务", "正文混入了元叙事或提示词残留"),
]

SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
WHITESPACE_RE = re.compile(r"\s+")
VISIBLE_CHAR_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
TERMINAL_PUNCTUATION = "。！？!?…』」》）)】"
TRUNCATION_TRAILING_WORDS = (
    "像一",
    "像是",
    "仿佛",
    "似乎",
    "岩石下方",
    "门外有",
    "他正要",
    "却忽然",
    "就在这",
    "随后便",
)
ACTION_MARKERS = ("抬", "按", "抓", "推", "看", "听", "摸", "藏", "退", "走", "停", "问", "答", "递", "翻", "敲")
DISCOVERY_MARKERS = ("发现", "看见", "听见", "察觉", "摸到", "意识到", "露出", "显出", "有异样", "不对")
HOOK_MARKERS = ("忽然", "却", "但", "未必", "还没", "还在", "将要", "像是", "不对", "异样")
TRANSITION_ENDING_STYLES = {"平稳过渡", "余味收束", "normal_transition", "transition", "quiet_close"}
STYLE_OVERUSE_RULES: list[tuple[str, int]] = [
    (r"不是错觉", 2),
    (r"心跳(?:快了几分|快了一拍|漏了一拍|微微一紧)", 2),
    (r"看了片刻", 2),
    (r"若有若无", 2),
    (r"微弱的暖意", 2),
    (r"温凉(?:的触感)?", 3),
    (r"微弱", 4),
    (r"几息", 3),
    (r"没有再说什么", 2),
    (r"盯着[^。！？!?]{0,12}看了片刻", 2),
]


def visible_length(text: str) -> int:
    return len(VISIBLE_CHAR_RE.findall(text or ""))


def _normalize_line(text: str) -> str:
    text = WHITESPACE_RE.sub("", text)
    return re.sub(r"[，。、“”‘’：:；;！？!?（）()《》<>\-—…·,.]", "", text)


def _non_empty_paragraphs(text: str) -> list[str]:
    return [item.strip() for item in text.split("\n") if item.strip()]


def _duplicate_paragraphs(text: str) -> list[str]:
    paragraphs = _non_empty_paragraphs(text)
    normalized = [_normalize_line(item) for item in paragraphs if _normalize_line(item)]
    counts = Counter(normalized)
    return [item for item, count in counts.items() if count >= 2 and len(item) >= 18]


def _sentence_repeat_ratio(text: str) -> float:
    sentences = [_normalize_line(x) for x in SENTENCE_SPLIT_RE.split(text) if _normalize_line(x)]
    if not sentences:
        return 0.0
    counts = Counter(sentences)
    repeated = sum(count for sentence, count in counts.items() if count >= 2 and len(sentence) >= 12)
    return repeated / max(len(sentences), 1)


def _ending_issue(text: str) -> str | None:
    stripped = (text or "").rstrip()
    if not stripped:
        return "empty"
    if stripped[-1] not in TERMINAL_PUNCTUATION:
        return "missing_terminal_punctuation"
    tail = stripped[-40:]
    if any(tail.endswith(token) for token in TRUNCATION_TRAILING_WORDS):
        return "truncated_phrase"
    if tail.count("“") > tail.count("”") or tail.count("『") > tail.count("』") or tail.count("《") > tail.count("》"):
        return "unclosed_quote"
    if re.search(r"(像一|像是|仿佛|似乎|随后|然后|就在|门外|崖边).{0,6}$", tail):
        return "hanging_clause"
    return None


def _style_overuse(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for pattern, threshold in STYLE_OVERUSE_RULES:
        count = len(re.findall(pattern, text))
        if count >= threshold:
            hits[pattern] = count
    return hits


def _progress_signals(text: str) -> dict[str, int]:
    paragraphs = _non_empty_paragraphs(text)
    dialogue_count = text.count("“") + text.count('"')
    action_hits = sum(text.count(marker) for marker in ACTION_MARKERS)
    discovery_hits = sum(text.count(marker) for marker in DISCOVERY_MARKERS)
    hook_hits = sum(text.count(marker) for marker in HOOK_MARKERS)
    return {
        "paragraphs": len(paragraphs),
        "dialogue_count": dialogue_count,
        "action_hits": action_hits,
        "discovery_hits": discovery_hits,
        "hook_hits": hook_hits,
    }



def validate_chapter_content(
    *,
    title: str,
    content: str,
    min_visible_chars: int,
    hard_min_visible_chars: int | None = None,
    recent_chapter_texts: Iterable[str] | None = None,
    similarity_checker=None,
    max_similarity: float = 0.76,
    target_visible_chars_max: int | None = None,
    hook_style: str | None = None,
) -> None:
    text = (content or "").strip()
    visible_chars = visible_length(text)
    hard_min = int(hard_min_visible_chars or min_visible_chars)
    if visible_chars < hard_min:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_SHORT,
            message=f"模型返回的章节过短，未达到最低正文长度要求（至少 {hard_min} 个可见字符）。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={
                "title": title,
                "visible_chars": visible_chars,
                "hard_min_visible_chars": hard_min,
                "target_min_visible_chars": min_visible_chars,
                "severity": "hard",
            },
        )
    if visible_chars < min_visible_chars:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_SHORT,
            message=f"模型返回的章节偏短，尚未达到目标正文长度（至少 {min_visible_chars} 个可见字符）。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={
                "title": title,
                "visible_chars": visible_chars,
                "hard_min_visible_chars": hard_min,
                "target_min_visible_chars": min_visible_chars,
                "target_visible_chars_max": target_visible_chars_max,
                "severity": "soft",
            },
        )

    if text.count("{") >= 2 and text.count("}") >= 2:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="模型返回内容仍像 JSON 或混有结构化残留，未形成可直接入库的正文。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title},
        )

    ending_issue = _ending_issue(text)
    if ending_issue:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_ENDING_INCOMPLETE,
            message="模型返回的正文疑似被截断，结尾没有自然收束，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "tail": text[-60:], "ending_issue": ending_issue},
        )

    for pattern, msg in FORBIDDEN_REGEX_RULES:
        if re.search(pattern, text, flags=re.S):
            raise GenerationError(
                code=ErrorCodes.CHAPTER_META_TEXT,
                message=msg,
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, "pattern": pattern},
            )

    duplicated_paragraphs = _duplicate_paragraphs(text)
    if duplicated_paragraphs:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_DUPLICATED_PARAGRAPHS,
            message="正文存在重复段落，说明本次生成质量不稳定。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "duplicates": duplicated_paragraphs[:3]},
        )

    style_hits = _style_overuse(text)
    if style_hits:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="正文里高频口头禅或固定句式重复过多，AI 痕迹仍然偏重。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "style_hits": style_hits},
        )

    if _sentence_repeat_ratio(text) > 0.22:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="正文内部重复句过多，整体读感接近模板拼接，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title},
        )

    progress = _progress_signals(text)
    transition_ending = str(hook_style or "").strip() in TRANSITION_ENDING_STYLES
    weak_progress = progress["paragraphs"] < 4 or progress["action_hits"] < 4 or progress["discovery_hits"] < 1
    weak_ending = (not transition_ending) and progress["hook_hits"] < 1
    if weak_progress or weak_ending:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
            message="本章虽然成文，但事件推进不足，像片段或铺垫残段，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, **progress, "visible_chars": visible_chars},
        )

    if similarity_checker and recent_chapter_texts:
        best_similarity = 0.0
        for previous in recent_chapter_texts:
            if not previous:
                continue
            best_similarity = max(best_similarity, float(similarity_checker(text, previous)))
        if best_similarity >= max_similarity:
            raise GenerationError(
                code=ErrorCodes.CHAPTER_TOO_SIMILAR,
                message="本章与最近章节过于相似，疑似重复套模板生成。",
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, "similarity": round(best_similarity, 4)},
            )
