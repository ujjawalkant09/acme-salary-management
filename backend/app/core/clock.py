"""The only place that reads the wall clock, so tests can freeze time."""

from datetime import UTC, date, datetime


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().date()


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as the UTC they were stored in."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
