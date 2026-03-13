from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.hard_fact_guard_conflicts import _apply_facts_to_state, check_hard_fact_conflicts
from app.services.hard_fact_guard_extractors import extract_chapter_hard_facts
from app.services.hard_fact_guard_review import _apply_llm_review_to_report, _review_hard_fact_conflicts_with_llm, _should_use_llm_hard_fact_review
from app.services.hard_fact_guard_utils import HardFactConflict, _now_iso, build_hard_fact_guard_rules, empty_hard_fact_guard, ensure_hard_fact_guard


def register_hard_fact_check(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    chapter_title: str,
    facts: dict[str, Any],
    serial_stage: str,
    report: dict[str, Any],
    raise_on_conflict: bool = False,
) -> dict[str, Any]:
    guard = ensure_hard_fact_guard(story_bible)
    report_entry = {
        "chapter_no": chapter_no,
        "chapter_title": chapter_title,
        "serial_stage": serial_stage,
        "passed": report.get("passed", True),
        "conflict_count": report.get("conflict_count", 0),
        "summary": report.get("summary"),
        "conflicts": report.get("conflicts", [])[:8],
        "facts": {
            "realm": facts.get("realm", []),
            "life_status": facts.get("life_status", []),
            "injury_status": facts.get("injury_status", []),
            "identity_exposure": facts.get("identity_exposure", []),
            "item_ownership": facts.get("item_ownership", []),
        },
        "llm_review": report.get("llm_review"),
        "checked_at": report.get("checked_at") or _now_iso(),
    }
    reports = [item for item in guard.get("chapter_reports", []) if int(item.get("chapter_no", 0) or 0) != chapter_no]
    reports.append(report_entry)
    guard["chapter_reports"] = reports[-18:]
    guard["last_checked_chapter"] = max(int(guard.get("last_checked_chapter", 0) or 0), chapter_no)
    guard["last_conflict_report"] = None if report.get("passed", True) else report_entry

    base_published = deepcopy(guard.get("published_state") or {})
    base_stock = deepcopy(guard.get("stock_state") or base_published)
    if serial_stage == "published":
        guard["published_state"] = _apply_facts_to_state(base_published, facts, chapter_no=chapter_no, chapter_title=chapter_title)
        guard["stock_state"] = _apply_facts_to_state(base_stock, facts, chapter_no=chapter_no, chapter_title=chapter_title)
    else:
        guard["stock_state"] = _apply_facts_to_state(base_stock, facts, chapter_no=chapter_no, chapter_title=chapter_title)

    story_bible["hard_fact_guard"] = guard
    if raise_on_conflict and not report.get("passed", True):
        raise HardFactConflict(report_entry)
    return story_bible


def validate_and_register_chapter(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
    chapter_no: int,
    chapter_title: str,
    content: str,
    plan: dict[str, Any] | None,
    summary: Any | None,
    serial_stage: str,
    reference_mode: str = "stock",
    raise_on_conflict: bool = False,
    use_llm_review: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    guard = ensure_hard_fact_guard(story_bible)
    reference_state = deepcopy(guard.get("stock_state") if reference_mode == "stock" else guard.get("published_state")) or {}
    facts = extract_chapter_hard_facts(
        protagonist_name=protagonist_name,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        content=content,
        plan=plan,
        summary=summary,
        reference_state=reference_state,
    )
    report = check_hard_fact_conflicts(reference_state, facts, chapter_no=chapter_no)
    if report.get("conflicts") and use_llm_review and _should_use_llm_hard_fact_review():
        review = _review_hard_fact_conflicts_with_llm(
            chapter_no=chapter_no,
            chapter_title=chapter_title,
            serial_stage=serial_stage,
            content=content,
            reference_state=reference_state,
            facts=facts,
            conflicts=list(report.get("conflicts") or []),
        )
        report = _apply_llm_review_to_report(report, review)
    story_bible = register_hard_fact_check(
        story_bible,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        facts=facts,
        serial_stage=serial_stage,
        report=report,
        raise_on_conflict=raise_on_conflict,
    )
    return story_bible, facts, report


def rebuild_hard_fact_guard_from_chapters(
    story_bible: dict[str, Any],
    *,
    protagonist_name: str,
    chapters: list[Any],
) -> dict[str, Any]:
    guard = empty_hard_fact_guard()
    story_bible["hard_fact_guard"] = guard
    for chapter in sorted(chapters, key=lambda item: int(getattr(item, "chapter_no", 0) or 0)):
        meta = getattr(chapter, "generation_meta", None) or {}
        report = meta.get("hard_fact_report") if isinstance(meta, dict) else None
        facts = report.get("facts") if isinstance(report, dict) else None
        if not isinstance(facts, dict):
            summary = getattr(chapter, "summary", None)
            plan = meta.get("chapter_plan") if isinstance(meta, dict) else {}
            facts = extract_chapter_hard_facts(
                protagonist_name=protagonist_name,
                chapter_no=int(getattr(chapter, "chapter_no", 0) or 0),
                chapter_title=getattr(chapter, "title", ""),
                content=getattr(chapter, "content", ""),
                plan=plan if isinstance(plan, dict) else {},
                summary=summary,
                reference_state=guard.get("stock_state", {}),
            )
        ref_state = deepcopy(guard.get("stock_state") if not bool(getattr(chapter, "is_published", False)) else guard.get("published_state"))
        checked = check_hard_fact_conflicts(ref_state, facts, chapter_no=int(getattr(chapter, "chapter_no", 0) or 0))
        register_hard_fact_check(
            story_bible,
            chapter_no=int(getattr(chapter, "chapter_no", 0) or 0),
            chapter_title=getattr(chapter, "title", ""),
            facts=facts,
            serial_stage="published" if bool(getattr(chapter, "is_published", False)) else "stock",
            report=report if isinstance(report, dict) else checked,
            raise_on_conflict=False,
        )
        guard = ensure_hard_fact_guard(story_bible)
    return story_bible


def compact_hard_fact_guard(guard: dict[str, Any], *, max_items: int = 4) -> dict[str, Any]:
    if not isinstance(guard, dict):
        return {}

    def _tail_map(bucket: dict[str, Any]) -> dict[str, Any]:
        items = list((bucket or {}).items())[-max_items:]
        return {key: value for key, value in items}

    published_state = guard.get("published_state") or {}
    stock_state = guard.get("stock_state") or {}
    return {
        "enabled": bool(guard.get("enabled", True)),
        "protected_categories": list((guard.get("protected_categories") or [])[:5]),
        "published_state": {key: _tail_map(published_state.get(key) or {}) for key in ["realm", "life_status", "injury_status", "identity_exposure", "item_ownership"]},
        "stock_state": {key: _tail_map(stock_state.get(key) or {}) for key in ["realm", "life_status", "injury_status", "identity_exposure", "item_ownership"]},
        "last_conflict_report": guard.get("last_conflict_report"),
    }
