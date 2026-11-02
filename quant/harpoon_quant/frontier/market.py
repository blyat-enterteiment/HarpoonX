"""Normalize supplied, timestamped sessions and halts. No implicit exchange feed."""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise
from typing import Any

from ..core import digest, timestamp
from .contracts import require


def market_clock(
    asof: str, book: str, calendar: dict[str, Any], halts: list[dict[str, Any]]
) -> dict[str, Any]:
    now = timestamp(asof)
    require(book in {"equity", "etf", "crypto"}, "DERIVATIVE_CALENDAR_NOT_IMPLEMENTED")
    require(timestamp(calendar["known_at"]) <= now, "FUTURE_CALENDAR")
    require(
        calendar["coverage_start"] <= asof[:10]
        and calendar["coverage_end"] >= (now + timedelta(hours=72)).date().isoformat(),
        "CALENDAR_COVERAGE_72H",
    )
    sessions = []
    if book != "crypto":
        require(calendar.get("venue") in {"NASDAQ", "NYSE"}, "EXPLICIT_EQUITY_VENUE")
        for row in calendar["sessions"]:
            start, end = timestamp(row["open"]), timestamp(row["close"])
            require(start < end, "SESSION_CLOCK")
            sessions.append((start, end))
        sessions.sort()
        require(
            all(a[1] <= b[0] for a, b in pairwise(sessions)),
            "OVERLAPPING_SESSIONS",
        )
    windows = []
    for halt in halts:
        require(timestamp(halt["known_at"]) <= now, "FUTURE_HALT_RECORD")
        start = timestamp(halt["start_at"])
        end = (
            timestamp(halt["end_at"])
            if halt.get("end_at")
            else now + timedelta(hours=73)
        )
        require(start < end, "HALT_WINDOW")
        windows.append((start, end))

    def halted(start: Any, end: Any) -> bool:
        return any(a < end and b > start for a, b in windows)

    schedule = []
    for step in range(1, 73):
        start, end = now + timedelta(hours=step - 1), now + timedelta(hours=step)
        opened = book == "crypto" or any(a < end <= b for a, b in sessions)
        schedule.append(opened and not halted(start, end))
    open_now = book == "crypto" or any(a <= now < b for a, b in sessions)
    halted_now = any(a <= now < b for a, b in windows)
    return {
        "tradable_now": open_now and not halted_now,
        "halted": halted_now,
        "schedule": schedule,
        "schedule_known_at": calendar["known_at"],
        "schedule_source_hash": digest({"calendar": calendar, "halts": halts}),
        "scope": "SUPPLIED_STATUS_ONLY_NOT_LIVE_EXCHANGE_CONNECTIVITY",
    }
