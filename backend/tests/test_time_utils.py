from datetime import UTC

from app.models.time_utils import utcnow_naive


def test_utcnow_naive_returns_naive_utc_datetime() -> None:
    value = utcnow_naive()
    assert value.tzinfo is None
    aware = value.replace(tzinfo=UTC)
    assert aware.utcoffset().total_seconds() == 0
