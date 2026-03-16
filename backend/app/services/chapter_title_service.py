from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.core.config import settings
from app.services.generation_exceptions import GenerationError
from app.services.openai_story_engine import generate_chapter_title_candidates

_GENERIC_TITLE_TERMS = {
    "微光", "暗流", "夜半", "余波", "回响", "试探", "旧纸", "旧巷", "旧街", "坊市",
    "风起", "涟漪", "暗影", "波澜", "前夜", "薄雾", "残页", "低语", "回声", "异动",
}


_BAD_TITLE_FRAGMENTS = {
    "主角", "有人", "那人", "对方", "自己", "这里", "那里", "事情", "东西", "时候", "结果", "变化", "问题",
}

_STRUCTURE_PATTERNS: list[tuple[str, str]] = [
    ("X之Y", r".+之.+"),
    ("再X", r"^(再|又|仍|重|复).+"),
    ("旧X", r"^(旧|老|前).+"),
    ("新X", r"^(新|初|首).+"),
    ("X将Y", r"^.+将.+"),
    ("X之夜", r"^.+之夜$"),
]


@dataclass(slots=True)
class TitleCandidateScore:
    title: str
    total_score: float
    duplicate_risk: float
    concreteness_score: float
    generic_penalty: float
    cooling_penalty: float
    structure_penalty: float
    notes: list[str]
    source: str
    title_type: str | None = None
    angle: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class TitleRefinementResult:
    final_title: str
    original_title: str
    candidates: list[TitleCandidateScore]
    ai_attempted: bool
    ai_succeeded: bool
    ai_error: dict[str, Any] | None
    cooled_terms: list[str]
    recent_titles: list[str]



def _strip_title_prefix(title: str) -> str:
    text = str(title or "").strip()
    text = re.sub(r"^第\s*[0-9零一二三四五六七八九十百千两]+\s*章[：:、\-—\s]*", "", text)
    return text.strip("《》【】[]()（）『』「」“”‘’ ")



def normalize_title(title: str | None, chapter_no: int | None = None) -> str:
    text = _strip_title_prefix(str(title or "").replace("\n", " ").replace("\r", " "))
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^[：:、·•\-—]+", "", text)
    text = re.sub(r"[：:、·•\-—]+$", "", text)
    if not text and chapter_no:
        return f"第{chapter_no}章"
    if len(text) > 16:
        text = text[:16].rstrip("，。；、！？!?：:")
    return text or (f"第{chapter_no}章" if chapter_no else "未命名章节")



def _title_key(title: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", normalize_title(title))



def _char_bigrams(text: str) -> set[str]:
    if len(text) <= 1:
        return {text} if text else set()
    return {text[idx : idx + 2] for idx in range(len(text) - 1)}



def _extract_phrases(text: str, *, max_count: int = 24) -> list[str]:
    normalized = normalize_title(text)
    chunks = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", normalized)
    phrases: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if re.fullmatch(r"[A-Za-z0-9]+", chunk):
            if len(chunk) >= 2:
                phrases.append(chunk.lower())
            continue
        if len(chunk) <= 4:
            phrases.append(chunk)
        else:
            phrases.append(chunk[:4])
            phrases.append(chunk[-4:])
        if len(chunk) >= 2:
            for idx in range(min(len(chunk) - 1, 6)):
                phrases.append(chunk[idx : idx + 2])
    ordered: list[str] = []
    seen: set[str] = set()
    for item in phrases:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
        if len(ordered) >= max_count:
            break
    return ordered



def _structure_signature(title: str) -> str:
    normalized = normalize_title(title)
    for label, pattern in _STRUCTURE_PATTERNS:
        if re.fullmatch(pattern, normalized):
            return label
    if len(normalized) <= 4:
        return f"短标题_{len(normalized)}"
    if len(normalized) <= 8:
        return "中短标题"
    return "长标题"



def title_similarity(left: str, right: str) -> float:
    a = _title_key(left)
    b = _title_key(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    grams_a = _char_bigrams(a)
    grams_b = _char_bigrams(b)
    gram_score = len(grams_a & grams_b) / max(len(grams_a | grams_b), 1)
    phrases_a = set(_extract_phrases(a))
    phrases_b = set(_extract_phrases(b))
    phrase_score = len(phrases_a & phrases_b) / max(len(phrases_a | phrases_b), 1)
    return max(seq, (seq * 0.5) + (gram_score * 0.35) + (phrase_score * 0.15))



def _frequent_recent_terms(recent_titles: list[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for title in recent_titles:
        counter.update(_extract_phrases(title))
    return counter



def build_cooled_terms(recent_titles: list[str]) -> list[str]:
    counter = _frequent_recent_terms(recent_titles)
    result: list[str] = []
    for term, count in counter.most_common(32):
        if count < 2:
            continue
        if len(term) < 2:
            continue
        result.append(term)
        if len(result) >= 12:
            break
    return result



def _plan_keywords(plan: dict[str, Any] | None, summary: dict[str, Any] | None = None) -> set[str]:
    payload = plan or {}
    values = [
        payload.get("goal"),
        payload.get("conflict"),
        payload.get("ending_hook"),
        payload.get("main_scene"),
        payload.get("proactive_move"),
        payload.get("progress_kind"),
        payload.get("event_type"),
        payload.get("supporting_character_focus"),
    ]
    if summary:
        values.extend(
            [
                summary.get("event_summary"),
                " ".join(summary.get("new_clues") or []),
                " ".join(summary.get("open_hooks") or []),
            ]
        )
    keywords: set[str] = set()
    for value in values:
        keywords.update(_extract_phrases(str(value or ""), max_count=12))
    return {item for item in keywords if len(item) >= 2}



def _fallback_candidates(
    *,
    chapter_no: int,
    original_title: str,
    plan: dict[str, Any],
    summary: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    seeds = [
        summary.get("event_summary") if summary else None,
        plan.get("goal"),
        plan.get("conflict"),
        plan.get("ending_hook"),
        plan.get("main_scene"),
        plan.get("proactive_move"),
    ]
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for seed in seeds:
        for phrase in _extract_phrases(str(seed or ""), max_count=10):
            normalized = normalize_title(phrase, chapter_no)
            if len(normalized) < 2 or normalized in _BAD_TITLE_FRAGMENTS:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(
                {
                    "title": normalized,
                    "title_type": "结果型",
                    "angle": "本地回退",
                    "reason": "从本章推进结果与场景信息中抽取短标题。",
                    "source": "local_fallback",
                }
            )
            if len(candidates) >= 5:
                return candidates
    normalized_original = normalize_title(original_title, chapter_no)
    if normalized_original not in seen:
        candidates.insert(
            0,
            {
                "title": normalized_original,
                "title_type": "原规划标题",
                "angle": "保底",
                "reason": "保留章节规划阶段的工作标题。",
                "source": "original",
            },
        )
    return candidates[:5]



def score_title_candidate(
    *,
    title: str,
    recent_titles: list[str],
    cooled_terms: list[str],
    plan: dict[str, Any],
    summary: dict[str, Any] | None,
    original_title: str,
    source: str,
    title_type: str | None = None,
    angle: str | None = None,
    reason: str | None = None,
) -> TitleCandidateScore:
    normalized = normalize_title(title, int(plan.get("chapter_no") or 0) or None)
    recent_normalized = [normalize_title(item) for item in recent_titles if normalize_title(item)]
    notes: list[str] = []
    best_similarity = 0.0
    most_similar_title = ""
    for recent in recent_normalized:
        similarity = title_similarity(normalized, recent)
        if similarity > best_similarity:
            best_similarity = similarity
            most_similar_title = recent

    duplicate_threshold = float(getattr(settings, "chapter_title_similarity_threshold", 0.72) or 0.72)
    duplicate_penalty = 0.0
    if any(_title_key(normalized) == _title_key(item) for item in recent_normalized):
        duplicate_penalty += 120.0
        notes.append("与最近章节同名")
    if best_similarity >= duplicate_threshold:
        duplicate_penalty += 72.0 + max((best_similarity - duplicate_threshold) * 110.0, 0.0)
        notes.append(f"与“{most_similar_title}”过近({best_similarity:.2f})")
    elif best_similarity >= duplicate_threshold - 0.08:
        duplicate_penalty += 18.0 + max((best_similarity - (duplicate_threshold - 0.08)) * 80.0, 0.0)
        notes.append(f"与“{most_similar_title}”略近({best_similarity:.2f})")

    structure_penalty = 0.0
    signature = _structure_signature(normalized)
    if sum(1 for item in recent_normalized if _structure_signature(item) == signature) >= 2:
        structure_penalty += 8.0
        notes.append(f"结构模板“{signature}”近期偏热")

    cooling_penalty = 0.0
    phrases = set(_extract_phrases(normalized))
    hits = [term for term in cooled_terms if term in phrases or term in normalized]
    if hits:
        cooling_penalty += min(len(hits) * 6.0, 24.0)
        notes.append(f"命中冷却词：{'/'.join(hits[:4])}")

    generic_penalty = 0.0
    generic_hits = [term for term in _GENERIC_TITLE_TERMS if term in normalized]
    if normalized in _BAD_TITLE_FRAGMENTS:
        generic_penalty += 22.0
        notes.append("标题过于空泛")
    if generic_hits:
        generic_penalty += min(len(generic_hits) * 5.0, 18.0)
        notes.append(f"偏模板词：{'/'.join(generic_hits[:4])}")

    concreteness_score = 0.0
    keywords = _plan_keywords(plan, summary=summary)
    if keywords:
        matched = [term for term in keywords if term in normalized or term in phrases]
        if matched:
            concreteness_score += min(18.0, 5.0 + len(matched) * 2.5)
            notes.append(f"贴近本章结果词：{'/'.join(matched[:4])}")
    if 2 <= len(normalized) <= 10:
        concreteness_score += 8.0
    elif len(normalized) <= 14:
        concreteness_score += 4.0
    else:
        generic_penalty += 6.0
        notes.append("标题偏长")

    if normalized == normalize_title(original_title):
        concreteness_score += 3.0
        notes.append("延续原规划标题")

    if any(ch.isdigit() for ch in normalized):
        generic_penalty += 4.0
        notes.append("含数字感较强")

    total = 100.0 + concreteness_score - duplicate_penalty - generic_penalty - cooling_penalty - structure_penalty
    total = round(total, 3)
    return TitleCandidateScore(
        title=normalized,
        total_score=total,
        duplicate_risk=round(best_similarity, 3),
        concreteness_score=round(concreteness_score, 3),
        generic_penalty=round(generic_penalty, 3),
        cooling_penalty=round(cooling_penalty, 3),
        structure_penalty=round(structure_penalty, 3),
        notes=notes,
        source=source,
        title_type=title_type,
        angle=angle,
        reason=reason,
    )



def refine_generated_chapter_title(
    *,
    chapter_no: int,
    original_title: str,
    content: str,
    plan: dict[str, Any],
    recent_titles: list[str],
    summary: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
) -> TitleRefinementResult:
    recent_clean = [normalize_title(item) for item in recent_titles if normalize_title(item)]
    recent_window = max(int(getattr(settings, "chapter_title_recent_window", 20) or 20), 5)
    recent_window_titles = recent_clean[-recent_window:]
    cooled_terms = build_cooled_terms(recent_window_titles)

    ai_attempted = bool(getattr(settings, "chapter_title_refinement_enabled", True))
    ai_succeeded = False
    ai_error: dict[str, Any] | None = None
    raw_candidates: list[dict[str, Any]] = []

    if ai_attempted:
        try:
            raw_candidates = generate_chapter_title_candidates(
                chapter_no=chapter_no,
                original_title=original_title,
                chapter_plan=plan,
                chapter_content=content,
                recent_titles=recent_window_titles,
                cooled_terms=cooled_terms,
                summary=summary or {},
                candidate_count=max(int(getattr(settings, "chapter_title_refinement_candidate_count", 5) or 5), 3),
                request_timeout_seconds=timeout_seconds,
            )
            ai_succeeded = bool(raw_candidates)
        except GenerationError as exc:
            ai_error = {
                "code": exc.code,
                "stage": exc.stage,
                "message": exc.message,
                "details": exc.details or {},
            }
        except Exception as exc:  # pragma: no cover
            ai_error = {
                "code": "TITLE_REFINEMENT_UNKNOWN",
                "stage": "chapter_title_refinement",
                "message": str(exc),
                "details": {"error_type": type(exc).__name__},
            }

    merged_candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    fallback_candidates = _fallback_candidates(
        chapter_no=chapter_no,
        original_title=original_title,
        plan=plan,
        summary=summary,
    ) if (not ai_succeeded or len(raw_candidates) < 2) else []
    for item in raw_candidates + fallback_candidates:
        title = normalize_title(str(item.get("title") or ""), chapter_no)
        key = _title_key(title)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        merged_candidates.append({**item, "title": title})

    if normalize_title(original_title, chapter_no) not in [item.get("title") for item in merged_candidates]:
        merged_candidates.insert(
            0,
            {
                "title": normalize_title(original_title, chapter_no),
                "title_type": "原规划标题",
                "angle": "保底",
                "reason": "保留章节规划阶段的工作标题。",
                "source": "original",
            },
        )

    scored = [
        score_title_candidate(
            title=item.get("title") or original_title,
            recent_titles=recent_window_titles,
            cooled_terms=cooled_terms,
            plan={**plan, "chapter_no": chapter_no},
            summary=summary,
            original_title=original_title,
            source=str(item.get("source") or ("ai" if ai_succeeded else "local")),
            title_type=item.get("title_type"),
            angle=item.get("angle"),
            reason=item.get("reason"),
        )
        for item in merged_candidates
    ]
    scored.sort(key=lambda item: (item.total_score, -item.duplicate_risk, 1 if item.source == "original" else 0), reverse=True)
    final_title = scored[0].title if scored else normalize_title(original_title, chapter_no)
    return TitleRefinementResult(
        final_title=final_title,
        original_title=normalize_title(original_title, chapter_no),
        candidates=scored,
        ai_attempted=ai_attempted,
        ai_succeeded=ai_succeeded,
        ai_error=ai_error,
        cooled_terms=cooled_terms,
        recent_titles=recent_window_titles,
    )
