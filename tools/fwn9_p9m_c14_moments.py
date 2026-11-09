#!/usr/bin/env python3
"""FWN9/C14: conditional moments of one OHLC bar-high funded cash-share book.

The result is an UPPER ENVELOPE over original native OHLC marks, NOT
execution-price attainability, market alpha, stochastic full-native certification,
or proof of N9-S. Draws are ideal M9 stochastic draws, no market seed sampled.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

H = 8
TRADABLE = ("SYNA", "SYNB")
ORDERS = (1, 2, 4)
ONE_DAY_MS = 86_400_000
HIGH_MULTIPLIER_PROB = 0.004
FINAL_SIGMA_MAX = 1.2
ACTIVITY_MAX = math.exp(0.7)
WEAK_WORLD_SIGMA = 1.25
NATIVE_HURDLE = 0.0001


def phi(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def positive_power_call(mu: float, variance: float, power: int) -> float:
    """E[(exp(power*X)-1)_+] for X Gaussian(mu, variance).

    Uses no Monte Carlo. For power >= 1 the payoff is convex as a function
    of exp(X), permitting worst-case volatility selection by convex order.
    """
    if (
        power not in ORDERS
        or not all(math.isfinite(x) for x in (mu, variance))
        or variance <= 0
    ):
        raise ValueError("C14_GAUSSIAN_MOMENT_DOMAIN")
    sd = math.sqrt(variance)
    result = (
        math.exp(power * mu + 0.5 * power * power * variance)
        * phi((mu + power * variance) / sd)
        - phi(mu / sd)
    )
    return max(0.0, result)


def moment_bounds(protocol: dict[str, Any]) -> dict[str, Any]:
    cfg, limits = protocol["generator"], protocol["limits"]
    if (
        cfg["intrabar_substeps"] != H
        or limits["capitalUsd"] != 20000
        or limits["grossFraction"] != 0.12
        or limits["openRiskFraction"] != 0.0025
        or limits["dailyLoss"] != 0.02
        or limits["maxDrawdown"] != 0.08
        or cfg["weak_drift_per_bar"] != 0.000025
        or cfg["final_parameter_shift"]["sigma_multiplier_range"] != [0.9, 1.2]
        or cfg["final_parameter_shift"]["drift_multiplier_range"] != [0.75, 1.1]
        or cfg["worlds"] != ["TREND", "WEAK", "FALSE", "NULL", "GAP"]
    ):
        raise ValueError("C14_FROZEN_M9_CONTRACT")
    max_drift = cfg["weak_drift_per_bar"] * 1.1
    bars: dict[str, dict[str, float]] = {}
    nights: dict[str, dict[str, float]] = {}
    for j, asset in enumerate(TRADABLE):
        sigma = cfg["bar_sigma"][j] * WEAK_WORLD_SIGMA * FINAL_SIGMA_MAX * ACTIVITY_MAX
        ns = cfg["overnight_sigma"][j] * FINAL_SIGMA_MAX * ACTIVITY_MAX
        bar_result: dict[str, float] = {}
        night_result: dict[str, float] = {}
        for p in ORDERS:
            call_sum = 0.0
            for k in range(1, H + 1):
                frac = k / H
                for multiplier, probability in ((1.0, 0.996), (4.0, 0.004)):
                    current_sigma = sigma * multiplier
                    variance = current_sigma**2 * frac
                    mu = (max_drift - 0.5 * current_sigma**2) * frac
                    call_sum += probability * positive_power_call(mu, variance, p)
            bar_result[str(p)] = call_sum
            night_result[str(p)] = sum(
                prob * positive_power_call(
                    math.log(jump) - 0.5 * ns**2, ns**2, p
                )
                for jump, prob in ((0.97, 0.003), (1.0, 0.994), (1.03, 0.003))
            )
        bars[asset], nights[asset] = bar_result, night_result
    return {
        "schema": "HARPOON_FWN9_C14_WEAK_NATIVE_BAR_P_MOMENTS_1",
        "world": "WEAK",
        "powers": list(ORDERS),
        "bar_positive_power_allowances": bars,
        "overnight_positive_power_allowances": nights,
        "bar_sigma_final_activity_max_by_asset": {
            asset: cfg["bar_sigma"][j] * WEAK_WORLD_SIGMA * FINAL_SIGMA_MAX * ACTIVITY_MAX
            for j, asset in enumerate(TRADABLE)
        },
        "conditional_assumptions": [
            "original registered 8 independent Gaussian increments per bar in marginal",
            "current-bar four-sigma mixture is independent of prebar quantities",
            "cash and shares long/nonnegative, no financing by unknown future receipts",
            "all acquisitions at observed opening, each acquisition >= opening price",
            "all intra-bar sales nonnegative and <= full-bar eight-step observed high",
            "no new acquisition using intra-bar sale proceeds after the opening",
            "external costs and commissions nonnegative",
            "no use of 12 percent as a continuous cap",
        ],
        "mathematical_contract": (
            "For preinnovation W0=C0+sum(q_a*Sopen_a)>0 and "
            "f_a=q_a*Sopen_a/W0, E[W_end^p|F_open] <= "
            "W0^p*(1+sum(f_a*bar_allowance[a,p])), p in {1,2,4}."
        ),
        "overnight_contract": (
            "Preopen long cash shares: E[W_next_open^p|F_prev_close] "
            "<= W_prev_close^p*(1+sum(f_a*night_allowance[a,p]))."
        ),
        "native_executable_price_equivalence_proven": False,
        "native_full_population_applicability_proven": False,
        "N9S_threshold_certified": False,
    }


def conditional_one_bar(
    bounds: dict[str, Any],
    cash: float,
    shares: dict[str, int],
    opening: dict[str, float],
    p: int,
    overnight: bool = False,
) -> dict[str, float]:
    if p not in ORDERS or not math.isfinite(cash) or cash < 0:
        raise ValueError("C14_FINANCING_AND_P_DOMAIN")
    gross = cash
    for asset in TRADABLE:
        if (
            not isinstance(shares.get(asset), int)
            or shares[asset] < 0
            or not math.isfinite(opening.get(asset, float("nan")))
            or opening[asset] <= 0
        ):
            raise ValueError("C14_LONG_PRICE_AND_INVENTORY")
        gross += shares[asset] * opening[asset]
    if not math.isfinite(gross) or gross <= 0:
        raise ValueError("C14_POSITIVE_WEALTH_REQUIRED")
    key = (
        "overnight_positive_power_allowances"
        if overnight else "bar_positive_power_allowances"
    )
    fractions = {asset: shares[asset] * opening[asset] / gross for asset in TRADABLE}
    factor = 1 + sum(
        fractions[asset] * bounds[key][asset][str(p)] for asset in TRADABLE
    )
    return {
        "openingWealthUsd": gross,
        "cashFraction": cash / gross,
        "fractionA": fractions["SYNA"],
        "fractionB": fractions["SYNB"],
        "conditionalMomentFactor": factor,
        "conditionalMomentUpperUsdPower": gross**p * factor,
    }


def max_window_moment(
    bounds: dict[str, Any], p: int, bars: int, nights: int,
    first_wealth: float = 20000.0,
) -> dict[str, float]:
    """Uniform finite <=72h certificate, NOT a 1bp/day growth certificate."""
    if (
        p not in ORDERS or not (0 <= bars <= 234 and 0 <= nights <= 3)
        or not math.isfinite(first_wealth) or first_wealth <= 0
    ):
        raise ValueError("C14_LOCAL_WINDOW_DOMAIN")
    bar_max = max(bounds["bar_positive_power_allowances"][s][str(p)] for s in TRADABLE)
    night_max = max(
        bounds["overnight_positive_power_allowances"][s][str(p)] for s in TRADABLE
    )
    log_factor = bars * math.log1p(bar_max) + nights * math.log1p(night_max)
    factor = math.exp(log_factor)
    # Jensen: E log(W/W0) <= (1/p) log E[(W/W0)^p], for W>0.
    return {
        "power": p,
        "bars": bars,
        "overnights": nights,
        "wealthMomentFactorUpper": factor,
        "wealthMomentUpper": (first_wealth**p) * factor,
        "expectedLogGrowthUpper": log_factor / p,
        "originalThreeCalendarDayHurdle": 3 * NATIVE_HURDLE,
        "hurdleProvedImpossible": log_factor / p < 3 * NATIVE_HURDLE,
        "nativeUniversalityCertified": False,
        "cannotEquateUpperWithAchievedGrowth": True,
        "tail20xWealthUpperMarkov": min(1.0, factor / (20.0**p)),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "research/modulation9/protocol.json").read_text())
    if not isinstance(data, dict):
        raise ValueError("C14_JSON_ROOT_OBJECT")
    bounds = moment_bounds(cast(dict[str, Any], data))
    report = {
        "bounds": bounds,
        "all_cash": conditional_one_bar(
            bounds, 20000, {"SYNA": 0, "SYNB": 0},
            {"SYNA": 100, "SYNB": 150}, 2
        ),
        "independent_inventory": [
            conditional_one_bar(bounds, 18000, {"SYNA": 8, "SYNB": 5},
                {"SYNA": 100, "SYNB": 150}, p)
            for p in ORDERS
        ],
        "max_72h_window": [
            max_window_moment(bounds, p, 234, 3) for p in ORDERS
        ],
        "accounts_opened": 0,
        "market_seeds_opened": 0,
        "alpha_spent": 0,
        "M10_final_unopened": 3200,
    }
    print("FWN9_C14_ANALYTIC=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
