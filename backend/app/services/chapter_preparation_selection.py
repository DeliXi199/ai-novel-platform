from __future__ import annotations

"""Public façade for chapter-preparation selection.

The heavy execution pipeline lives in ``chapter_preparation_selection_runner``.
This file stays intentionally small so external callers import a stable entrypoint
without dragging in the full execution implementation at module-read time.
"""

from app.services.chapter_preparation_selection_runner import (
    review_character_relation_schedule_and_select_cards,
    run_chapter_preparation_selection,
)

__all__ = [
    "run_chapter_preparation_selection",
    "review_character_relation_schedule_and_select_cards",
]
