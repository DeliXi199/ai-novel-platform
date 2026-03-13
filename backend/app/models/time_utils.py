from __future__ import annotations

from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    """Return a naive UTC datetime without using deprecated datetime.utcnow()."""
    return datetime.now(UTC).replace(tzinfo=None)
