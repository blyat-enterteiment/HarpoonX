"""Paired funded-account growth on the same USD capital and valuation clock."""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise
from typing import Any

import numpy as np
from numpy.typing import NDArray

BOOKS = ("JOINT", "EQUITY_ETF", "CRYPTO", "CASH")


def paired_growth(
    accounts: dict[str, dict[str, Any]],
) -> tuple[dict[str, float], NDArray[np.float64]]:
    """Columns are absolute joint and joint minus equity, crypto and cash respectively."""
    if set(accounts) != set(BOOKS):
        raise ValueError("FOUR_FUNDED_ACCOUNTS_REQUIRED")
    joint = accounts["JOINT"]
    capital = joint["initial_usd"]
    if type(capital) not in (int, float) or not np.isfinite(capital) or capital <= 0:
        raise ValueError("INVALID_INITIAL_CAPITAL")
    if not joint["curve"]:
        raise ValueError("EMPTY_CURVE")
    dates = [date.fromisoformat(r["day"]) for r in joint["curve"]]
    if any(b - a != timedelta(days=1) for a, b in pairwise(dates)):
        raise ValueError("NONCONTIGUOUS_UTC_MARKS")
    expected = [d.isoformat() for d in dates]
    logs = []
    fixed_events = [
        (e["at"], e["cash_delta"]) for e in joint["events"] if e["kind"] == "FIXED"
    ]
    if (
        len(fixed_events) != len(dates)
        or [t[:10] for t, _ in fixed_events] != expected
        or any(not np.isfinite(v) or v > 0 for _, v in fixed_events)
    ):
        raise ValueError("FIXED_COST_SCHEDULE")
    for name in BOOKS:
        a = accounts[name]
        if (
            a["initial_usd"] != capital
            or a["stress"] != joint["stress"]
            or [row["day"] for row in a["curve"]] != expected
        ):
            raise ValueError("UNPAIRED_ACCOUNT")
        fees = [(e["at"], e["cash_delta"]) for e in a["events"] if e["kind"] == "FIXED"]
        if fees != fixed_events or not np.isclose(
            a["fixed_cost_usd"], -sum(v for _, v in fees), rtol=0, atol=1e-6
        ):
            raise ValueError("UNPAIRED_FIXED_COSTS")
        values = np.array(
            [capital, *(row["equity"] for row in a["curve"])], dtype=float
        )
        if (
            not np.isfinite(values).all()
            or (values <= 0).any()
            or not np.isclose(values[-1], a["terminal_usd"], rtol=0, atol=1e-6)
        ):
            raise ValueError("INVALID_FUNDED_EQUITY")
        logs.append(np.diff(np.log(values)))
    paired = np.column_stack([logs[0], *(logs[0] - baseline for baseline in logs[1:])])
    totals = dict(
        zip(
            (
                "joint_log_growth",
                "add_crypto_to_equity",
                "add_equity_to_crypto",
                "joint_vs_cash",
            ),
            (float(x) for x in paired.sum(axis=0)),
            strict=True,
        )
    )
    return totals, paired
