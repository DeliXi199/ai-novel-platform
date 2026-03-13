from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _compact_fact_text(value: Any, fallback: str = "") -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return fallback
    return text[:120]


def _chapter_fact_entry(*, chapter_no: int, chapter_title: str, kind: str, fact: str, source: str) -> dict[str, Any]:
    return {
        "chapter_no": int(chapter_no),
        "chapter_title": chapter_title,
        "kind": kind,
        "fact": _compact_fact_text(fact),
        "source": source,
        "indexed_at": _now_iso(),
    }


def _empty_fact_ledger() -> dict[str, Any]:
    return {
        "published_facts": [],
        "stock_facts": [],
        "latest_indexed_chapter": 0,
        "last_rebuilt_at": None,
    }


def _ensure_fact_ledger(story_bible: dict[str, Any]) -> dict[str, Any]:
    ledger = story_bible.setdefault("fact_ledger", _empty_fact_ledger())
    ledger.setdefault("published_facts", [])
    ledger.setdefault("stock_facts", [])
    ledger.setdefault("latest_indexed_chapter", 0)
    ledger.setdefault("last_rebuilt_at", None)
    return ledger


def _dedupe_fact_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in sorted(entries, key=lambda row: (int(row.get("chapter_no", 0) or 0), str(row.get("kind") or ""), str(row.get("fact") or ""))):
        key = (int(item.get("chapter_no", 0) or 0), str(item.get("kind") or ""), str(item.get("fact") or ""), str(item.get("source") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extract_chapter_fact_entries(
    *,
    chapter_no: int,
    chapter_title: str,
    summary: Any | None = None,
    plan: dict[str, Any] | None = None,
    fallback_content: str = "",
    source: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    summary_text = _compact_fact_text(getattr(summary, "event_summary", None), "")
    if summary_text:
        entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="event", fact=summary_text, source=source))

    plan = plan or {}
    goal_text = _compact_fact_text(plan.get("goal"), "")
    if goal_text:
        entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="chapter_goal", fact=goal_text, source=source))

    for clue in (getattr(summary, "new_clues", None) or [])[:4]:
        clue_text = _compact_fact_text(clue, "")
        if clue_text:
            entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="new_clue", fact=clue_text, source=source))

    for hook in (getattr(summary, "open_hooks", None) or [])[:4]:
        hook_text = _compact_fact_text(hook, "")
        if hook_text:
            entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="open_hook", fact=hook_text, source=source))

    for hook in (getattr(summary, "closed_hooks", None) or [])[:4]:
        hook_text = _compact_fact_text(hook, "")
        if hook_text:
            entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="closed_hook", fact=hook_text, source=source))

    character_updates = getattr(summary, "character_updates", None) or {}
    if isinstance(character_updates, dict):
        for name, state in list(character_updates.items())[:4]:
            state_text = _compact_fact_text(state, "")
            if state_text:
                entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="character_state", fact=f"{name}: {state_text}", source=source))

    if not entries:
        fallback = _compact_fact_text(fallback_content, f"第{chapter_no}章《{chapter_title}》已发生新的推进。")
        entries.append(_chapter_fact_entry(chapter_no=chapter_no, chapter_title=chapter_title, kind="fallback", fact=fallback, source=source))
    return _dedupe_fact_entries(entries)


def record_chapter_fact_entries(
    story_bible: dict[str, Any],
    *,
    chapter_no: int,
    chapter_title: str,
    summary: Any | None,
    plan: dict[str, Any] | None,
    serial_stage: str,
    fallback_content: str = "",
) -> dict[str, Any]:
    ledger = _ensure_fact_ledger(story_bible)
    target_key = "published_facts" if serial_stage == "published" else "stock_facts"
    other_key = "stock_facts" if target_key == "published_facts" else "published_facts"
    source = "published_chapter" if serial_stage == "published" else "stock_chapter"
    new_entries = _extract_chapter_fact_entries(
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        summary=summary,
        plan=plan,
        fallback_content=fallback_content,
        source=source,
    )
    ledger[target_key] = _dedupe_fact_entries([item for item in ledger.get(target_key, []) if int(item.get("chapter_no", 0) or 0) != chapter_no] + new_entries)
    ledger[other_key] = [item for item in ledger.get(other_key, []) if int(item.get("chapter_no", 0) or 0) != chapter_no]
    ledger["latest_indexed_chapter"] = max(int(ledger.get("latest_indexed_chapter", 0) or 0), chapter_no)
    ledger["last_rebuilt_at"] = _now_iso()
    story_bible["fact_ledger"] = ledger
    return story_bible


def promote_stock_fact_entries(story_bible: dict[str, Any], chapter_nos: list[int]) -> dict[str, Any]:
    if not chapter_nos:
        return story_bible
    ledger = _ensure_fact_ledger(story_bible)
    target = set(int(no) for no in chapter_nos)
    remaining_stock: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    for item in ledger.get("stock_facts", []):
        chapter_no = int(item.get("chapter_no", 0) or 0)
        if chapter_no in target:
            promoted.append({**item, "source": "published_chapter", "indexed_at": _now_iso()})
        else:
            remaining_stock.append(item)
    existing_published = [item for item in ledger.get("published_facts", []) if int(item.get("chapter_no", 0) or 0) not in target]
    ledger["stock_facts"] = remaining_stock
    ledger["published_facts"] = _dedupe_fact_entries(existing_published + promoted)
    ledger["latest_indexed_chapter"] = max([int(ledger.get("latest_indexed_chapter", 0) or 0), *target])
    ledger["last_rebuilt_at"] = _now_iso()
    story_bible["fact_ledger"] = ledger
    return story_bible


def rebuild_fact_ledger_from_chapters(story_bible: dict[str, Any], chapters: list[Any]) -> dict[str, Any]:
    ledger = _ensure_fact_ledger(story_bible)
    published_entries: list[dict[str, Any]] = []
    stock_entries: list[dict[str, Any]] = []
    existing_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for bucket in (ledger.get("published_facts", []), ledger.get("stock_facts", [])):
        for item in bucket:
            existing_by_chapter.setdefault(int(item.get("chapter_no", 0) or 0), []).append(item)

    latest = 0
    for chapter in sorted(chapters, key=lambda item: int(getattr(item, "chapter_no", 0) or 0)):
        chapter_no = int(getattr(chapter, "chapter_no", 0) or 0)
        latest = max(latest, chapter_no)
        bucket = published_entries if bool(getattr(chapter, "is_published", False)) else stock_entries
        meta = getattr(chapter, "generation_meta", None) or {}
        meta_entries = meta.get("fact_entries") if isinstance(meta, dict) else None
        if isinstance(meta_entries, list) and meta_entries:
            normalized = []
            for item in meta_entries:
                if isinstance(item, dict):
                    normalized.append({
                        **item,
                        "chapter_no": chapter_no,
                        "chapter_title": getattr(chapter, "title", ""),
                        "source": "published_chapter" if bool(getattr(chapter, "is_published", False)) else "stock_chapter",
                    })
            bucket.extend(normalized)
            continue
        if chapter_no in existing_by_chapter:
            for item in existing_by_chapter[chapter_no]:
                bucket.append({
                    **item,
                    "chapter_no": chapter_no,
                    "chapter_title": getattr(chapter, "title", ""),
                    "source": "published_chapter" if bool(getattr(chapter, "is_published", False)) else "stock_chapter",
                })
            continue
        preview = _compact_fact_text(getattr(chapter, "content", ""), f"第{chapter_no}章《{getattr(chapter, 'title', '')}》已写成。")
        bucket.append(_chapter_fact_entry(
            chapter_no=chapter_no,
            chapter_title=getattr(chapter, "title", ""),
            kind="fallback",
            fact=preview,
            source="published_chapter" if bool(getattr(chapter, "is_published", False)) else "stock_chapter",
        ))

    ledger["published_facts"] = _dedupe_fact_entries(published_entries)
    ledger["stock_facts"] = _dedupe_fact_entries(stock_entries)
    ledger["latest_indexed_chapter"] = latest
    ledger["last_rebuilt_at"] = _now_iso()
    story_bible["fact_ledger"] = ledger
    return story_bible
