#!/usr/bin/env python3
"""C20: event-activated native OHLC stop/TP credit and 72h admission exposure.

Analytic bounds for the ideal frozen WEAK process, zero market RNG and zero
account executions. Stop/target thresholds are required to be measurable at
the *bar opening*. Original post-bar OHLC fills are NOT proven tradable.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fwn9_p9m_c19_native_credit_moment import asset_downward_variation

SOURCE_SHA = {
    "quant/harpoon_quant/modulation9.py":
    "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab",
    "research/modulation9/protocol.json":
    "de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d",
    "runtime30/profit8_replay.js":
    "303aa6956cfa0a249f0432bea23894b3ee8e514c60ff011177baabc7a6974810",
    "runtime30/ultimate_reservations.js":
    "94553547da3e02b972d72e8ea296a2e1ecc468a82133c75868eaea5fbe2ba494",
}
ASSETS = {"SYNA": 0.00075, "SYNB": 0.00085}
MIXTURE = ((1.0, 0.996), (4.0, 0.004))
BAR_DRIFT_MAX = 0.000025 * 1.1
STEPS = 8
MAX_HOLD_INTRADAY_SUBSTEPS = 4 * 78 * STEPS
CAPITAL = 20000.0
DAYS = 176
SCHEMA = "HARPOON_M11_C20_TRIGGER_GATED_WEAK_NATIVE_MODEL_U_A_1"


def _num(v: float, name: str, positive: bool = False) -> float:
    if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
        raise ValueError("C20_INVALID_" + name)
    if (positive and v <= 0) or (not positive and v < 0):
        raise ValueError("C20_INVALID_" + name)
    return float(v)


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def gaussian_put_moments(strike: float, mu: float, variance: float) -> tuple[float, float]:
    """Exact formulas for E[(K-exp X)+] and E[(K-exp X)+**2].

    Validation uses a second independent integration. Floating point outputs
    are not formally outward-rounded transcendental interval certificates.
    """
    K = _num(strike, "STRIKE", True)
    v = _num(variance, "VARIANCE", True)
    if not math.isfinite(mu):
        raise ValueError("C20_INVALID_MU")
    sd = math.sqrt(v)
    z = (math.log(K) - mu) / sd
    cdf0 = norm_cdf(z)
    m1 = math.exp(mu + 0.5 * v) * norm_cdf(z - sd)
    m2 = math.exp(2 * mu + 2 * v) * norm_cdf(z - 2 * sd)
    p1 = K * cdf0 - m1
    p2 = K * K * cdf0 - 2 * K * m1 + m2
    return max(0.0, p1), max(0.0, p2)


def gaussian_upper_tail(barrier_log_ratio: float, mu_max: float, sigma_max: float) -> float:
    """For a positive upper log barrier, bound P(X>=barrier)."""
    if barrier_log_ratio <= mu_max:
        return 1.0
    z = (barrier_log_ratio - mu_max) / sigma_max
    return max(1e-300, 0.5 * math.erfc(z / math.sqrt(2)))


def gaussian_lower_tail(barrier_log_ratio: float, mu_min: float, sigma_max: float) -> float:
    """For a negative lower log barrier, bound P(X<=barrier)."""
    if barrier_log_ratio >= mu_min:
        return 1.0
    z = (mu_min - barrier_log_ratio) / sigma_max
    return max(1e-300, 0.5 * math.erfc(z / math.sqrt(2)))


def event_probability_bound(
    *,
    strike_ratio: float,
    is_lower: bool,
    base_sigma: float,
    mixture_multiplier: float,
) -> float:
    """WEAK conditional hit probability upper via 8 Gaussian prefix union.

    Lower and upper sigma extrema are distinct and source frozen. Never
    condition on a future price or a realized crossing event to choose q.
    """
    k = _num(strike_ratio, "BARRIER_RATIO", True)
    base = _num(base_sigma, "BASE_VOLATILITY", True)
    mult = _num(mixture_multiplier, "MIXTURE_MULTIPLIER", True)
    if (is_lower and k >= 1) or (not is_lower and k <= 1):
        return 1.0  # Trigger already true at the bar opening.
    low_sigma = base * 1.25 * 0.9 * math.exp(-0.7) * mult
    high_sigma = base * 1.25 * 1.2 * math.exp(0.7) * mult
    threshold = math.log(k)
    p = 0.0
    for prefix in range(1, STEPS + 1):
        f = prefix / STEPS
        mu_min = (-BAR_DRIFT_MAX - 0.5 * high_sigma**2) * f
        mu_max = (BAR_DRIFT_MAX - 0.5 * low_sigma**2) * f
        sdmax = high_sigma * math.sqrt(f)
        p += (
            gaussian_lower_tail(threshold, mu_min, sdmax)
            if is_lower
            else gaussian_upper_tail(threshold, mu_max, sdmax)
        )
    return min(1.0, p)


def event_weighted_put_upper(
    *,
    payoff_strike_ratio: float,
    trigger_barrier_ratio: float,
    is_lower_trigger: bool,
    sigma_base: float,
) -> dict[str, float]:
    """Uniform pre-bar conditional upper E[(strike-Pclose)+ 1_trigger] / Popen.

    Total expectation is mixed with the ORIGINAL 0.996/0.004 weights.
    For each mixture component use min(first put moment,
    sqrt(second put moment * union-tail-probability)).
    No assumption that the trigger implies a profitable exit.
    """
    strike = _num(payoff_strike_ratio, "PAYOFF_STRIKE", True)
    ans = 0.0
    event_probability = 0.0
    ungated = 0.0
    for multiplier, mixture_weight in MIXTURE:
        sigma = sigma_base * 1.25 * 1.2 * math.exp(.7) * multiplier
        v = sigma**2
        mu_min = -BAR_DRIFT_MAX - 0.5 * v
        p1, p2 = gaussian_put_moments(strike, mu_min, v)
        p_hit = event_probability_bound(
            strike_ratio=trigger_barrier_ratio,
            is_lower=is_lower_trigger,
            base_sigma=sigma_base,
            mixture_multiplier=multiplier,
        )
        # Guard ~1e-13 FP cancellation conservatively. Does not replace
        # formal interval arithmetic; native certification remains prohibited.
        first = p1 + 1e-12
        second = p2 + 1e-12
        term = min(first, math.sqrt(second * p_hit))
        ans += mixture_weight * term
        event_probability += mixture_weight * p_hit
        ungated += mixture_weight * first
    return {
        "conditional_event_probability_upper": min(1.0, event_probability),
        "activated_credit_put_upper": ans,
        "unconditional_credit_put_upper": ungated,
        "coefficient_is_population_conditional_only": True,
    }


def trigger_conditioned_bar_upper(
    symbol: str,
    opening: float,
    inventory_before_innovation: int,
    stop: float,
    targets: list[tuple[float, int]],
) -> dict[str, Any]:
    """Credit on one bar's original *modeled* STOP-first / TP events.

    Prebar target quantities cannot exceed available inventory, and STOP
    supersedes targets when both are triggered. Sum of event-specific bounds
    deliberately discards that negative-dependence, so remains conservative.
    """
    if symbol not in ASSETS:
        raise ValueError("C20_UNREGISTERED_ASSET")
    S = _num(opening, "OPENING", True)
    stop_px = _num(stop, "STOP", True)
    if not isinstance(inventory_before_innovation, int) or isinstance(inventory_before_innovation, bool) or inventory_before_innovation < 0:
        raise ValueError("C20_INVALID_LONG_INVENTORY")
    if not isinstance(targets, list) or len(targets) > 2:
        raise ValueError("C20_MAX_TWO_TARGETS")
    qtargets = 0
    validated: list[tuple[float, int]] = []
    for px, qty in targets:
        tp = _num(px, "TARGET", True)
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            raise ValueError("C20_INVALID_TARGET_LOT")
        qtargets += qty
        validated.append((tp, qty))
    if qtargets > inventory_before_innovation:
        raise ValueError("C20_UNFUNDED_TARGET_QUANTITY")
    base = ASSETS[symbol]
    stop_bound = event_weighted_put_upper(
        payoff_strike_ratio=min(1.0, stop_px / S),
        trigger_barrier_ratio=stop_px / S,
        is_lower_trigger=True,
        sigma_base=base,
    )
    total = inventory_before_innovation * S * stop_bound["activated_credit_put_upper"]
    target_rows: list[dict[str, Any]] = []
    for price, qty in validated:
        bound = event_weighted_put_upper(
            payoff_strike_ratio=price / S,
            trigger_barrier_ratio=price / S,
            is_lower_trigger=False,
            sigma_base=base,
        )
        total += qty * S * bound["activated_credit_put_upper"]
        target_rows.append({"target": price, "maximumTargetShares": qty, **bound})
    # The old C19 unconditioned negative-variation upper remains valid.
    # Taking the minimum means C20's trigger-conditioned refinement can
    # NEVER loosen C19's global event-independent certificate.
    unconditional_c19_upper = (
        inventory_before_innovation * S * asset_downward_variation(base)
    )
    refined = min(total, unconditional_c19_upper)
    return {
        "source_event_conditional_raw_upper_usd": total,
        "unconditional_C19_variation_upper_usd": unconditional_c19_upper,
        "refined_C20_model_credit_upper_usd": refined,
        "improvement_against_C19_usd": unconditional_c19_upper - refined,
        "schema": SCHEMA,
        "asset": symbol,
        "prebarPrice": S,
        "prebarLongQuantity": inventory_before_innovation,
        "stop": stop_px,
        "stopModelCreditCoefficient": stop_bound,
        "targetModelCreditCoefficients": target_rows,
        "conditional_expected_positive_model_credit_usd_upper": refined,
        "trigger_thresholds_known_before_bar_required": True,
        "actual_broker_fill_equivalence_proven": False,
        "full_native_receipt_state_proven": False,
        "N9S": "NO_GO",
    }


@dataclass(frozen=True)
class AdmissionCohort:
    max_calendar_holding_hours: int = 72
    max_daily_sessions_over_horizon: int = 4
    bars_per_session: int = 78
    substeps_per_bar: int = 8
    drift_per_bar_max: float = BAR_DRIFT_MAX
    admission_fraction: float = 0.12

    @property
    def max_hold_steps(self) -> int:
        return self.max_daily_sessions_over_horizon * self.bars_per_session * self.substeps_per_bar

    @property
    def gamma(self) -> float:
        return math.expm1(self.drift_per_bar_max / self.substeps_per_bar)

    @property
    def max_admission_to_exposure_multiplier(self) -> float:
        delta = self.drift_per_bar_max / self.substeps_per_bar
        return math.expm1(self.max_hold_steps * delta) / math.expm1(delta)


def admission_population_upper(
    expected_funded_buy_notional_upper_usd: float | None = None,
) -> dict[str, Any]:
    """E[A] <= H_72 * E[sum_i q_i * original source opening_i].

    Observed filled buys satisfy q_i*Sopen_i <= q_i*Pfilled_i
    <= committed IOC limit. The sum is over *all* admitted lots, not
    wealth-per-bar nor a continuous 12% cap. Early sales only reduce A.
    """
    cohort = AdmissionCohort()
    out: dict[str, Any] = {
        "schema": "HARPOON_M11_C20_ADMISSION_COHORT_EXPECTED_A_BOUND_1",
        "calendar_conservative_72h_max_intraday_substeps": cohort.max_hold_steps,
        "original_12pct_is_admission_only": True,
        "funded_entry_notional_sum_expected_upper_usd": None,
        "population_expected_A_upper_usd_substeps": None,
        "admission_cohort_factor": cohort.max_admission_to_exposure_multiplier,
        "population_native_certificate": False,
        "holdout_M10_accounts_opened": 0,
        "no_market_seeds_or_economic_account_runs": True,
        "N9S": "NO_GO",
    }
    if expected_funded_buy_notional_upper_usd is None:
        out["missing"] = "E_WEAK[sum of actual funded admission buy notionals] upper for all native runs"
        return out
    B = _num(expected_funded_buy_notional_upper_usd, "EXPECTED_FUNDED_BUY_UPPER")
    exposure = cohort.max_admission_to_exposure_multiplier * B
    if not math.isfinite(exposure):
        raise ValueError("C20_EXPOSURE_UPPER_OVERFLOW")
    out.update({
        "hypothetical_admission_expectation_input_usd": B,
        "conditional_class_expected_A_upper_usd_substeps": exposure,
        "native_input_independently_certified": False,
        "result_does_not_certify_live_or_N9S": True,
    })
    return out


def original_source_hashes(root: Path) -> dict[str, str]:
    for path, expected in SOURCE_SHA.items():
        actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("C20_ORIGINAL_SOURCE_HASH_MISMATCH:" + path)
    p: dict[str, Any] = json.loads(
        (root / "research/modulation9/protocol.json").read_text(encoding="utf-8")
    )
    if (
        p["generator"]["weak_drift_per_bar"] != .000025
        or p["generator"]["intrabar_substeps"] != 8
        or p["generator"]["bars_per_session"] != 78
        or p["generator"]["evaluation_sessions"] != 126
        or p["limits"]["grossFraction"] != .12
        or p["limits"]["capitalUsd"] != CAPITAL
        or p["gates"]["max_holding_elapsed_hours"] != 72
    ):
        raise ValueError("C20_ORIGINAL_M9_ECONOMIC_CONTRACT_CHANGED")
    return SOURCE_SHA


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    proof = original_source_hashes(args.root)
    example = trigger_conditioned_bar_upper(
        "SYNA", 100.0, 20, 98.0, [(103.0, 5), (106.0, 5)]
    )
    print("C20_MATHEMATICAL_CONDITIONAL=" + json.dumps(
        {
            "frozen_source": proof,
            "example": example,
            "admission": admission_population_upper(),
            "frozen_no_trade_budget": {
                "new_signals": 0, "new_market_seeds": 0,
                "new_economic_accounts": 0, "M10_final_unopened": 3200,
            },
        },
        sort_keys=True, allow_nan=False,
    ))


if __name__ == "__main__":
    main()
