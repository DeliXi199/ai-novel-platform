from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def emit_progress(progress_callback: Callable[[dict[str, Any]], None] | None, snapshot: dict[str, Any] | None) -> None:
    if not progress_callback or not isinstance(snapshot, dict):
        return
    try:
        progress_callback(snapshot)
    except Exception:  # pragma: no cover
        logger.debug("chapter progress callback failed", exc_info=True)
