from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.novel import Novel
from app.services.story_architecture import build_story_workspace_snapshot, ensure_story_architecture

logger = logging.getLogger(__name__)

_PHASES = {"before", "after", "failed", "manual", "runtime"}


def _utc_now() -> datetime:
    return datetime.now(UTC)



def _utc_now_iso() -> str:
    return _utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")



def _utc_now_stamp() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%S_%fZ")



def _safe_slug(value: Any, *, fallback: str = "snapshot", limit: int = 48) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-_")
    if not text:
        text = fallback
    return text[:limit]



def _chapter_dir(novel_id: int, chapter_no: int) -> Path:
    return settings.story_workspace_archive_root_path / f"novel_{int(novel_id)}" / f"chapter_{int(chapter_no):04d}"



def _archive_path(*, novel_id: int, chapter_no: int, phase: str, stage: str | None = None) -> Path:
    phase_slug = _safe_slug(phase, fallback="snapshot", limit=16)
    stage_slug = _safe_slug(stage, fallback="state", limit=40) if stage else None
    name = f"{_utc_now_stamp()}_{phase_slug}"
    if stage_slug:
        name += f"_{stage_slug}"
    return _chapter_dir(novel_id, chapter_no) / f"{name}.json"



def _json_text(payload: dict[str, Any]) -> str:
    pretty = bool(getattr(settings, "story_workspace_archive_pretty_json", True))
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=pretty,
    )



def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)



def _prune_old_files(novel_id: int) -> None:
    keep = max(int(getattr(settings, "story_workspace_archive_keep_files_per_novel", 240) or 240), 0)
    if keep <= 0:
        return
    novel_root = settings.story_workspace_archive_root_path / f"novel_{int(novel_id)}"
    if not novel_root.exists():
        return
    files = sorted((item for item in novel_root.rglob("*.json") if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in files[keep:]:
        try:
            stale.unlink(missing_ok=True)
        except Exception:
            logger.debug("failed to prune story workspace archive file %s", stale, exc_info=True)



def archive_story_workspace_snapshot(
    novel: Novel,
    *,
    chapter_no: int,
    phase: str,
    stage: str | None = None,
    note: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str | None:
    if not bool(getattr(settings, "story_workspace_archive_enabled", True)):
        return None
    phase_name = _safe_slug(phase, fallback="snapshot", limit=16)
    if phase_name not in _PHASES:
        phase_name = "runtime"
    try:
        story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
        snapshot = build_story_workspace_snapshot(novel)
        planning_state = snapshot.get("planning_state") or {}
        live_runtime = planning_state.get("live_runtime") or {}
        current_pipeline = planning_state.get("current_pipeline") or {}
        payload: dict[str, Any] = {
            "archive_meta": {
                "saved_at": _utc_now_iso(),
                "novel_id": novel.id,
                "novel_title": novel.title,
                "chapter_no": int(chapter_no or 0),
                "phase": phase_name,
                "stage": stage or live_runtime.get("stage") or current_pipeline.get("last_live_stage") or "",
                "note": note or live_runtime.get("note") or current_pipeline.get("last_live_note") or "",
                "novel_status": novel.status,
                "current_chapter_no": int(getattr(novel, "current_chapter_no", 0) or 0),
                "archive_root": str(settings.story_workspace_archive_root_path),
            },
            "live_runtime": live_runtime,
            "current_pipeline": current_pipeline,
            "snapshot": snapshot,
        }
        if isinstance(extra, dict) and extra:
            payload["extra"] = extra
        if bool(getattr(settings, "story_workspace_archive_include_story_bible", False)):
            payload["story_bible"] = story_bible
        path = _archive_path(novel_id=novel.id, chapter_no=chapter_no, phase=phase_name, stage=stage or live_runtime.get("stage"))
        _write_text_atomic(path, _json_text(payload))
        _prune_old_files(novel.id)
        logger.info(
            "story_workspace archive saved novel_id=%s chapter_no=%s phase=%s path=%s",
            novel.id,
            chapter_no,
            phase_name,
            path,
        )
        return str(path)
    except Exception:
        logger.warning(
            "story_workspace archive save failed novel_id=%s chapter_no=%s phase=%s",
            getattr(novel, "id", None),
            chapter_no,
            phase_name,
            exc_info=True,
        )
        return None



def list_story_workspace_archives(*, novel_id: int, chapter_no: int | None = None, limit: int = 100) -> dict[str, Any]:
    root = settings.story_workspace_archive_root_path / f"novel_{int(novel_id)}"
    if not root.exists():
        return {
            "novel_id": novel_id,
            "archive_root": str(root),
            "total": 0,
            "items": [],
        }
    if chapter_no is not None:
        scan_root = root / f"chapter_{int(chapter_no):04d}"
    else:
        scan_root = root
    files = sorted((item for item in scan_root.rglob("*.json") if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
    items: list[dict[str, Any]] = []
    for path in files[: max(int(limit or 0), 1)]:
        rel_path = path.relative_to(root).as_posix()
        items.append(
            {
                "relative_path": rel_path,
                "file_name": path.name,
                "chapter_dir": path.parent.name,
                "size_bytes": path.stat().st_size,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
        )
    return {
        "novel_id": novel_id,
        "archive_root": str(root),
        "total": len(files),
        "items": items,
    }



def read_story_workspace_archive(*, novel_id: int, relative_path: str) -> dict[str, Any]:
    root = settings.story_workspace_archive_root_path / f"novel_{int(novel_id)}"
    candidate = (root / str(relative_path or "")).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise ValueError("Invalid archive path")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return json.loads(candidate.read_text(encoding="utf-8"))
