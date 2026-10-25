"""The only place that reads the wall clock, so tests can freeze time."""

from datetime import UTC, date, datetime


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().date()
