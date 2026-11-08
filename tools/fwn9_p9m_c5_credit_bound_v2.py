#!/usr/bin/env python3
"""FWN9 P9M-C5: rigorous one-bar WEAK stop-interpolation credit envelope.

Analytic expectations only. This is NOT a bound on full native wealth, nor a
signal, random-market trial, backtest or broker execution model.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

SUBSTEPS = 8
WEAK_SIGMA_MULTIPLIER = 1.25
ACTIVITY_LOG_MAX = 0.7
HIGH_VOL_MULTIPLIER = 4.0
HIGH_VOL_PROBABILITY = 0.004
CAP_ADMISSION_ONLY = 0.12
NOMINAL_FRICTION = (2.0 / 2.0 + 2.0) / 10000.0
WEAK_PRIOR_UPPER_BP_PER_DAY = 0.9051232469572758
HURDLE_BP_PER_DAY = 1.0


def normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / math.sqrt(2.0))


def exact_one_step_put(
    drift_per_bar: float, sigma_per_bar: float, strike_over_previous: float = 1.0
) -> float:
    """E[(H-S_next)_+ / S_prev] for S_next/S_prev=exp(N(mu,variance)).

    H/S_prev is known before this step; the stopped-state bound uses H <= S_prev.
    """
    if not (
        math.isfinite(drift_per_bar)
        and math.isfinite(sigma_per_bar)
        and sigma_per_bar > 0
        and math.isfinite(strike_over_previous)
        and 0 < strike_over_previous <= 1
    ):
        raise ValueError("C5_INVALID_ONE_STEP_GAUSSIAN_CONTRACT")
    sd = sigma_per_bar / math.sqrt(SUBSTEPS)
    mu = (drift_per_bar - 0.5 * sigma_per_bar**2) / SUBSTEPS
    z = (math.log(strike_over_previous) - mu) / sd
    outcome = (
        strike_over_previous * normal_cdf(z)
        - math.exp(drift_per_bar / SUBSTEPS) * normal_cdf(z - sd)
    )
    return max(0.0, outcome)  # Remove only sub-ulp cancellation, never an economic loss.


def weak_credit_envelope(m9_protocol: dict[str, Any]) -> dict[str, Any]:
    """One-bar expectation bound conditional on pre-bar cash shares and opening marks.

    Requires that the current bar's mixture draw is independent of the pre-bar
    admissible policy and earlier bar innovations, as in the frozen generator.
    The conditional credit of a native stop relative to same-state first-cross
    is <= (1-friction)*q*S_open*bar_factor + q*tick.
    No fraction-of-equity assumption is made during the bar.
    """
    cfg = m9_protocol["generator"]
    if (
        cfg["intrabar_substeps"] != 8
        or cfg["worlds"] != ["TREND", "WEAK", "FALSE", "NULL", "GAP"]
        or m9_protocol["limits"]["capitalUsd"] != 20000
        or m9_protocol["limits"]["grossFraction"] != CAP_ADMISSION_ONLY
        or m9_protocol["limits"]["maxDrawdown"] != 0.08
        or m9_protocol["limits"]["dailyLoss"] != 0.02
    ):
        raise ValueError("C5_FROZEN_ORIGINAL_M9_CONTRACT_REQUIRED")
    traded = cfg["bar_sigma"][:2]
    assert len(traded) == 2
    max_bar_sigma = (
        max(traded)
        * WEAK_SIGMA_MULTIPLIER
        * max(cfg["final_parameter_shift"]["sigma_multiplier_range"])
        * math.exp(ACTIVITY_LOG_MAX)
    )
    max_drift = cfg["weak_drift_per_bar"] * max(
        cfg["final_parameter_shift"]["drift_multiplier_range"]
    )
    # With positive drift, expected downside is smaller. We deliberately use
    # negative worst-case drift for the put and positive drift for prior S growth.
    lambda_base = exact_one_step_put(-max_drift, max_bar_sigma)
    lambda_tail = exact_one_step_put(-max_drift, max_bar_sigma * HIGH_VOL_MULTIPLIER)
    lambda_mixture = (
        (1 - HIGH_VOL_PROBABILITY) * lambda_base
        + HIGH_VOL_PROBABILITY * lambda_tail
    )
    growth_sum = sum(math.exp(k * max_drift / SUBSTEPS) for k in range(SUBSTEPS))
    coefficient = lambda_mixture * growth_sum
    # Adversarial sigma is a valid bound even with mixture inferred intrabar,
    # but is looser than integrating the independent pre-bar mixture draw.
    adversarial_coefficient = lambda_tail * growth_sum
    return {
        "schema": "HARPOON_FWN9_C5_ONE_BAR_WEAK_STOP_CREDIT_1",
        "world": "WEAK",
        "sigma_bar_upper_base": max_bar_sigma,
        "sigma_bar_upper_high_mixture": max_bar_sigma * HIGH_VOL_MULTIPLIER,
        "drift_per_bar_absolute_max": max_drift,
        "high_sigma_probability": HIGH_VOL_PROBABILITY,
        "one_step_downside_fraction_base": lambda_base,
        "one_step_downside_fraction_high_sigma": lambda_tail,
        "one_step_downside_fraction_mixture": lambda_mixture,
        "eight_step_expected_ratio_growth_sum_upper": growth_sum,
        "bar_positive_stop_credit_fraction_of_prior_bar_notional_upper_before_friction": coefficient,
        "bar_positive_stop_credit_fraction_adversarial_mixture_upper": adversarial_coefficient,
        "bar_credit_formula": (
            "(1-friction)*prebar_quantity*prebar_open_price*coefficient"
            " + prebar_quantity*exit_tick"
        ),
        "rounding_tick_charge_limit": "At most one tick per exited share for same-state stop",
        "nominal_friction": NOMINAL_FRICTION,
        "conditional_12pct_at_bar_open_illustration_bp": (
            CAP_ADMISSION_ONLY * coefficient * (1 - NOMINAL_FRICTION) * 10000
        ),
        "conditional_12pct_at_bar_open_price100_with_tick_illustration_bp": (
            CAP_ADMISSION_ONLY * (
                coefficient * (1 - NOMINAL_FRICTION) + 0.01 / 100.0
            ) * 10000
        ),
        "prior_conditional_weak_bound_bp_per_day": WEAK_PRIOR_UPPER_BP_PER_DAY,
        "original_nominal_hurdle_bp_per_day": HURDLE_BP_PER_DAY,
        "gap_to_nominal_hurdle_bp_per_day": (
            HURDLE_BP_PER_DAY - WEAK_PRIOR_UPPER_BP_PER_DAY
        ),
        "native_full_stochastic_bound_certified": False,
        "bar_credit_bound_is_calendar_daily_growth_bound": False,
        "prebar_exposure_is_not_assumed_continuously_capped": True,
        "target_order_and_endogenous_inventory_across_bars_unbounded": True,
        "no_market_paths_or_holdouts_opened": True,
        "no_real_fill_claim": True,
    }


def load_registered_protocol(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("C5_PROTOCOL_OBJECT_REQUIRED")
    return cast(dict[str, Any], data)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "research/modulation9/protocol.json"
    report = weak_credit_envelope(load_registered_protocol(source))
    print("FWN9_P9MC5_ANALYTIC=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
