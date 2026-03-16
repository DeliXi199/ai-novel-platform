from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any


_CACHE_LIMIT = 64


@dataclass(slots=True)
class RuntimeSnapshotCacheEntry:
    synced_story_bible: dict[str, Any]
    snapshot: dict[str, Any]


_cache: OrderedDict[str, RuntimeSnapshotCacheEntry] = OrderedDict()
_cache_lock = Lock()


def _normalize_timestamp(value: datetime | None) -> str:
    if value is None:
        return ''
    return value.isoformat()


def _story_bible_digest(story_bible: dict[str, Any] | None) -> str:
    payload = json.dumps(story_bible or {}, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.md5(payload.encode('utf-8')).hexdigest()


def build_runtime_snapshot_cache_key(
    *,
    novel_id: int,
    title: str,
    genre: str,
    protagonist_name: str,
    current_chapter_no: int,
    novel_updated_at: datetime | None,
    story_bible: dict[str, Any] | None,
    chapter_count: int,
    chapter_last_updated_at: datetime | None,
) -> str:
    return '|'.join(
        [
            str(novel_id),
            str(current_chapter_no),
            _normalize_timestamp(novel_updated_at),
            str(chapter_count),
            _normalize_timestamp(chapter_last_updated_at),
            title or '',
            genre or '',
            protagonist_name or '',
            _story_bible_digest(story_bible),
        ]
    )


def get_runtime_snapshot(cache_key: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    with _cache_lock:
        entry = _cache.get(cache_key)
        if entry is None:
            return None
        _cache.move_to_end(cache_key)
        return deepcopy(entry.synced_story_bible), deepcopy(entry.snapshot)


def store_runtime_snapshot(cache_key: str, synced_story_bible: dict[str, Any], snapshot: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[cache_key] = RuntimeSnapshotCacheEntry(
            synced_story_bible=deepcopy(synced_story_bible),
            snapshot=deepcopy(snapshot),
        )
        _cache.move_to_end(cache_key)
        while len(_cache) > _CACHE_LIMIT:
            _cache.popitem(last=False)


def invalidate_runtime_snapshot_for_novel(novel_id: int) -> None:
    prefix = f'{novel_id}|'
    with _cache_lock:
        doomed = [key for key in _cache if key.startswith(prefix)]
        for key in doomed:
            _cache.pop(key, None)


def clear_runtime_snapshot_cache() -> None:
    with _cache_lock:
        _cache.clear()
