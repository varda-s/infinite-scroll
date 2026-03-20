"""Time helpers for receipt timestamps."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


SAN_FRANCISCO_TZ = ZoneInfo("America/Los_Angeles")


def san_francisco_now() -> datetime:
    """Return the current time in the San Francisco timezone."""
    return datetime.now(SAN_FRANCISCO_TZ)


def format_receipt_timestamp(dt: datetime | None = None) -> str:
    """Format a timestamp for receipt printing in San Francisco local time."""
    value = dt.astimezone(SAN_FRANCISCO_TZ) if dt is not None else san_francisco_now()
    return value.strftime("%Y-%m-%d %H:%M:%S")
