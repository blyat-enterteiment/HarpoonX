"""Development inference from already reconciled, dated HF37 wealth ledgers."""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date
from itertools import pairwise
from pathlib import Path

POLICIES = ("WHALE_SECTOR", "SECTOR", "ORIGINAL", "CASH")
BLOCKS = (5, 10)
DRAWS = 10_000
SEED = 3702
MIN_SESSIONS = 30
TAIL = 0.05 / (len(BLOCKS) * (len(POLICIES) - 1))


def evaluate(calendar: list[str], ledgers: dict[str, dict]) -> dict:
    dates = [date.fromisoformat(day) for day in calendar]
    if (len(dates) < MIN_SESSIONS or dates != sorted(set(dates))
            or any((day.year, day.month) == (2026, 11) for day in dates)):
        raise ValueError("INVALID_DEVELOPMENT_CALENDAR")
    if set(ledgers) != set(POLICIES):
        raise ValueError("EXACT_FOUR_LEDGER_SET_REQUIRED")
    returns: dict[str, list[float]] = {}
    for name in POLICIES:
        ledger = ledgers[name]
        if ledger["sessions"] != calendar:
            raise ValueError("UNPAIRED_LEDGER_CALENDAR")
        values = ledger["wealth"]
        if len(values) != len(dates) + 1 or values[0] != 20_000 or any(
            isinstance(x, bool) or not isinstance(x, (int, float))
            or not math.isfinite(x) or x <= 0 for x in values
        ):
            raise ValueError("INVALID_CONTINUOUS_WEALTH")
        if name == "CASH" and any(value != 20_000 for value in values):
            raise ValueError("CASH_WITHOUT_INTEREST_MUST_BE_CONSTANT")
        logs = list(map(math.log, values))
        returns[name] = [after - before for before, after in pairwise(logs)]

    n = len(dates)
    contrasts = {name: [a - b for a, b in zip(returns[POLICIES[0]], returns[name])]
                 for name in POLICIES[1:]}
    bounds: dict[str, dict[int, float]] = {name: {} for name in contrasts}
    rng = random.Random(SEED)
    for block in BLOCKS:
        samples: dict[str, list[float]] = {name: [] for name in contrasts}
        for _ in range(DRAWS):
            indices = [(start + offset) % n
                       for start in (rng.randrange(n) for _ in range(math.ceil(n / block)))
                       for offset in range(block)][:n]
            for name, delta in contrasts.items():
                samples[name].append(math.fsum(delta[i] for i in indices) / n)
        for name in contrasts:
            bounds[name][block] = sorted(samples[name])[math.floor(TAIL * DRAWS)]

    return {
        "status": "DEVELOPMENT_ESTIMATE_ONLY",
        "sessions": n,
        "geometric_growth_per_session": {
            name: math.expm1(math.fsum(series) / n) for name, series in returns.items()
        },
        "mean_log_advantage_vs": {
            name: math.fsum(series) / n for name, series in contrasts.items()
        },
        "nominal_block_bootstrap_lower_bounds_log_units": bounds,
        "all_lower_bounds_positive": all(
            value > 0 for contrast in bounds.values() for value in contrast.values()
        ),
        "promotion_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    inputs = json.loads(args.input.read_text())
    print(json.dumps(evaluate(inputs["calendar"], inputs["ledgers"]), sort_keys=True))


if __name__ == "__main__":
    main()
